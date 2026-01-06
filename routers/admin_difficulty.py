from typing import List, Dict

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func, case

from db import get_db
import models

router = APIRouter(
    prefix="/admin/difficulty",
    tags=["admin_difficulty"],
)

# ======================================================
# 1️⃣ 문제별 난이도 자동 산정
# ======================================================
@router.get("/questions")
def question_difficulty_analysis(
    min_attempts: int = 5,
    db: Session = Depends(get_db),
):
    """
    문제별 난이도 분석
    """

    rows = (
        db.query(
            models.Question.id.label("question_id"),
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
        .group_by(models.Question.id)
        .having(func.count(models.StudentAnswer.id) >= min_attempts)
        .all()
    )

    results: List[Dict] = []

    for r in rows:
        accuracy = round((r.correct / r.total) * 100, 2)

        if accuracy >= 85:
            difficulty = "easy"
            action = "decrease_usage"
        elif accuracy >= 60:
            difficulty = "medium"
            action = "keep"
        else:
            difficulty = "hard"
            action = "review_or_increase_practice"

        results.append(
            {
                "question_id": r.question_id,
                "question_type": r.question_type,
                "total_attempts": r.total,
                "accuracy_rate": accuracy,
                "difficulty": difficulty,
                "recommended_action": action,
            }
        )

    return results


# ======================================================
# 2️⃣ 유형별 난이도 분포 (출제 전략용)
# ======================================================
@router.get("/by-type")
def difficulty_by_type(
    min_attempts: int = 10,
    db: Session = Depends(get_db),
):
    """
    문제 유형별 난이도 분포
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
        .group_by(models.Question.question_type)
        .having(func.count(models.StudentAnswer.id) >= min_attempts)
        .all()
    )

    results = []

    for r in rows:
        accuracy = round((r.correct / r.total) * 100, 2)

        if accuracy >= 85:
            difficulty = "easy"
        elif accuracy >= 60:
            difficulty = "medium"
        else:
            difficulty = "hard"

        results.append(
            {
                "question_type": r.question_type,
                "accuracy_rate": accuracy,
                "difficulty": difficulty,
            }
        )

    return results


# ======================================================
# 3️⃣ 자동 출제 비율 추천 로직 ⭐
# ======================================================
@router.get("/recommend-distribution")
def recommend_question_distribution(
    db: Session = Depends(get_db),
):
    """
    출제 비율 자동 추천
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
        .group_by(models.Question.question_type)
        .all()
    )

    distribution = []

    for r in rows:
        accuracy = round((r.correct / r.total) * 100, 2) if r.total else 0

        if accuracy >= 85:
            ratio = 0.2
        elif accuracy >= 60:
            ratio = 0.4
        else:
            ratio = 0.6

        distribution.append(
            {
                "question_type": r.question_type,
                "accuracy_rate": accuracy,
                "recommended_ratio": ratio,
            }
        )

    return {
        "description": "Recommended ratio for next problem sets",
        "distribution": distribution,
    }