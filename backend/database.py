from sqlalchemy import create_engine, Column, Integer, String
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

DATABASE_URL = "sqlite:///./files.db"
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


class File(Base):
    __tablename__ = "files"
    id = Column(Integer, primary_key=True, index=True)
    chapter = Column(String)
    section_no = Column(String)
    section = Column(String)
    sub_section = Column(String)
    summary = Column(String)
    action_item = Column(String)
    deadline = Column(String)
    role_assigned_to = Column(String)  # Nullable by default
    file_path = Column(String)


Base.metadata.create_all(bind=engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
