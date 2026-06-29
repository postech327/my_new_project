import json
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from db import get_db
import models
from utils.security import require_role


router = APIRouter(
    prefix="/student/final-touch-practice-results",
    tags=["student_final_touch_practice_results"],
)


class FinalTouchPracticeResultCreate(BaseModel):
    final_touch_id: int
    passage_id: int | None = None
    source_label: str | None = None
    total_questions: int = Field(..., ge=1)
    correct_count: int = Field(..., ge=0)
    accuracy_rate: float | None = None
    practiced_types: list[str] = Field(default_factory=list)
    wrong_types: list[str] = Field(default_factory=list)


def _json_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item) for item in value if str(item).strip()]
    if isinstance(value, str):
        try:
            decoded = json.loads(value)
        except json.JSONDecodeError:
            return []
        return _json_list(decoded)
    return []


def _serialize(result: models.FinalTouchPracticeResult) -> dict:
    return {
        "id": result.id,
        "student_id": result.student_id,
        "final_touch_id": result.final_touch_id,
        "passage_id": result.passage_id,
        "source_label": result.source_label or "",
        "total_questions": result.total_questions,
        "correct_count": result.correct_count,
        "accuracy_rate": result.accuracy_rate,
        "practiced_types": _json_list(result.practiced_types),
        "wrong_types": _json_list(result.wrong_types),
        "created_at": result.created_at.isoformat() if result.created_at else None,
    }


@router.post("")
def create_practice_result(
    payload: FinalTouchPracticeResultCreate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_role("student")),
):
    if payload.correct_count > payload.total_questions:
        raise HTTPException(
            status_code=400,
            detail="correct_count cannot exceed total_questions",
        )

    final_touch = (
        db.query(models.AnalysisRecord)
        .filter(models.AnalysisRecord.id == payload.final_touch_id)
        .first()
    )
    if not final_touch:
        raise HTTPException(status_code=404, detail="Final Touch not found")

    accuracy_rate = (
        payload.accuracy_rate
        if payload.accuracy_rate is not None
        else round(payload.correct_count / payload.total_questions * 100, 1)
    )

    result = models.FinalTouchPracticeResult(
        student_id=int(current_user["sub"]),
        final_touch_id=payload.final_touch_id,
        passage_id=payload.passage_id or final_touch.passage_id,
        source_label=(payload.source_label or "").strip() or None,
        total_questions=payload.total_questions,
        correct_count=payload.correct_count,
        accuracy_rate=accuracy_rate,
        practiced_types=json.dumps(payload.practiced_types, ensure_ascii=False),
        wrong_types=json.dumps(payload.wrong_types, ensure_ascii=False),
    )
    db.add(result)
    db.commit()
    db.refresh(result)

    return {"success": True, "result": _serialize(result)}


@router.get("/latest/{final_touch_id}")
def get_latest_practice_result(
    final_touch_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_role("student")),
):
    result = (
        db.query(models.FinalTouchPracticeResult)
        .filter(
            models.FinalTouchPracticeResult.student_id == int(current_user["sub"]),
            models.FinalTouchPracticeResult.final_touch_id == final_touch_id,
        )
        .order_by(
            models.FinalTouchPracticeResult.created_at.desc(),
            models.FinalTouchPracticeResult.id.desc(),
        )
        .first()
    )
    return {"result": _serialize(result) if result else None}
