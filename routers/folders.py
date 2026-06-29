from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from db import get_db
import models

router = APIRouter(prefix="/folders", tags=["Folders"])


@router.post("/")
def create_folder(name: str, db: Session = Depends(get_db)):
    folder = models.Folder(
        name=name,
        owner_id=1,   # 임시 teacher1
        is_public=True,
    )
    db.add(folder)
    db.commit()
    db.refresh(folder)
    return folder


@router.get("/")
def get_folders(db: Session = Depends(get_db)):
    return db.query(models.Folder).all()

@router.get("/{folder_id}/passages")
def get_passages_by_folder(folder_id: int, db: Session = Depends(get_db)):
    return db.query(models.Passage).filter(
        models.Passage.folder_id == folder_id
    ).all()