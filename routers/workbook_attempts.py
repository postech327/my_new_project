from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlalchemy.orm import Session

import models
from db import get_db
from utils.security import require_role

router = APIRouter(tags=["workbook_attempts"])


class WorkbookAttemptAnswerIn(BaseModel):
    question_id: int
    question_type: str
    item_number: Optional[int] = None
    student_answer: Optional[str] = None
    subtype: Optional[str] = None


class WorkbookAttemptSubmitRequest(BaseModel):
    assignment_id: int
    workbook_id: int
    section_id: Optional[int] = None
    answers: list[WorkbookAttemptAnswerIn] = Field(default_factory=list)


def _user_id(current_user: dict) -> int:
    return int(current_user["sub"])


def _assignment_for_student(db: Session, assignment_id: int, student_id: int):
    assignment = (
        db.query(models.LearningAssignment)
        .filter(
            models.LearningAssignment.id == assignment_id,
            models.LearningAssignment.student_id == student_id,
            models.LearningAssignment.content_type == "workbook",
        )
        .first()
    )
    if not assignment:
        raise HTTPException(status_code=404, detail="Workbook assignment not found")
    return assignment


def _assignment_for_teacher(db: Session, assignment_id: int, teacher_id: int):
    assignment = (
        db.query(models.LearningAssignment)
        .filter(
            models.LearningAssignment.id == assignment_id,
            models.LearningAssignment.teacher_id == teacher_id,
            models.LearningAssignment.content_type == "workbook",
        )
        .first()
    )
    if not assignment:
        raise HTTPException(status_code=404, detail="Workbook assignment not found")
    return assignment


def _workbook_or_404(db: Session, workbook_id: int):
    workbook = db.query(models.Workbook).filter(models.Workbook.id == workbook_id).first()
    if not workbook:
        raise HTTPException(status_code=404, detail="Workbook not found")
    return workbook


def _normalize_text(value: Optional[str]) -> str:
    return (value or "").strip()


def _normalize_answer(value: Optional[str]) -> str:
    return _normalize_text(value).lower()


def _tf_to_bool(value: Optional[str]) -> Optional[bool]:
    text = _normalize_answer(value)
    if text in {"t", "true", "o", "1", "yes", "맞음"}:
        return True
    if text in {"f", "false", "x", "0", "no", "틀림"}:
        return False
    return None


def _normalize_insertion_answer(value: Optional[str]) -> str:
    text = _normalize_text(value)
    circle_map = {"①": "1", "②": "2", "③": "3", "④": "4", "⑤": "5"}
    for mark, number in circle_map.items():
        if mark in text:
            return number
    for char in text:
        if char in {"1", "2", "3", "4", "5"}:
            return char
    return text.lower()


def _normalize_order_answer(value: Optional[str]) -> str:
    text = _normalize_text(value).upper()
    letters = [char for char in text if char in {"A", "B", "C"}]
    return "-".join(letters)


def _answer_lookup(answers: list[WorkbookAttemptAnswerIn]):
    lookup: dict[tuple[int, Optional[int]], WorkbookAttemptAnswerIn] = {}
    for answer in answers:
        lookup[(answer.question_id, answer.item_number)] = answer
    return lookup


def _score_question(
    question: models.WorkbookQuestion,
    submitted: dict[tuple[int, Optional[int]], WorkbookAttemptAnswerIn],
):
    answer_json = question.answer_json or {}
    rows: list[dict[str, Any]] = []

    if question.question_type == "inline_choice":
        items = answer_json.get("items") if isinstance(answer_json, dict) else []
        if not isinstance(items, list):
            items = []
        for fallback_index, item in enumerate(items, start=1):
            if not isinstance(item, dict):
                continue
            number = int(item.get("number") or fallback_index)
            student = submitted.get((question.id, number))
            student_answer = _normalize_text(student.student_answer if student else None)
            correct_answer = _normalize_text(item.get("answer"))
            is_correct = (
                bool(student_answer)
                and _normalize_answer(student_answer) == _normalize_answer(correct_answer)
            )
            rows.append(
                {
                    "question_id": question.id,
                    "question_type": question.question_type,
                    "item_number": number,
                    "student_answer": student_answer,
                    "correct_answer": correct_answer,
                    "is_correct": is_correct,
                    "explanation": _normalize_text(item.get("explanation")),
                }
            )
        return rows

    if question.question_type == "true_false" and isinstance(answer_json.get("items"), list):
        for fallback_index, item in enumerate(answer_json.get("items") or [], start=1):
            if not isinstance(item, dict):
                continue
            number = int(item.get("number") or fallback_index)
            student = submitted.get((question.id, number))
            student_answer = _normalize_text(student.student_answer if student else None)
            student_bool = _tf_to_bool(student_answer)
            raw_correct = item.get("answer")
            correct_bool = raw_correct if isinstance(raw_correct, bool) else _tf_to_bool(str(raw_correct))
            is_correct = bool(student_answer) and student_bool is correct_bool
            rows.append(
                {
                    "question_id": question.id,
                    "question_type": question.question_type,
                    "item_number": number,
                    "student_answer": student_answer,
                    "correct_answer": "T" if correct_bool is True else "F",
                    "is_correct": is_correct,
                    "explanation": _normalize_text(item.get("explanation")),
                }
            )
        return rows

    if question.question_type == "check_learning_set":
        section_a = answer_json.get("section_a") or {}
        section_b = answer_json.get("section_b") or {}
        section_c = answer_json.get("section_c") or {}
        answers_b = section_b.get("answers") or []
        explanations_b = section_b.get("explanations") or []
        note_b = _normalize_text(section_b.get("note"))

        if answers_b:
            for index, correct in enumerate(answers_b, start=1):
                student = submitted.get((question.id, index)) or submitted.get((question.id, 2000 + index))
                student_answer = _normalize_text(student.student_answer if student else None)
                correct_answer = _normalize_text(correct)
                explanation = ""
                if isinstance(explanations_b, list) and index - 1 < len(explanations_b):
                    explanation = _normalize_text(explanations_b[index - 1])
                rows.append(
                    {
                        "question_id": question.id,
                        "question_type": "check_learning_set",
                        "item_number": index,
                        "student_answer": student_answer,
                        "correct_answer": correct_answer,
                        "is_correct": bool(student_answer)
                        and _normalize_answer(student_answer) == _normalize_answer(correct_answer),
                        "explanation": explanation,
                    }
                )
            if note_b and not any(row.get("explanation") for row in rows):
                target = next((row for row in rows if not row["is_correct"]), rows[0])
                target["explanation"] = note_b
            return rows

        for fallback_index, item in enumerate(section_a.get("items") or [], start=1):
            if not isinstance(item, dict):
                continue
            number = int(item.get("number") or fallback_index)
            lookup_number = 1000 + number
            student = submitted.get((question.id, lookup_number))
            student_answer = _normalize_text(student.student_answer if student else None)
            correct_answer = _normalize_text(item.get("answer"))
            rows.append(
                {
                    "question_id": question.id,
                    "question_type": "check_learning_set:A",
                    "item_number": number,
                    "student_answer": student_answer,
                    "correct_answer": correct_answer,
                    "is_correct": bool(student_answer)
                    and _normalize_answer(student_answer) == _normalize_answer(correct_answer),
                    "explanation": _normalize_text(item.get("explanation")),
                }
            )

        for fallback_index, item in enumerate(section_c.get("items") or [], start=1):
            if not isinstance(item, dict):
                continue
            number = int(item.get("number") or fallback_index)
            lookup_number = 3000 + number
            student = submitted.get((question.id, lookup_number))
            student_answer = _normalize_text(student.student_answer if student else None)
            student_bool = _tf_to_bool(student_answer)
            raw_correct = item.get("answer")
            correct_bool = raw_correct if isinstance(raw_correct, bool) else _tf_to_bool(str(raw_correct))
            rows.append(
                {
                    "question_id": question.id,
                    "question_type": "check_learning_set:C",
                    "item_number": number,
                    "student_answer": student_answer,
                    "correct_answer": "T" if correct_bool is True else "F",
                    "is_correct": bool(student_answer) and student_bool is correct_bool,
                    "explanation": _normalize_text(item.get("explanation")),
                }
            )
        return rows

    if question.question_type == "initial_blank":
        items = answer_json.get("items") if isinstance(answer_json, dict) else []
        if not isinstance(items, list):
            items = []
        for fallback_index, item in enumerate(items, start=1):
            if not isinstance(item, dict):
                continue
            student = submitted.get((question.id, fallback_index))
            student_answer = _normalize_text(student.student_answer if student else None)
            correct_answer = _normalize_text(item.get("answer"))
            label = _normalize_text(item.get("label")) or str(fallback_index)
            rows.append(
                {
                    "question_id": question.id,
                    "question_type": question.question_type,
                    "item_number": fallback_index,
                    "student_answer": student_answer,
                    "correct_answer": correct_answer,
                    "is_correct": bool(student_answer)
                    and _normalize_answer(student_answer) == _normalize_answer(correct_answer),
                    "explanation": None,
                }
            )
        return rows

    if question.question_type == "sentence_insertion":
        student = submitted.get((question.id, 1)) or submitted.get((question.id, None))
        student_answer = _normalize_text(student.student_answer if student else None)
        correct_answer = _normalize_text(answer_json.get("answer"))
        rows.append(
            {
                "question_id": question.id,
                "question_type": question.question_type,
                "item_number": 1,
                "student_answer": student_answer,
                "correct_answer": correct_answer,
                "is_correct": bool(student_answer)
                and _normalize_insertion_answer(student_answer)
                == _normalize_insertion_answer(correct_answer),
                "explanation": None,
            }
        )
        return rows

    if question.question_type == "paragraph_order":
        student = submitted.get((question.id, 1)) or submitted.get((question.id, None))
        student_answer = _normalize_text(student.student_answer if student else None)
        raw_order = answer_json.get("answer_order") or []
        correct_answer = "-".join(str(item).strip().upper() for item in raw_order)
        rows.append(
            {
                "question_id": question.id,
                "question_type": question.question_type,
                "item_number": 1,
                "student_answer": student_answer,
                "correct_answer": correct_answer,
                "is_correct": bool(student_answer)
                and _normalize_order_answer(student_answer) == correct_answer,
                "explanation": None,
            }
        )
        return rows

    # TODO: free-answer scoring will be added after the structured HWP-first
    # parser is finalized.
    student = submitted.get((question.id, None))
    rows.append(
        {
            "question_id": question.id,
            "question_type": question.question_type,
            "item_number": None,
            "student_answer": _normalize_text(student.student_answer if student else None),
            "correct_answer": None,
            "is_correct": False,
            "explanation": None,
        }
    )
    return rows


def _serialize_attempt(attempt: models.WorkbookAttempt, include_answers: bool = True):
    data = {
        "attempt_id": attempt.id,
        "id": attempt.id,
        "assignment_id": attempt.assignment_id,
        "workbook_id": attempt.workbook_id,
        "student_id": attempt.student_id,
        "teacher_id": attempt.teacher_id,
        "attempt_no": attempt.attempt_no,
        "status": attempt.status,
        "total_questions": attempt.total_questions,
        "correct_count": attempt.correct_count,
        "wrong_count": attempt.wrong_count,
        "score_percent": attempt.score_percent,
        "started_at": attempt.started_at.isoformat() if attempt.started_at else None,
        "submitted_at": attempt.submitted_at.isoformat() if attempt.submitted_at else None,
        "created_at": attempt.created_at.isoformat() if attempt.created_at else None,
    }
    if include_answers:
        data["results"] = [
            {
                "id": answer.id,
                "question_id": answer.question_id,
                "question_type": answer.question_type,
                "item_number": answer.item_number,
                "student_answer": answer.student_answer,
                "correct_answer": answer.correct_answer,
                "is_correct": answer.is_correct,
                "explanation": answer.explanation,
                "created_at": answer.created_at.isoformat()
                if answer.created_at
                else None,
            }
            for answer in sorted(
                attempt.answers or [],
                key=lambda item: (item.question_id, item.item_number or 0, item.id),
            )
        ]
    return data


def _latest_attempt(db: Session, assignment_id: int):
    return (
        db.query(models.WorkbookAttempt)
        .filter(models.WorkbookAttempt.assignment_id == assignment_id)
        .order_by(models.WorkbookAttempt.attempt_no.desc(), models.WorkbookAttempt.id.desc())
        .first()
    )


@router.post("/student/workbook-attempts/submit")
def submit_workbook_attempt(
    payload: WorkbookAttemptSubmitRequest,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_role("student")),
):
    student_id = _user_id(current_user)
    assignment = _assignment_for_student(db, payload.assignment_id, student_id)
    if assignment.content_id != payload.workbook_id:
        raise HTTPException(status_code=400, detail="Workbook does not match assignment")
    workbook = _workbook_or_404(db, payload.workbook_id)

    questions = sorted(
        workbook.questions or [],
        key=lambda question: (question.order_index, question.id),
    )
    if payload.section_id is not None:
        if payload.section_id == 0:
            questions = [question for question in questions if question.section_id is None]
        else:
            questions = [
                question
                for question in questions
                if question.section_id == payload.section_id
            ]
    submitted = _answer_lookup(payload.answers)
    scored_rows: list[dict[str, Any]] = []
    for question in questions:
        scored_rows.extend(_score_question(question, submitted))

    total = len(scored_rows)
    correct = sum(1 for row in scored_rows if row["is_correct"] is True)
    wrong = total - correct
    score = round((correct / total * 100) if total else 0, 1)
    now = datetime.utcnow()
    last_attempt_no = (
        db.query(func.max(models.WorkbookAttempt.attempt_no))
        .filter(models.WorkbookAttempt.assignment_id == assignment.id)
        .scalar()
        or 0
    )
    attempt = models.WorkbookAttempt(
        assignment_id=assignment.id,
        workbook_id=workbook.id,
        student_id=student_id,
        teacher_id=assignment.teacher_id,
        attempt_no=int(last_attempt_no) + 1,
        status="submitted",
        total_questions=total,
        correct_count=correct,
        wrong_count=wrong,
        score_percent=score,
        started_at=now,
        submitted_at=now,
        created_at=now,
    )
    db.add(attempt)
    db.flush()
    for row in scored_rows:
        db.add(
            models.WorkbookAttemptAnswer(
                attempt_id=attempt.id,
                question_id=row["question_id"],
                question_type=row["question_type"],
                item_number=row["item_number"],
                student_answer=row["student_answer"],
                correct_answer=row["correct_answer"],
                is_correct=row["is_correct"],
                explanation=row["explanation"],
                created_at=now,
            )
        )

    if assignment.status != "completed":
        assignment.status = "completed"
        assignment.completed_at = assignment.completed_at or now
    assignment.started_at = assignment.started_at or now
    assignment.updated_at = now
    db.commit()
    db.refresh(attempt)
    return _serialize_attempt(attempt, include_answers=True)


@router.get("/student/workbook-attempts/latest/{assignment_id}")
def get_student_latest_workbook_attempt(
    assignment_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_role("student")),
):
    assignment = _assignment_for_student(db, assignment_id, _user_id(current_user))
    attempt = _latest_attempt(db, assignment.id)
    if not attempt:
        return {
            "has_attempt": False,
            "latest_attempt": None,
            "message": "아직 제출한 결과가 없습니다.",
        }
    return {
        "has_attempt": True,
        "latest_attempt": _serialize_attempt(attempt, include_answers=True),
        "message": None,
    }


@router.get("/student/workbook-attempts")
def list_student_workbook_attempts(
    assignment_id: int = Query(...),
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_role("student")),
):
    assignment = _assignment_for_student(db, assignment_id, _user_id(current_user))
    attempts = (
        db.query(models.WorkbookAttempt)
        .filter(models.WorkbookAttempt.assignment_id == assignment.id)
        .order_by(models.WorkbookAttempt.attempt_no.desc())
        .all()
    )
    return {"items": [_serialize_attempt(attempt, include_answers=False) for attempt in attempts]}


@router.get("/teacher/workbook-attempts/assignment/{assignment_id}")
def get_teacher_workbook_attempts_for_assignment(
    assignment_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_role("teacher")),
):
    teacher_id = _user_id(current_user)
    assignment = _assignment_for_teacher(db, assignment_id, teacher_id)
    workbook = _workbook_or_404(db, assignment.content_id)
    student = db.query(models.User).filter(models.User.id == assignment.student_id).first()
    attempts = (
        db.query(models.WorkbookAttempt)
        .filter(models.WorkbookAttempt.assignment_id == assignment.id)
        .order_by(models.WorkbookAttempt.attempt_no.desc())
        .all()
    )
    latest = attempts[0] if attempts else None
    return {
        "student": {
            "id": assignment.student_id,
            "nickname": student.nickname if student else f"student{assignment.student_id}",
            "email": student.email if student else None,
        },
        "workbook": {
            "id": workbook.id,
            "title": workbook.title,
            "question_count": len(workbook.questions or []),
        },
        "assignment": {
            "id": assignment.id,
            "status": assignment.status,
            "assigned_at": assignment.assigned_at.isoformat()
            if assignment.assigned_at
            else None,
            "started_at": assignment.started_at.isoformat()
            if assignment.started_at
            else None,
            "completed_at": assignment.completed_at.isoformat()
            if assignment.completed_at
            else None,
            "due_at": assignment.due_at.isoformat() if assignment.due_at else None,
        },
        "attempt_count": len(attempts),
        "latest_attempt": _serialize_attempt(latest, include_answers=True)
        if latest
        else None,
        "attempts": [
            _serialize_attempt(attempt, include_answers=False) for attempt in attempts
        ],
    }
