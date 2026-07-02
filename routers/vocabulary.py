from __future__ import annotations

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

import models
from db import get_db
from utils.security import require_role

router = APIRouter(tags=["vocabulary"])

VALID_STATUSES = {"draft", "published", "archived"}


class VocabularySetCreate(BaseModel):
    title: str
    description: Optional[str] = None
    source_type: Optional[str] = None
    source_label: Optional[str] = None
    grade_label: Optional[str] = None
    unit_label: Optional[str] = None
    status: str = "draft"


class VocabularySetUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    source_type: Optional[str] = None
    source_label: Optional[str] = None
    grade_label: Optional[str] = None
    unit_label: Optional[str] = None
    status: Optional[str] = None


class VocabularyItemIn(BaseModel):
    word: str
    meaning_ko: str
    example_sentence: Optional[str] = None
    synonym: Optional[str] = None
    antonym: Optional[str] = None
    note: Optional[str] = None


class VocabularyBulkItemsIn(BaseModel):
    replace: bool = True
    items: list[VocabularyItemIn] = Field(default_factory=list)


class VocabularyAnswerIn(BaseModel):
    item_id: int
    student_answer: Optional[str] = None


class VocabularyAttemptIn(BaseModel):
    set_id: int
    mode: str = "meaning_quiz"
    answers: list[VocabularyAnswerIn] = Field(default_factory=list)


class VocabularyAssignIn(BaseModel):
    student_ids: list[int] = Field(default_factory=list)


def _user_id(current_user: dict) -> int:
    return int(current_user["sub"])


def _clean(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    text = value.strip()
    return text or None


def _validate_status(status: str) -> str:
    if status not in VALID_STATUSES:
        raise HTTPException(status_code=400, detail="Invalid vocabulary status")
    return status


def _teacher_set_or_404(db: Session, set_id: int, teacher_id: int):
    item = (
        db.query(models.VocabularySet)
        .filter(
            models.VocabularySet.id == set_id,
            models.VocabularySet.created_by == teacher_id,
        )
        .first()
    )
    if not item:
        raise HTTPException(status_code=404, detail="Vocabulary set not found")
    return item


def _published_set_or_404(db: Session, set_id: int):
    item = (
        db.query(models.VocabularySet)
        .filter(
            models.VocabularySet.id == set_id,
            models.VocabularySet.status == "published",
        )
        .first()
    )
    if not item:
        raise HTTPException(status_code=404, detail="Vocabulary set not found")
    return item


def _serialize_item(item: models.VocabularyItem):
    return {
        "id": item.id,
        "item_id": item.id,
        "set_id": item.set_id,
        "word": item.word,
        "meaning_ko": item.meaning_ko,
        "example_sentence": item.example_sentence,
        "synonym": item.synonym,
        "antonym": item.antonym,
        "note": item.note,
        "order_index": item.order_index,
        "created_at": item.created_at.isoformat() if item.created_at else None,
        "updated_at": item.updated_at.isoformat() if item.updated_at else None,
    }


def _serialize_set(item: models.VocabularySet, include_items: bool = False):
    data = {
        "id": item.id,
        "set_id": item.id,
        "title": item.title,
        "description": item.description,
        "source_type": item.source_type,
        "source_label": item.source_label,
        "grade_label": item.grade_label,
        "unit_label": item.unit_label,
        "status": item.status,
        "created_by": item.created_by,
        "item_count": len(item.items or []),
        "created_at": item.created_at.isoformat() if item.created_at else None,
        "updated_at": item.updated_at.isoformat() if item.updated_at else None,
    }
    if include_items:
        data["items"] = [_serialize_item(vocabulary_item) for vocabulary_item in item.items]
    return data


def _vocabulary_assignment(
    db: Session,
    set_id: int,
    student_id: int,
):
    return (
        db.query(models.LearningAssignment)
        .filter(
            models.LearningAssignment.student_id == student_id,
            models.LearningAssignment.content_type == "vocabulary_set",
            models.LearningAssignment.content_id == set_id,
        )
        .first()
    )


def _serialize_assignment(assignment: models.LearningAssignment):
    return {
        "id": assignment.id,
        "assignment_id": assignment.id,
        "student_id": assignment.student_id,
        "student_username": assignment.student.nickname if assignment.student else None,
        "student_email": assignment.student.email if assignment.student else None,
        "status": assignment.status,
        "assigned_at": assignment.assigned_at.isoformat()
        if assignment.assigned_at
        else None,
    }


@router.get("/teacher/vocabulary-sets")
def list_teacher_vocabulary_sets(
    status: Optional[str] = None,
    search: Optional[str] = Query(default=None),
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_role("teacher")),
):
    query = db.query(models.VocabularySet).filter(
        models.VocabularySet.created_by == _user_id(current_user)
    )
    if status and status != "all":
        query = query.filter(models.VocabularySet.status == _validate_status(status))
    if search and search.strip():
        query = query.filter(models.VocabularySet.title.ilike(f"%{search.strip()}%"))
    items = query.order_by(models.VocabularySet.created_at.desc()).all()
    return {"items": [_serialize_set(item) for item in items]}


@router.post("/teacher/vocabulary-sets")
def create_teacher_vocabulary_set(
    payload: VocabularySetCreate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_role("teacher")),
):
    title = payload.title.strip()
    if not title:
        raise HTTPException(status_code=400, detail="Title is required")
    item = models.VocabularySet(
        title=title,
        description=_clean(payload.description),
        source_type=_clean(payload.source_type),
        source_label=_clean(payload.source_label),
        grade_label=_clean(payload.grade_label),
        unit_label=_clean(payload.unit_label),
        status=_validate_status(payload.status),
        created_by=_user_id(current_user),
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return _serialize_set(item, include_items=True)


@router.get("/teacher/vocabulary-sets/{set_id}")
def get_teacher_vocabulary_set(
    set_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_role("teacher")),
):
    return _serialize_set(
        _teacher_set_or_404(db, set_id, _user_id(current_user)),
        include_items=True,
    )


@router.patch("/teacher/vocabulary-sets/{set_id}")
def update_teacher_vocabulary_set(
    set_id: int,
    payload: VocabularySetUpdate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_role("teacher")),
):
    item = _teacher_set_or_404(db, set_id, _user_id(current_user))
    values = payload.model_dump(exclude_unset=True)
    if "title" in values:
        title = (values["title"] or "").strip()
        if not title:
            raise HTTPException(status_code=400, detail="Title is required")
        item.title = title
    for field in (
        "description",
        "source_type",
        "source_label",
        "grade_label",
        "unit_label",
    ):
        if field in values:
            setattr(item, field, _clean(values[field]))
    if "status" in values and values["status"] is not None:
        item.status = _validate_status(values["status"])
    item.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(item)
    return _serialize_set(item, include_items=True)


@router.delete("/teacher/vocabulary-sets/{set_id}")
def delete_teacher_vocabulary_set(
    set_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_role("teacher")),
):
    item = _teacher_set_or_404(db, set_id, _user_id(current_user))
    if item.attempts:
        raise HTTPException(
            status_code=409,
            detail="Attempts exist; archive this vocabulary set instead",
        )
    db.delete(item)
    db.commit()
    return {"message": "Vocabulary set deleted", "set_id": set_id}


@router.post("/teacher/vocabulary-sets/{set_id}/items/bulk")
def bulk_save_vocabulary_items(
    set_id: int,
    payload: VocabularyBulkItemsIn,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_role("teacher")),
):
    vocabulary_set = _teacher_set_or_404(db, set_id, _user_id(current_user))
    valid_items = [
        item
        for item in payload.items
        if item.word.strip() and item.meaning_ko.strip()
    ]
    if payload.replace:
        vocabulary_set.items.clear()
        db.flush()
        start_index = 1
    else:
        start_index = len(vocabulary_set.items) + 1
    for offset, item in enumerate(valid_items):
        vocabulary_set.items.append(
            models.VocabularyItem(
                word=item.word.strip(),
                meaning_ko=item.meaning_ko.strip(),
                example_sentence=_clean(item.example_sentence),
                synonym=_clean(item.synonym),
                antonym=_clean(item.antonym),
                note=_clean(item.note),
                order_index=start_index + offset,
            )
        )
    vocabulary_set.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(vocabulary_set)
    return _serialize_set(vocabulary_set, include_items=True)


@router.post("/teacher/vocabulary-sets/{set_id}/assign")
def assign_vocabulary_set(
    set_id: int,
    payload: VocabularyAssignIn,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_role("teacher")),
):
    teacher_id = _user_id(current_user)
    vocabulary_set = _teacher_set_or_404(db, set_id, teacher_id)
    if vocabulary_set.status != "published":
        raise HTTPException(
            status_code=400,
            detail="Only published vocabulary sets can be assigned",
        )
    student_ids = sorted({student_id for student_id in payload.student_ids if student_id > 0})
    if not student_ids:
        raise HTTPException(status_code=400, detail="student_ids is required")

    created = []
    skipped_count = 0
    for student_id in student_ids:
        student = (
            db.query(models.User)
            .filter(models.User.id == student_id, models.User.role == "student")
            .first()
        )
        if not student:
            raise HTTPException(status_code=400, detail=f"Invalid student: {student_id}")
        existing = (
            db.query(models.LearningAssignment)
            .filter(
                models.LearningAssignment.teacher_id == teacher_id,
                models.LearningAssignment.student_id == student_id,
                models.LearningAssignment.content_type == "vocabulary_set",
                models.LearningAssignment.content_id == set_id,
            )
            .first()
        )
        if existing:
            skipped_count += 1
            continue
        assignment = models.LearningAssignment(
            teacher_id=teacher_id,
            student_id=student_id,
            content_type="vocabulary_set",
            content_id=set_id,
            title=vocabulary_set.title,
            status="assigned",
            assigned_at=datetime.utcnow(),
        )
        db.add(assignment)
        created.append(assignment)
    db.commit()
    for assignment in created:
        db.refresh(assignment)
    return {
        "assigned_count": len(created),
        "skipped_count": skipped_count,
        "assignments": [_serialize_assignment(item) for item in created],
    }


@router.get("/teacher/vocabulary-sets/{set_id}/assignments")
def list_vocabulary_assignments(
    set_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_role("teacher")),
):
    teacher_id = _user_id(current_user)
    _teacher_set_or_404(db, set_id, teacher_id)
    items = (
        db.query(models.LearningAssignment)
        .filter(
            models.LearningAssignment.teacher_id == teacher_id,
            models.LearningAssignment.content_type == "vocabulary_set",
            models.LearningAssignment.content_id == set_id,
        )
        .order_by(models.LearningAssignment.assigned_at.desc())
        .all()
    )
    return {"items": [_serialize_assignment(item) for item in items]}


@router.get("/student/vocabulary-sets")
def list_student_vocabulary_sets(
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_role("student")),
):
    student_id = _user_id(current_user)
    assigned_set_ids = (
        db.query(models.LearningAssignment.content_id)
        .filter(
            models.LearningAssignment.student_id == student_id,
            models.LearningAssignment.content_type == "vocabulary_set",
        )
    )
    items = (
        db.query(models.VocabularySet)
        .filter(
            models.VocabularySet.status == "published",
            models.VocabularySet.id.in_(assigned_set_ids),
        )
        .order_by(models.VocabularySet.created_at.desc())
        .all()
    )
    return {"items": [_serialize_set(item) for item in items]}


@router.get("/student/vocabulary-sets/{set_id}")
def get_student_vocabulary_set(
    set_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_role("student")),
):
    vocabulary_set = _published_set_or_404(db, set_id)
    if not _vocabulary_assignment(db, set_id, _user_id(current_user)):
        raise HTTPException(status_code=404, detail="Vocabulary set not assigned")
    return _serialize_set(vocabulary_set, include_items=True)


@router.post("/student/vocabulary-attempts/submit")
def submit_vocabulary_attempt(
    payload: VocabularyAttemptIn,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_role("student")),
):
    student_id = _user_id(current_user)
    vocabulary_set = _published_set_or_404(db, payload.set_id)
    assignment = _vocabulary_assignment(db, payload.set_id, student_id)
    if not assignment:
        raise HTTPException(status_code=403, detail="Vocabulary set not assigned")
    item_by_id = {item.id: item for item in vocabulary_set.items}
    answers = []
    seen_item_ids = set()
    for answer in payload.answers:
        item = item_by_id.get(answer.item_id)
        if item is None or item.id in seen_item_ids:
            continue
        seen_item_ids.add(item.id)
        student_answer = (answer.student_answer or "").strip()
        correct_answer = item.meaning_ko.strip()
        answers.append(
            {
                "item": item,
                "student_answer": student_answer,
                "correct_answer": correct_answer,
                "is_correct": student_answer == correct_answer,
            }
        )
    total = len(answers)
    correct = sum(1 for answer in answers if answer["is_correct"])
    attempt = models.VocabularyAttempt(
        student_id=student_id,
        set_id=vocabulary_set.id,
        mode=payload.mode,
        total_count=total,
        correct_count=correct,
        score=round((correct / total * 100) if total else 0, 1),
    )
    db.add(attempt)
    db.flush()
    for answer in answers:
        db.add(
            models.VocabularyAttemptAnswer(
                attempt_id=attempt.id,
                item_id=answer["item"].id,
                student_answer=answer["student_answer"],
                correct_answer=answer["correct_answer"],
                is_correct=answer["is_correct"],
            )
        )
    db.commit()
    db.refresh(attempt)
    if assignment.status != "completed":
        assignment.status = "completed"
        assignment.started_at = assignment.started_at or datetime.utcnow()
        assignment.completed_at = datetime.utcnow()
        assignment.updated_at = datetime.utcnow()
        db.commit()
    return {
        "attempt_id": attempt.id,
        "set_id": attempt.set_id,
        "mode": attempt.mode,
        "score": attempt.score,
        "total_count": attempt.total_count,
        "correct_count": attempt.correct_count,
        "created_at": attempt.created_at.isoformat() if attempt.created_at else None,
        "results": [
            {
                "item_id": answer["item"].id,
                "word": answer["item"].word,
                "student_answer": answer["student_answer"],
                "correct_answer": answer["correct_answer"],
                "is_correct": answer["is_correct"],
            }
            for answer in answers
        ],
    }


@router.get("/student/vocabulary-attempts")
def list_student_vocabulary_attempts(
    set_id: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_role("student")),
):
    query = db.query(models.VocabularyAttempt).filter(
        models.VocabularyAttempt.student_id == _user_id(current_user)
    )
    if set_id is not None:
        query = query.filter(models.VocabularyAttempt.set_id == set_id)
    attempts = query.order_by(models.VocabularyAttempt.created_at.desc()).all()
    return {
        "items": [
            {
                "attempt_id": attempt.id,
                "set_id": attempt.set_id,
                "mode": attempt.mode,
                "total_count": attempt.total_count,
                "correct_count": attempt.correct_count,
                "score": attempt.score,
                "created_at": attempt.created_at.isoformat()
                if attempt.created_at
                else None,
            }
            for attempt in attempts
        ]
    }
