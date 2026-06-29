from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from models import Class, ClassStudent, User
from db import get_db
from dependencies import get_current_user

router = APIRouter(prefix="/student/classes", tags=["Student Classes"])


@router.post("/join")
def join_class(
    join_code: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # 학생만 가능
    if current_user.role != "student":
        raise HTTPException(status_code=403, detail="Only students can join classes")

    class_obj = db.query(Class).filter(Class.join_code == join_code).first()
    if not class_obj:
        raise HTTPException(status_code=404, detail="Class not found")

    existing = db.query(ClassStudent).filter(
        ClassStudent.class_id == class_obj.id,
        ClassStudent.student_id == current_user.id,
    ).first()

    if existing:
        raise HTTPException(status_code=400, detail="Already joined")

    new_join = ClassStudent(
        class_id=class_obj.id,
        student_id=current_user.id,
    )

    db.add(new_join)
    db.commit()

    return {"message": "Joined successfully"}