from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import Dict

import models


def get_student_dashboard(db: Session, user_id: int):

    reports = (
        db.query(models.StudyReport)
        .filter(models.StudyReport.student_id == user_id)
        .all()
    )

    if not reports:
        return {
            "student_id": user_id,
            "total_attempts": 0,
            "overall_accuracy": 0,
            "weakest_type": None,
            "by_type": {},
        }

    total_attempts = sum(r.total_attempts for r in reports)
    total_correct = sum(r.correct_count for r in reports)

    overall_accuracy = (
        int((total_correct / total_attempts) * 100)
        if total_attempts > 0
        else 0
    )

    by_type: Dict[str, Dict] = {}
    weakest_type = None
    lowest_accuracy = 101

    for r in reports:
        acc = int(r.accuracy * 100)

        by_type[r.question_type] = {
            "total": r.total_attempts,
            "correct": r.correct_count,
            "accuracy": acc,
        }

        if acc < lowest_accuracy:
            lowest_accuracy = acc
            weakest_type = r.question_type

    return {
        "student_id": user_id,
        "total_attempts": total_attempts,
        "overall_accuracy": overall_accuracy,
        "weakest_type": weakest_type,
        "by_type": by_type,
    }