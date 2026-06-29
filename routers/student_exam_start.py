from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from db import get_db
from utils.security import require_role
import models

router = APIRouter(
    prefix="/student/exams",
    tags=["student_exam_start"],
)


@router.post("/start/{problem_set_id}")
def start_exam(
    problem_set_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_role("student")),
):
    user_id = int(current_user["sub"])

    # 현재 시도 횟수 계산
    attempt_count = (
        db.query(models.ExamAttempt)
        .filter(
            models.ExamAttempt.user_id == user_id,
            models.ExamAttempt.problem_set_id == problem_set_id,
        )
        .count()
    )

    attempt = models.ExamAttempt(
        user_id=user_id,
        problem_set_id=problem_set_id,
        attempt_number=attempt_count + 1,
    )

    db.add(attempt)
    db.commit()
    db.refresh(attempt)

    return {
        "attempt_id": attempt.id,
        "problem_set_id": problem_set_id,
    }