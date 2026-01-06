# routers/teacher.py
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from db import get_db
import models

router = APIRouter(
    prefix="/teacher",
    tags=["teacher"],
)


# 예시: 특정 지문 정보 조회
@router.get("/passages/{passage_id}")
def get_passage(
    passage_id: int,
    db: Session = Depends(get_db),
):
    """
    선생님용: 특정 Passage 한 개 조회
    (response_model / schemas 사용하지 않고 dict로 직접 반환)
    """
    passage = (
        db.query(models.Passage)
        .filter(models.Passage.id == passage_id)
        .first()
    )
    if not passage:
        raise HTTPException(status_code=404, detail="Passage not found")

    return {
        "id": passage.id,
        "title": passage.title,
        "content": passage.content,
        "source": passage.source,
        "level": passage.level,
        "created_by": passage.created_by,
    }