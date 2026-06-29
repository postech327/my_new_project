from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from db import get_db
from utils.security import require_role
import models

import os
print("🔥 LOADED FILE:", __file__)

router = APIRouter(
    prefix="/student/wrong_answers",
    tags=["student_wrong_answers"],
)


@router.get("")
def get_wrong_answers(
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_role("student")),
):
    student_id = int(current_user["sub"])

    # =====================================================
    # 1️⃣ 오답 조회
    # =====================================================

    wrong_answers = (
        db.query(models.StudentAnswer)
        .join(models.ExamAttempt, models.StudentAnswer.attempt_id == models.ExamAttempt.id)
        .join(models.Question, models.StudentAnswer.question_id == models.Question.id)
        .filter(
            models.ExamAttempt.user_id == student_id,  # 🔥 수정
            models.StudentAnswer.is_correct.is_(False),  # 🔥 수정
        )
        .order_by(models.StudentAnswer.id.desc())
        .all()
    )

    result = []

    # =====================================================
    # 2️⃣ 결과 구성
    # =====================================================

    for ans in wrong_answers:
        question = ans.question

        # 🔥 relationship 사용 (성능 개선)
        options = sorted(
            question.options,
            key=lambda x: x.label  # label 기준 정렬
        )

        result.append({
            "student_answer_id": ans.id,
            "question_id": question.id,
            "problem_set_id": question.problem_set_id,  # 🔥 추가 (매우 중요)
            "question_type": question.question_type,
            "question_text": question.text,

            "selected_index": ans.selected_index,
            "correct_index": question.answer_index,

            "is_correct": False,  # 🔥 명확하게 추가

            "options": [
                {
                    "label": opt.label,
                    "text": opt.text,
                }
                for opt in options
            ],
        })

    # =====================================================
    # 3️⃣ 응답
    # =====================================================

    return {
        "student_id": student_id,
        "total_wrong_answers": len(result),
        "wrong_answers": result,
    }