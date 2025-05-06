from flask import Flask, request, jsonify, render_template
from werkzeug.utils import secure_filename
import os
import pandas as pd
from datetime import datetime, timedelta
import nest_asyncio
import pdfplumber
import re
import dotenv
import csv
import logging
import threading
from langchain_openai import AzureChatOpenAI

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.FileHandler("app.log"), logging.StreamHandler()],
)
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.config["UPLOAD_FOLDER"] = "Uploads"
app.config["EXTRACTED_TEXT"] = "data/Extracted Text"
app.config["EXCEL_SHEETS"] = "data/Excel Sheets"
ALLOWED_EXTENSIONS = {"pdf"}

# Ensure directories exist
os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)
os.makedirs(app.config["EXTRACTED_TEXT"], exist_ok=True)
os.makedirs(app.config["EXCEL_SHEETS"], exist_ok=True)
logger.info("Application directories initialized")

# Load environment variables
dotenv.load_dotenv()
openai_client = AzureChatOpenAI(
    azure_deployment=os.getenv("AZURE_DEPLOYMENT_NAME", "gpt-35-turbo"),
    api_version=os.getenv("OPENAI_API_VERSION", "2023-06-01-preview"),
    api_key=os.getenv("OPENAI_API_KEY"),
    azure_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT"),
    temperature=0,
    max_tokens=None,
    timeout=None,
    max_retries=2,
)
logger.info("Environment variables loaded and AzureChatOpenAI initialized")

# Apply nest_asyncio to allow nested event loops
nest_asyncio.apply()
logger.info("Nested asyncio applied")

# In-memory status tracking
file_status = {}


def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


# Function to clean text (remove problematic characters)
def clean_text(text):
    return re.sub(r"[^\x00-\x7F]+", " ", text).strip()


# Function to parse raw data using AzureChatOpenAI
def parse_rbi_directions(raw_data):
    logger.info("Starting RBI directions parsing")
    raw_data = clean_text(raw_data)
    logger.info(f"Raw data (first 500 chars): {raw_data[:500]}")
    rows = []
    columns = ["Chapter", "Section No.", "Section", "Sub-Section"]

    # Regex to match numbered sections (e.g., "1.", "2.")
    section_re = re.compile(r"^(?<!\d\.)\s*(\d+)\.\s*(.*?)(?=\n|$)", re.MULTILINE)
    # Sub-section regex for nested items (e.g., "1.1", "1.1.1", "a)", "(i)")
    subsection_re = re.compile(
        r"^(?<!\d\.)\s*(\d+\.\d+(?:\.\d+)*|\w+\)|\(\w+\))\s*(.*?)(?=\n|$)", re.MULTILINE
    )

    def parse_section_text(section_num, section_title, text):
        logger.info(f"Parsing section: {section_num} - {section_title}")
        prompt = f"""
You are a data extraction assistant tasked with extracting structured data from a regulatory document section. The input text is plain text extracted from a PDF and may have inconsistent formatting. Your task is to identify subsections (e.g., '1.1', 'a)', '(i)') and their text. Output the result as a list of entries, each formatted as:

Chapter: {section_num} - {section_title}|Section No.: <number>|Section: <title>|Sub-Section: <label> <text>

- **Chapter**: Use the provided section number and title (e.g., '1 - Purpose').
- **Section No.**: Identify subsection numbers (e.g., '1.1', '1.1.1').
- **Section**: Extract the subsection title if available, or use the subsection number.
- **Sub-Section**: Include the subsection label and text (e.g., 'a) Text...', '1.1 Text...').

Identify subsections by numbers (e.g., '1.1', '1.1.1') or labels (e.g., 'a)', '(i)'). If the structure is unclear, infer based on context. Ensure each entry is on a new line. If no subsections are found, return an empty string.

Input Text:
{text[:4000]}

Example Output:
Chapter: 1 - Purpose|Section No.: 1.1|Section: Operational Risk|Sub-Section: 1.1 Effective management of Operational Risk...
Chapter: 1 - Purpose|Section No.: 1.2|Section: Scope|Sub-Section: 1.2 This applies to all regulated entities...
"""
        try:
            # Use tuple-based message format
            messages = [
                ("system", "You are a precise data extraction assistant."),
                ("human", prompt),
            ]
            response = openai_client.invoke(messages)
            response_content = response.content.strip()
            logger.info(
                f"Azure response for section {section_num}: {response_content[:500]}"
            )
            lines = response_content.splitlines()
            if not lines:
                logger.warning(f"No data extracted for section: {section_num}")
                return
            for line in lines:
                if line.startswith("Chapter:"):
                    parts = line.split("|")
                    if len(parts) == 4:
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
            logger.info(f"Parsed section: {section_num} with {len(lines)} entries")
        except Exception as e:
            logger.error(f"Error parsing section {section_num}: {str(e)}")

    # Find sections
    sections = section_re.finditer(raw_data)
    section_starts = [(m.start(), m.group(1), m.group(2).strip()) for m in sections]
    logger.info(
        f"Found {len(section_starts)} sections: {[(num, title) for _, num, title in section_starts]}"
    )
    section_starts.append((len(raw_data), None, None))

    # Process each section
    for i in range(len(section_starts) - 1):
        start_pos, section_num, section_title = section_starts[i]
        end_pos = section_starts[i + 1][0]
        section_text = raw_data[start_pos:end_pos]
        if section_num:
            parse_section_text(section_num, section_title, section_text)

    # Fallback: If no sections are found, process the entire text
    if not section_starts[:-1]:
        logger.warning("No sections found, processing entire text")
        prompt = f"""
You are a data extraction assistant tasked with extracting structured data from a regulatory document. The input text is plain text extracted from a PDF and may have inconsistent formatting. Identify sections (e.g., '1.', '2.') and subsections (e.g., '1.1', 'a)', '(i)') and their text. Output the result as a list of entries, each formatted as:

Chapter: <section_num> - <section_title>|Section No.: <number>|Section: <title>|Sub-Section: <label> <text>

If no clear section structure is found, treat top-level numbered items as sections and nested items as subsections. Ensure each entry is on a new line. If no data is found, return an empty string.

Input Text:
{raw_data[:8000]}

Example Output:
Chapter: 1 - Purpose|Section No.: 1.1|Section: Operational Risk|Sub-Section: 1.1 Effective management of Operational Risk...
"""
        try:
            # Use tuple-based message format
            messages = [
                ("system", "You are a precise data extraction assistant."),
                ("human", prompt),
            ]
            response = openai_client.invoke(messages)
            response_content = response.content.strip()
            logger.info(f"Azure response for full text: {response_content[:500]}")
            lines = response_content.splitlines()
            for line in lines:
                if line.startswith("Chapter:"):
                    parts = line.split("|")
                    if len(parts) == 4:
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
            logger.info(f"Parsed full text with {len(lines)} entries")
        except Exception as e:
            logger.error(f"Error parsing full text: {str(e)}")

    logger.info(f"Completed RBI directions parsing with {len(rows)} rows")
    return pd.DataFrame(rows, columns=columns)


# Function to enhance CSV with Summary and Action Item
def enhance_csv_with_summary_and_action(csv_path):
    logger.info(f"Enhancing CSV with Summary and Action Item: {csv_path}")
    try:
        df = pd.read_csv(csv_path)
        if df.empty:
            logger.error(f"CSV is empty: {csv_path}")
            return False

        df["Summary"] = ""
        df["Action Item"] = ""

        for index, row in df.iterrows():
            sub_section = row["Sub Section"]
            if pd.isna(sub_section) or not sub_section.strip():
                logger.warning(f"Empty Sub-Section at index {index}")
                continue

            prompt = f"""
You are a compliance assistant. Below is a subsection from a regulatory document. Your task is to:
1. Summarize the subsection in one concise sentence (max 50 words).
2. Provide a specific action item to address the subsection's requirements.

Sub-Section:
{sub_section[:1000]}

Return the result as:
Summary: <one-line summary>|Action Item: <specific action>

Example:
Summary: Entities must implement multi-factor authentication by 2023.|Action Item: Deploy MFA across all systems by Q4 2023.
"""
            try:
                # Use tuple-based message format
                messages = [
                    ("system", "You are a precise compliance assistant."),
                    ("human", prompt),
                ]
                response = openai_client.invoke(messages)
                result = response.content.strip()
                if "|" in result:
                    summary, action = result.split("|", 1)
                    df.at[index, "Summary"] = summary.replace("Summary:", "").strip()
                    df.at[index, "Action Item"] = action.replace(
                        "Action Item:", ""
                    ).strip()
                else:
                    logger.warning(
                        f"Invalid response format for index {index}: {result}"
                    )
            except Exception as e:
                logger.error(f"Error processing Sub-Section at index {index}: {str(e)}")

        df.to_csv(csv_path, index=False, encoding="utf-8")
        logger.info(f"Successfully enhanced CSV with {len(df)} rows")
        return True
    except Exception as e:
        logger.error(f"Error enhancing CSV {csv_path}: {str(e)}")
        return False


# Rest of the code remains unchanged
@app.route("/")
def index():
    logger.info("Rendering index page")
    return render_template("index.html")


@app.route("/api/upload", methods=["POST"])
def upload_file():
    logger.info("Received file upload request")
    if "file" not in request.files:
        logger.error("No file part in request")
        return jsonify({"error": "No file part"}), 400
    file = request.files["file"]
    if file.filename == "":
        logger.error("No selected file")
        return jsonify({"error": "No selected file"}), 400
    if file and allowed_file(file.filename):
        filename = secure_filename(file.filename)
        file_path = os.path.join(app.config["UPLOAD_FOLDER"], filename)
        csv_filename = os.path.splitext(filename)[0] + ".csv"
        logger.info(f"Saving uploaded file: {filename}")
        file.save(file_path)

        file_status[csv_filename] = "Processing"
        logger.info(f"Set status to Processing for {csv_filename}")

        def process_file():
            try:
                logger.info(f"Extracting text from PDF: {filename}")
                with pdfplumber.open(file_path) as pdf:
                    text = "\n".join(page.extract_text() or "" for page in pdf.pages)

                if not text.strip():
                    logger.error(f"No text extracted from PDF: {filename}")
                    file_status[csv_filename] = "Failed"
                    return

                txt_path = os.path.join(
                    app.config["EXTRACTED_TEXT"], os.path.splitext(filename)[0] + ".txt"
                )
                logger.info(f"Saving extracted text to: {txt_path}")
                with open(txt_path, "w", encoding="utf-8") as f:
                    f.write(text)

                logger.info(f"Reading text from: {txt_path}")
                with open(txt_path, "r", encoding="utf-8") as file:
                    raw_data = file.read()

                logger.info("Parsing text data into DataFrame")
                df = parse_rbi_directions(raw_data)

                if df.empty:
                    logger.error(f"Parsed DataFrame is empty for {filename}")
                    file_status[csv_filename] = "Failed"
                    return
                logger.info(f"Parsed DataFrame contains {len(df)} rows")

                csv_path = os.path.join(app.config["EXCEL_SHEETS"], csv_filename)
                logger.info(f"Saving initial CSV to: {csv_path}")
                df.to_csv(csv_path, index=False, encoding="utf-8")

                structured_data = []
                document_id = os.path.splitext(filename)[0]
                for _, row in df.iterrows():
                    structured_data.append(
                        [
                            document_id,
                            row["Chapter"],
                            row["Section"],
                            row["Sub-Section"],
                            row["Sub-Section"],
                            "Compliance required",
                            "2023-10-01",
                            "Regulated Entities",
                            "Compliance Team",
                            "",  # Placeholder for Summary
                            "",  # Placeholder for Action Item
                        ]
                    )

                if not structured_data:
                    logger.error(f"No structured data generated for {filename}")
                    file_status[csv_filename] = "Failed"
                    return
                logger.info(f"Generated {len(structured_data)} rows of structured data")

                logger.info(f"Saving structured CSV to: {csv_path}")
                with open(csv_path, "w", newline="", encoding="utf-8") as csvfile:
                    writer = csv.writer(csvfile)
                    writer.writerow(
                        [
                            "Document_ID",
                            "Chapter",
                            "Section",
                            "Sub Section",
                            "Description",
                            "Compliance_Requirements",
                            "Effective_Date",
                            "Applicability",
                            "Role Assigned To",
                            "Summary",
                            "Action Item",
                        ]
                    )
                    writer.writerows(structured_data)

                logger.info(f"Enhancing CSV with summary and action items: {csv_path}")
                if not enhance_csv_with_summary_and_action(csv_path):
                    logger.error(f"Failed to enhance CSV: {csv_path}")
                    file_status[csv_filename] = "Failed"
                    return

                if not os.path.exists(csv_path):
                    logger.error(f"CSV file was not created: {csv_path}")
                    file_status[csv_filename] = "Failed"
                    return
                csv_size = os.path.getsize(csv_path)
                if csv_size < 100:
                    logger.error(
                        f"CSV file is suspiciously small ({csv_size} bytes): {csv_path}"
                    )
                    file_status[csv_filename] = "Failed"
                    return

                logger.info(f"File {filename} processed successfully")
                file_status[csv_filename] = "Completed"
            except Exception as e:
                logger.error(f"Error processing file {filename}: {str(e)}")
                file_status[csv_filename] = "Failed"

        threading.Thread(target=process_file, daemon=True).start()

        return (
            jsonify(
                {
                    "message": "File upload started",
                    "filename": filename,
                    "csv_path": csv_filename,
                }
            ),
            202,
        )
    logger.error(f"Invalid file type: {file.filename}")
    return jsonify({"error": "Invalid file type"}), 400


@app.route("/api/files", methods=["GET"])
def list_files():
    logger.info("Listing CSV files")
    files = []
    try:
        for filename in os.listdir(app.config["EXCEL_SHEETS"]):
            if filename.endswith(".csv"):
                file_path = os.path.join(app.config["EXCEL_SHEETS"], filename)
                document_id = os.path.splitext(filename)[0]
                files.append(
                    {
                        "filename": filename,
                        "document_id": document_id,
                        "upload_date": datetime.fromtimestamp(
                            os.path.getctime(file_path)
                        ).strftime("%Y-%m-%d %H:%M:%S"),
                        "size": os.path.getsize(file_path),
                        "status": file_status.get(filename, "Completed"),
                    }
                )
        logger.info(f"Found {len(files)} CSV files")
    except Exception as e:
        logger.error(f"Error listing files: {str(e)}")
        return jsonify({"error": "Failed to list files"}), 500
    return jsonify(files)


@app.route("/api/file/<filename>", methods=["GET"])
def get_file_content(filename):
    logger.info(f"Fetching content for file: {filename}")
    file_path = os.path.join(app.config["EXCEL_SHEETS"], filename)
    if not os.path.exists(file_path):
        logger.error(f"File not found: {filename}")
        return jsonify({"error": "File not found"}), 404
    try:
        df = pd.read_csv(file_path)
        if df.empty:
            logger.error(f"File is empty: {filename}")
            return jsonify({"error": "File is empty"}), 400
        expected_columns = [
            "Document_ID",
            "Chapter",
            "Section",
            "Sub Section",
            "Description",
            "Compliance_Requirements",
            "Effective_Date",
            "Applicability",
            "Role Assigned To",
            "Summary",
            "Action Item",
        ]
        if not all(col in df.columns for col in expected_columns):
            logger.error(f"Invalid CSV structure: {filename}")
            return jsonify({"error": "Invalid CSV structure"}), 400
        df = df.fillna("")
        data = df.to_dict(orient="records")
        headers = df.columns.tolist()
        logger.info(f"Successfully fetched content for {filename}")
        return jsonify({"headers": headers, "data": data})
    except Exception as e:
        logger.error(f"Error reading file {filename}: {str(e)}")
        return jsonify({"error": f"Failed to read file: {str(e)}"}), 500


@app.route("/file/<filename>", methods=["GET"])
def view_file(filename):
    logger.info(f"Rendering file view for: {filename}")
    file_path = os.path.join(app.config["EXCEL_SHEETS"], filename)
    if not os.path.exists(file_path):
        logger.error(f"File not found: {filename}")
        return render_template("error.html", message="File not found"), 404
    try:
        df = pd.read_csv(file_path)
        if df.empty:
            logger.error(f"File is empty: {filename}")
            return render_template("error.html", message="File is empty"), 400
        expected_columns = [
            "Document_ID",
            "Chapter",
            "Section",
            "Sub Section",
            "Description",
            "Compliance_Requirements",
            "Effective_Date",
            "Applicability",
            "Role Assigned To",
            "Summary",
            "Action Item",
        ]
        if not all(col in df.columns for col in expected_columns):
            logger.error(f"Invalid CSV structure: {filename}")
            return render_template("error.html", message="Invalid CSV structure"), 400
        df = df.fillna("")
        headers = df.columns.tolist()
        data = df.to_dict(orient="records")
        logger.info(f"Successfully loaded file for view: {filename}")
        return render_template(
            "file_view.html", filename=filename, headers=headers, data=data
        )
    except Exception as e:
        logger.error(f"Error reading file {filename}: {str(e)}")
        return (
            render_template("error.html", message=f"Failed to read file: {str(e)}"),
            500,
        )


@app.route("/api/update_role/<filename>", methods=["POST"])
def update_role(filename):
    logger.info(f"Updating Role Assigned To for file: {filename}")
    file_path = os.path.join(app.config["EXCEL_SHEETS"], filename)
    if not os.path.exists(file_path):
        logger.error(f"File not found: {filename}")
        return jsonify({"error": "File not found"}), 404
    try:
        data = request.json
        row_index = data.get("row_index")
        new_role = data.get("role_assigned_to")
        if row_index is None or new_role is None:
            logger.error("Missing row_index or role_assigned_to in request")
            return jsonify({"error": "Missing row_index or role_assigned_to"}), 400

        df = pd.read_csv(file_path)
        if row_index < 0 or row_index >= len(df):
            logger.error(f"Invalid row_index: {row_index}")
            return jsonify({"error": "Invalid row_index"}), 400

        df.at[row_index, "Role Assigned To"] = new_role
        df.to_csv(file_path, index=False, encoding="utf-8")
        logger.info(
            f"Successfully updated Role Assigned To for row {row_index} in {filename}"
        )
        return jsonify({"message": "Role updated successfully"})
    except Exception as e:
        logger.error(f"Error updating file {filename}: {str(e)}")
        return jsonify({"error": f"Failed to update file: {str(e)}"}), 500


@app.route("/api/metrics", methods=["GET"])
def get_metrics():
    logger.info("Calculating metrics")
    today = datetime.now().date()
    week_ago = today - timedelta(days=7)
    dates = [(today - timedelta(days=x)).strftime("%Y-%m-%d") for x in range(6, -1, -1)]

    try:
        files = os.listdir(app.config["EXCEL_SHEETS"])
        file_data = [
            {
                "date": datetime.fromtimestamp(
                    os.path.getctime(os.path.join(app.config["EXCEL_SHEETS"], f))
                ).date(),
                "filename": f,
                "status": file_status.get(f, "Completed"),
            }
            for f in files
            if f.endswith(".csv")
        ]

        df = pd.DataFrame(file_data)
        logger.info(f"Created DataFrame with {len(df)} entries")

        if df.empty:
            logger.warning("No CSV files found for metrics calculation")
            return jsonify(
                {
                    "daily_avg_uploads": 0,
                    "weekly_uploads": 0,
                    "total_uploads": 0,
                    "unique_documents": 0,
                    "daily_uploads": {date: 0 for date in dates},
                    "status_distribution": {
                        "Processing": 0,
                        "Completed": 0,
                        "Failed": 0,
                    },
                }
            )

        daily_avg = len(df[df["date"] == today]) / 7 if "date" in df.columns else 0
        weekly_uploads = len(df[df["date"] >= week_ago]) if "date" in df.columns else 0
        total_uploads = len(df)
        unique_documents = (
            len(df["filename"].unique()) if "filename" in df.columns else 0
        )

        daily_uploads = {}
        for date in dates:
            date_obj = datetime.strptime(date, "%Y-%m-%d").date()
            count = len(df[df["date"] == date_obj]) if "date" in df.columns else 0
            daily_uploads[date] = count

        status_counts = (
            df["status"].value_counts().to_dict() if "status" in df.columns else {}
        )
        status_distribution = {
            "Processing": status_counts.get("Processing", 0),
            "Completed": status_counts.get("Completed", 0),
            "Failed": status_counts.get("Failed", 0),
        }

        logger.info("Metrics calculated successfully")
        return jsonify(
            {
                "daily_avg_uploads": round(daily_avg, 2),
                "weekly_uploads": weekly_uploads,
                "total_uploads": total_uploads,
                "unique_documents": unique_documents,
                "daily_uploads": daily_uploads,
                "status_distribution": status_distribution,
            }
        )
    except Exception as e:
        logger.error(f"Error calculating metrics: {str(e)}")
        return jsonify({"error": f"Failed to calculate metrics: {str(e)}"}), 500


if __name__ == "__main__":
    logger.info("Starting Flask application")
    app.run(debug=True)
