# student_answers.py

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from db import get_db
import models
from schemas.student_answer import StudentAnswerSubmit
from utils.auth_jwt import get_current_user

router = APIRouter(
    prefix="/student",
    tags=["student_answers"],
)


@router.post("/answers")
def submit_answers(
    payload: StudentAnswerSubmit,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    # 1️⃣ 학생만 가능
    if current_user["role"] != "student":
        raise HTTPException(status_code=403, detail="Students only")

    student_id = int(current_user["sub"])

    # 🔥 attempt 찾기
    attempt = db.query(models.ExamAttempt).filter(
        models.ExamAttempt.user_id == student_id,
        models.ExamAttempt.problem_set_id == payload.problem_set_id
    ).first()

    # 🔥 없으면 생성
    if not attempt:
        attempt = models.ExamAttempt(
            user_id=student_id,
            problem_set_id=payload.problem_set_id,
            attempt_number=1,
            score=0,
            correct_count=0,
            total_questions=0,
        )

        db.add(attempt)
        db.commit()
        db.refresh(attempt)

    attempt_id = attempt.id

    # 🔥 기존 답안 삭제 (재제출 허용)
    db.query(models.StudentAnswer).filter(
        models.StudentAnswer.attempt_id == attempt_id,
        models.StudentAnswer.question_id.in_(
            [a.question_id for a in payload.answers]
        ),
    ).delete(synchronize_session=False)

    # 🔥 채점 + 저장
    correct_count = 0
    total = 0

    for ans in payload.answers:
        question = db.query(models.Question).filter(
            models.Question.id == ans.question_id
        ).first()

        if not question:
            continue

        is_correct = (ans.selected_index == question.answer_index)

        if is_correct:
            correct_count += 1

        total += 1

        answer = models.StudentAnswer(
            attempt_id=attempt_id,
            question_id=ans.question_id,
            selected_index=ans.selected_index,
            is_correct=is_correct,
        )

        db.add(answer)

    # ✅ ⭐⭐⭐ for문 끝난 후 (핵심 위치)
    score = int((correct_count / total) * 100) if total > 0 else 0

    attempt.score = score
    attempt.correct_count = correct_count
    attempt.total_questions = total

    db.commit()

    return {
        "ok": True,
        "total": total,
        "correct": correct_count,
        "score": score,
    }


# 🔹 단일 답안 API (테스트용)
@router.post("/")
def submit_answer(
    student_id: int,
    question_id: int,
    selected_index: int,
    db: Session = Depends(get_db)
):
    attempt = models.ExamAttempt(
        user_id=student_id,
        problem_set_id=0
    )
    db.add(attempt)
    db.commit()
    db.refresh(attempt)

    answer = models.StudentAnswer(
        attempt_id=attempt.id,
        question_id=question_id,
        selected_index=selected_index,
        is_correct=False
    )

    db.add(answer)
    db.commit()
    db.refresh(answer)

    return {"status": "ok"}