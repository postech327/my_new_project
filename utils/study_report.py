from datetime import datetime
from models import StudyReport


def update_study_report(db, student_answer):
    # 정답이거나 error_type이 없으면 누적 안 함
    if not student_answer.error_type:
        return

    report = db.query(StudyReport).filter(
        StudyReport.student_id == student_answer.user_id,
        StudyReport.error_type == student_answer.error_type,
    ).first()

    if not report:
        report = StudyReport(
            student_id=student_answer.user_id,
            error_type=student_answer.error_type,
            total_attempts=0,
            total_incorrect=0,
        )
        db.add(report)

    report.total_attempts += 1

    if not student_answer.is_correct:
        report.total_incorrect += 1

    report.accuracy = (
        (report.total_attempts - report.total_incorrect)
        / report.total_attempts
    )

    report.last_attempt_at = student_answer.created_at
    report.updated_at = datetime.utcnow()