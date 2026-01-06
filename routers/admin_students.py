from datetime import datetime, timedelta
from typing import Dict, List

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import func, case

from db import get_db
import models

router = APIRouter(
    prefix="/admin/students",
    tags=["admin_students"],
)

# ======================================================
# 1️⃣ 학생 기본 요약 정보
# ======================================================
@router.get("/{user_id}/summary")
def student_summary(
    user_id: int,
    db: Session = Depends(get_db),
):
    user = db.get(models.User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="Student not found")

    total = (
        db.query(func.count(models.StudentAnswer.id))
        .filter(models.StudentAnswer.user_id == user_id)
        .scalar()
        or 0
    )

    correct = (
        db.query(func.count(models.StudentAnswer.id))
        .filter(
            models.StudentAnswer.user_id == user_id,
            models.StudentAnswer.is_correct == True,
        )
        .scalar()
        or 0
    )

    accuracy = round((correct / total) * 100, 2) if total else 0.0

    return {
        "user_id": user.id,
        "nickname": user.nickname,
        "level": user.level,
        "total_attempts": total,
        "accuracy_rate": accuracy,
    }


# ======================================================
# 2️⃣ 최근 주별 학습 추이
# ======================================================
@router.get("/{user_id}/weekly-trend")
def student_weekly_trend(
    user_id: int,
    weeks: int = Query(8, ge=1, le=52),
    db: Session = Depends(get_db),
):
    since = datetime.utcnow() - timedelta(weeks=weeks)

    rows = (
        db.query(
            func.strftime("%Y-%W", models.StudentAnswer.created_at).label("week"),
            func.count(models.StudentAnswer.id).label("total"),
            func.sum(
                case(
                    (models.StudentAnswer.is_correct == True, 1),
                    else_=0,
                )
            ).label("correct"),
        )
        .filter(
            models.StudentAnswer.user_id == user_id,
            models.StudentAnswer.created_at >= since,
        )
        .group_by("week")
        .order_by("week")
        .all()
    )

    return [
        {
            "week": r.week,
            "total_attempts": r.total,
            "accuracy_rate": round((r.correct / r.total) * 100, 2)
            if r.total
            else 0.0,
        }
        for r in rows
    ]


# ======================================================
# 3️⃣ 유형별 성취도 (약점 분석)
# ======================================================
@router.get("/{user_id}/by-type")
def student_accuracy_by_type(
    user_id: int,
    db: Session = Depends(get_db),
):
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
        .join(models.Question)
        .filter(models.StudentAnswer.user_id == user_id)
        .group_by(models.Question.question_type)
        .all()
    )

    results = []
    weakest_rate = 101
    weakest_type = None

    for r in rows:
        rate = round((r.correct / r.total) * 100, 2) if r.total else 0.0
        results.append(
            {
                "question_type": r.question_type,
                "total_attempts": r.total,
                "accuracy_rate": rate,
            }
        )
        if rate < weakest_rate:
            weakest_rate = rate
            weakest_type = r.question_type

    return {
        "by_type": results,
        "weakest_type": weakest_type,
    }


# ======================================================
# 4️⃣ 최근 학습 리포트 요약
# ======================================================
@router.get("/{user_id}/latest-report")
def student_latest_report(
    user_id: int,
    db: Session = Depends(get_db),
):
    report = (
        db.query(models.StudyReport)
        .filter(models.StudyReport.user_id == user_id)
        .order_by(models.StudyReport.created_at.desc())
        .first()
    )

    if not report:
        return {"message": "No report available"}

    return {
        "report_id": report.id,
        "period": f"{report.period_start.date()} ~ {report.period_end.date()}",
        "accuracy_rate": report.accuracy_rate,
        "weakest_type": report.weakest_type,
        "coach_message": report.coach_message,
        "created_at": report.created_at,
    }
    
@router.get("/students/{user_id}/history")
def student_history(user_id: int, db: Session = Depends(get_db)):
    rows = (
        db.query(
            models.Question.question_type,
            models.StudentAnswer.is_correct,
            models.StudentAnswer.created_at,
        )
        .join(models.Question)
        .filter(models.StudentAnswer.user_id == user_id)
        .order_by(models.StudentAnswer.created_at.desc())
        .limit(50)
        .all()
    )

    return [
        {
            "question_type": r.question_type,
            "is_correct": r.is_correct,
            "created_at": r.created_at,
        }
        for r in rows
    ]
    
@router.get("/students/{user_id}/weak-types")
def student_weak_types(
    user_id: int,
    db: Session = Depends(get_db),
):
    """
    학생 유형별 약점 분석
    """
    rows = (
        db.query(
            models.Question.question_type,
            func.count(models.StudentAnswer.id).label("total"),
            func.sum(
                case(
                    (models.StudentAnswer.is_correct == False, 1),
                    else_=0,
                )
            ).label("wrong"),
        )
        .join(models.Question)
        .filter(models.StudentAnswer.user_id == user_id)
        .group_by(models.Question.question_type)
        .all()
    )

    result = []

    for r in rows:
        accuracy = round(
            ((r.total - r.wrong) / r.total) * 100, 2
        ) if r.total else 0.0

        result.append({
            "question_type": r.question_type,
            "total_attempts": r.total,
            "wrong_attempts": r.wrong,
            "accuracy_rate": accuracy,
            "is_weak": accuracy < 70,  # ⭐ 기준
        })

    # 👉 약한 유형부터 정렬
    result.sort(key=lambda x: x["accuracy_rate"])

    return result