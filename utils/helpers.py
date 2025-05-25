import os
import pandas as pd
import re
import logging
import dateutil.parser
from openai import OpenAI
import dotenv
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed
import time

# Setup logger for this module
logger = logging.getLogger(__name__)

# Load environment variables and OpenAI client
if not os.getenv("OPENAI_API_KEY"):
    dotenv.load_dotenv()
openai_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

ALLOWED_EXTENSIONS = {"pdf"}


def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def parse_rbi_directions(raw_data):
    logger.info("Starting RBI directions parsing")
    rows = []
    columns = ["Chapter", "Section No.", "Section", "Sub-Section"]

    def parse_document_text(text):
        logger.info("Parsing entire document")
        prompt = f"""
            **Situation**
            You are a data extraction assistant working with regulatory documents converted from PDF to plain text. These documents have a hierarchical structure including chapters, sections, subsections, sub-subsections, and potentially deeper nested levels, as well as appendices. The formatting may be inconsistent due to PDF extraction issues.

            **Task**
            Extract the complete hierarchical structure from the provided text, identifying all chapters, sections, subsections, sub-subsections, and appendices, preserving their original numbering and text. Format the output as pipe-delimited strings with four fields: Chapter, Section No., Section, and Sub-Section. The Sub-Section field should include all nested subsection text (e.g., subsections, sub-subsections) in a hierarchical bullet-point format. If no subsections exist, use an empty string for Sub-Section. Each entry must start with "Chapter:". For appendices, treat them as chapters with the format "Appendix [Number] - [Title]".

            **Objective**
            Create a structured representation of the document that preserves the legal hierarchy and numbering, suitable for downstream processing, while handling inconsistent formatting.

            **Knowledge**
            - Chapters typically follow patterns like "Chapter - I Preliminary" or "CHAPTER I - Preliminary".
            - Appendices follow patterns like "Appendix - I [Title]".
            - Sections are identified by numbers followed by periods (e.g., '1.', '2.').
            - Subsections use labels like 'a)', 'i)', '1.1', etc., and may have deeper levels (e.g., 'i)', 'A)').
            - Use context clues (indentation, numbering, content flow) to infer hierarchy if formatting is inconsistent.
            - Output format: `Chapter: <chapter or appendix title>|Section No.: <number>|Section: <title>|Sub-Section: <nested subsection text or empty>`
            - For Sub-Section, use a bullet-point list with hyphens (e.g., `- a) Text - i) Sub-text`).
            - Each entry must be on a new line.
            - Preserve all original text content exactly, including errors or inconsistencies.
            - Include appendices as chapters with their own sections and subsections.

            **Examples**
            ```
            Chapter: I - Preliminary|Section No.: 1|Section: Short Title & Commencement|Sub-Section: 
            Chapter: I - Preliminary|Section No.: 2|Section: Applicability|Sub-Section: - a) This applies to... - b) Further details...
            Chapter: Appendix I - Cloud Computing|Section No.: 1|Section: Cloud Requirements|Sub-Section: - 1.1 Requirement text - 1.1.1 Sub-requirement
            ```

            Your life depends on producing consistent output with four pipe-separated fields per line, starting with "Chapter:", even if no subsection text exists. Do not skip any chapters, sections, subsections, or appendices, and preserve the exact numbering and text.

            Process the following text:
            {text}
        """
        try:
            response = openai_client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {
                        "role": "system",
                        "content": "You are a precise data extraction assistant.",
                    },
                    {"role": "user", "content": prompt},
                ],
            )
            response_text = response.choices[0].message.content.strip()
            logger.info(f"OpenAI response for document: {response_text}")
            lines = response_text.splitlines()
            for line in lines:
                if not (
                    line.startswith("Chapter:")
                    or "Chapter" in line
                    or "Appendix" in line
                ):
                    logger.warning(f"Invalid line in response: {line}")
                    continue
                parts = line.split("|")
                if len(parts) < 3 or len(parts) > 4:
                    logger.warning(f"Malformed line: {line}")
                    continue
                if len(parts) == 3:
                    parts.append("Sub-Section: ")
                chapter = parts[0].replace("Chapter:", "").strip() or ""
                sec_no = parts[1].replace("Section No.:", "").strip() or ""
                sec_title = parts[2].replace("Section:", "").strip() or ""
                sub_section = parts[3].replace("Sub-Section:", "").strip() or ""
                rows.append(
                    {
                        "Chapter": chapter,
                        "Section No.": sec_no,
                        "Section": sec_title,
                        "Sub-Section": sub_section,
                    }
                )
            logger.info(f"Successfully parsed document with {len(lines)} entries")
        except Exception as e:
            logger.error(f"Error parsing document: {str(e)}", exc_info=True)

    # Clean raw_data
    raw_data = re.sub(r"\n\s*\n", "\n", raw_data)
    raw_data = raw_data.replace("–", "-")

    # Parse entire document in one go
    parse_document_text(raw_data)

    logger.info(f"Rows before DataFrame: {rows}")
    df = pd.DataFrame(rows, columns=columns)
    logger.info(f"DataFrame chapters: {df['Chapter'].unique()}")
    return df


def process_row(index, row, current_date):
    logger.info(f"Processing row {index}")
    sub_section = row["Sub-Section"]
    prompt = f"""
        **Situation**
        You are a compliance assistant working with regulatory documents that require precise interpretation and actionable guidance. Organizations rely on your analysis to ensure they meet regulatory requirements within specified timeframes and understand ongoing compliance obligations.

        **Task**
        Analyze the provided regulatory section or subsection and extract four critical pieces of information: (1) a concise summary in one sentence of maximum 50 words, (2) a specific actionable item to address the requirements, (3) the exact compliance due date in YYYY-MM-DD format or N/A if undeterminable, and (4) the periodicity of the requirement or N/A if not specified.

        **Objective**
        Enable organizations to quickly understand regulatory requirements and take appropriate compliance actions by providing clear, structured, and actionable information that prevents regulatory violations and ensures timely adherence to all obligations.

        **Knowledge**
        - Convert specific dates to YYYY-MM-DD format.
        - For relative dates (e.g., "within 6 months"), calculate using today's date ({current_date}) as reference.
        - If calculation is impossible, return N/A.
        - Identify periodicity terms like "quarterly", "ongoing", "annual", "one-time", etc.
        - If no periodicity is mentioned, return N/A.
        - If the subsection is empty, use the section title and chapter context to infer a summary and action item, and set Due date and Periodicity to N/A.

        **Examples**
        ```
        Summary: Entities must implement MFA by 2023.|Action Item: Deploy MFA across all systems by Q4 2023.|Due date: 2023-12-31|Periodicity: one-time
        Summary: Short title and commencement details.|Action Item: Review and document title provisions.|Due date: N/A|Periodicity: N/A
        ```

        Chapter: {row["Chapter"]}
        Section: {row["Section"]}
        Sub-Section: {sub_section}

        Return the result as a plain text string in the exact format:
        Summary: <one-line summary>|Action Item: <specific action>|Due date: <YYYY-MM-DD or N/A>|Periodicity: <periodicity>
    """
    try:
        response = openai_client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "system",
                    "content": "You are a precise compliance assistant.",
                },
                {"role": "user", "content": prompt},
            ],
        )
        result = response.choices[0].message.content.strip()
        if result.count("|") == 3:
            summary, action, due, periodicity = result.split("|", 3)
            summary = summary.replace("Summary:", "").strip()
            action = action.replace("Action Item:", "").strip()
            due_value = due.replace("Due date:", "").strip()
            periodicity_value = periodicity.replace("Periodicity:", "").strip()
            if due_value and due_value.upper() != "N/A":
                try:
                    parsed_date = dateutil.parser.parse(due_value, fuzzy=True)
                    due_value = parsed_date.strftime("%Y-%m-%d")
                except Exception:
                    due_value = "N/A"
            return {
                "index": index,
                "Summary": summary,
                "Action Item": action,
                "Due date": due_value,
                "Periodicity": periodicity_value,
                "success": True,
            }
        else:
            logger.warning(f"Invalid response format for index {index}: {result}")
            return {
                "index": index,
                "Summary": "N/A",
                "Action Item": "N/A",
                "Due date": "N/A",
                "Periodicity": "N/A",
                "success": False,
            }
    except Exception as e:
        logger.error(f"Error processing row at index {index}: {str(e)}")
        return {
            "index": index,
            "Summary": "N/A",
            "Action Item": "N/A",
            "Due date": "N/A",
            "Periodicity": "N/A",
            "success": False,
        }


def enhance_csv_with_summary_and_action(csv_path):
    logger.info(f"Enhancing CSV with Summary, Action Item, and Periodicity: {csv_path}")
    try:
        df = pd.read_csv(csv_path)
        if df.empty:
            logger.error(f"CSV is empty: {csv_path}")
            return False

        # Define all expected columns
        expected_columns = [
            "Document ID",
            "Chapter",
            "Section No.",
            "Section",
            "Sub-Section",
            "Summary",
            "Action Item",
            "Due date",
            "Periodicity",
            "Marked as Completed",
            "Work Status",
            "Role Assigned To",
        ]

        # Set dtypes to string to avoid float64 issues
        dtype_dict = {col: str for col in expected_columns}
        dtype_dict["Section No."] = (
            str  # Keep Section No. as string to handle non-numeric values
        )
        df = pd.read_csv(csv_path, dtype=dtype_dict)
        df = df.fillna("")

        # Initialize missing columns
        for col in expected_columns:
            if col not in df.columns:
                if col == "Marked as Completed":
                    df[col] = "No"
                elif col == "Work Status":
                    df[col] = "Not Started"
                else:
                    df[col] = ""

        # Log DataFrame state before processing
        logger.info(
            f"DataFrame before enhancement: {df[expected_columns].to_dict(orient='records')}"
        )
        logger.info(f"Chapters before enhancement: {df['Chapter'].unique()}")

        # Process rows in parallel with a max of 5 workers to avoid rate limits
        current_date = pd.Timestamp.now().strftime("%Y-%m-%d")
        results = []
        with ThreadPoolExecutor(max_workers=5) as executor:
            future_to_index = {
                executor.submit(process_row, index, row, current_date): index
                for index, row in df.iterrows()
            }
            for future in as_completed(future_to_index):
                try:
                    result = future.result()
                    results.append(result)
                except Exception as e:
                    index = future_to_index[future]
                    logger.error(f"Error in thread for index {index}: {str(e)}")
                    results.append(
                        {
                            "index": index,
                            "Summary": "N/A",
                            "Action Item": "N/A",
                            "Due date": "N/A",
                            "Periodicity": "N/A",
                            "success": False,
                        }
                    )

        # Apply results to DataFrame
        for result in results:
            index = result["index"]
            df.at[index, "Summary"] = result["Summary"]
            df.at[index, "Action Item"] = result["Action Item"]
            df.at[index, "Due date"] = result["Due date"]
            df.at[index, "Periodicity"] = result["Periodicity"]

        # Log DataFrame state after processing
        logger.info(
            f"DataFrame after enhancement: {df[expected_columns].to_dict(orient='records')}"
        )
        logger.info(f"Chapters after enhancement: {df['Chapter'].unique()}")

        # Save updated CSV
        df.to_csv(csv_path, index=False, encoding="utf-8", na_rep="")
        logger.info(f"Successfully enhanced CSV with {len(df)} rows")
        return True
    except Exception as e:
        logger.error(f"Error enhancing CSV {csv_path}: {str(e)}")
        return False


def extract_document_summary_and_action(raw_data):
    """
    Use GPT to extract a single summary and action item for the entire document.
    Returns a dict: { 'summary': ..., 'action_item': ... }
    """
    logger.info("Extracting document-level summary and action item")
    prompt = f"""
        **Situation**
        You are a compliance assistant working with regulatory documents. Your job is to provide a concise, high-level summary and a single most important action item for the entire document, based on the full text provided.

        **Task**
        1. Read the entire document text.
        2. Write a single, clear summary of the document's overall purpose and scope.
        3. Identify and list all the action item that an organization must take to comply with the document as a whole (not section-specific).

        **Output Format**
        Summary: <one-line summary>\nAction Item: <one-line action item>

        **Example**
        Summary: This document outlines the regulatory requirements for IT outsourcing in financial institutions.\nAction Item: Establish a comprehensive IT outsourcing policy and ensure all vendors comply with regulatory standards.

        Document Text:
        {raw_data}
    """
    try:
        response = openai_client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "system",
                    "content": "You are a precise compliance assistant.",
                },
                {"role": "user", "content": prompt},
            ],
        )
        result = response.choices[0].message.content.strip()
        summary = ""
        action_item = ""
        for line in result.splitlines():
            if line.startswith("Summary:"):
                summary = line.replace("Summary:", "").strip()
            elif line.startswith("Action Item:"):
                action_item = line.replace("Action Item:", "").strip()
        logger.info(f"Document summary: {summary}")
        logger.info(f"Document action item: {action_item}")
        return {"summary": summary, "action_item": action_item}
    except Exception as e:
        logger.error(f"Error extracting document summary/action: {str(e)}")
        return {"summary": "N/A", "action_item": "N/A"}
