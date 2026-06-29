# routers/student_recommend.py

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import not_
import random
from collections import defaultdict

from db import get_db
from utils.security import require_role
import models

router = APIRouter(
    prefix="/student/recommend",
    tags=["student_recommend"],
)


@router.get("")
def recommend_questions(
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_role("student")),
):
    student_id = int(current_user["sub"])

    # =====================================================
    # 1️⃣ 약점 유형 분석
    # =====================================================

    attempts = (
        db.query(models.ExamAttempt)
        .filter(models.ExamAttempt.user_id == student_id)  # 🔥 수정
        .all()
    )

    if not attempts:
        return {"message": "No exam history"}

    attempt_ids = [a.id for a in attempts]

    answers = (
        db.query(models.StudentAnswer)
        .join(models.Question, models.StudentAnswer.question_id == models.Question.id)
        .filter(models.StudentAnswer.attempt_id.in_(attempt_ids))
        .all()
    )

    by_type = defaultdict(lambda: {"total": 0, "correct": 0})

    for ans in answers:
        q_type = ans.question.question_type or "기타"  # 🔥 안정화

        by_type[q_type]["total"] += 1
        if ans.is_correct:
            by_type[q_type]["correct"] += 1

    weakest_type = None
    lowest_accuracy = float("inf")

    for q_type, data in by_type.items():
        if data["total"] == 0:
            continue

        acc = (data["correct"] / data["total"]) * 100

        if acc < lowest_accuracy:
            lowest_accuracy = acc
            weakest_type = q_type

    if not weakest_type:
        return {"message": "No weakness detected"}

    # =====================================================
    # 2️⃣ 이미 푼 문제 제외
    # =====================================================

    solved_question_ids = list(set([a.question_id for a in answers]))

    candidate_questions = (
        db.query(models.Question)
        .filter(
            models.Question.question_type == weakest_type,
            not_(models.Question.id.in_(solved_question_ids)),
        )
        .all()
    )

    if not candidate_questions:
        return {
            "weakest_type": weakest_type,
            "message": "No new questions available"
        }

    # =====================================================
    # 3️⃣ 랜덤 추천
    # =====================================================

    recommended = random.sample(
        candidate_questions,
        min(3, len(candidate_questions))
    )

    return {
        "weakest_type": weakest_type,
        "recommended_questions": [
            {
                "question_id": q.id,
                "problem_set_id": q.problem_set_id,
                "question_type": q.question_type,
                "text": q.text,
            }
            for q in recommended
        ],
    }