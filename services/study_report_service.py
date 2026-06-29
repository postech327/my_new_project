from sqlalchemy.orm import Session
from typing import Dict, Any

import models


def get_student_study_report(
    *,
    db: Session,
    student_id: int,
) -> Dict[str, Any]:
    """
    학생 개인 StudyReport 조회
    """

    reports = (
        db.query(models.StudyReport)
        .filter(
            models.StudyReport.student_id == student_id  # ✅ 핵심 수정
        )
        .order_by(models.StudyReport.updated_at.desc())
        .all()
    )

    if not reports:
        return {
            "student_id": student_id,
            "overall": {
                "total_attempts": 0,
                "correct_count": 0,
                "wrong_count": 0,
                "accuracy": 0.0,
            },
            "by_type": [],
        }

    total_attempts = sum(r.total_attempts for r in reports)
    correct_count = sum(r.correct_count for r in reports)
    wrong_count = sum(r.wrong_count for r in reports)
    accuracy = round((correct_count / total_attempts) * 100, 2) if total_attempts else 0.0

    return {
        "student_id": student_id,
        "overall": {
            "total_attempts": total_attempts,
            "correct_count": correct_count,
            "wrong_count": wrong_count,
            "accuracy": accuracy,
        },
        "by_type": [
            {
                "question_type": r.question_type,
                "total_attempts": r.total_attempts,
                "correct_count": r.correct_count,
                "wrong_count": r.wrong_count,
                "accuracy": r.accuracy,
                "last_attempt_at": r.last_attempt_at,
            }
            for r in reports
        ],
    }