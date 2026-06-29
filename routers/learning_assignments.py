from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

import models
from db import get_db
from utils.security import require_role

router = APIRouter(tags=["learning_assignments"])

ALLOWED_CONTENT_TYPES = {"final_touch", "workbook"}
ACTIVE_STATUSES = {"assigned", "in_progress"}


class AssignmentCreateRequest(BaseModel):
    student_ids: List[int] = Field(default_factory=list)
    content_type: str = "final_touch"
    content_id: int
    title: Optional[str] = None
    teacher_message: Optional[str] = None
    due_at: Optional[datetime] = None


def _user_id(current_user: dict) -> int:
    return int(current_user["sub"])


def _content_title(record: models.AnalysisRecord) -> str:
    passage = record.passage
    source = getattr(passage, "source_title", None) or f"Final Touch #{record.id}"
    title = (record.title_ko or record.title_en or "").strip()
    return f"{source} · {title}" if title else source


def _content_source(record: models.AnalysisRecord) -> str:
    return getattr(record.passage, "source_title", None) or f"Final Touch #{record.id}"


def _folder_name(db: Session, record: models.AnalysisRecord) -> str:
    folder_id = getattr(record, "folder_id", None) or getattr(record.passage, "folder_id", None)
    if folder_id is None:
        return "미분류"
    folder = db.query(models.Folder).filter(models.Folder.id == folder_id).first()
    return folder.name if folder else "미분류"


def _get_final_touch(db: Session, content_id: int, teacher_id: int | None = None):
    query = db.query(models.AnalysisRecord).filter(models.AnalysisRecord.id == content_id)
    if teacher_id is not None:
        query = query.filter(models.AnalysisRecord.teacher_id == teacher_id)
    record = query.first()
    if not record:
        raise HTTPException(status_code=404, detail="Final Touch not found")
    return record


def _get_workbook(db: Session, content_id: int, teacher_id: int | None = None):
    query = db.query(models.Workbook).filter(models.Workbook.id == content_id)
    if teacher_id is not None:
        query = query.filter(models.Workbook.teacher_id == teacher_id)
    workbook = query.first()
    if not workbook:
        raise HTTPException(status_code=404, detail="Workbook not found")
    return workbook


def _assignment_content(db: Session, assignment: models.LearningAssignment):
    if assignment.content_type == "workbook":
        workbook = db.query(models.Workbook).filter(
            models.Workbook.id == assignment.content_id
        ).first()
        if not workbook:
            return {}
        return {
            "source_label": workbook.source_label,
            "folder_name": workbook.folder_name,
            "title_en": workbook.title,
            "title_ko": workbook.title,
            "topic_en": workbook.description,
            "topic_ko": workbook.description,
        }
    if assignment.content_type != "final_touch":
        return {}
    record = db.query(models.AnalysisRecord).filter(
        models.AnalysisRecord.id == assignment.content_id
    ).first()
    if not record:
        return {}
    return {
        "source_label": _content_source(record),
        "folder_name": _folder_name(db, record),
        "title_en": record.title_en,
        "title_ko": record.title_ko,
        "topic_en": record.topic_en,
        "topic_ko": record.topic_ko,
    }


def _serialize_assignment(db: Session, assignment: models.LearningAssignment):
    content = _assignment_content(db, assignment)
    return {
        "id": assignment.id,
        "assignment_id": assignment.id,
        "teacher_id": assignment.teacher_id,
        "student_id": assignment.student_id,
        "content_type": assignment.content_type,
        "content_id": assignment.content_id,
        "title": assignment.title,
        "teacher_message": assignment.teacher_message,
        "due_at": assignment.due_at.isoformat() if assignment.due_at else None,
        "status": assignment.status,
        "assigned_at": assignment.assigned_at.isoformat() if assignment.assigned_at else None,
        "started_at": assignment.started_at.isoformat() if assignment.started_at else None,
        "completed_at": assignment.completed_at.isoformat() if assignment.completed_at else None,
        "created_at": assignment.created_at.isoformat() if assignment.created_at else None,
        "updated_at": assignment.updated_at.isoformat() if assignment.updated_at else None,
        "teacher_name": assignment.teacher.nickname if assignment.teacher else None,
        "student_name": assignment.student.nickname if assignment.student else None,
        "source_label": content.get("source_label"),
        "folder_name": content.get("folder_name"),
        "content_summary": content,
    }


def _student_or_404(db: Session, student_id: int):
    student = db.query(models.User).filter(models.User.id == student_id).first()
    if not student:
        raise HTTPException(status_code=404, detail="Student not found")
    if student.role != "student":
        raise HTTPException(status_code=400, detail="Target user is not a student")
    return student


@router.get("/teacher/learning-assignments/students")
def list_assignable_students(
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_role("teacher")),
):
    students = (
        db.query(models.User)
        .filter(models.User.role == "student")
        .order_by(models.User.nickname.asc(), models.User.id.asc())
        .all()
    )
    return {
        "items": [
            {
                "id": student.id,
                "nickname": student.nickname,
                "email": student.email,
                "role": student.role,
            }
            for student in students
        ]
    }


@router.post("/teacher/learning-assignments")
def create_learning_assignments(
    payload: AssignmentCreateRequest,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_role("teacher")),
):
    teacher_id = _user_id(current_user)
    content_type = payload.content_type.strip().lower()
    if content_type not in ALLOWED_CONTENT_TYPES:
        raise HTTPException(status_code=400, detail="Unsupported learning content type")

    student_ids = sorted({int(sid) for sid in payload.student_ids if int(sid) > 0})
    if not student_ids:
        raise HTTPException(status_code=400, detail="student_ids is required")

    if content_type == "final_touch":
        record = _get_final_touch(db, payload.content_id, teacher_id=teacher_id)
        title = (payload.title or "").strip() or _content_title(record)
    else:
        workbook = _get_workbook(db, payload.content_id, teacher_id=teacher_id)
        title = (payload.title or "").strip() or workbook.title
    teacher_message = (payload.teacher_message or "").strip() or None

    created = []
    skipped = []

    for student_id in student_ids:
        student = _student_or_404(db, student_id)
        existing = (
            db.query(models.LearningAssignment)
            .filter(
                models.LearningAssignment.teacher_id == teacher_id,
                models.LearningAssignment.student_id == student_id,
                models.LearningAssignment.content_type == content_type,
                models.LearningAssignment.content_id == payload.content_id,
            )
            .first()
        )
        if existing:
            skipped.append(student.nickname or f"student{student_id}")
            continue

        assignment = models.LearningAssignment(
            teacher_id=teacher_id,
            student_id=student_id,
            content_type=content_type,
            content_id=payload.content_id,
            title=title,
            teacher_message=teacher_message,
            due_at=payload.due_at,
            status="assigned",
            assigned_at=datetime.utcnow(),
        )
        db.add(assignment)
        created.append(assignment)

    db.commit()
    for assignment in created:
        db.refresh(assignment)

    return {
        "created_count": len(created),
        "skipped_count": len(skipped),
        "skipped_students": skipped,
        "items": [_serialize_assignment(db, assignment) for assignment in created],
    }


@router.get("/teacher/learning-assignments")
def list_teacher_assignments(
    status: Optional[str] = Query(default=None),
    student_id: Optional[int] = Query(default=None),
    content_type: Optional[str] = Query(default=None),
    content_id: Optional[int] = Query(default=None),
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_role("teacher")),
):
    query = db.query(models.LearningAssignment).filter(
        models.LearningAssignment.teacher_id == _user_id(current_user)
    )
    if status:
        query = query.filter(models.LearningAssignment.status == status)
    if student_id:
        query = query.filter(models.LearningAssignment.student_id == student_id)
    if content_type:
        query = query.filter(models.LearningAssignment.content_type == content_type)
    if content_id:
        query = query.filter(models.LearningAssignment.content_id == content_id)
    items = query.order_by(models.LearningAssignment.assigned_at.desc()).all()
    return {"items": [_serialize_assignment(db, item) for item in items]}


@router.delete("/teacher/learning-assignments/{assignment_id}")
def cancel_teacher_assignment(
    assignment_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_role("teacher")),
):
    teacher_id = _user_id(current_user)
    assignment = (
        db.query(models.LearningAssignment)
        .filter(
            models.LearningAssignment.id == assignment_id,
            models.LearningAssignment.teacher_id == teacher_id,
        )
        .first()
    )
    if not assignment:
        raise HTTPException(status_code=404, detail="Assignment not found")
    if assignment.status == "completed":
        raise HTTPException(
            status_code=400,
            detail="Completed assignments cannot be canceled",
        )
    db.delete(assignment)
    db.commit()
    return {"message": "Assignment canceled", "assignment_id": assignment_id}


@router.get("/teacher/learning-assignments/final-touch/{final_touch_id}")
def final_touch_assignment_status(
    final_touch_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_role("teacher")),
):
    teacher_id = _user_id(current_user)
    _get_final_touch(db, final_touch_id, teacher_id=teacher_id)
    items = (
        db.query(models.LearningAssignment)
        .filter(
            models.LearningAssignment.teacher_id == teacher_id,
            models.LearningAssignment.content_type == "final_touch",
            models.LearningAssignment.content_id == final_touch_id,
        )
        .order_by(models.LearningAssignment.assigned_at.desc())
        .all()
    )
    counts = {"assigned": 0, "in_progress": 0, "completed": 0, "overdue": 0}
    now = datetime.utcnow()
    serialized = []
    for item in items:
        data = _serialize_assignment(db, item)
        display_status = item.status
        if item.status != "completed" and item.due_at and item.due_at < now:
            display_status = "overdue"
        counts[display_status] = counts.get(display_status, 0) + 1
        data["display_status"] = display_status
        serialized.append(data)
    return {"total": len(items), "counts": counts, "items": serialized}


@router.get("/student/learning-assignments")
def list_student_assignments(
    status: Optional[str] = Query(default=None),
    content_type: Optional[str] = Query(default=None),
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_role("student")),
):
    query = db.query(models.LearningAssignment).filter(
        models.LearningAssignment.student_id == _user_id(current_user)
    )
    if status:
        query = query.filter(models.LearningAssignment.status == status)
    if content_type:
        query = query.filter(models.LearningAssignment.content_type == content_type)
    items = query.all()
    status_order = {"assigned": 0, "in_progress": 1, "completed": 2}

    def sort_key(item: models.LearningAssignment):
        due_sort = item.due_at or datetime.max
        assigned_ts = item.assigned_at.timestamp() if item.assigned_at else 0
        return (status_order.get(item.status, 9), due_sort, -assigned_ts)

    items.sort(key=sort_key)
    return {"items": [_serialize_assignment(db, item) for item in items]}


def _student_assignment(db: Session, assignment_id: int, student_id: int):
    assignment = (
        db.query(models.LearningAssignment)
        .filter(
            models.LearningAssignment.id == assignment_id,
            models.LearningAssignment.student_id == student_id,
        )
        .first()
    )
    if not assignment:
        raise HTTPException(status_code=404, detail="Assignment not found")
    return assignment


@router.post("/student/learning-assignments/{assignment_id}/start")
def start_student_assignment(
    assignment_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_role("student")),
):
    assignment = _student_assignment(db, assignment_id, _user_id(current_user))
    if assignment.status == "assigned":
        assignment.status = "in_progress"
        assignment.started_at = assignment.started_at or datetime.utcnow()
        assignment.updated_at = datetime.utcnow()
        db.commit()
        db.refresh(assignment)
    return _serialize_assignment(db, assignment)


@router.post("/student/learning-assignments/{assignment_id}/complete")
def complete_student_assignment(
    assignment_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_role("student")),
):
    assignment = _student_assignment(db, assignment_id, _user_id(current_user))
    if assignment.status != "completed":
        now = datetime.utcnow()
        assignment.status = "completed"
        assignment.started_at = assignment.started_at or now
        assignment.completed_at = now
        assignment.updated_at = now
        db.commit()
        db.refresh(assignment)
    return _serialize_assignment(db, assignment)


@router.get("/student/learning-assignments/{assignment_id}")
def get_student_assignment(
    assignment_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_role("student")),
):
    assignment = _student_assignment(db, assignment_id, _user_id(current_user))
    return _serialize_assignment(db, assignment)
