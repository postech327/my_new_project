from pydantic import BaseModel
from typing import Dict


class TypeStatsOut(BaseModel):
    total: int
    correct: int
    accuracy: int


class StudentDashboardOut(BaseModel):
    student_id: int
    total_attempts: int
    overall_accuracy: int
    weakest_type: str | None
    by_type: Dict[str, TypeStatsOut]