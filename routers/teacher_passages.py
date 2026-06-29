from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from db import get_db
import models
from utils.security import require_role

# 🔥 schema
from schemas.passage import PassageCreate, PassageResponse


router = APIRouter(
    prefix="/teacher/passages",
    tags=["teacher_passages"],
)

# =====================================================
# 🔥 교사 지문 생성 (핵심 API)
# =====================================================
@router.post("", response_model=PassageResponse)
def create_teacher_passage(
    req: PassageCreate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_role("teacher")),
):
    """
    교사가 지문 생성
    """
    teacher_id = int(current_user["sub"])

    # ❌ title 제거
    passage = models.Passage(
    content=req.content,
    teacher_id=teacher_id,
)

    db.add(passage)
    db.commit()
    db.refresh(passage)

    return passage


# =====================================================
# 교사 지문 목록 조회
# =====================================================
@router.get("")
def read_teacher_passages(
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_role("teacher")),
):
    teacher_id = int(current_user["sub"])

    passages = (
        db.query(models.Passage)
        .filter(models.Passage.created_by_id == teacher_id)
        .order_by(models.Passage.created_at.desc())
        .all()
    )

    return {
        "ok": True,
        "count": len(passages),
        "passages": passages,
    }


# =====================================================
# 교사 지문 단건 조회
# =====================================================
@router.get("/{passage_id}")
def read_teacher_passage(
    passage_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_role("teacher")),
):
    teacher_id = int(current_user["sub"])

    passage = (
        db.query(models.Passage)
        .filter(
            models.Passage.id == passage_id,
            models.Passage.created_by_id == teacher_id,
        )
        .first()
    )

    if not passage:
        raise HTTPException(status_code=404, detail="Passage not found")

    return {
        "ok": True,
        "passage": passage,
    }


# =====================================================
# 교사 지문 삭제
# =====================================================
@router.delete("/{passage_id}")
def delete_teacher_passage(
    passage_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_role("teacher")),
):
    teacher_id = int(current_user["sub"])

    passage = (
        db.query(models.Passage)
        .filter(
            models.Passage.id == passage_id,
            models.Passage.created_by_id == teacher_id,
        )
        .first()
    )

    if not passage:
        raise HTTPException(status_code=404, detail="Passage not found")

    db.delete(passage)
    db.commit()

    return {
        "ok": True,
        "deleted_passage_id": passage_id,
    }