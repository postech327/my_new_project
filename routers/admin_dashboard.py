from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import func, case

from db import get_db
import models

router = APIRouter(
    prefix="/admin/dashboard",
    tags=["admin_dashboard"],
)

# ======================================================
# 1️⃣ 관리자 대시보드 요약 (주차 선택 가능)
# ======================================================
@router.get("/overview")
def dashboard_overview(
    week: str | None = Query(None, description="예: 2024-05"),
    db: Session = Depends(get_db),
):
    """
    관리자 대시보드 요약
    - week 없으면 전체
    - week 있으면 해당 주차 기준
    """

    answer_query = db.query(models.StudentAnswer)

    if week:
        answer_query = answer_query.filter(
            func.strftime("%Y-%W", models.StudentAnswer.created_at) == week
        )

    total_students = (
        db.query(func.count(models.User.id))
        .filter(models.User.role == "normal")
        .scalar()
        or 0
    )

    total_answers = answer_query.count()

    correct_answers = (
        answer_query.filter(models.StudentAnswer.is_correct == True).count()
    )

    avg_accuracy = (
        round((correct_answers / total_answers) * 100, 2)
        if total_answers > 0
        else 0.0
    )

    return {
        "total_students": total_students,
        "total_answers": total_answers,
        "average_accuracy": avg_accuracy,
        "selected_week": week or "전체",
    }


# ======================================================
# 2️⃣ 문제 유형별 정답률 (주차 선택 가능)
# ======================================================
@router.get("/by-type")
def accuracy_by_type(
    week: str | None = Query(None),
    db: Session = Depends(get_db),
):
    query = (
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
    )

    if week:
        query = query.filter(
            func.strftime("%Y-%W", models.StudentAnswer.created_at) == week
        )

    rows = query.group_by(models.Question.question_type).all()

    return [
        {
            "question_type": r.question_type,
            "total_attempts": r.total,
            "accuracy_rate": round((r.correct / r.total) * 100, 2)
            if r.total
            else 0.0,
        }
        for r in rows
    ]


# ======================================================
# 3️⃣ 상위 활동 학생 (주차 선택 가능)
# ======================================================
@router.get("/top-students")
def top_students(
    week: str | None = Query(None),
    db: Session = Depends(get_db),
):
    query = (
        db.query(
            models.User.nickname,
            func.count(models.StudentAnswer.id).label("attempts"),
            func.sum(
                case(
                    (models.StudentAnswer.is_correct == True, 1),
                    else_=0,
                )
            ).label("correct"),
        )
        .join(models.StudentAnswer)
    )

    if week:
        query = query.filter(
            func.strftime("%Y-%W", models.StudentAnswer.created_at) == week
        )

    rows = (
        query.group_by(models.User.id)
        .order_by(func.count(models.StudentAnswer.id).desc())
        .limit(10)
        .all()
    )

    return [
        {
            "nickname": r.nickname,
            "attempts": r.attempts,
            "accuracy": round((r.correct / r.attempts) * 100, 2)
            if r.attempts
            else 0.0,
        }
        for r in rows
    ]
    
@router.get("/by-type/detail")
def accuracy_detail_by_type(
    type: str,
    db: Session = Depends(get_db),
):
    rows = (
        db.query(
            models.User.nickname,
            func.count(models.StudentAnswer.id).label("total"),
            func.sum(
                case(
                    (models.StudentAnswer.is_correct == True, 1),
                    else_=0,
                )
            ).label("correct"),
        )
        .join(models.StudentAnswer)
        .join(models.Question)
        .filter(models.Question.question_type == type)
        .group_by(models.User.id)
        .order_by(func.count(models.StudentAnswer.id).desc())
        .all()
    )

    return [
        {
            "nickname": r.nickname,
            "total_attempts": r.total,
            "accuracy_rate": round((r.correct / r.total) * 100, 2)
            if r.total else 0.0,
        }
        for r in rows
    ]