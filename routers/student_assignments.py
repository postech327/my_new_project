# routers/student_assignments.py

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from db import get_db
import models
from utils.auth_jwt import get_current_user

router = APIRouter(
    prefix="/student",
    tags=["student_assignments"],
)

# =====================================================
# STEP 11-A
# 학생이 배정받은 ProblemSet 목록 조회
# =====================================================
@router.get("/assignments")
def get_my_assignments(
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    # 1️⃣ 학생만 접근 가능
    if current_user["role"] != "student":
        return {"detail": "Only students can access this endpoint"}

    student_id = int(current_user["sub"])

    # 2️⃣ ExamAssignment 조회
    assignments = (
        db.query(models.ExamAssignment)
        .filter(models.ExamAssignment.user_id == student_id)
        .all()
    )

    # 3️⃣ 응답 정리
    result = []
    for a in assignments:
        result.append(
            {
                "assignment_id": a.id,
                "problem_set_id": a.problem_set.id,
                "problem_set_name": a.problem_set.name,
                "is_completed": a.is_completed,
            }
        )

    return {
        "ok": True,
        "assignments": result,
    }
