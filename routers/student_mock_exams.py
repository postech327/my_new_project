from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from db import get_db
import models
from utils.security import require_role

router = APIRouter(
    prefix="/student/mock-exams",
    tags=["student_mock_exams"],
)

TYPE_LABELS = {
    "purpose": "목적",
    "mood": "심경/분위기",
    "claim": "주장",
    "implication": "함의",
    "gist": "요지",
    "topic": "주제",
    "title": "제목",
    "content_match": "일치",
    "grammar": "어법",
    "vocabulary": "어휘",
    "blank": "빈칸",
    "irrelevant": "무관한 문장",
    "order": "순서",
    "insertion": "삽입",
    "summary": "요약",
}

TYPE_ORDER = [
    "purpose",
    "mood",
    "claim",
    "implication",
    "gist",
    "topic",
    "title",
    "content_match",
    "grammar",
    "vocabulary",
    "blank",
    "irrelevant",
    "order",
    "insertion",
    "summary",
]


class MockAnswerSubmit(BaseModel):
    question_id: int
    selected_index: int


class MockExamSubmitRequest(BaseModel):
    answers: list[MockAnswerSubmit]


def _user_id(current_user: dict[str, Any]) -> int:
    return int(current_user["sub"])


def _type_label(question_type: str):
    return TYPE_LABELS.get(question_type, question_type)


def _serialize_exam_summary(exam: models.MockExam):
    question_count = len(exam.questions or [])
    return {
        "id": exam.id,
        "grade": exam.grade,
        "year": exam.year,
        "month": exam.month,
        "title": exam.title,
        "total_questions": exam.total_questions,
        "total_score": exam.total_score,
        "has_listening": exam.has_listening,
        "question_count": question_count,
        "is_complete": question_count == exam.total_questions,
        "created_at": exam.created_at.isoformat() if exam.created_at else None,
    }


def _serialize_question_for_student(question: models.MockQuestion):
    return {
        "id": question.id,
        "mock_exam_id": question.mock_exam_id,
        "number": question.number,
        "question_type": question.question_type,
        "type_label": _type_label(question.question_type),
        "source": question.source,
        "passage": question.passage,
        "question_text": question.question_text,
        "options": question.options or [],
        "passage_group_id": question.passage_group_id,
    }


def _serialize_exam_detail(exam: models.MockExam):
    questions = sorted(exam.questions or [], key=lambda item: item.number)
    data = _serialize_exam_summary(exam)
    data["questions"] = [
        _serialize_question_for_student(question) for question in questions
    ]
    return data


def _score_value(correct_count: int, total_questions: int, total_score: int):
    if total_questions <= 0:
        return 0
    score = correct_count / total_questions * total_score
    return int(score) if score.is_integer() else round(score, 2)


def _weak_types(type_results: list[dict]):
    seen = set()
    weak = []
    for type_code in TYPE_ORDER:
        if any(
            item["type"] == type_code and item["correct"] is False
            for item in type_results
        ):
            label = _type_label(type_code)
            if label not in seen:
                seen.add(label)
                weak.append(label)
    return weak


def _score_text(value: float | int | None):
    if value is None:
        return 0
    score = float(value)
    return int(score) if score.is_integer() else round(score, 1)


def _question_type_counts(exam: models.MockExam):
    counts: dict[str, int] = {type_code: 0 for type_code in TYPE_ORDER}
    for question in exam.questions or []:
        counts[question.question_type] = counts.get(question.question_type, 0) + 1
    return counts


def _weak_types_for_attempt(attempt: models.MockAttempt):
    seen: set[str] = set()
    weak: list[str] = []
    answered_question_ids = set()
    for answer in sorted(attempt.answers or [], key=lambda item: item.id):
        answered_question_ids.add(answer.mock_question_id)
        if answer.is_correct:
            continue
        label = _type_label(answer.question_type)
        if label not in seen:
            seen.add(label)
            weak.append(label)

    questions = sorted(
        attempt.mock_exam.questions or [],
        key=lambda item: item.number,
    ) if attempt.mock_exam else []
    for question in questions:
        if question.id in answered_question_ids:
            continue
        label = _type_label(question.question_type)
        if label not in seen:
            seen.add(label)
            weak.append(label)
    return weak


def _student_mock_report(db: Session, user_id: int):
    attempts = (
        db.query(models.MockAttempt)
        .filter(models.MockAttempt.user_id == user_id)
        .order_by(models.MockAttempt.submitted_at.desc(), models.MockAttempt.id.desc())
        .all()
    )

    attempt_count = len(attempts)
    scores = [float(attempt.score or 0) for attempt in attempts]
    correct_by_type: dict[str, int] = {type_code: 0 for type_code in TYPE_ORDER}
    total_by_type: dict[str, int] = {type_code: 0 for type_code in TYPE_ORDER}

    for attempt in attempts:
        exam = attempt.mock_exam
        if exam:
            for type_code, count in _question_type_counts(exam).items():
                total_by_type[type_code] = total_by_type.get(type_code, 0) + count
        else:
            for answer in attempt.answers or []:
                total_by_type[answer.question_type] = (
                    total_by_type.get(answer.question_type, 0) + 1
                )

        for answer in attempt.answers or []:
            correct_by_type.setdefault(answer.question_type, 0)
            total_by_type.setdefault(answer.question_type, 0)
            if answer.is_correct:
                correct_by_type[answer.question_type] += 1

    type_stats = []
    for type_code in TYPE_ORDER:
        total = total_by_type.get(type_code, 0)
        correct = correct_by_type.get(type_code, 0)
        rate = round(correct / total * 100, 1) if total else 0
        type_stats.append(
            {
                "type": type_code,
                "label": _type_label(type_code),
                "correct": correct,
                "total": total,
                "rate": rate,
            }
        )

    weak_types = [
        item["label"]
        for item in sorted(
            [item for item in type_stats if item["total"] > 0],
            key=lambda item: (item["rate"], -item["total"]),
        )[:3]
        if item["rate"] < 70
    ]

    recent_attempts = []
    for attempt in attempts[:10]:
        exam = attempt.mock_exam
        recent_attempts.append(
            {
                "attempt_id": attempt.id,
                "mock_exam_id": attempt.mock_exam_id,
                "title": exam.title if exam else "삭제된 모의고사",
                "grade": exam.grade if exam else "-",
                "year": exam.year if exam else None,
                "month": exam.month if exam else None,
                "score": _score_text(attempt.score),
                "correct_count": attempt.correct_count,
                "total_questions": attempt.total_questions,
                "weak_types": _weak_types_for_attempt(attempt),
                "submitted_at": attempt.submitted_at.isoformat()
                if attempt.submitted_at
                else None,
            }
        )

    return {
        "summary": {
            "attempt_count": attempt_count,
            "average_score": _score_text(sum(scores) / attempt_count)
            if attempt_count
            else 0,
            "highest_score": _score_text(max(scores)) if scores else 0,
            "latest_score": _score_text(attempts[0].score) if attempts else 0,
            "weak_types": weak_types,
        },
        "type_stats": type_stats,
        "recent_attempts": recent_attempts,
        "score_trend": list(reversed(recent_attempts[:10])),
    }


def _get_attempt_or_404(db: Session, attempt_id: int, user_id: int):
    attempt = (
        db.query(models.MockAttempt)
        .filter(
            models.MockAttempt.id == attempt_id,
            models.MockAttempt.user_id == user_id,
        )
        .first()
    )
    if not attempt:
        raise HTTPException(status_code=404, detail="Mock attempt not found")
    return attempt


def _attempt_detail(attempt: models.MockAttempt):
    exam = attempt.mock_exam
    questions = sorted(exam.questions or [], key=lambda item: item.number) if exam else []
    answer_by_question_id = {
        answer.mock_question_id: answer for answer in attempt.answers or []
    }

    question_items = []
    type_results = []
    for question in questions:
        answer = answer_by_question_id.get(question.id)
        selected_index = answer.selected_index if answer else None
        is_correct = bool(answer.is_correct) if answer else False
        type_results.append(
            {
                "type": question.question_type,
                "label": _type_label(question.question_type),
                "correct": is_correct,
            }
        )
        question_items.append(
            {
                "question_id": question.id,
                "number": question.number,
                "question_type": question.question_type,
                "type_label": _type_label(question.question_type),
                "source": question.source,
                "passage": question.passage,
                "question_text": question.question_text,
                "options": question.options or [],
                "selected_index": selected_index,
                "answer_index": question.answer_index,
                "is_correct": is_correct,
                "explanation": question.explanation,
            }
        )

    weak_types = _weak_types_for_attempt(attempt)
    return {
        "attempt": {
            "id": attempt.id,
            "mock_exam_id": attempt.mock_exam_id,
            "title": exam.title if exam else "삭제된 모의고사",
            "grade": exam.grade if exam else "-",
            "year": exam.year if exam else None,
            "month": exam.month if exam else None,
            "score": _score_text(attempt.score),
            "correct_count": attempt.correct_count,
            "total_questions": attempt.total_questions,
            "submitted_at": attempt.submitted_at.isoformat()
            if attempt.submitted_at
            else None,
        },
        "summary": {
            "weak_types": weak_types,
            "correct_count": attempt.correct_count,
            "incorrect_count": max(
                (attempt.total_questions or 0) - (attempt.correct_count or 0),
                0,
            ),
            "score": _score_text(attempt.score),
        },
        "questions": question_items,
    }


def _get_exam_or_404(db: Session, mock_exam_id: int):
    exam = db.query(models.MockExam).filter(models.MockExam.id == mock_exam_id).first()
    if not exam:
        raise HTTPException(status_code=404, detail="Mock exam not found")
    return exam


@router.get("")
def list_mock_exams(
    grade: str | None = Query(default=None),
    year: int | None = Query(default=None),
    month: int | None = Query(default=None),
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_role("student")),
):
    query = db.query(models.MockExam)
    if grade:
        query = query.filter(models.MockExam.grade == grade)
    if year:
        query = query.filter(models.MockExam.year == year)
    if month:
        query = query.filter(models.MockExam.month == month)

    exams = (
        query.order_by(
            models.MockExam.year.desc(),
            models.MockExam.month.desc(),
            models.MockExam.id.desc(),
        )
        .all()
    )
    return [_serialize_exam_summary(exam) for exam in exams]


@router.get("/report")
def get_student_mock_exam_report(
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_role("student")),
):
    return _student_mock_report(db, _user_id(current_user))


@router.get("/attempts/{attempt_id}")
def get_student_mock_exam_attempt_detail(
    attempt_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_role("student")),
):
    attempt = _get_attempt_or_404(db, attempt_id, _user_id(current_user))
    return _attempt_detail(attempt)


@router.get("/{mock_exam_id}")
def get_mock_exam(
    mock_exam_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_role("student")),
):
    exam = _get_exam_or_404(db, mock_exam_id)
    return _serialize_exam_detail(exam)


@router.post("/{mock_exam_id}/submit")
def submit_mock_exam(
    mock_exam_id: int,
    payload: MockExamSubmitRequest,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_role("student")),
):
    exam = _get_exam_or_404(db, mock_exam_id)
    questions = sorted(exam.questions or [], key=lambda item: item.number)
    if len(questions) != exam.total_questions:
        raise HTTPException(
            status_code=400,
            detail=(
                "Mock exam is incomplete: "
                f"expected {exam.total_questions}, actual {len(questions)}"
            ),
        )

    question_by_id = {question.id: question for question in questions}
    submitted = {}
    for answer in payload.answers:
        question = question_by_id.get(answer.question_id)
        if not question:
            raise HTTPException(
                status_code=400,
                detail=f"question_id does not belong to this exam: {answer.question_id}",
            )
        if answer.selected_index < 0 or answer.selected_index > 4:
            raise HTTPException(
                status_code=400,
                detail=f"selected_index must be 0-4: {answer.question_id}",
            )
        submitted[answer.question_id] = answer.selected_index

    type_results = []
    correct_count = 0
    for question in questions:
        selected_index = submitted.get(question.id)
        is_correct = selected_index == question.answer_index
        if is_correct:
            correct_count += 1
        type_results.append(
            {
                "question_id": question.id,
                "number": question.number,
                "type": question.question_type,
                "label": _type_label(question.question_type),
                "correct": bool(is_correct),
            }
        )

    now = datetime.utcnow()
    total_questions = exam.total_questions
    score = _score_value(correct_count, total_questions, exam.total_score)
    attempt = models.MockAttempt(
        user_id=_user_id(current_user),
        mock_exam_id=exam.id,
        correct_count=correct_count,
        total_questions=total_questions,
        score=score,
        started_at=now,
        submitted_at=now,
    )
    db.add(attempt)
    db.flush()

    for question_id, selected_index in submitted.items():
        question = question_by_id[question_id]
        db.add(
            models.MockAnswer(
                attempt_id=attempt.id,
                mock_question_id=question.id,
                selected_index=selected_index,
                is_correct=selected_index == question.answer_index,
                question_type=question.question_type,
            )
        )

    db.commit()
    db.refresh(attempt)

    return {
        "attempt_id": attempt.id,
        "mock_exam_id": exam.id,
        "correct_count": correct_count,
        "total_questions": total_questions,
        "score": score,
        "type_results": type_results,
        "weak_types": _weak_types(type_results),
        "submitted_at": attempt.submitted_at.isoformat()
        if attempt.submitted_at
        else None,
    }
