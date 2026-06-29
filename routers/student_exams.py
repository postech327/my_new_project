from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from datetime import datetime

from db import get_db
from services import student_exam_service
from utils.security import require_role

from schemas.student_exam import (
    StudentExamSubmitRequest,
    StudentExamSubmitResponse,
    RetrySubmitRequest,
    RetrySubmitResponse,
    ExamSummaryResponse,
)

import models

router = APIRouter(
    prefix="/student/exams",
    tags=["student_exams"],
)

# =====================================================
# 0️⃣ 🔥 내가 배정받은 시험 목록 조회
# =====================================================
@router.get("/")
def get_my_exams(
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_role("student")),
):
    student_id = int(current_user["sub"])

    assignments = (
        db.query(models.ExamAssignment)
        .filter(models.ExamAssignment.user_id == student_id)
        .all()
    )

    result = []

    for a in assignments:
        problem_set = (
            db.query(models.ProblemSet)
            .filter(models.ProblemSet.id == a.problem_set_id)
            .first()
        )

        if problem_set:
            result.append({
                "assignment_id": a.id,
                "problem_set_id": problem_set.id,
                "name": problem_set.name,
                "description": problem_set.description,
                "is_completed": a.is_completed,
                "assigned_at": a.assigned_at,
            })

    return result


# =====================================================
# 1️⃣ 시험 최초 제출 (🔥 score 저장 추가)
# =====================================================
@router.post(
    "/submit",
    response_model=StudentExamSubmitResponse,
)
def submit_student_exam(
    payload: StudentExamSubmitRequest,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_role("student")),
):
    try:
        student_id = int(current_user["sub"])

        result = student_exam_service.submit_student_exam(
            db=db,
            user_id=student_id,
            problem_set_id=payload.problem_set_id,
            answers=payload.answers,
        )
        
        return result

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


# =====================================================
# 2️⃣ 오답 재도전 문제 제공
# =====================================================
@router.get("/{problem_set_id}/retry")
def get_retry_questions(
    problem_set_id: int,
    limit: int = 5,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_role("student")),
):
    try:
        return student_exam_service.get_retry_questions(
            db=db,
            problem_set_id=problem_set_id,
            user_id=int(current_user["sub"]),
            limit=limit,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )


# =====================================================
# 3️⃣ 오답 재도전 제출
# =====================================================
@router.post(
    "/{problem_set_id}/retry-submit",
    response_model=RetrySubmitResponse,
)
def submit_retry_answers(
    problem_set_id: int,
    payload: RetrySubmitRequest,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_role("student")),
):
    try:
        return student_exam_service.submit_retry_answers(
            db=db,
            problem_set_id=problem_set_id,
            user_id=int(current_user["sub"]),
            answers=payload.answers,
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


# =====================================================
# 4️⃣ 시험 결과 요약
# =====================================================
@router.get(
    "/{problem_set_id}/summary",
    response_model=ExamSummaryResponse,
)
def get_exam_summary(
    problem_set_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_role("student")),
):
    try:
        return student_exam_service.get_exam_summary(
            db=db,
            problem_set_id=problem_set_id,
            user_id=int(current_user["sub"]),
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )


# =====================================================
# 5️⃣ 시험 결과 상세 조회
# =====================================================
@router.get("/{problem_set_id}/result")
def get_exam_result(
    problem_set_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_role("student")),
):
    student_id = int(current_user["sub"])

    # 1️⃣ 시험 할당 확인
    assignment = (
        db.query(models.ExamAssignment)
        .filter(
            models.ExamAssignment.user_id == student_id,
            models.ExamAssignment.problem_set_id == problem_set_id,
        )
        .first()
    )

    if not assignment:
        raise HTTPException(status_code=403, detail="Not assigned exam")

    # 2️⃣ 최신 attempt 가져오기
    attempt = (
        db.query(models.ExamAttempt)
        .filter(
            models.ExamAttempt.user_id == student_id,
            models.ExamAttempt.problem_set_id == problem_set_id,
        )
        .order_by(models.ExamAttempt.attempt_number.desc())
        .first()
    )

    if not attempt:
        raise HTTPException(status_code=404, detail="No attempt found")

    # 3️⃣ 문제 가져오기
    questions = (
        db.query(models.Question)
        .filter(models.Question.problem_set_id == problem_set_id)
        .all()
    )

    # 4️⃣ 해당 attempt의 답안 가져오기
    answers = (
        db.query(models.StudentAnswer)
        .filter(models.StudentAnswer.attempt_id == attempt.id)
        .all()
    )

    answer_map = {a.question_id: a for a in answers}

    total = len(questions)
    correct = 0
    results = []

    for q in questions:
        student_answer = answer_map.get(q.id)

        if student_answer:
            is_correct = student_answer.is_correct
            selected_index = student_answer.selected_index
        else:
            is_correct = False
            selected_index = None

        if is_correct:
            correct += 1

        results.append({
            "question_id": q.id,
            "selected_index": selected_index,
            "correct_index": q.answer_index,
            "is_correct": is_correct,
        })

    score = round((correct / total) * 100) if total > 0 else 0

    return {
        "problem_set_id": problem_set_id,
        "attempt_number": attempt.attempt_number,
        "total": total,
        "correct_count": correct,
        "wrong_count": total - correct,
        "accuracy": round(correct / total, 2) if total > 0 else 0,
        "score": score,
        "results": results,
    }
    

# =====================================================
# 6️⃣ 시험 시작 (문제 + 보기 내려주기)
# =====================================================
@router.get("/{problem_set_id}/start")
def start_exam(
    problem_set_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_role("student")),
):
    student_id = int(current_user["sub"])

    # 1️⃣ 배정 여부 확인
    assignment = (
        db.query(models.ExamAssignment)
        .filter(
            models.ExamAssignment.user_id == student_id,
            models.ExamAssignment.problem_set_id == problem_set_id,
        )
        .first()
    )

    # 🔥 테스트용: 배정 체크 비활성화
    # if not assignment:
    #     raise HTTPException(
    #         status_code=status.HTTP_403_FORBIDDEN,
    #         detail="Not assigned exam",
    #     )

    # 2️⃣ ProblemSet 조회
    problem_set = (
        db.query(models.ProblemSet)
        .filter(models.ProblemSet.id == problem_set_id)
        .first()
    )

    if not problem_set:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="ProblemSet not found",
        )

    # 3️⃣ 문제 조회
    questions = (
        db.query(models.Question)
        .filter(models.Question.problem_set_id == problem_set_id)
        .order_by(models.Question.order)
        .all()
    )

    result_questions = []

    for q in questions:
        result_questions.append({
            "question_id": q.id,
            "question_type": q.question_type,
            "question_text": q.text,
            "options": [
                {
                    "option_id": o.id,
                    "text": o.text,
                }
                for o in q.options  # 🔥 relationship 활용
            ],
        })

    return {
        "problem_set_id": problem_set.id,
        "name": problem_set.name,
        "description": problem_set.description,
        "questions": result_questions,
    }