# routers/teacher_exam_assignments.py

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from db import get_db
import models
from utils.security import require_role

router = APIRouter(
    prefix="/teacher/assignments",
    tags=["teacher_assignments"],
)


@router.post("")
def assign_problem_set_to_student(
    *,
    student_id: int,
    problem_set_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_role("teacher")),
):
    """
    STEP 10
    교사가 ProblemSet을 학생에게 배정
    """

    # 1️⃣ 학생 존재 확인
    student = (
        db.query(models.User)
        .filter(models.User.id == student_id)
        .first()
    )
    if not student:
        raise HTTPException(status_code=404, detail="Student not found")

    if student.role != "student":
        raise HTTPException(status_code=400, detail="Target user is not a student")

    # 2️⃣ ProblemSet 존재 확인
    problem_set = (
        db.query(models.ProblemSet)
        .filter(models.ProblemSet.id == problem_set_id)
        .first()
    )
    if not problem_set:
        raise HTTPException(status_code=404, detail="ProblemSet not found")

    # 3️⃣ 중복 배정 방지
    existing = (
        db.query(models.ExamAssignment)
        .filter(
            models.ExamAssignment.user_id == student_id,
            models.ExamAssignment.problem_set_id == problem_set_id,
        )
        .first()
    )
    if existing:
        raise HTTPException(status_code=400, detail="Already assigned")

    # 4️⃣ ExamAssignment 생성
    assignment = models.ExamAssignment(
        user_id=student_id,
        problem_set_id=problem_set_id,
    )

    db.add(assignment)
    db.commit()
    db.refresh(assignment)

    # 5️⃣ 응답
    return {
        "ok": True,
        "assignment": {
            "id": assignment.id,
            "student_id": student_id,
            "problem_set_id": problem_set_id,
        },
    }
