from pydantic import BaseModel
from typing import Optional


class FileBase(BaseModel):
    chapter: str
    section_no: str
    section: str
    sub_section: str
    summary: str
    action_item: str
    deadline: str
    role_assigned_to: Optional[str] = None  # Allow None
    file_path: str


class FileCreate(FileBase):
    pass


class File(FileBase):
    id: int

    class Config:
        from_attributes = True
