from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from db import get_db
import models

router = APIRouter(
    prefix="/study-reports",
    tags=["study_reports"],
)

# =====================================================
# ① 내 학습 리포트 조회
# GET /study-reports/me?user_id=1
# =====================================================
@router.get("/me")
def get_my_study_report(user_id: int, db: Session = Depends(get_db)):
    reports = (
        db.query(models.StudyReport)
        .filter(models.StudyReport.student_id == user_id)  # ✅ 여기
        .order_by(models.StudyReport.accuracy.asc())
        .all()
    )

    return {
        "user_id": user_id,
        "reports": [
            {
                "error_type": r.error_type,
                "total_attempts": r.total_attempts,
                "total_incorrect": r.total_incorrect,
                "accuracy": round((r.accuracy or 0) * 100, 2),
                "last_attempt_at": (
                    r.last_attempt_at.isoformat()
                    if r.last_attempt_at else None
                ),
            }
            for r in reports
        ],
    }


# =====================================================
# ② 약점 TOP N
# GET /study-reports/weak-top?user_id=1&limit=3
# =====================================================
@router.get("/weak-top")
def get_weak_top(user_id: int, limit: int = 3, db: Session = Depends(get_db)):
    reports = (
        db.query(models.StudyReport)
        .filter(models.StudyReport.student_id == user_id)  # ✅ 여기
        .order_by(models.StudyReport.accuracy.asc())
        .limit(limit)
        .all()
    )

    return {
        "user_id": user_id,
        "weak_types": [
            {
                "error_type": r.error_type,
                "accuracy": round((r.accuracy or 0) * 100, 2),
                "total_attempts": r.total_attempts,
            }
            for r in reports
        ],
    }