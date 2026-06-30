from __future__ import annotations

from datetime import datetime
from typing import Any, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlalchemy.orm import Session, object_session

import models
from db import get_db
from utils.security import require_role

router = APIRouter(prefix="/teacher/workbooks", tags=["teacher_workbooks"])

ALLOWED_WORKBOOK_STATUSES = {"draft", "published", "archived"}
ALLOWED_QUESTION_TYPES = {
    "multiple_choice",
    "check_learning",
    "true_false",
    "inline_choice",
    "check_learning_set",
    "initial_blank",
    "sentence_insertion",
    "paragraph_order",
}


class WorkbookCreateRequest(BaseModel):
    title: str
    description: Optional[str] = None
    final_touch_id: Optional[int] = None
    source_label: Optional[str] = None
    folder_name: Optional[str] = None
    unit_label: Optional[str] = None


class WorkbookUpdateRequest(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    source_label: Optional[str] = None
    folder_name: Optional[str] = None
    unit_label: Optional[str] = None
    status: Optional[str] = None


class WorkbookQuestionRequest(BaseModel):
    question_type: str
    prompt: str
    section_id: Optional[int] = None
    section_key: Optional[str] = None
    section_title: Optional[str] = None
    passage_text: Optional[str] = None
    choices: Optional[List[str]] = None
    answer: dict[str, Any] = Field(default_factory=dict)
    explanation: Optional[str] = None
    points: int = 1


class WorkbookQuestionUpdateRequest(BaseModel):
    prompt: Optional[str] = None
    section_id: Optional[int] = None
    section_key: Optional[str] = None
    section_title: Optional[str] = None
    passage_text: Optional[str] = None
    choices: Optional[List[str]] = None
    answer: Optional[dict[str, Any]] = None
    explanation: Optional[str] = None
    points: Optional[int] = None


class WorkbookSectionRequest(BaseModel):
    title: str
    source_label: Optional[str] = None
    unit_label: Optional[str] = None
    section_key: Optional[str] = None
    sort_order: Optional[int] = None


class WorkbookSectionUpdateRequest(BaseModel):
    title: Optional[str] = None
    sort_order: Optional[int] = None
    source_label: Optional[str] = None
    unit_label: Optional[str] = None
    section_key: Optional[str] = None


class WorkbookReorderRequest(BaseModel):
    question_ids: List[int] = Field(default_factory=list)


def _user_id(current_user: dict) -> int:
    return int(current_user["sub"])


def _clean_optional(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    text = value.strip()
    return text or None


def _teacher_workbook_or_404(db: Session, workbook_id: int, teacher_id: int):
    workbook = (
        db.query(models.Workbook)
        .filter(
            models.Workbook.id == workbook_id,
            models.Workbook.teacher_id == teacher_id,
        )
        .first()
    )
    if not workbook:
        raise HTTPException(status_code=404, detail="Workbook not found")
    return workbook


def _question_or_404(db: Session, workbook: models.Workbook, question_id: int):
    question = (
        db.query(models.WorkbookQuestion)
        .filter(
            models.WorkbookQuestion.id == question_id,
            models.WorkbookQuestion.workbook_id == workbook.id,
        )
        .first()
    )
    if not question:
        raise HTTPException(status_code=404, detail="Workbook question not found")
    return question


def _section_or_404(db: Session, workbook: models.Workbook, section_id: int):
    section = (
        db.query(models.WorkbookSection)
        .filter(
            models.WorkbookSection.id == section_id,
            models.WorkbookSection.workbook_id == workbook.id,
        )
        .first()
    )
    if not section:
        raise HTTPException(status_code=404, detail="Workbook section not found")
    return section


def _next_section_order(db: Session, workbook_id: int) -> int:
    max_order = (
        db.query(func.max(models.WorkbookSection.sort_order))
        .filter(models.WorkbookSection.workbook_id == workbook_id)
        .scalar()
    )
    return int(max_order or 0) + 1


def _section_sort_value(section_key: Optional[str], fallback: int = 9990) -> int:
    key = (section_key or "").strip().lower()
    if key.startswith("unit_"):
        try:
            return int(key.split("_", 1)[1])
        except (IndexError, ValueError):
            return fallback
    if key == "test":
        return 9000
    if key == "unclassified":
        return 9999
    return fallback


def _get_or_create_section(
    db: Session,
    workbook: models.Workbook,
    *,
    section_id: Optional[int] = None,
    section_key: Optional[str] = None,
    section_title: Optional[str] = None,
):
    if section_id is not None:
        return _section_or_404(db, workbook, section_id)
    key = _clean_optional(section_key)
    if not key:
        return None
    existing = (
        db.query(models.WorkbookSection)
        .filter(
            models.WorkbookSection.workbook_id == workbook.id,
            models.WorkbookSection.section_key == key,
        )
        .first()
    )
    if existing:
        return existing
    title = _clean_optional(section_title) or key
    section = models.WorkbookSection(
        workbook_id=workbook.id,
        title=title,
        source_label=workbook.source_label,
        unit_label=title,
        section_key=key,
        sort_order=_section_sort_value(key, _next_section_order(db, workbook.id)),
    )
    db.add(section)
    db.flush()
    return section


def _validate_final_touch(db: Session, final_touch_id: Optional[int], teacher_id: int):
    if not final_touch_id:
        return
    exists = (
        db.query(models.AnalysisRecord.id)
        .filter(
            models.AnalysisRecord.id == final_touch_id,
            models.AnalysisRecord.teacher_id == teacher_id,
        )
        .first()
    )
    if not exists:
        raise HTTPException(status_code=404, detail="Final Touch not found")


def _validate_question_payload(
    question_type: str,
    prompt: str,
    choices: Optional[List[str]],
    answer: dict[str, Any],
) -> tuple[str, list[str] | None, dict[str, Any]]:
    qtype = question_type.strip().lower()
    if qtype not in ALLOWED_QUESTION_TYPES:
        raise HTTPException(status_code=400, detail="Unsupported workbook question_type")
    if not prompt.strip():
        raise HTTPException(status_code=400, detail="prompt is required")

    if qtype == "inline_choice":
        items = answer.get("items")
        if not isinstance(items, list) or not items:
            raise HTTPException(status_code=400, detail="inline_choice requires items")
        for index, item in enumerate(items, start=1):
            if not isinstance(item, dict):
                raise HTTPException(status_code=400, detail=f"inline_choice item {index} is invalid")
            item_choices = item.get("choices")
            if not isinstance(item_choices, list) or len(item_choices) < 2:
                raise HTTPException(status_code=400, detail=f"inline_choice item {index} requires choices")
            answer_index = item.get("answer_index")
            if isinstance(answer_index, str):
                answer_index = int(answer_index) if answer_index.isdigit() else None
            if not isinstance(answer_index, int) or answer_index < 0 or answer_index >= len(item_choices):
                raise HTTPException(status_code=400, detail=f"inline_choice item {index} answer_index is invalid")
            item["answer_index"] = answer_index
        return qtype, None, answer

    if qtype == "check_learning_set":
        # TODO: HWP-first workbook import will populate structured A/B/C
        # sections here. Excel import is a lower-priority path and should
        # reuse the same JSON contract later.
        return qtype, None, answer

    if qtype == "initial_blank":
        items = answer.get("items")
        if not isinstance(items, list) or not items:
            raise HTTPException(status_code=400, detail="initial_blank requires items")
        for index, item in enumerate(items, start=1):
            if not isinstance(item, dict):
                raise HTTPException(status_code=400, detail=f"initial_blank item {index} is invalid")
            if not str(item.get("label") or "").strip():
                raise HTTPException(status_code=400, detail=f"initial_blank item {index} requires label")
            if not str(item.get("answer") or "").strip():
                raise HTTPException(status_code=400, detail=f"initial_blank item {index} requires answer")
        return qtype, None, answer

    if qtype == "sentence_insertion":
        if not str(answer.get("insert_sentence") or "").strip():
            raise HTTPException(status_code=400, detail="sentence_insertion requires insert_sentence")
        if not str(answer.get("answer") or "").strip():
            raise HTTPException(status_code=400, detail="sentence_insertion requires answer")
        return qtype, None, answer

    if qtype == "paragraph_order":
        segments = answer.get("segments")
        order = answer.get("answer_order")
        if not isinstance(segments, list) or len(segments) < 3:
            raise HTTPException(status_code=400, detail="paragraph_order requires A/B/C segments")
        if not isinstance(order, list) or len(order) != 3:
            raise HTTPException(status_code=400, detail="paragraph_order requires answer_order")
        normalized = [str(item).strip().upper() for item in order]
        if sorted(normalized) != ["A", "B", "C"]:
            raise HTTPException(status_code=400, detail="paragraph_order answer_order must contain A, B, C")
        answer["answer_order"] = normalized
        return qtype, None, answer

    if qtype == "multiple_choice":
        clean_choices = [c.strip() for c in (choices or []) if c and c.strip()]
        if len(clean_choices) < 2:
            raise HTTPException(
                status_code=400,
                detail="multiple_choice requires at least two choices",
            )
        answer_index = answer.get("answer_index")
        if isinstance(answer_index, str):
            answer_index = int(answer_index) if answer_index.isdigit() else None
        if not isinstance(answer_index, int):
            raise HTTPException(status_code=400, detail="answer_index is required")
        if answer_index < 0 or answer_index >= len(clean_choices):
            raise HTTPException(status_code=400, detail="answer_index is out of range")
        return qtype, clean_choices, {"answer_index": answer_index}

    if qtype == "check_learning":
        answer_text = str(answer.get("answer_text") or "").strip()
        if not answer_text:
            raise HTTPException(status_code=400, detail="answer_text is required")
        return qtype, None, {"answer_text": answer_text}

    if isinstance(answer.get("items"), list):
        subtype = str(answer.get("subtype") or "").strip()
        if subtype and subtype not in {"true_false_en", "true_false_ko"}:
            raise HTTPException(status_code=400, detail="Unsupported true_false subtype")
        for index, item in enumerate(answer["items"], start=1):
            if not isinstance(item, dict):
                raise HTTPException(status_code=400, detail=f"true_false item {index} is invalid")
            raw_item_answer = item.get("answer")
            if isinstance(raw_item_answer, str):
                lowered = raw_item_answer.strip().lower()
                raw_item_answer = lowered in {"true", "t", "1", "o", "yes"}
            if not isinstance(raw_item_answer, bool):
                raise HTTPException(status_code=400, detail=f"true_false item {index} answer must be boolean")
            item["answer"] = raw_item_answer
        return qtype, None, answer

    raw = answer.get("answer")
    if isinstance(raw, str):
        lowered = raw.strip().lower()
        raw = lowered in {"true", "t", "1", "o", "맞음", "yes"}
    if not isinstance(raw, bool):
        raise HTTPException(status_code=400, detail="true_false answer must be boolean")
    return qtype, None, {"answer": raw}


def _serialize_question(question: models.WorkbookQuestion):
    answer = question.answer_json or {}
    return {
        "id": question.id,
        "question_id": question.id,
        "workbook_id": question.workbook_id,
        "section_id": question.section_id,
        "question_type": question.question_type,
        "order_index": question.order_index,
        "prompt": question.prompt,
        "passage_text": question.passage_text,
        "choices": question.choices_json or [],
        "answer": answer,
        "content": answer,
        "explanation": question.explanation,
        "points": question.points,
        "created_at": question.created_at.isoformat() if question.created_at else None,
        "updated_at": question.updated_at.isoformat() if question.updated_at else None,
    }


def _serialize_section(section: models.WorkbookSection, question_count: int = 0):
    return {
        "id": section.id,
        "section_id": section.id,
        "workbook_id": section.workbook_id,
        "title": section.title,
        "source_label": section.source_label,
        "unit_label": section.unit_label,
        "section_key": section.section_key,
        "sort_order": section.sort_order,
        "question_count": question_count,
        "created_at": section.created_at.isoformat() if section.created_at else None,
        "updated_at": section.updated_at.isoformat() if section.updated_at else None,
    }


def _section_counts(db: Session, workbook_id: int) -> dict[int, int]:
    rows = (
        db.query(models.WorkbookQuestion.section_id, func.count(models.WorkbookQuestion.id))
        .filter(
            models.WorkbookQuestion.workbook_id == workbook_id,
            models.WorkbookQuestion.section_id.isnot(None),
        )
        .group_by(models.WorkbookQuestion.section_id)
        .all()
    )
    return {int(section_id): int(count) for section_id, count in rows if section_id is not None}


def _serialized_sections_for_workbook(db: Session, workbook: models.Workbook):
    counts = _section_counts(db, workbook.id)
    sections = sorted(
        workbook.sections or [],
        key=lambda item: (item.sort_order or 0, item.id),
    )
    return [_serialize_section(section, counts.get(section.id, 0)) for section in sections]


def _serialize_workbook(workbook: models.Workbook, include_questions: bool = False):
    data = {
        "id": workbook.id,
        "workbook_id": workbook.id,
        "teacher_id": workbook.teacher_id,
        "title": workbook.title,
        "description": workbook.description,
        "source_label": workbook.source_label,
        "folder_name": workbook.folder_name,
        "unit_label": workbook.unit_label,
        "final_touch_id": workbook.final_touch_id,
        "status": workbook.status,
        "question_count": len(workbook.questions or []),
        "total_question_count": len(workbook.questions or []),
        "sections": _serialized_sections_for_workbook(object_session(workbook), workbook)
        if object_session(workbook)
        else [],
        "created_at": workbook.created_at.isoformat() if workbook.created_at else None,
        "updated_at": workbook.updated_at.isoformat() if workbook.updated_at else None,
    }
    if include_questions:
        data["questions"] = [_serialize_question(q) for q in workbook.questions]
    return data


def _reindex_questions(db: Session, workbook_id: int):
    questions = (
        db.query(models.WorkbookQuestion)
        .filter(models.WorkbookQuestion.workbook_id == workbook_id)
        .order_by(models.WorkbookQuestion.order_index.asc(), models.WorkbookQuestion.id.asc())
        .all()
    )
    for index, question in enumerate(questions, start=1):
        question.order_index = index


@router.post("")
def create_workbook(
    payload: WorkbookCreateRequest,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_role("teacher")),
):
    teacher_id = _user_id(current_user)
    title = payload.title.strip()
    if not title:
        raise HTTPException(status_code=400, detail="title is required")
    _validate_final_touch(db, payload.final_touch_id, teacher_id)
    workbook = models.Workbook(
        teacher_id=teacher_id,
        title=title,
        description=_clean_optional(payload.description),
        final_touch_id=payload.final_touch_id,
        source_label=_clean_optional(payload.source_label),
        folder_name=_clean_optional(payload.folder_name),
        unit_label=_clean_optional(payload.unit_label),
        status="draft",
    )
    db.add(workbook)
    db.commit()
    db.refresh(workbook)
    return _serialize_workbook(workbook, include_questions=True)


@router.get("")
def list_workbooks(
    status: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_role("teacher")),
):
    query = db.query(models.Workbook).filter(
        models.Workbook.teacher_id == _user_id(current_user)
    )
    if status and status != "all":
        query = query.filter(models.Workbook.status == status)
    elif status in (None, "", "all"):
        query = query.filter(models.Workbook.status != "archived")
    items = query.order_by(models.Workbook.created_at.desc()).all()
    return {"items": [_serialize_workbook(item) for item in items]}


@router.get("/{workbook_id}")
def get_workbook(
    workbook_id: int,
    section_id: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_role("teacher")),
):
    workbook = _teacher_workbook_or_404(db, workbook_id, _user_id(current_user))
    data = _serialize_workbook(workbook, include_questions=False)
    questions = sorted(
        workbook.questions or [],
        key=lambda question: (question.order_index, question.id),
    )
    if section_id is not None:
        if section_id == 0:
            questions = [question for question in questions if question.section_id is None]
        else:
            questions = [question for question in questions if question.section_id == section_id]
    data["questions"] = [_serialize_question(q) for q in questions]
    data["question_count"] = len(questions) if section_id is not None else len(workbook.questions or [])
    return data


@router.get("/{workbook_id}/sections")
def list_sections(
    workbook_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_role("teacher")),
):
    workbook = _teacher_workbook_or_404(db, workbook_id, _user_id(current_user))
    return {"items": _serialized_sections_for_workbook(db, workbook)}


@router.post("/{workbook_id}/sections")
def create_section(
    workbook_id: int,
    payload: WorkbookSectionRequest,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_role("teacher")),
):
    workbook = _teacher_workbook_or_404(db, workbook_id, _user_id(current_user))
    title = payload.title.strip()
    if not title:
        raise HTTPException(status_code=400, detail="section title is required")
    key = _clean_optional(payload.section_key)
    if key:
        existing = (
            db.query(models.WorkbookSection)
            .filter(
                models.WorkbookSection.workbook_id == workbook.id,
                models.WorkbookSection.section_key == key,
            )
            .first()
        )
        if existing:
            return _serialize_section(existing, _section_counts(db, workbook.id).get(existing.id, 0))
    section = models.WorkbookSection(
        workbook_id=workbook.id,
        title=title,
        source_label=_clean_optional(payload.source_label) or workbook.source_label,
        unit_label=_clean_optional(payload.unit_label),
        section_key=key,
        sort_order=payload.sort_order
        if payload.sort_order is not None
        else _section_sort_value(key, _next_section_order(db, workbook.id)),
    )
    workbook.updated_at = datetime.utcnow()
    db.add(section)
    db.commit()
    db.refresh(section)
    return _serialize_section(section, 0)


@router.patch("/{workbook_id}/sections/{section_id}")
def update_section(
    workbook_id: int,
    section_id: int,
    payload: WorkbookSectionUpdateRequest,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_role("teacher")),
):
    workbook = _teacher_workbook_or_404(db, workbook_id, _user_id(current_user))
    section = _section_or_404(db, workbook, section_id)
    if payload.title is not None:
        title = payload.title.strip()
        if not title:
            raise HTTPException(status_code=400, detail="section title is required")
        section.title = title
    if payload.sort_order is not None:
        section.sort_order = payload.sort_order
    if payload.source_label is not None:
        section.source_label = _clean_optional(payload.source_label)
    if payload.unit_label is not None:
        section.unit_label = _clean_optional(payload.unit_label)
    if payload.section_key is not None:
        section.section_key = _clean_optional(payload.section_key)
    now = datetime.utcnow()
    section.updated_at = now
    workbook.updated_at = now
    db.commit()
    db.refresh(section)
    return _serialize_section(section, _section_counts(db, workbook.id).get(section.id, 0))


@router.delete("/{workbook_id}/sections/{section_id}")
def delete_section(
    workbook_id: int,
    section_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_role("teacher")),
):
    workbook = _teacher_workbook_or_404(db, workbook_id, _user_id(current_user))
    section = _section_or_404(db, workbook, section_id)
    has_questions = (
        db.query(models.WorkbookQuestion.id)
        .filter(
            models.WorkbookQuestion.workbook_id == workbook.id,
            models.WorkbookQuestion.section_id == section.id,
        )
        .first()
        is not None
    )
    if has_questions:
        raise HTTPException(
            status_code=400,
            detail="문제가 있는 섹션은 삭제할 수 없습니다. 먼저 문제를 이동하거나 삭제해 주세요.",
        )
    db.delete(section)
    workbook.updated_at = datetime.utcnow()
    db.commit()
    return {"message": "Workbook section deleted", "section_id": section_id}


@router.patch("/{workbook_id}")
def update_workbook(
    workbook_id: int,
    payload: WorkbookUpdateRequest,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_role("teacher")),
):
    workbook = _teacher_workbook_or_404(db, workbook_id, _user_id(current_user))
    if payload.title is not None:
        title = payload.title.strip()
        if not title:
            raise HTTPException(status_code=400, detail="title is required")
        workbook.title = title
    if payload.status is not None:
        status = payload.status.strip().lower()
        if status not in ALLOWED_WORKBOOK_STATUSES:
            raise HTTPException(status_code=400, detail="Unsupported workbook status")
        workbook.status = status
    for field in ("description", "source_label", "folder_name", "unit_label"):
        value = getattr(payload, field)
        if value is not None:
            setattr(workbook, field, _clean_optional(value))
    workbook.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(workbook)
    return _serialize_workbook(workbook, include_questions=True)


@router.patch("/{workbook_id}/archive")
def archive_workbook(
    workbook_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_role("teacher")),
):
    workbook = _teacher_workbook_or_404(db, workbook_id, _user_id(current_user))
    workbook.status = "archived"
    workbook.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(workbook)
    return _serialize_workbook(workbook)


@router.delete("/{workbook_id}")
def delete_workbook(
    workbook_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_role("teacher")),
):
    teacher_id = _user_id(current_user)
    workbook = (
        db.query(models.Workbook)
        .filter(models.Workbook.id == workbook_id)
        .first()
    )
    if not workbook:
        raise HTTPException(status_code=404, detail="Workbook not found")
    if workbook.teacher_id != teacher_id:
        raise HTTPException(status_code=403, detail="Workbook access denied")

    has_assignment = (
        db.query(models.LearningAssignment.id)
        .filter(
            models.LearningAssignment.content_type == "workbook",
            models.LearningAssignment.content_id == workbook.id,
        )
        .first()
        is not None
    )
    has_attempt = (
        db.query(models.WorkbookAttempt.id)
        .filter(models.WorkbookAttempt.workbook_id == workbook.id)
        .first()
        is not None
    )
    if has_assignment or has_attempt:
        raise HTTPException(
            status_code=400,
            detail=(
                "이미 배포되었거나 학생 결과가 있는 워크북은 삭제할 수 없습니다. "
                "보관 처리해 주세요."
            ),
        )

    db.delete(workbook)
    db.commit()
    return {"message": "Workbook deleted", "workbook_id": workbook_id}


@router.post("/{workbook_id}/questions")
def create_question(
    workbook_id: int,
    payload: WorkbookQuestionRequest,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_role("teacher")),
):
    workbook = _teacher_workbook_or_404(db, workbook_id, _user_id(current_user))
    qtype, choices, answer = _validate_question_payload(
        payload.question_type,
        payload.prompt,
        payload.choices,
        payload.answer,
    )
    section = _get_or_create_section(
        db,
        workbook,
        section_id=payload.section_id,
        section_key=payload.section_key,
        section_title=payload.section_title,
    )
    next_order = len(workbook.questions or []) + 1
    question = models.WorkbookQuestion(
        workbook_id=workbook.id,
        section_id=section.id if section else None,
        question_type=qtype,
        order_index=next_order,
        prompt=payload.prompt.strip(),
        passage_text=_clean_optional(payload.passage_text),
        choices_json=choices,
        answer_json=answer,
        explanation=_clean_optional(payload.explanation),
        points=max(1, int(payload.points or 1)),
    )
    workbook.updated_at = datetime.utcnow()
    db.add(question)
    db.commit()
    db.refresh(question)
    return _serialize_question(question)


@router.patch("/{workbook_id}/questions/{question_id}")
def update_question(
    workbook_id: int,
    question_id: int,
    payload: WorkbookQuestionUpdateRequest,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_role("teacher")),
):
    workbook = _teacher_workbook_or_404(db, workbook_id, _user_id(current_user))
    question = _question_or_404(db, workbook, question_id)
    qtype, choices, answer = _validate_question_payload(
        question.question_type,
        payload.prompt if payload.prompt is not None else question.prompt,
        payload.choices if payload.choices is not None else question.choices_json,
        payload.answer if payload.answer is not None else question.answer_json,
    )
    section = _get_or_create_section(
        db,
        workbook,
        section_id=payload.section_id,
        section_key=payload.section_key,
        section_title=payload.section_title,
    )
    question.question_type = qtype
    fields_set = getattr(
        payload,
        "model_fields_set",
        getattr(payload, "__fields_set__", set()),
    )
    if (
        "section_id" in fields_set
        or payload.section_key is not None
        or payload.section_title is not None
    ):
        question.section_id = section.id if section else None
    if payload.prompt is not None:
        question.prompt = payload.prompt.strip()
    if payload.passage_text is not None:
        question.passage_text = _clean_optional(payload.passage_text)
    if payload.choices is not None:
        question.choices_json = choices
    if payload.answer is not None:
        question.answer_json = answer
    if payload.explanation is not None:
        question.explanation = _clean_optional(payload.explanation)
    if payload.points is not None:
        question.points = max(1, int(payload.points))
    now = datetime.utcnow()
    question.updated_at = now
    workbook.updated_at = now
    db.commit()
    db.refresh(question)
    return _serialize_question(question)


@router.delete("/{workbook_id}/questions/{question_id}")
def delete_question(
    workbook_id: int,
    question_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_role("teacher")),
):
    workbook = _teacher_workbook_or_404(db, workbook_id, _user_id(current_user))
    question = _question_or_404(db, workbook, question_id)
    db.delete(question)
    workbook.updated_at = datetime.utcnow()
    db.flush()
    _reindex_questions(db, workbook.id)
    db.commit()
    return {"message": "Workbook question deleted", "question_id": question_id}


@router.post("/{workbook_id}/questions/reorder")
def reorder_questions(
    workbook_id: int,
    payload: WorkbookReorderRequest,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_role("teacher")),
):
    workbook = _teacher_workbook_or_404(db, workbook_id, _user_id(current_user))
    questions = {
        q.id: q
        for q in db.query(models.WorkbookQuestion)
        .filter(models.WorkbookQuestion.workbook_id == workbook.id)
        .all()
    }
    if set(payload.question_ids) != set(questions):
        raise HTTPException(status_code=400, detail="question_ids must match workbook questions")
    for index, question_id in enumerate(payload.question_ids, start=1):
        questions[question_id].order_index = index
    workbook.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(workbook)
    return _serialize_workbook(workbook, include_questions=True)
