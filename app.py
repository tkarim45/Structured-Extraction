from flask import Flask, request, jsonify, render_template
from werkzeug.utils import secure_filename
import os
import pandas as pd
from datetime import datetime, timedelta
import nest_asyncio
import PyPDF2
import re
from openai import OpenAI
import dotenv
import csv
import logging
import threading
import dateutil.parser
from utils.helpers import (
    allowed_file,
    parse_rbi_directions,
    enhance_csv_with_summary_and_action,
)
import uuid

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
openai_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
logger.info("Environment variables loaded")

# Apply nest_asyncio to allow nested event loops
nest_asyncio.apply()
logger.info("Nested asyncio applied")

# In-memory status tracking
file_status = {}
notice_status = {}  # notice_id: {status, last_updated, filename}


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
        # Add timestamp and UUID to filename
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        notice_id = str(uuid.uuid4())
        base, ext = os.path.splitext(secure_filename(file.filename))
        unique_filename = f"{base}_{timestamp}_{notice_id}{ext}"
        file_path = os.path.join(app.config["UPLOAD_FOLDER"], unique_filename)
        csv_filename = f"{base}_{timestamp}_{notice_id}.csv"
        logger.info(f"Saving uploaded file: {unique_filename}")
        file.save(file_path)

        file_status[csv_filename] = "Processing"
        notice_status[notice_id] = {
            "status": "Pending Approval",
            "last_updated": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "filename": csv_filename,
        }
        logger.info(f"Set status to Processing for {csv_filename}")

        def process_file():
            try:
                logger.info(f"Extracting text from PDF: {unique_filename}")
                with open(file_path, "rb") as file:
                    pdf_reader = PyPDF2.PdfReader(file)
                    text = ""
                    for page in pdf_reader.pages:
                        page_text = page.extract_text()
                        if page_text:
                            text += page_text + "\n"
                        else:
                            logger.warning(
                                f"Empty text extracted from page in {unique_filename}"
                            )

                if not text.strip():
                    logger.error(f"No text extracted from PDF: {unique_filename}")
                    file_status[csv_filename] = "Failed"
                    return

                txt_path = os.path.join(
                    app.config["EXTRACTED_TEXT"], f"{base}_{timestamp}_{notice_id}.txt"
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
                    logger.error(f"Parsed DataFrame is empty for {unique_filename}")
                    file_status[csv_filename] = "Failed"
                    return
                logger.info(f"Parsed DataFrame contains {len(df)} rows")

                csv_path = os.path.join(app.config["EXCEL_SHEETS"], csv_filename)
                logger.info(f"Saving initial CSV to: {csv_path}")
                df.to_csv(csv_path, index=False, encoding="utf-8", na_rep="")

                structured_data = []
                document_id = f"{base}_{timestamp}_{notice_id}"
                for _, row in df.iterrows():
                    structured_data.append(
                        [
                            document_id,
                            row["Chapter"],
                            row["Section No."],
                            row["Section"],
                            row["Sub-Section"],
                            "",  # Summary
                            "",  # Action Item
                            "",  # Due date
                            "",  # Periodicity
                            "No",  # Marked as Completed
                            "Not Started",  # Work Status
                            "",  # Role Assigned To
                        ]
                    )

                if not structured_data:
                    logger.error(f"No structured data generated for {unique_filename}")
                    file_status[csv_filename] = "Failed"
                    return
                logger.info(f"Generated {len(structured_data)} rows of structured data")

                logger.info(f"Saving structured CSV to: {csv_path}")
                with open(csv_path, "w", newline="", encoding="utf-8") as csvfile:
                    writer = csv.writer(csvfile)
                    writer.writerow(
                        [
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
                    )
                    writer.writerows(structured_data)

                # Enhance CSV with Summary, Action Item, Due date, and Periodicity
                logger.info(
                    f"Enhancing CSV with summary, action items, and periodicity: {csv_path}"
                )
                if not enhance_csv_with_summary_and_action(csv_path):
                    logger.error(f"Failed to enhance CSV: {csv_path}")
                    file_status[csv_filename] = "Failed"
                    return

                # Verify CSV file
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

                logger.info(f"File {unique_filename} processed successfully")
                file_status[csv_filename] = "Completed"
                notice_status[notice_id]["last_updated"] = datetime.now().strftime(
                    "%Y-%m-%d %H:%M:%S"
                )
            except Exception as e:
                logger.error(f"Error processing file {unique_filename}: {str(e)}")
                file_status[csv_filename] = "Failed"
                notice_status[notice_id]["last_updated"] = datetime.now().strftime(
                    "%Y-%m-%d %H:%M:%S"
                )

        threading.Thread(target=process_file, daemon=True).start()

        return (
            jsonify(
                {
                    "message": "File upload started",
                    "filename": unique_filename,
                    "csv_path": csv_filename,
                    "notice_id": notice_id,
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
        excel_dir = app.config["EXCEL_SHEETS"]
        for filename in os.listdir(excel_dir):
            if filename.endswith(".csv"):
                file_path = os.path.join(excel_dir, filename)
                document_id = os.path.splitext(filename)[0]
                found_notice_id = None
                for notice_id, notice_info in notice_status.items():
                    if notice_info["filename"] == filename:
                        found_notice_id = notice_id
                        break
                if found_notice_id:
                    approval_status = notice_status[found_notice_id]["status"]
                    last_updated = notice_status[found_notice_id]["last_updated"]
                else:
                    approval_status = "Pending Approval"
                    last_updated = datetime.fromtimestamp(
                        os.path.getctime(file_path)
                    ).strftime("%Y-%m-%d %H:%M:%S")
                files.append(
                    {
                        "filename": filename,
                        "document_id": document_id,
                        "upload_date": datetime.fromtimestamp(
                            os.path.getctime(file_path)
                        ).strftime("%Y-%m-%d %H:%M:%S"),
                        "size": os.path.getsize(file_path),
                        "status": file_status.get(filename, "Completed"),
                        "notice_id": found_notice_id or document_id,
                        "approval_status": approval_status,
                        "last_updated": last_updated,
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


@app.route("/api/notices", methods=["GET"])
def list_notices():
    logger.info("Listing all notices for approval table")
    notices = []
    try:
        excel_dir = app.config["EXCEL_SHEETS"]
        for filename in os.listdir(excel_dir):
            if filename.endswith(".csv"):
                file_path = os.path.join(excel_dir, filename)
                found_notice_id = None
                for notice_id, notice_info in notice_status.items():
                    if notice_info["filename"] == filename:
                        found_notice_id = notice_id
                        break
                if found_notice_id:
                    status = notice_status[found_notice_id]["status"]
                    last_updated = notice_status[found_notice_id]["last_updated"]
                else:
                    status = "Pending Approval"
                    last_updated = datetime.fromtimestamp(
                        os.path.getctime(file_path)
                    ).strftime("%Y-%m-%d %H:%M:%S")
                notices.append(
                    {
                        "notice_id": found_notice_id or os.path.splitext(filename)[0],
                        "status": status,
                        "last_updated": last_updated,
                        "filename": filename,
                    }
                )
        logger.info(f"Found {len(notices)} notices")
    except Exception as e:
        logger.error(f"Error listing notices: {str(e)}")
        return jsonify({"error": "Failed to list notices"}), 500
    return jsonify(notices)


@app.route("/api/approve_notice/<notice_id>", methods=["POST"])
def approve_notice(notice_id):
    logger.info(f"Updating approval status for notice: {notice_id}")
    filename = None
    for f in os.listdir(app.config["EXCEL_SHEETS"]):
        if f.startswith(notice_id) or os.path.splitext(f)[0] == notice_id:
            filename = f
            break
    if notice_id not in notice_status:
        if filename:
            file_path = os.path.join(app.config["EXCEL_SHEETS"], filename)
            notice_status[notice_id] = {
                "status": "Pending Approval",
                "last_updated": datetime.fromtimestamp(
                    os.path.getctime(file_path)
                ).strftime("%Y-%m-%d %H:%M:%S"),
                "filename": filename,
            }
        else:
            logger.error(f"Notice ID not found: {notice_id}")
            return jsonify({"error": "Notice ID not found"}), 404
    try:
        data = request.json
        new_status = data.get("status")
        if new_status not in ["Pending Approval", "Approved", "Rejected"]:
            logger.error(f"Invalid status: {new_status}")
            return jsonify({"error": "Invalid status"}), 400
        notice_status[notice_id]["status"] = new_status
        notice_status[notice_id]["last_updated"] = datetime.now().strftime(
            "%Y-%m-%d %H:%M:%S"
        )
        logger.info(f"Notice {notice_id} status updated to {new_status}")
        return jsonify({"message": "Notice status updated successfully"})
    except Exception as e:
        logger.error(f"Error updating notice {notice_id}: {str(e)}")
        return jsonify({"error": f"Failed to update notice: {str(e)}"}), 500


@app.route("/api/update_work_status/<filename>", methods=["POST"])
def update_work_status(filename):
    logger.info(f"Updating work status for file: {filename}")
    file_path = os.path.join(app.config["EXCEL_SHEETS"], filename)
    if not os.path.exists(file_path):
        logger.error(f"File not found: {filename}")
        return jsonify({"error": "File not found"}), 404
    try:
        data = request.json
        row_index = data.get("row_index")
        marked_completed = data.get("marked_completed")
        work_status = data.get("work_status")  # New field for Work Status
        if row_index is None:
            logger.error("Missing row_index in request")
            return jsonify({"error": "Missing row_index"}), 400
        df = pd.read_csv(file_path)
        if row_index < 0 or row_index >= len(df):
            logger.error(f"Invalid row_index: {row_index}")
            return jsonify({"error": "Invalid row_index"}), 400
        if marked_completed is not None:
            df.at[row_index, "Marked as Completed"] = marked_completed
        if work_status is not None:
            df.at[row_index, "Work Status"] = work_status
        df.to_csv(file_path, index=False, encoding="utf-8")
        logger.info(
            f"Successfully updated work status for row {row_index} in {filename}"
        )
        return jsonify({"message": "Work status updated successfully"})
    except Exception as e:
        logger.error(f"Error updating work status for file {filename}: {str(e)}")
        return jsonify({"error": f"Failed to update work status: {str(e)}"}), 500


if __name__ == "__main__":
    logger.info("Starting Flask application")
    app.run(debug=True)
