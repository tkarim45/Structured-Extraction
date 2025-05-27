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
            You are a data extraction assistant processing a regulatory document from the Reserve Bank of India (RBI), titled "Guidance Note on Operational Risk Management and Operational Resilience," converted from PDF to plain text. The document contains English and Hindi text, metadata (e.g., department address, contact details, signatures), and a structured hierarchy of chapters, sections, subsections, principles, and annexes. Your task is to extract the entire hierarchical structure, capturing every single word, sentence, and detail of the English regulatory content, and format it as pipe-delimited strings with four fields: Chapter, Section No., Section, and Sub-Section.

            **Task**
            1. Extract the complete hierarchical structure, identifying all chapters, sections, subsections, principles, and annexes. If no explicit chapter names are present (e.g., "Chapter I"), infer chapters from major headings (e.g., "1. Preliminary," "Annex") or use "Main Document" for sections without a clear chapter title.
            2. Map the document's structure to the output format:
               - **Chapter**: Major heading or inferred chapter (e.g., "Preliminary," "Annex," or "Main Document").
               - **Section No.**: Numeric identifier of the section (e.g., "1," "4").
               - **Section**: Section title or description (e.g., "Purpose," "Governance and Risk Culture").
               - **Sub-Section**: Full text of all nested subsections (e.g., "1.1," "4.1") and principles (e.g., "Principle 1") under the section, in a hierarchical bullet-point list using hyphens (e.g., `- 1.1 Text - 1.1.1 Sub-text`). Include every single word, sentence, and detail without any omission, truncation, or ellipses ('...'). If no subsections exist, use an empty string.
            3. Exclude metadata (e.g., department address, contact details, email, fax, signatures, "Yours faithfully") and Hindi text (e.g., "हिंदंी आसान है"). Focus solely on English regulatory content, including sections, subsections, principles, and annexes.
            4. Output each entry as a pipe-delimited string on a new line, starting with "Chapter:". Ensure four fields per line, capturing all subsection and principle text in the Sub-Section field without missing any content.

            **Objective**
            Produce a structured representation of the document’s regulatory content, preserving the legal hierarchy and every single word, sentence, and detail of the English text, suitable for Excel export, while excluding irrelevant metadata and non-English text.

            **Knowledge**
            - The document begins with metadata (e.g., RBI department details, date, reference number), followed by an Index listing sections (e.g., "1. Preliminary," "4. Governance and Risk Culture"), and the main content.
            - Sections are numbered (e.g., "1. Purpose," "2. Application"), with subsections (e.g., "1.1," "1.2") and principles (e.g., "Principle 1" under "4. Governance and Risk Culture") treated as subsections.
            - Principles are key requirements (e.g., "Principle 1- The Board of Directors should take the lead...") and must be included in full in the Sub-Section field.
            - Annexes (e.g., "Annex") are treated as chapters with their own content.
            - Use context clues (e.g., numbering, indentation, headings) to infer hierarchy if formatting is inconsistent due to PDF extraction.
            - Output format: `Chapter: <chapter or annex title or 'Main Document'>|Section No.: <number>|Section: <title or text>|Sub-Section: <full nested subsection text or empty>`
            - **CRITICAL**: Do NOT omit, truncate, or summarize any part of the regulatory content. Include every single word, sentence, and detail of subsections and principles, avoiding ellipses ('...') entirely.
            - Preserve original wording, numbering, and punctuation exactly as in the document.

            **Examples**
            ```
            Chapter: Preliminary|Section No.: 1|Section: Purpose|Sub-Section: - 1.1 Operational Risk is inherent in all banking/financial products, services, activities, processes, and systems. Effective management of Operational Risk is an integral part of the Regulated Entities’ (REs) risk management framework. Sound Management of Operational Risk shows the overall effectiveness of the Board of Directors and Senior Management in administering the RE’s portfolio of products, services, activities, processes, and systems. - 1.2 An operational disruption can threaten the viability of an RE, impact its customers and other market participants, and ultimately have an impact on financial stability. It can result from man-made causes, Information Technology (IT) threats (e.g., cyber-attacks, changes in technology, technology failures, etc), geopolitical conflicts, business disruptions, internal/external frauds, execution/delivery errors, third party dependencies, or natural causes (e.g., climate change, pandemic, etc.).
            Chapter: Governance and Risk Culture|Section No.: 4|Section: Governance and Risk Culture|Sub-Section: - Principle 1- The Board of Directors should take the lead in establishing a strong risk management culture, implemented by Senior Management. The Board of Directors and Senior Management should establish a corporate culture guided by strong risk management, set standards and incentives for professional and responsible behaviour, and ensure that staff receives appropriate risk management and ethics training. - 4.1 REs with a strong culture of risk management and ethical business practices are less likely to experience damaging Operational Risk events and are better placed to effectively deal with those events that occur. The actions of the Board of Directors and Senior Management as well as the RE’s risk management policies, processes and systems provide the foundation for a sound risk management culture. - 4.2 The Board of Directors should establish a code of conduct or an ethics policy to address conduct risk...
            Chapter: Annex|Section No.: 1|Section: Key Changes|Sub-Section: - Key changes carried out in the Guidance Note vis-à-vis repealed Guidance Note...
            ```

            **Output Format (MANDATORY)**
            - Each entry starts with "Chapter:" followed by pipe-separated fields.
            - Sub-Section contains all nested subsections and principles in a bullet-point list (e.g., `- 1.1 Text`).
            - Capture every word and sentence in full; no ellipses or truncation allowed.
            - Empty Sub-Section field if no subsections/principles exist.

            Process the following text exactly as provided, capturing every word and sentence of the English regulatory content, excluding metadata and Hindi text:
            ```
            {text}
            ```
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
        Analyze the provided regulatory section or subsection and extract four critical pieces of information: (1) a concise summary in one sentence of maximum 200 words, (2) a specific actionable item to address the requirements, (3) the exact compliance due date in YYYY-MM-DD format or N/A if undeterminable, and (4) the periodicity of the requirement or N/A if not specified.

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
    logger.info("Extracting document-level summary and action item")
    logger.info(f"Raw data preview: {raw_data[:100]}")

    if not raw_data.strip() or len(raw_data) < 100:
        logger.warning("Raw data is empty or too short, using fallback")
        return {
            "summary": "The document appears to be a regulatory guideline, but specific content could not be extracted due to formatting or extraction issues.",
            "action_item": "Conduct a manual review of the document to identify and implement key compliance requirements.",
        }

    prompt = f"""
        **Situation**
        You are a compliance assistant working with regulatory documents converted from PDF to plain text. Your job is to provide a concise, high-level, and detailed summary and a single most important action item for the entire document, even if the structure (e.g., chapters) is unclear or missing.

        **Task**
        1. Read the entire document text.
        2. Write a detailed summary (200-500 words) of the document's purpose, scope, and key requirements. If no clear structure (e.g., chapters) is present, assume the document is a single cohesive regulatory guideline and summarize its overall intent.
        3. Identify all the, specific, and actionable item for compliance, prioritizing the most critical requirement for the organization.

        **Objective**
        Enable organizations to understand the document’s regulatory requirements and take appropriate compliance actions, even for poorly structured or short documents.

        **Knowledge**
        - Regulatory documents may lack explicit chapter names or have inconsistent formatting due to PDF extraction.
        - If no chapters are identified, treat the document as a single unit ("Main Document") and summarize its key points.
        - Focus on regulatory intent, compliance obligations, and actionable steps.
        - Avoid generic or empty responses (e.g., "N/A", "Not specified").

        **Output Format (MANDATORY)**
        Summary: <detailed summary, 200-500 words>
        Action Item: <specific, actionable item, multiple items separated by new lines>

        **Examples**
        Summary: The document provides guidelines for operational risk management, emphasizing robust internal controls, risk assessments, and business continuity planning for financial institutions. It outlines senior management responsibilities and regulatory reporting requirements to ensure resilience against disruptions.
        Action Item: - Implement a comprehensive operational risk management framework with regular risk assessments and business continuity plans to meet regulatory requirements.
        - Review and document title provisions.
        - Deploy MFA across all systems by Q4 2023.
        - Conduct a manual review to identify and implement compliance actions.

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
        logger.info(f"OpenAI raw response: {result}")

        # Initialize defaults
        summary = ""
        action_item = ""

        # Use regex to extract summary and action item, handling Markdown and multi-line content
        summary_match = re.search(
            r"(?:\*\*Summary\*\*:|Summary:)\s*(.*?)(?=(?:\*\*Action Item\*\*:|Action Item:|$))",
            result,
            re.DOTALL | re.IGNORECASE,
        )
        action_match = re.search(
            r"(?:\*\*Action Item\*\*:|Action Item:)\s*(.*)",
            result,
            re.DOTALL | re.IGNORECASE,
        )

        if summary_match:
            summary = summary_match.group(1).strip()
        if action_match:
            action_item = action_match.group(1).strip()

        # Fallback if either field is empty or generic
        if not summary or summary.lower() in ["n/a", "not specified", ""]:
            summary = "The document outlines regulatory requirements, but specific details could not be extracted due to formatting issues."
        if not action_item or action_item.lower() in ["n/a", "not specified", ""]:
            action_item = (
                "Conduct a manual review to identify and implement compliance actions."
            )

        logger.info(f"Document summary: {summary}")
        logger.info(f"Document action item: {action_item}")
        return {"summary": summary, "action_item": action_item}
    except Exception as e:
        logger.error(f"Error extracting document summary/action: {str(e)}")
        return {"summary": "N/A", "action_item": "N/A"}
