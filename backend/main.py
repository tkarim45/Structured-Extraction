from fastapi import FastAPI, Depends, HTTPException, UploadFile, File as FastAPIFile
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from typing import List
from models import FileCreate, File
from database import SessionLocal, File as FileModel
from fastapi.middleware.cors import CORSMiddleware
import csv
import os
import shutil
import pandas as pd
import logging

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Directory to store uploaded files
UPLOAD_DIR = "uploads"
if not os.path.exists(UPLOAD_DIR):
    os.makedirs(UPLOAD_DIR)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@app.get("/files", response_model=List[File])
def get_files(db: Session = Depends(get_db), sort: str = None, action: str = None):
    query = db.query(FileModel)
    if action:
        query = query.filter(FileModel.action_item == action)
    if sort == "id":
        query = query.order_by(FileModel.id)
    elif sort == "action":
        query = query.order_by(FileModel.action_item)
    return query.all()


@app.get("/files/{id}", response_model=File)
def get_file(id: int, db: Session = Depends(get_db)):
    file = db.query(FileModel).filter(FileModel.id == id).first()
    if not file:
        raise HTTPException(status_code=404, detail="File not found")
    return file


@app.post("/upload")
async def upload_file(
    file: UploadFile = FastAPIFile(...), db: Session = Depends(get_db)
):
    # Validate file extension
    if not file.filename.endswith((".csv", ".xlsx")):
        raise HTTPException(
            status_code=400, detail="Only CSV or Excel files are allowed"
        )

    # Save file locally
    file_path = os.path.join(UPLOAD_DIR, file.filename)
    try:
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
    except Exception as e:
        logger.error(f"Error saving file: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to save file: {str(e)}")

    # Required columns
    required_columns = [
        "Chapter",
        "Section No.",
        "Section",
        "Sub-Section",
        "Summary",
        "Action Item",
        "Deadline",
        "Role Assigned To",
    ]

    # Process file based on extension
    try:
        if file.filename.endswith(".csv"):
            with open(file_path, "r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                # Check for required columns
                if not all(col in reader.fieldnames for col in required_columns):
                    missing = [
                        col for col in required_columns if col not in reader.fieldnames
                    ]
                    raise HTTPException(
                        status_code=400,
                        detail=f"Missing required columns: {', '.join(missing)}",
                    )
                rows = [row for row in reader]
        else:  # .xlsx
            df = pd.read_excel(file_path)
            # Check for required columns
            if not all(col in df.columns for col in required_columns):
                missing = [col for col in required_columns if col not in df.columns]
                raise HTTPException(
                    status_code=400,
                    detail=f"Missing required columns: {', '.join(missing)}",
                )
            rows = df.to_dict("records")

        if not rows:
            raise HTTPException(
                status_code=400, detail="File is empty or contains no valid data"
            )

        for row in rows:
            role_assigned_to = row.get("Role Assigned To")
            if role_assigned_to is None or role_assigned_to.strip() == "":
                logger.info(f"Empty or missing 'Role Assigned To' in row: {row}")
                role_assigned_to = None  # Explicitly set to None

            file_data = FileModel(
                chapter=row["Chapter"],
                section_no=row["Section No."],
                section=row["Section"],
                sub_section=row["Sub-Section"],
                summary=row["Summary"],
                action_item=row["Action Item"],
                deadline=row.get("Deadline", ""),
                role_assigned_to=role_assigned_to,
                file_path=file_path,
            )
            db.add(file_data)
        db.commit()
        return {"message": "File uploaded successfully"}
    except HTTPException:
        raise
    except KeyError as e:
        logger.error(f"Missing column in file: {str(e)}")
        raise HTTPException(status_code=400, detail=f"Missing column in file: {str(e)}")
    except pd.errors.EmptyDataError:
        logger.error("Empty or invalid file")
        raise HTTPException(status_code=400, detail="File is empty or invalid")
    except Exception as e:
        logger.error(f"Error processing file: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error processing file: {str(e)}")


@app.put("/files/{id}")
def update_file(id: int, file: FileCreate, db: Session = Depends(get_db)):
    db_file = db.query(FileModel).filter(FileModel.id == id).first()
    if not db_file:
        raise HTTPException(status_code=404, detail="File not found")
    for key, value in file.dict().items():
        setattr(db_file, key, value)
    db.commit()
    db.refresh(db_file)
    return db_file


@app.get("/download/{id}")
def download_file(id: int, db: Session = Depends(get_db)):
    file = db.query(FileModel).filter(FileModel.id == id).first()
    if not file or not os.path.exists(file.file_path):
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(file.file_path, filename=os.path.basename(file.file_path))
