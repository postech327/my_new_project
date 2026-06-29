from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

import models
from db import get_db
from utils.security import require_role

router = APIRouter(prefix="/student/workbooks", tags=["student_workbooks"])

VISIBLE_ASSIGNMENT_STATUSES = {"assigned", "in_progress", "completed"}


def _user_id(current_user: dict) -> int:
    return int(current_user["sub"])


def _serialize_question_for_student(question: models.WorkbookQuestion):
    content = _student_safe_content(question)
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
        "content": content,
        "points": question.points,
        "created_at": question.created_at.isoformat() if question.created_at else None,
        "updated_at": question.updated_at.isoformat() if question.updated_at else None,
    }


def _student_safe_content(question: models.WorkbookQuestion):
    answer = question.answer_json or {}
    if question.question_type == "inline_choice":
        return {
            "unit_title": answer.get("unit_title"),
            "passage_text": answer.get("passage_text") or question.passage_text,
            "items": [
                {
                    "number": item.get("number"),
                    "choices": item.get("choices") or [],
                }
                for item in answer.get("items", [])
                if isinstance(item, dict)
            ],
        }
    if question.question_type == "true_false" and isinstance(answer.get("items"), list):
        return {
            "unit_title": answer.get("unit_title"),
            "subtype": answer.get("subtype"),
            "passage_text": answer.get("passage_text") or question.passage_text,
            "items": [
                {
                    "number": item.get("number"),
                    "statement": item.get("statement"),
                }
                for item in answer.get("items", [])
                if isinstance(item, dict)
            ],
        }
    if question.question_type == "check_learning_set":
        section_b = answer.get("section_b") or {}
        return {
            "unit_title": answer.get("unit_title"),
            "section_b": {
                "title": section_b.get("title") or "확인학습",
                "type": section_b.get("type") or "word_bank_blank",
                "instruction": section_b.get("instruction") or "",
                "word_bank": section_b.get("word_bank") or [],
                "passage_text": section_b.get("passage_text") or "",
                "blank_count": section_b.get("blank_count") or len(section_b.get("answers") or []),
            },
        }
    if question.question_type == "initial_blank":
        return {
            "unit_title": answer.get("unit_title"),
            "instruction": answer.get("instruction") or "",
            "passage_text": answer.get("passage_text") or question.passage_text,
            "items": [
                {
                    "label": item.get("label"),
                    "initial": item.get("initial"),
                }
                for item in answer.get("items", [])
                if isinstance(item, dict)
            ],
        }
    if question.question_type == "sentence_insertion":
        return {
            "unit_title": answer.get("unit_title"),
            "instruction": answer.get("instruction") or "",
            "insert_sentence": answer.get("insert_sentence") or "",
            "passage_text": answer.get("passage_text") or question.passage_text,
            "positions": answer.get("positions") or [],
        }
    if question.question_type == "paragraph_order":
        return {
            "unit_title": answer.get("unit_title"),
            "instruction": answer.get("instruction") or "",
            "lead_text": answer.get("lead_text") or question.passage_text,
            "segments": answer.get("segments") or [],
        }
    return {}


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


def _serialized_sections(db: Session, workbook: models.Workbook):
    rows = (
        db.query(models.WorkbookQuestion.section_id, func.count(models.WorkbookQuestion.id))
        .filter(
            models.WorkbookQuestion.workbook_id == workbook.id,
            models.WorkbookQuestion.section_id.isnot(None),
        )
        .group_by(models.WorkbookQuestion.section_id)
        .all()
    )
    counts = {int(section_id): int(count) for section_id, count in rows if section_id is not None}
    return [
        _serialize_section(section, counts.get(section.id, 0))
        for section in sorted(
            workbook.sections or [],
            key=lambda item: (item.sort_order or 0, item.id),
        )
    ]


@router.get("/{workbook_id}")
def get_assigned_workbook(
    workbook_id: int,
    section_id: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_role("student")),
):
    student_id = _user_id(current_user)
    assignment = (
        db.query(models.LearningAssignment)
        .filter(
            models.LearningAssignment.student_id == student_id,
            models.LearningAssignment.content_type == "workbook",
            models.LearningAssignment.content_id == workbook_id,
            models.LearningAssignment.status.in_(VISIBLE_ASSIGNMENT_STATUSES),
        )
        .first()
    )
    if not assignment:
        raise HTTPException(status_code=404, detail="Workbook assignment not found")

    workbook = (
        db.query(models.Workbook)
        .filter(models.Workbook.id == workbook_id)
        .first()
    )
    if not workbook:
        raise HTTPException(status_code=404, detail="Workbook not found")

    questions = sorted(
        workbook.questions or [],
        key=lambda question: (question.order_index, question.id),
    )
    if section_id is not None:
        if section_id == 0:
            questions = [question for question in questions if question.section_id is None]
        else:
            questions = [question for question in questions if question.section_id == section_id]
    return {
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
        "question_count": len(questions),
        "total_question_count": len(workbook.questions or []),
        "created_at": workbook.created_at.isoformat() if workbook.created_at else None,
        "updated_at": workbook.updated_at.isoformat() if workbook.updated_at else None,
        "assignment_id": assignment.id,
        "assignment_status": assignment.status,
        "teacher_message": assignment.teacher_message,
        "due_at": assignment.due_at.isoformat() if assignment.due_at else None,
        "sections": _serialized_sections(db, workbook),
        "questions": [_serialize_question_for_student(question) for question in questions],
    }
