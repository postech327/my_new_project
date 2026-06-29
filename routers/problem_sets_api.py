# routers/problem_sets_api.py

from __future__ import annotations

import traceback
import re

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from db import get_db
import models
from utils.security import require_role

from schemas.problem_set import (
    ProblemSetGenerateRequest,
    ProblemSetOut,
    QuestionOut,
    OptionOut,
)

from services.question_set_service import create_problem_set_with_questions

router = APIRouter(
    prefix="/teacher/problem_sets",
    tags=["teacher-problem-sets"],
)

UNFILED_NAME = "미분류"
DIRECT_BUCKET_NAME = "기타 자료"

TYPE_LABELS = {
    "topic": "주제",
    "title": "제목",
    "gist": "요지",
    "summary": "요약",
    "cloze": "빈칸",
    "blank": "빈칸",
    "order": "순서",
    "insertion": "삽입",
    "mismatch": "불일치",
    "content": "불일치",
    "grammar": "어법",
    "vocabulary": "어휘",
}

TYPE_ORDER = [
    "topic",
    "title",
    "gist",
    "summary",
    "cloze",
    "blank",
    "order",
    "insertion",
    "mismatch",
    "content",
    "grammar",
    "vocabulary",
]


def _problem_set_folder_id(problem_set: models.ProblemSet):
    return getattr(problem_set, "folder_id", None) or getattr(
        problem_set.passage, "folder_id", None
    )


def _folder_name(db: Session, folder_id):
    if folder_id is None:
        return UNFILED_NAME
    folder = db.query(models.Folder).filter(models.Folder.id == folder_id).first()
    return folder.name if folder else UNFILED_NAME


def _children(db: Session, parent_id: int | None):
    query = db.query(models.Folder)
    if parent_id is None:
        query = query.filter(models.Folder.parent_id.is_(None))
    else:
        query = query.filter(models.Folder.parent_id == parent_id)
    return query.all()


def _sort_key(name: str):
    match = re.search(r"\d+", name or "")
    number = int(match.group()) if match else 9999
    return (number, name or "")


def _visible_problem_sets(db: Session, current_user: dict):
    username = current_user.get("username")
    user_id = current_user.get("sub")
    values = {str(user_id), str(username), "teacher1", None}
    problem_sets = db.query(models.ProblemSet).all()
    filtered = [ps for ps in problem_sets if getattr(ps, "created_by", None) in values]
    return filtered or problem_sets


def _count_map(problem_sets):
    counts: dict[int | None, int] = {}
    for ps in problem_sets:
        fid = _problem_set_folder_id(ps)
        counts[fid] = counts.get(fid, 0) + 1
    return counts


def _folder_total_count(db: Session, folder_id: int, counts: dict[int | None, int]):
    total = counts.get(folder_id, 0)
    for child in _children(db, folder_id):
        total += counts.get(child.id, 0)
    return total


def _serialize_problem_set_summary(db: Session, ps: models.ProblemSet):
    folder_id = _problem_set_folder_id(ps)
    return {
        "problem_set_id": ps.id,
        "id": ps.id,
        "folder_id": folder_id,
        "folder_name": _folder_name(db, folder_id),
        "name": ps.name,
        "title": ps.name,
        "description": ps.description,
        "question_count": len(ps.questions or []),
        "numQuestions": len(ps.questions or []),
        "created_at": ps.created_at.isoformat() if ps.created_at else None,
        "is_completed": False,
    }


def _attempt_key(attempt: models.ExamAttempt):
    created_at = attempt.created_at.timestamp() if attempt.created_at else 0
    return (created_at, attempt.id or 0)


def _latest_attempts_by_user(attempts):
    latest = {}
    for attempt in attempts:
        existing = latest.get(attempt.user_id)
        if existing is None or _attempt_key(attempt) > _attempt_key(existing):
            latest[attempt.user_id] = attempt
    return list(latest.values())


def _type_label(question_type: str):
    return TYPE_LABELS.get((question_type or "").lower(), question_type or "문제")


def _type_sort_key(item):
    q_type = item["type"]
    try:
        return TYPE_ORDER.index(q_type)
    except ValueError:
        return len(TYPE_ORDER)


def _folder_context(db: Session, problem_set: models.ProblemSet):
    folder_id = _problem_set_folder_id(problem_set)
    unit_folder = None
    book_folder = None
    if folder_id is not None:
        unit_folder = db.query(models.Folder).filter(models.Folder.id == folder_id).first()
        if unit_folder and unit_folder.parent_id is not None:
            book_folder = (
                db.query(models.Folder)
                .filter(models.Folder.id == unit_folder.parent_id)
                .first()
            )
    return {
        "book_folder_id": book_folder.id if book_folder else None,
        "book_folder_name": book_folder.name if book_folder else None,
        "unit_folder_id": unit_folder.id if unit_folder else folder_id,
        "unit_folder_name": unit_folder.name if unit_folder else _folder_name(db, folder_id),
    }

# ======================================================
# 🔥 핵심: 지문 → 분석 + 10문제 생성 + 저장
# ======================================================
@router.post("/generate_and_save", response_model=ProblemSetOut)
def generate_and_save_problem_set(
    req: ProblemSetGenerateRequest,
    db: Session = Depends(get_db),
):
    
    print("🔥 DEBUG: problem_sets_api 실행됨")  # 👈 여기에 추가
    try:
        ps = create_problem_set_with_questions(db, req)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(
            status_code=500,
            detail=f"Problem set generation failed: {type(e).__name__}: {e}",
        )

    questions_out: list[QuestionOut] = []

    for q in ps.questions:
        options_out = [
            OptionOut(
                label=o.label,
                text=o.text,
                is_correct=(i == q.answer_index),
            )
            for i, o in enumerate(q.options)
        ]

        questions_out.append(
            QuestionOut(
                id=q.id,
                question_type=q.question_type,
                question_text=q.text,  # ✅ 여기 수정
                explanation=q.explanation,
                order=q.order,
                options=options_out,
            )
        )

    return ProblemSetOut(
        id=ps.id,
        passage_id=ps.passage_id,
        name=ps.name,
        types=[],  # 이제 필요 없음
        mode=ps.mode,
        questions=questions_out,
    )


# ======================================================
# 📌 조회 API
# ======================================================
@router.get("/by_passage/{passage_id}")
def get_problem_sets_by_passage(
    passage_id: int,
    db: Session = Depends(get_db),
):
    return db.query(models.ProblemSet).filter(
        models.ProblemSet.passage_id == passage_id
    ).all()


@router.get("/folders")
def list_teacher_problem_set_folders(
    parent_id: int | None = None,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_role("teacher")),
):
    problem_sets = _visible_problem_sets(db, current_user)
    counts = _count_map(problem_sets)
    folders = _children(db, parent_id)

    items = []
    if parent_id is None and counts.get(None, 0) > 0:
        items.append({
            "folder_id": None,
            "parent_id": None,
            "folder_name": UNFILED_NAME,
            "count": counts[None],
            "has_children": False,
            "is_unfiled": True,
            "is_direct_bucket": False,
        })

    if parent_id is not None and counts.get(parent_id, 0) > 0:
        items.append({
            "folder_id": parent_id,
            "parent_id": parent_id,
            "folder_name": DIRECT_BUCKET_NAME,
            "count": counts[parent_id],
            "has_children": False,
            "is_unfiled": False,
            "is_direct_bucket": True,
        })

    for folder in folders:
        child_count = len(_children(db, folder.id))
        total = _folder_total_count(db, folder.id, counts)
        if total <= 0 and child_count <= 0:
            continue
        items.append({
            "folder_id": folder.id,
            "parent_id": folder.parent_id,
            "folder_name": folder.name,
            "count": total,
            "has_children": child_count > 0,
            "is_unfiled": False,
            "is_direct_bucket": False,
        })

    items.sort(key=lambda item: (item["is_unfiled"], _sort_key(item["folder_name"])))
    return {"items": items}


@router.get("/list")
def list_teacher_problem_sets(
    folder_id: int | None = None,
    unfiled: bool = False,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_role("teacher")),
):
    problem_sets = _visible_problem_sets(db, current_user)
    if unfiled:
        problem_sets = [ps for ps in problem_sets if _problem_set_folder_id(ps) is None]
    elif folder_id is not None:
        problem_sets = [ps for ps in problem_sets if _problem_set_folder_id(ps) == folder_id]

    problem_sets.sort(
        key=lambda ps: (
            ps.created_at is None,
            ps.created_at or 0,
            ps.id,
        ),
        reverse=True,
    )
    return [_serialize_problem_set_summary(db, ps) for ps in problem_sets]


@router.get("/{problem_set_id}/report")
def get_teacher_problem_set_report(
    problem_set_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_role("teacher")),
):
    problem_set = (
        db.query(models.ProblemSet)
        .filter(models.ProblemSet.id == problem_set_id)
        .first()
    )
    if not problem_set:
        raise HTTPException(status_code=404, detail="ProblemSet not found")

    questions = (
        db.query(models.Question)
        .filter(models.Question.problem_set_id == problem_set_id)
        .order_by(models.Question.order.asc(), models.Question.id.asc())
        .all()
    )
    attempts = (
        db.query(models.ExamAttempt)
        .filter(models.ExamAttempt.problem_set_id == problem_set_id)
        .all()
    )
    latest_attempts = _latest_attempts_by_user(attempts)
    latest_attempts.sort(key=_attempt_key, reverse=True)

    attempt_ids = [attempt.id for attempt in latest_attempts]
    answers = []
    if attempt_ids:
        answers = (
            db.query(models.StudentAnswer)
            .filter(models.StudentAnswer.attempt_id.in_(attempt_ids))
            .all()
        )

    answers_by_attempt: dict[int, dict[int, models.StudentAnswer]] = {}
    for answer in answers:
        answers_by_attempt.setdefault(answer.attempt_id, {})[answer.question_id] = answer

    participant_count = len(latest_attempts)
    scores = [attempt.score or 0 for attempt in latest_attempts]
    average_score = round(sum(scores) / participant_count, 1) if scores else 0
    highest_score = max(scores) if scores else 0
    lowest_score = min(scores) if scores else 0
    assigned_count = (
        db.query(models.ExamAssignment)
        .filter(models.ExamAssignment.problem_set_id == problem_set_id)
        .count()
    )
    denominator = assigned_count or participant_count
    completion_rate = (
        int(round((participant_count / denominator) * 100)) if denominator else 0
    )

    grouped = {}
    for question in questions:
        q_type = (question.question_type or "unknown").lower()
        bucket = grouped.setdefault(
            q_type,
            {
                "type": q_type,
                "label": _type_label(q_type),
                "correct_count": 0,
                "total": 0,
            },
        )
        for attempt in latest_attempts:
            bucket["total"] += 1
            answer = answers_by_attempt.get(attempt.id, {}).get(question.id)
            if answer and answer.is_correct:
                bucket["correct_count"] += 1

    type_stats = []
    for item in grouped.values():
        total = item["total"]
        correct = item["correct_count"]
        item["accuracy"] = int(round((correct / total) * 100)) if total else 0
        type_stats.append(item)
    type_stats.sort(key=_type_sort_key)

    users = {}
    if latest_attempts:
        user_ids = [attempt.user_id for attempt in latest_attempts]
        users = {
            user.id: user
            for user in db.query(models.User).filter(models.User.id.in_(user_ids)).all()
        }

    students = []
    for attempt in latest_attempts:
        answer_map = answers_by_attempt.get(attempt.id, {})
        weak_types = []
        for question in questions:
            answer = answer_map.get(question.id)
            if not answer or not answer.is_correct:
                label = _type_label(question.question_type)
                if label not in weak_types:
                    weak_types.append(label)

        user = users.get(attempt.user_id)
        students.append(
            {
                "user_id": attempt.user_id,
                "nickname": getattr(user, "nickname", None) or f"student{attempt.user_id}",
                "score": attempt.score or 0,
                "correct_count": attempt.correct_count or 0,
                "total_questions": attempt.total_questions or len(questions),
                "submitted_at": attempt.created_at.isoformat() if attempt.created_at else None,
                "weak_types": weak_types,
            }
        )

    weak_types = [
        item["label"]
        for item in sorted(type_stats, key=lambda item: item["accuracy"])
        if item["total"] > 0 and item["accuracy"] < 70
    ][:3]
    if not weak_types and type_stats:
        weak_types = [sorted(type_stats, key=lambda item: item["accuracy"])[0]["label"]]

    folder_context = _folder_context(db, problem_set)

    return {
        "problem_set_id": problem_set.id,
        "title": problem_set.name,
        "description": problem_set.description,
        "question_count": len(questions),
        "folder_id": _problem_set_folder_id(problem_set),
        **folder_context,
        "assigned_count": assigned_count,
        "participant_count": participant_count,
        "average_score": average_score,
        "highest_score": highest_score,
        "lowest_score": lowest_score,
        "completion_rate": completion_rate,
        "type_stats": type_stats,
        "students": students,
        "weak_types": weak_types,
        "recommended_types": weak_types,
    }


@router.get("/{problem_set_id}/questions")
def get_questions_by_problem_set(
    problem_set_id: int,
    db: Session = Depends(get_db),
):
    questions = db.query(models.Question).filter(
        models.Question.problem_set_id == problem_set_id
    ).order_by(models.Question.order.asc()).all()

    result = []

    for q in questions:
        options = db.query(models.Option).filter(
            models.Option.question_id == q.id
        ).order_by(models.Option.label.asc()).all()

        options_list = []

    for opt in options:
        options_list.append({
            "id": opt.id,
            "label": opt.label,
            "text": opt.text
        })

    result.append({
        "id": q.id,
        "question_type": q.question_type,
        "question_text": q.text,
        "answer_index": q.answer_index,
        "options": options_list
})
    return result
