from datetime import datetime, timedelta
from typing import List, Dict

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import func, case

from db import get_db
import models

router = APIRouter(
    prefix="/admin/charts",
    tags=["admin_charts"],
)

# ======================================================
# 1️⃣ 주별 학습 추이 (풀이 수 + 평균 정답률)
# ======================================================
@router.get("/weekly")
def weekly_activity_trend(
    weeks: int = Query(8, ge=1, le=52),
    db: Session = Depends(get_db),
):
    # ✅ 임시 더미 데이터 (Flutter 차트 테스트용)
    return [
        {"week": "2024-01", "total_attempts": 12, "accuracy_rate": 75.0},
        {"week": "2024-02", "total_attempts": 20, "accuracy_rate": 82.5},
        {"week": "2024-03", "total_attempts": 18, "accuracy_rate": 66.7},
        {"week": "2024-04", "total_attempts": 25, "accuracy_rate": 88.0},
        {"week": "2024-05", "total_attempts": 30, "accuracy_rate": 91.3},
    ]


# @router.get("/weekly")
# def weekly_activity_trend(
#    weeks: int = Query(8, ge=1, le=52),
#    db: Session = Depends(get_db),
# ):
    """
    관리자 차트: 주별 학습 추이
    """

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
        .filter(models.StudentAnswer.created_at >= since)
        .group_by("week")
        .order_by("week")
        .all()
    )

    return [
        {
            "week": r.week,
            "total_attempts": r.total,
            "accuracy_rate": round((r.correct / r.total) * 100, 2) if r.total else 0.0,
        }
        for r in rows
    ]


# ======================================================
# 2️⃣ 월별 학습 추이 (풀이 수 + 평균 정답률)
# ======================================================
@router.get("/monthly")
def monthly_activity_trend(
    months: int = Query(6, ge=1, le=24),
    db: Session = Depends(get_db),
):
    """
    관리자 차트: 월별 학습 추이
    """

    since = datetime.utcnow() - timedelta(days=months * 30)

    rows = (
        db.query(
            func.strftime("%Y-%m", models.StudentAnswer.created_at).label("month"),
            func.count(models.StudentAnswer.id).label("total"),
            func.sum(
                case(
                    (models.StudentAnswer.is_correct == True, 1),
                    else_=0,
                )
            ).label("correct"),
        )
        .filter(models.StudentAnswer.created_at >= since)
        .group_by("month")
        .order_by("month")
        .all()
    )

    return [
        {
            "month": r.month,
            "total_attempts": r.total,
            "accuracy_rate": round((r.correct / r.total) * 100, 2) if r.total else 0.0,
        }
        for r in rows
    ]


# ======================================================
# 3️⃣ 유형별 정답률 추이 (라인 차트용)
# ======================================================
@router.get("/by-type/weekly")
def weekly_accuracy_by_type(
    weeks: int = Query(6, ge=1, le=24),
    db: Session = Depends(get_db),
):
    """
    관리자 차트: 유형별 주간 정답률
    """

    since = datetime.utcnow() - timedelta(weeks=weeks)

    rows = (
        db.query(
            func.strftime("%Y-%W", models.StudentAnswer.created_at).label("week"),
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
        .filter(models.StudentAnswer.created_at >= since)
        .group_by("week", models.Question.question_type)
        .order_by("week")
        .all()
    )

    data: Dict[str, Dict] = {}

    for r in rows:
        data.setdefault(r.question_type, [])
        data[r.question_type].append(
            {
                "week": r.week,
                "accuracy_rate": round((r.correct / r.total) * 100, 2)
                if r.total
                else 0.0,
            }
        )

    return data


# ======================================================
# 4️⃣ 활성 학생 수 추이
# ======================================================
@router.get("/active-students/weekly")
def weekly_active_students(
    weeks: int = Query(6, ge=1, le=24),
    db: Session = Depends(get_db),
):
    """
    관리자 차트: 주별 활성 학생 수
    """

    since = datetime.utcnow() - timedelta(weeks=weeks)

    rows = (
        db.query(
            func.strftime("%Y-%W", models.StudentAnswer.created_at).label("week"),
            func.count(func.distinct(models.StudentAnswer.user_id)).label("students"),
        )
        .filter(models.StudentAnswer.created_at >= since)
        .group_by("week")
        .order_by("week")
        .all()
    )

    return [
        {
            "week": r.week,
            "active_students": r.students,
        }
        for r in rows
    ]