from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from db import get_db
import models

from utils.security import require_role
from services.study_report_service import get_student_study_report
from schemas.study_report import StudyReportSummary

router = APIRouter(
    prefix="/student/study-reports",
    tags=["student_study_reports"],
)


@router.get(
    "",
    response_model=StudyReportSummary,
)
def read_my_study_report(
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_role("student")),
):
    """
    학생 개인 StudyReport 대시보드 조회
    """

    return get_student_study_report(
        db=db,
        student_id=int(current_user["sub"]),
    )