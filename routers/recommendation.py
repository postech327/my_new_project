from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func, case

from db import get_db
import models

router = APIRouter(
    prefix="/recommendation",
    tags=["recommendation"],
)

# ======================================================
# 🎯 학생 약점 유형 자동 추천
# ======================================================
@router.get("/students/{user_id}/weak-types")
def recommend_weak_types(
    user_id: int,
    db: Session = Depends(get_db),
):
    """
    특정 학생의 풀이 기록을 기반으로
    정답률이 낮은 문제 유형을 우선순위별로 추천
    """

    rows = (
        db.query(
            models.Question.question_type,
            func.count(models.StudentAnswer.id).label("total"),
            func.sum(
                case(
                    (models.StudentAnswer.is_correct == True, 1),
                    else_=0,
                )
            ).label("correct"),
        )
        .join(models.StudentAnswer)
        .filter(models.StudentAnswer.user_id == user_id)
        .group_by(models.Question.question_type)
        .all()
    )

    result = []

    for r in rows:
        if r.total == 0:
            continue

        accuracy = round((r.correct / r.total) * 100, 2)

        # 🎯 추천 기준
        if accuracy < 75:
            result.append(
                {
                    "question_type": r.question_type,
                    "total_attempts": r.total,
                    "accuracy_rate": accuracy,
                    "priority": "high" if accuracy < 60 else "medium",
                }
            )

    # 정답률 낮은 순 → 우선순위
    result.sort(key=lambda x: x["accuracy_rate"])

    return {
        "user_id": user_id,
        "weak_types": result,
    }