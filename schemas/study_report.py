# schemas/study_report.py

from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime


class StudyReportByType(BaseModel):
    question_type: str
    total_attempts: int
    correct_count: int
    wrong_count: int
    accuracy: float
    last_attempt_at: Optional[datetime]

    class Config:
        from_attributes = True


class StudyReportSummary(BaseModel):
    student_id: int
    by_type: List[StudyReportByType]