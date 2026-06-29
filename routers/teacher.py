# routers/teacher.py
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from db import get_db
import models
from utils.security import require_role

router = APIRouter(
    prefix="/teacher",
    tags=["teacher"],
)


class RecommendationAssignRequest(BaseModel):
    recommendation_type: str
    message: str
    priority: str = "medium"
    target_route: str | None = None
    book_folder_id: int | None = None
    unit_folder_id: int | None = None
    problem_set_id: int | None = None
    analysis_record_id: int | None = None

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


def _type_label(question_type: str):
    return TYPE_LABELS.get((question_type or "").lower(), question_type or "문제")


def _attempt_key(attempt: models.ExamAttempt):
    created_at = attempt.created_at.timestamp() if attempt.created_at else 0
    return (created_at, attempt.id or 0)


def _dated_key(item):
    created_at = item.created_at.timestamp() if item.created_at else 0
    return (created_at, item.id or 0)


def _record_folder_id(record: models.AnalysisRecord):
    return getattr(record, "folder_id", None) or getattr(record.passage, "folder_id", None)


def _problem_set_folder_id(problem_set: models.ProblemSet):
    return getattr(problem_set, "folder_id", None) or getattr(
        problem_set.passage, "folder_id", None
    )


def _latest_attempts_by_user_and_set(attempts):
    latest = {}
    for attempt in attempts:
        key = (attempt.user_id, attempt.problem_set_id)
        existing = latest.get(key)
        if existing is None or _attempt_key(attempt) > _attempt_key(existing):
            latest[key] = attempt
    return list(latest.values())


def _folder_context(db: Session, folder_id: int):
    unit_folder = db.query(models.Folder).filter(models.Folder.id == folder_id).first()
    if not unit_folder:
        raise HTTPException(status_code=404, detail="Folder not found")

    book_folder = None
    if unit_folder.parent_id is not None:
        book_folder = (
            db.query(models.Folder)
            .filter(models.Folder.id == unit_folder.parent_id)
            .first()
        )
    return unit_folder, book_folder


def _folder_records(db: Session, folder_id: int):
    return [
        record
        for record in db.query(models.AnalysisRecord).all()
        if _record_folder_id(record) == folder_id
    ]


def _folder_problem_sets(db: Session, folder_id: int):
    return [
        problem_set
        for problem_set in db.query(models.ProblemSet).all()
        if _problem_set_folder_id(problem_set) == folder_id
    ]


def _folder_names(db: Session, folder_id: int | None):
    if folder_id is None:
        return "미분류", "미분류"
    unit_folder = db.query(models.Folder).filter(models.Folder.id == folder_id).first()
    if not unit_folder:
        return "미분류", "미분류"
    if unit_folder.parent_id is None:
        return unit_folder.name, unit_folder.name
    book_folder = (
        db.query(models.Folder)
        .filter(models.Folder.id == unit_folder.parent_id)
        .first()
    )
    return book_folder.name if book_folder else "미분류", unit_folder.name


def _build_teacher_recommendations(
    *,
    unviewed_final_touches: int,
    unattempted_problem_sets: int,
    weak_types: list[str],
    average_score,
    recent_study_at,
):
    recommendations = []
    if unviewed_final_touches > 0:
        recommendations.append(
            {
                "type": "final_touch",
                "message": f"미열람 Final Touch {unviewed_final_touches}개를 먼저 확인하도록 안내하세요.",
                "priority": "high",
            }
        )
    if unattempted_problem_sets > 0:
        recommendations.append(
            {
                "type": "problem_set",
                "message": f"미응시 문제세트 {unattempted_problem_sets}개가 남아 있습니다.",
                "priority": "high",
            }
        )
    if weak_types:
        recommendations.append(
            {
                "type": "weak_type",
                "message": f"{', '.join(weak_types[:3])} 유형을 복습하세요.",
                "priority": "medium",
            }
        )
    if average_score is not None and average_score < 60:
        recommendations.append(
            {
                "type": "review",
                "message": "전체 평균이 60점 미만입니다. Final Touch와 오답 복습을 함께 권장하세요.",
                "priority": "medium",
            }
        )
    if recent_study_at:
        if datetime.utcnow() - recent_study_at > timedelta(days=7):
            recommendations.append(
                {
                    "type": "stale",
                    "message": "최근 학습 기록이 오래되었습니다. 오늘 1세트를 다시 시작하도록 안내하세요.",
                    "priority": "low",
                }
            )
    else:
        recommendations.append(
            {
                "type": "start",
                "message": "아직 학습 기록이 없습니다. Final Touch 1개와 문제세트 1개부터 시작하세요.",
                "priority": "medium",
            }
        )
    return recommendations


def _serialize_assigned_recommendation(item: models.AssignedRecommendation):
    return {
        "id": item.id,
        "type": item.recommendation_type,
        "recommendation_type": item.recommendation_type,
        "message": item.message,
        "priority": item.priority,
        "route": item.target_route,
        "target_route": item.target_route,
        "book_folder_id": item.book_folder_id,
        "unit_folder_id": item.unit_folder_id,
        "problem_set_id": item.problem_set_id,
        "analysis_record_id": item.analysis_record_id,
        "status": item.status,
        "assigned_at": item.assigned_at.isoformat() if item.assigned_at else None,
        "completed_at": item.completed_at.isoformat() if item.completed_at else None,
        "teacher_name": item.teacher.nickname if item.teacher else None,
        "source": "teacher",
        "is_teacher_assigned": True,
        "assigned_recommendation_id": item.id,
    }


def _mark_assigned_recommendations(
    db: Session,
    student_id: int,
    recommendations: list[dict],
):
    assigned_items = (
        db.query(models.AssignedRecommendation)
        .filter(
            models.AssignedRecommendation.student_id == student_id,
            models.AssignedRecommendation.status == "assigned",
        )
        .all()
    )
    assigned_by_key = {
        (item.recommendation_type, item.message): item for item in assigned_items
    }
    for recommendation in recommendations:
        rec_type = recommendation.get("type")
        if "route" not in recommendation:
            if rec_type in {"final_touch", "review"}:
                recommendation["route"] = "/student/final-touch"
            else:
                recommendation["route"] = "/student/exams"
        if "target_route" not in recommendation:
            recommendation["target_route"] = recommendation.get("route")
        if "action_label" not in recommendation:
            recommendation["action_label"] = (
                "Final Touch 보기"
                if recommendation.get("route") == "/student/final-touch"
                else "시험 보러가기"
            )
        key = (recommendation.get("type"), recommendation.get("message"))
        assigned = assigned_by_key.get(key)
        recommendation["is_assigned"] = assigned is not None
        if assigned:
            recommendation["assigned_recommendation_id"] = assigned.id
    return recommendations


@router.post("/students/{student_id}/recommendations")
def assign_student_recommendation(
    student_id: int,
    payload: RecommendationAssignRequest,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_role("teacher")),
):
    teacher_id = int(current_user["sub"])
    student = (
        db.query(models.User)
        .filter(models.User.id == student_id, models.User.role == "student")
        .first()
    )
    if not student:
        raise HTTPException(status_code=404, detail="Student not found")

    existing = (
        db.query(models.AssignedRecommendation)
        .filter(
            models.AssignedRecommendation.teacher_id == teacher_id,
            models.AssignedRecommendation.student_id == student_id,
            models.AssignedRecommendation.recommendation_type
            == payload.recommendation_type,
            models.AssignedRecommendation.message == payload.message,
            models.AssignedRecommendation.status == "assigned",
        )
        .first()
    )
    if existing:
        return _serialize_assigned_recommendation(existing)

    item = models.AssignedRecommendation(
        teacher_id=teacher_id,
        student_id=student_id,
        recommendation_type=payload.recommendation_type,
        message=payload.message,
        priority=payload.priority,
        target_route=payload.target_route,
        book_folder_id=payload.book_folder_id,
        unit_folder_id=payload.unit_folder_id,
        problem_set_id=payload.problem_set_id,
        analysis_record_id=payload.analysis_record_id,
        status="assigned",
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return _serialize_assigned_recommendation(item)


@router.get("/folders/{folder_id}/progress-report")
def get_folder_progress_report(
    folder_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_role("teacher")),
):
    unit_folder, book_folder = _folder_context(db, folder_id)
    records = _folder_records(db, folder_id)
    problem_sets = _folder_problem_sets(db, folder_id)
    problem_set_ids = [problem_set.id for problem_set in problem_sets]

    students = (
        db.query(models.User)
        .filter(models.User.role == "student")
        .order_by(models.User.nickname.asc(), models.User.id.asc())
        .all()
    )

    attempts = []
    if problem_set_ids:
        attempts = (
            db.query(models.ExamAttempt)
            .filter(models.ExamAttempt.problem_set_id.in_(problem_set_ids))
            .all()
        )
    latest_attempts = _latest_attempts_by_user_and_set(attempts)
    attempts_by_student: dict[int, list[models.ExamAttempt]] = {}
    for attempt in latest_attempts:
        attempts_by_student.setdefault(attempt.user_id, []).append(attempt)

    attempt_ids = [attempt.id for attempt in latest_attempts]
    answers = []
    if attempt_ids:
        answers = (
            db.query(models.StudentAnswer)
            .filter(models.StudentAnswer.attempt_id.in_(attempt_ids))
            .all()
        )
    answers_by_attempt: dict[int, list[models.StudentAnswer]] = {}
    for answer in answers:
        answers_by_attempt.setdefault(answer.attempt_id, []).append(answer)

    questions = []
    if problem_set_ids:
        questions = (
            db.query(models.Question)
            .filter(models.Question.problem_set_id.in_(problem_set_ids))
            .all()
        )
    question_type_by_id = {
        question.id: (question.question_type or "unknown").lower()
        for question in questions
    }

    total_students = len(students)
    total_problem_sets = len(problem_sets)
    total_final_touches = len(records)
    total_possible_exams = total_students * total_problem_sets
    taken_exam_count = len(latest_attempts)
    exam_attempt_rate = (
        int(round((taken_exam_count / total_possible_exams) * 100))
        if total_possible_exams
        else 0
    )
    scores = [attempt.score or 0 for attempt in latest_attempts]
    average_score = round(sum(scores) / len(scores), 1) if scores else 0

    record_ids = [record.id for record in records]
    student_ids = [student.id for student in students]
    final_touch_views = []
    if record_ids and student_ids:
        final_touch_views = (
            db.query(models.FinalTouchView)
            .filter(
                models.FinalTouchView.analysis_record_id.in_(record_ids),
                models.FinalTouchView.user_id.in_(student_ids),
            )
            .all()
        )
    views_by_student: dict[int, dict[int, models.FinalTouchView]] = {}
    for view in final_touch_views:
        views_by_student.setdefault(view.user_id, {})[view.analysis_record_id] = view

    total_possible_views = total_students * total_final_touches
    total_viewed_count = sum(len(views) for views in views_by_student.values())
    final_touch_view_rate = (
        int(round((total_viewed_count / total_possible_views) * 100))
        if total_possible_views
        else 0
    )

    completed_students = 0
    student_rows = []
    folder_wrong_counts: dict[str, int] = {}

    for student in students:
        student_attempts = attempts_by_student.get(student.id, [])
        student_views = views_by_student.get(student.id, {})
        if total_problem_sets and len(student_attempts) >= total_problem_sets:
            completed_students += 1

        student_scores = [attempt.score or 0 for attempt in student_attempts]
        student_average = (
            round(sum(student_scores) / len(student_scores), 1)
            if student_scores
            else None
        )
        recent_at = max(
            [attempt.created_at for attempt in student_attempts if attempt.created_at]
            + [view.viewed_at for view in student_views.values() if view.viewed_at],
            default=None,
        )

        weak_counts: dict[str, int] = {}
        for attempt in student_attempts:
            for answer in answers_by_attempt.get(attempt.id, []):
                if answer.is_correct:
                    continue
                label = _type_label(question_type_by_id.get(answer.question_id, "unknown"))
                weak_counts[label] = weak_counts.get(label, 0) + 1
                folder_wrong_counts[label] = folder_wrong_counts.get(label, 0) + 1

        weak_types = [
            label
            for label, _count in sorted(
                weak_counts.items(),
                key=lambda item: (-item[1], item[0]),
            )
        ][:3]

        student_rows.append(
            {
                "user_id": student.id,
                "nickname": student.nickname,
                "final_touch_viewed_count": len(student_views),
                "final_touch_total": total_final_touches,
                "problem_set_taken_count": len(student_attempts),
                "problem_set_total": total_problem_sets,
                "average_score": student_average,
                "weak_types": weak_types,
                "recent_learning_at": recent_at.isoformat() if recent_at else None,
            }
        )

    weak_types = [
        label
        for label, _count in sorted(
            folder_wrong_counts.items(),
            key=lambda item: (-item[1], item[0]),
        )
    ][:3]

    return {
        "folder_id": unit_folder.id,
        "book_folder_id": book_folder.id if book_folder else None,
        "book_folder_name": book_folder.name if book_folder else None,
        "unit_folder_id": unit_folder.id,
        "unit_folder_name": unit_folder.name,
        "final_touch_count": total_final_touches,
        "problem_set_count": total_problem_sets,
        "student_count": total_students,
        "final_touch_tracking_available": True,
        "final_touch_view_rate": final_touch_view_rate,
        "problem_set_attempt_rate": exam_attempt_rate,
        "average_score": average_score,
        "completed_student_count": completed_students,
        "incomplete_student_count": max(total_students - completed_students, 0),
        "students": student_rows,
        "weak_types": weak_types,
        "recommended_types": weak_types,
    }


@router.get("/folders/{folder_id}/students/{student_id}/progress-detail")
def get_student_folder_progress_detail(
    folder_id: int,
    student_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_role("teacher")),
):
    unit_folder, book_folder = _folder_context(db, folder_id)
    student = (
        db.query(models.User)
        .filter(models.User.id == student_id, models.User.role == "student")
        .first()
    )
    if not student:
        raise HTTPException(status_code=404, detail="Student not found")

    records = sorted(
        _folder_records(db, folder_id),
        key=_dated_key,
    )
    problem_sets = sorted(
        _folder_problem_sets(db, folder_id),
        key=_dated_key,
    )
    problem_set_ids = [ps.id for ps in problem_sets]
    record_ids = [record.id for record in records]

    attempts = []
    if problem_set_ids:
        attempts = (
            db.query(models.ExamAttempt)
            .filter(
                models.ExamAttempt.user_id == student_id,
                models.ExamAttempt.problem_set_id.in_(problem_set_ids),
            )
            .all()
        )
    latest_attempts = _latest_attempts_by_user_and_set(attempts)
    attempt_by_problem_set = {
        attempt.problem_set_id: attempt for attempt in latest_attempts
    }

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

    questions = []
    if problem_set_ids:
        questions = (
            db.query(models.Question)
            .filter(models.Question.problem_set_id.in_(problem_set_ids))
            .all()
        )
    questions_by_problem_set: dict[int, list[models.Question]] = {}
    for question in questions:
        questions_by_problem_set.setdefault(question.problem_set_id, []).append(question)

    views = []
    if record_ids:
        views = (
            db.query(models.FinalTouchView)
            .filter(
                models.FinalTouchView.user_id == student_id,
                models.FinalTouchView.analysis_record_id.in_(record_ids),
            )
            .all()
        )
    views_by_record = {view.analysis_record_id: view for view in views}

    problem_set_rows = []
    type_groups: dict[str, dict] = {}
    recent_dates = [view.viewed_at for view in views if view.viewed_at]
    scores = []

    for ps in problem_sets:
        attempt = attempt_by_problem_set.get(ps.id)
        weak_counts: dict[str, int] = {}
        if attempt:
            scores.append(attempt.score or 0)
            if attempt.created_at:
                recent_dates.append(attempt.created_at)
            answer_map = answers_by_attempt.get(attempt.id, {})
            for question in questions_by_problem_set.get(ps.id, []):
                q_type = (question.question_type or "unknown").lower()
                bucket = type_groups.setdefault(
                    q_type,
                    {
                        "type": q_type,
                        "label": _type_label(q_type),
                        "correct": 0,
                        "total": 0,
                    },
                )
                answer = answer_map.get(question.id)
                bucket["total"] += 1
                if answer and answer.is_correct:
                    bucket["correct"] += 1
                else:
                    label = _type_label(q_type)
                    weak_counts[label] = weak_counts.get(label, 0) + 1

        weak_types = [
            label
            for label, _count in sorted(
                weak_counts.items(),
                key=lambda item: (-item[1], item[0]),
            )
        ][:3]

        problem_set_rows.append(
            {
                "id": ps.id,
                "title": ps.name,
                "status": "completed" if attempt else "not_started",
                "score": attempt.score if attempt else None,
                "correct_count": attempt.correct_count if attempt else None,
                "total_questions": (
                    attempt.total_questions
                    if attempt
                    else len(questions_by_problem_set.get(ps.id, []))
                ),
                "submitted_at": attempt.created_at.isoformat() if attempt and attempt.created_at else None,
                "weak_types": weak_types,
            }
        )

    type_stats = []
    for item in type_groups.values():
        total = item["total"]
        correct = item["correct"]
        item["accuracy"] = int(round((correct / total) * 100)) if total else 0
        type_stats.append(item)
    type_stats.sort(key=lambda item: item["accuracy"])

    weak_types = [
        item["label"]
        for item in type_stats
        if item["total"] > 0 and item["accuracy"] < 70
    ][:3]

    final_touches = []
    for record in records:
        view = views_by_record.get(record.id)
        passage = record.passage
        final_touches.append(
            {
                "id": record.id,
                "source": getattr(passage, "source_title", None)
                or f"Final Touch #{record.id}",
                "viewed": view is not None,
                "viewed_at": view.viewed_at.isoformat() if view and view.viewed_at else None,
            }
        )

    recent_study_at = max(recent_dates).isoformat() if recent_dates else None
    average_score = round(sum(scores) / len(scores), 1) if scores else None
    unviewed_final_touch_count = max(len(records) - len(views_by_record), 0)
    unattempted_problem_set_count = max(len(problem_sets) - len(latest_attempts), 0)

    recommendations = []
    if unviewed_final_touch_count > 0:
        recommendations.append(
            {
                "type": "final_touch",
                "message": f"미열람 Final Touch {unviewed_final_touch_count}개를 먼저 확인하세요.",
                "priority": "high",
            }
        )
    if unattempted_problem_set_count > 0:
        recommendations.append(
            {
                "type": "problem_set",
                "message": f"미응시 문제세트 {unattempted_problem_set_count}개를 완료하세요.",
                "priority": "high",
            }
        )
    if weak_types:
        recommendations.append(
            {
                "type": "weak_type",
                "message": f"{', '.join(weak_types[:3])} 유형 보충 자료를 제공해 보세요.",
                "priority": "medium",
            }
        )
    if average_score is not None and average_score < 60:
        recommendations.append(
            {
                "type": "review",
                "message": "평균 점수가 60점 미만입니다. Final Touch를 다시 보고 오답을 복습하세요.",
                "priority": "medium",
            }
        )
    if recent_dates:
        if datetime.utcnow() - max(recent_dates) > timedelta(days=7):
            recommendations.append(
                {
                    "type": "stale",
                    "message": "최근 학습 기록이 오래되었습니다. 오늘 1세트를 풀어보세요.",
                    "priority": "low",
                }
            )
    else:
        recommendations.append(
            {
                "type": "stale",
                "message": "아직 학습 기록이 없습니다. Final Touch 1개와 문제세트 1개부터 시작하세요.",
                "priority": "medium",
                }
            )

    for recommendation in recommendations:
        recommendation.setdefault("book_folder_id", book_folder.id if book_folder else None)
        recommendation.setdefault("book_folder_name", book_folder.name if book_folder else None)
        recommendation.setdefault("unit_folder_id", unit_folder.id)
        recommendation.setdefault("unit_folder_name", unit_folder.name)

    recommendations = _mark_assigned_recommendations(
        db,
        student_id,
        recommendations,
    )

    return {
        "student": {
            "id": student.id,
            "nickname": student.nickname,
        },
        "folder": {
            "id": unit_folder.id,
            "name": unit_folder.name,
            "book_id": book_folder.id if book_folder else None,
            "book_name": book_folder.name if book_folder else None,
        },
        "summary": {
            "final_touch_viewed": len(views_by_record),
            "final_touch_total": len(records),
            "problem_sets_completed": len(latest_attempts),
            "problem_sets_total": len(problem_sets),
            "average_score": average_score,
            "recent_study_at": recent_study_at,
        },
        "problem_sets": problem_set_rows,
        "type_stats": type_stats,
        "final_touches": final_touches,
        "weak_types": weak_types,
        "recommendations": recommendations,
        "recommendation": (
            f"{', '.join(weak_types[:2])} 유형 보충 자료를 제공해 보세요."
            if weak_types
            else "아직 뚜렷한 약점 유형이 없습니다."
        ),
    }


@router.get("/students/{student_id}/overall-report")
def get_student_overall_report(
    student_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_role("teacher")),
):
    student = (
        db.query(models.User)
        .filter(models.User.id == student_id, models.User.role == "student")
        .first()
    )
    if not student:
        raise HTTPException(status_code=404, detail="Student not found")

    records = sorted(db.query(models.AnalysisRecord).all(), key=_dated_key)
    problem_sets = sorted(db.query(models.ProblemSet).all(), key=_dated_key)
    record_ids = [record.id for record in records]
    problem_set_ids = [problem_set.id for problem_set in problem_sets]

    views = []
    if record_ids:
        views = (
            db.query(models.FinalTouchView)
            .filter(
                models.FinalTouchView.user_id == student_id,
                models.FinalTouchView.analysis_record_id.in_(record_ids),
            )
            .all()
        )
    views_by_record = {view.analysis_record_id: view for view in views}

    attempts = []
    if problem_set_ids:
        attempts = (
            db.query(models.ExamAttempt)
            .filter(
                models.ExamAttempt.user_id == student_id,
                models.ExamAttempt.problem_set_id.in_(problem_set_ids),
            )
            .all()
        )
    latest_attempts = _latest_attempts_by_user_and_set(attempts)
    attempt_by_problem_set = {
        attempt.problem_set_id: attempt for attempt in latest_attempts
    }

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

    questions = []
    if problem_set_ids:
        questions = (
            db.query(models.Question)
            .filter(models.Question.problem_set_id.in_(problem_set_ids))
            .all()
        )
    questions_by_problem_set: dict[int, list[models.Question]] = {}
    for question in questions:
        questions_by_problem_set.setdefault(question.problem_set_id, []).append(question)

    type_groups: dict[str, dict] = {}
    for attempt in latest_attempts:
        answer_map = answers_by_attempt.get(attempt.id, {})
        for question in questions_by_problem_set.get(attempt.problem_set_id, []):
            q_type = (question.question_type or "unknown").lower()
            bucket = type_groups.setdefault(
                q_type,
                {
                    "type": q_type,
                    "label": _type_label(q_type),
                    "correct": 0,
                    "total": 0,
                },
            )
            answer = answer_map.get(question.id)
            bucket["total"] += 1
            if answer and answer.is_correct:
                bucket["correct"] += 1

    type_stats = []
    for item in type_groups.values():
        total = item["total"]
        correct = item["correct"]
        item["accuracy"] = int(round((correct / total) * 100)) if total else 0
        type_stats.append(item)
    type_stats.sort(key=lambda item: item["accuracy"])

    weak_types = [
        item["label"]
        for item in type_stats
        if item["total"] > 0 and item["accuracy"] < 70
    ][:3]

    recent_dates = [view.viewed_at for view in views if view.viewed_at] + [
        attempt.created_at for attempt in latest_attempts if attempt.created_at
    ]
    recent_study_at = max(recent_dates) if recent_dates else None
    scores = [attempt.score or 0 for attempt in latest_attempts]
    average_score = round(sum(scores) / len(scores), 1) if scores else None

    records_by_folder: dict[int | None, list[models.AnalysisRecord]] = {}
    for record in records:
        records_by_folder.setdefault(_record_folder_id(record), []).append(record)

    problem_sets_by_folder: dict[int | None, list[models.ProblemSet]] = {}
    for problem_set in problem_sets:
        problem_sets_by_folder.setdefault(
            _problem_set_folder_id(problem_set),
            [],
        ).append(problem_set)

    folder_ids = sorted(
        set(records_by_folder.keys()) | set(problem_sets_by_folder.keys()),
        key=lambda value: (value is None, value or 0),
    )
    folder_progress = []
    for folder_id in folder_ids:
        folder_records = records_by_folder.get(folder_id, [])
        folder_problem_sets = problem_sets_by_folder.get(folder_id, [])
        folder_attempts = [
            attempt_by_problem_set[problem_set.id]
            for problem_set in folder_problem_sets
            if problem_set.id in attempt_by_problem_set
        ]
        folder_scores = [attempt.score or 0 for attempt in folder_attempts]
        book_name, unit_name = _folder_names(db, folder_id)
        folder_progress.append(
            {
                "folder_id": folder_id,
                "book_folder": book_name,
                "unit_folder": unit_name,
                "final_touch_viewed": sum(
                    1 for record in folder_records if record.id in views_by_record
                ),
                "final_touch_total": len(folder_records),
                "problem_sets_completed": len(folder_attempts),
                "problem_sets_total": len(folder_problem_sets),
                "average_score": (
                    round(sum(folder_scores) / len(folder_scores), 1)
                    if folder_scores
                    else None
                ),
            }
        )

    problem_set_by_id = {problem_set.id: problem_set for problem_set in problem_sets}
    recent_results = []
    for attempt in sorted(latest_attempts, key=_attempt_key, reverse=True)[:5]:
        problem_set = problem_set_by_id.get(attempt.problem_set_id)
        recent_results.append(
            {
                "problem_set_id": attempt.problem_set_id,
                "title": (
                    problem_set.name
                    if problem_set
                    else f"Problem Set #{attempt.problem_set_id}"
                ),
                "score": attempt.score or 0,
                "correct_count": attempt.correct_count or 0,
                "total_questions": attempt.total_questions or 0,
                "submitted_at": (
                    attempt.created_at.isoformat() if attempt.created_at else None
                ),
            }
        )

    recommendations = _build_teacher_recommendations(
        unviewed_final_touches=max(len(records) - len(views_by_record), 0),
        unattempted_problem_sets=max(len(problem_sets) - len(latest_attempts), 0),
        weak_types=weak_types,
        average_score=average_score,
        recent_study_at=recent_study_at,
    )
    recommendations = _mark_assigned_recommendations(
        db,
        student_id,
        recommendations,
    )

    return {
        "student": {
            "id": student.id,
            "nickname": student.nickname,
        },
        "summary": {
            "final_touch_viewed": len(views_by_record),
            "final_touch_total": len(records),
            "problem_sets_completed": len(latest_attempts),
            "problem_sets_total": len(problem_sets),
            "average_score": average_score,
            "recent_study_at": (
                recent_study_at.isoformat() if recent_study_at else None
            ),
            "weak_types": weak_types,
        },
        "type_stats": type_stats,
        "folder_progress": folder_progress,
        "recent_results": recent_results,
        "recommendations": recommendations,
        "weak_types": weak_types,
    }


# 예시: 특정 지문 정보 조회
@router.get("/passages/{passage_id}")
def get_passage(
    passage_id: int,
    db: Session = Depends(get_db),
):
    """
    선생님용: 특정 Passage 한 개 조회
    (response_model / schemas 사용하지 않고 dict로 직접 반환)
    """
    passage = (
        db.query(models.Passage)
        .filter(models.Passage.id == passage_id)
        .first()
    )
    if not passage:
        raise HTTPException(status_code=404, detail="Passage not found")

    return {
        "id": passage.id,
        "title": passage.title,
        "content": passage.content,
        "source": passage.source,
        "level": passage.level,
        "created_by": passage.created_by,
    }
