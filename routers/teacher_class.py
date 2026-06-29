from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List

from models import Class, ClassStudent, User
from db import get_db
from dependencies import get_current_user
from schemas.user_schema import StudentResponse
from models import ProblemSet, ExamAssignment


router = APIRouter(
    prefix="/teacher/classes",
    tags=["Teacher Classes"]
)


@router.get(
    "/{class_id}/students",
    response_model=List[StudentResponse],
)
def get_class_students(
    class_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # 🔥 1️⃣ 교사 권한 확인
    if current_user.role != "teacher":
        raise HTTPException(status_code=403, detail="Only teachers allowed")

    # 🔥 2️⃣ 클래스 존재 확인
    class_obj = db.query(Class).filter(Class.id == class_id).first()
    if not class_obj:
        raise HTTPException(status_code=404, detail="Class not found")

    # 🔥 3️⃣ 자기 클래스인지 확인 (보안 핵심)
    if class_obj.teacher_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not your class")

    # 🔥 4️⃣ 학생 목록 조회
    students = (
        db.query(User)
        .join(ClassStudent, ClassStudent.student_id == User.id)
        .filter(ClassStudent.class_id == class_id)
        .all()
    )

    return students

@router.post("/{class_id}/assign/{problem_set_id}")
def assign_problem_set_to_class(
    class_id: int,
    problem_set_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # 1️⃣ 교사 권한 확인
    if current_user.role != "teacher":
        raise HTTPException(status_code=403, detail="Only teachers allowed")

    # 2️⃣ 클래스 확인
    class_obj = db.query(Class).filter(Class.id == class_id).first()
    if not class_obj:
        raise HTTPException(status_code=404, detail="Class not found")

    if class_obj.teacher_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not your class")

    # 3️⃣ ProblemSet 확인
    problem_set = db.query(ProblemSet).filter(ProblemSet.id == problem_set_id).first()
    if not problem_set:
        raise HTTPException(status_code=404, detail="ProblemSet not found")

    # 4️⃣ 클래스 학생 조회
    students = (
        db.query(User)
        .join(ClassStudent, ClassStudent.student_id == User.id)
        .filter(ClassStudent.class_id == class_id)
        .all()
    )

    if not students:
        raise HTTPException(status_code=400, detail="No students in class")

    # 5️⃣ 각 학생에게 시험 배정
    created_count = 0

    for student in students:
        existing = db.query(ExamAssignment).filter(
            ExamAssignment.user_id == student.id,
            ExamAssignment.problem_set_id == problem_set_id,
        ).first()

        if not existing:
            assignment = ExamAssignment(
                user_id=student.id,
                problem_set_id=problem_set_id,
            )
            db.add(assignment)
            created_count += 1

    db.commit()

    return {
        "message": "ProblemSet assigned to class",
        "assigned_count": created_count
    }