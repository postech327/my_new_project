from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from db import get_db
import models
from utils.gpt_concept import generate_concept_by_error_type

router = APIRouter(
    prefix="/concepts",
    tags=["concepts"],
)

# =====================================================
# error_type → 개념 조회 (없으면 GPT 생성)
# GET /concepts/by-error-type?error_type=...
# =====================================================
@router.get("/by-error-type")
def get_or_create_concept(error_type: str, db: Session = Depends(get_db)):
    concept = (
        db.query(models.Concept)
        .filter(models.Concept.error_type == error_type)
        .first()
    )

    # ✅ DB에 있으면 바로 반환
    if concept:
        return {
            "error_type": concept.error_type,
            "title_ko": concept.title_ko,
            "title_en": concept.title_en,
            "description_ko": concept.description_ko,
            "description_en": concept.description_en,
            "example": concept.example,
            "source": "db",
        }

    # 🔥 DB에 없으면 GPT로 생성
    gpt_result = generate_concept_by_error_type(error_type)

    concept = models.Concept(
        error_type=error_type,
        title_ko=gpt_result["title_ko"],
        title_en=gpt_result["title_en"],
        description_ko=gpt_result["description_ko"],
        description_en=gpt_result["description_en"],
        example=gpt_result["example"],
    )

    db.add(concept)
    db.commit()
    db.refresh(concept)

    return {
        "error_type": concept.error_type,
        "title_ko": concept.title_ko,
        "title_en": concept.title_en,
        "description_ko": concept.description_ko,
        "description_en": concept.description_en,
        "example": concept.example,
        "source": "gpt",
    }