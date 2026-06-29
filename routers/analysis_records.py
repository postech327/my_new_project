from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel

from db import get_db
import models
from utils.security import require_role

router = APIRouter(
    prefix="/analysis-records",
    tags=["analysis_records"],
)

# =========================
# Request Schema
# =========================
class AnalysisRecordCreate(BaseModel):
    passage: str
    passage_bracketed: str
    topic_en: str
    topic_ko: str
    title_en: str
    title_ko: str
    gist_en: str
    gist_ko: str


# =========================
# AnalysisRecord 생성 (Teacher 전용)
# =========================
@router.post("")
def create_analysis_record(
    payload: AnalysisRecordCreate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_role("teacher")),
):
    """
    AnalysisRecord 생성
    - Passage 자동 생성
    - teacher 전용
    - STEP 8 (ProblemSet 자동 생성) 연결용
    """

    # 1️⃣ Passage 생성 (⚠️ NOT NULL 컬럼 방어)
    passage = models.Passage(
    content=payload.passage,
    title=payload.title_en,
    teacher_id=current_user["sub"],
    folder_id=payload.folder_id   # 🔥 핵심 추가
)
    db.add(passage)
    db.commit()
    db.refresh(passage)

    # 2️⃣ AnalysisRecord 생성
    analysis = models.AnalysisRecord(
        teacher_id=int(current_user["sub"]),
        passage_id=passage.id,
        passage_bracketed=payload.passage_bracketed,
        topic_en=payload.topic_en,
        topic_ko=payload.topic_ko,
        title_en=payload.title_en,
        title_ko=payload.title_ko,
        gist_en=payload.gist_en,
        gist_ko=payload.gist_ko,
    )

    db.add(analysis)
    db.commit()
    db.refresh(analysis)

    # 3️⃣ 응답
    return {
        "ok": True,
        "analysis_record": {
            "id": analysis.id,
            "teacher_id": analysis.teacher_id,
            "passage_id": analysis.passage_id,
        },
    }
