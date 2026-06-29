from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func
from collections import defaultdict
from datetime import datetime, timedelta

from db import get_db
from utils.security import require_role
import models

router = APIRouter(
    prefix="/student/dashboard",
    tags=["student_dashboard"],
)

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


def _record_folder_id(record: models.AnalysisRecord):
    return getattr(record, "folder_id", None) or getattr(record.passage, "folder_id", None)


def _problem_set_folder_id(problem_set: models.ProblemSet):
    return getattr(problem_set, "folder_id", None) or getattr(
        problem_set.passage, "folder_id", None
    )


def _folder_action_context(db: Session, folder_id: int | None):
    if folder_id is None:
        return {}

    unit_folder = db.query(models.Folder).filter(models.Folder.id == folder_id).first()
    if unit_folder is None:
        return {}

    book_folder = None
    if unit_folder.parent_id is not None:
        book_folder = (
            db.query(models.Folder)
            .filter(models.Folder.id == unit_folder.parent_id)
            .first()
        )
    else:
        book_folder = unit_folder

    return {
        "book_folder_id": book_folder.id if book_folder else None,
        "book_folder_name": book_folder.name if book_folder else None,
        "unit_folder_id": unit_folder.id,
        "unit_folder_name": unit_folder.name,
    }


def _first_unviewed_final_touch_context(db: Session, user_id: int):
    viewed_ids = (
        db.query(models.FinalTouchView.analysis_record_id)
        .filter(models.FinalTouchView.user_id == user_id)
        .subquery()
    )
    record = (
        db.query(models.AnalysisRecord)
        .filter(~models.AnalysisRecord.id.in_(viewed_ids))
        .order_by(models.AnalysisRecord.created_at.desc(), models.AnalysisRecord.id.desc())
        .first()
    )
    if record is None:
        return {}
    return _folder_action_context(db, _record_folder_id(record))


def _first_unattempted_problem_set_context(db: Session, user_id: int):
    attempted_ids = (
        db.query(models.ExamAttempt.problem_set_id)
        .filter(models.ExamAttempt.user_id == user_id)
        .subquery()
    )
    problem_set = (
        db.query(models.ProblemSet)
        .filter(~models.ProblemSet.id.in_(attempted_ids))
        .order_by(models.ProblemSet.created_at.desc(), models.ProblemSet.id.desc())
        .first()
    )
    if problem_set is None:
        return {}
    return _folder_action_context(db, _problem_set_folder_id(problem_set))


def _latest_low_score_context(db: Session, user_id: int):
    attempt = (
        db.query(models.ExamAttempt)
        .filter(models.ExamAttempt.user_id == user_id)
        .filter(models.ExamAttempt.score < 60)
        .order_by(models.ExamAttempt.created_at.desc(), models.ExamAttempt.id.desc())
        .first()
    )
    if attempt is None:
        attempt = (
            db.query(models.ExamAttempt)
            .filter(models.ExamAttempt.user_id == user_id)
            .order_by(models.ExamAttempt.created_at.desc(), models.ExamAttempt.id.desc())
            .first()
        )
    if attempt is None:
        return {}
    problem_set = (
        db.query(models.ProblemSet)
        .filter(models.ProblemSet.id == attempt.problem_set_id)
        .first()
    )
    if problem_set is None:
        return {}
    return _folder_action_context(db, _problem_set_folder_id(problem_set))


def _build_recommendations(
    *,
    db: Session,
    user_id: int,
    weak_types: list[str],
    average_score: float | int | None,
    recent_dates,
):
    total_final_touches = db.query(models.AnalysisRecord).count()
    viewed_final_touches = (
        db.query(models.FinalTouchView)
        .filter(models.FinalTouchView.user_id == user_id)
        .count()
    )
    total_problem_sets = db.query(models.ProblemSet).count()
    attempted_problem_sets = (
        db.query(models.ExamAttempt.problem_set_id)
        .filter(models.ExamAttempt.user_id == user_id)
        .distinct()
        .count()
    )

    unviewed_final_touches = max(total_final_touches - viewed_final_touches, 0)
    unattempted_problem_sets = max(total_problem_sets - attempted_problem_sets, 0)

    recommendations = []
    if unviewed_final_touches > 0:
        recommendations.append({
            "type": "final_touch",
            "message": f"미열람 Final Touch {unviewed_final_touches}개를 먼저 확인하세요.",
            "priority": "high",
            "action_label": "Final Touch 보기",
            "route": "/student/final-touch",
            **_first_unviewed_final_touch_context(db, user_id),
        })
    if unattempted_problem_sets > 0:
        recommendations.append({
            "type": "problem_set",
            "message": f"미응시 문제세트 {unattempted_problem_sets}개를 완료하세요.",
            "priority": "high",
            "action_label": "시험 보러가기",
            "route": "/student/exams",
            **_first_unattempted_problem_set_context(db, user_id),
        })
    if weak_types:
        recommendations.append({
            "type": "weak_type",
            "message": f"약점 유형: {', '.join(weak_types[:3])}. 보충 문제를 다시 풀어보세요.",
            "priority": "medium",
            "action_label": "보충 문제 보기",
            "route": "/student/exams",
            **_latest_low_score_context(db, user_id),
        })
    if average_score is not None and average_score < 60 and attempted_problem_sets > 0:
        recommendations.append({
            "type": "review",
            "message": "평균 점수가 60점 미만입니다. Final Touch를 다시 보고 오답을 복습하세요.",
            "priority": "medium",
            "action_label": "Final Touch 보기",
            "route": "/student/final-touch",
            **_latest_low_score_context(db, user_id),
        })

    clean_dates = [value for value in recent_dates if value]
    if clean_dates:
        if datetime.utcnow() - max(clean_dates) > timedelta(days=7):
            recommendations.append({
                "type": "stale",
                "message": "최근 학습 기록이 오래되었습니다. 오늘 1세트를 풀어보세요.",
                "priority": "low",
                "action_label": "시험 보러가기",
                "route": "/student/exams",
                **_first_unattempted_problem_set_context(db, user_id),
            })
    else:
        recommendations.append({
            "type": "start",
            "message": "오늘 Final Touch 1개와 문제세트 1개부터 시작하세요.",
            "priority": "medium",
            "action_label": "시험 보러가기",
            "route": "/student/exams",
            **_first_unattempted_problem_set_context(db, user_id),
        })

    return recommendations


def _serialize_assigned_recommendation(item: models.AssignedRecommendation):
    route = item.target_route
    rec_type = item.recommendation_type
    if route == "/student/final-touch" or rec_type in {"final_touch", "review"}:
        action_label = "Final Touch 보기"
    elif route == "/student/exams" or rec_type in {"problem_set", "weak_type", "start", "stale"}:
        action_label = "시험 보러가기"
    else:
        action_label = "바로가기"

    return {
        "id": item.id,
        "type": rec_type,
        "recommendation_type": rec_type,
        "message": item.message,
        "priority": item.priority,
        "action_label": action_label,
        "route": route,
        "target_route": route,
        "book_folder_id": item.book_folder_id,
        "unit_folder_id": item.unit_folder_id,
        "problem_set_id": item.problem_set_id,
        "analysis_record_id": item.analysis_record_id,
        "status": item.status,
        "assigned_at": item.assigned_at.isoformat() if item.assigned_at else None,
        "teacher_name": item.teacher.nickname if item.teacher else None,
        "source": "teacher",
        "is_teacher_assigned": True,
        "assigned_recommendation_id": item.id,
    }


def _assigned_recommendations(db: Session, user_id: int):
    return [
        _serialize_assigned_recommendation(item)
        for item in (
            db.query(models.AssignedRecommendation)
            .filter(
                models.AssignedRecommendation.student_id == user_id,
                models.AssignedRecommendation.status == "assigned",
            )
            .order_by(
                models.AssignedRecommendation.assigned_at.desc(),
                models.AssignedRecommendation.id.desc(),
            )
            .all()
        )
    ]


@router.get("")
def get_student_dashboard(
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_role("student")),
):
    user_id = int(current_user["sub"])

    # =====================================================
    # 1) 학생의 시험 시도 조회
    # =====================================================
    attempts = (
        db.query(models.ExamAttempt)
        .filter(models.ExamAttempt.user_id == user_id)
        .order_by(models.ExamAttempt.created_at.desc())
        .all()
    )

    if not attempts:
        recommendations = _build_recommendations(
            db=db,
            user_id=user_id,
            weak_types=[],
            average_score=None,
            recent_dates=[],
        )
        assigned_recommendations = _assigned_recommendations(db, user_id)
        return {
            "student_id": user_id,
            "total_attempts": 0,
            "total_exams": 0,
            "average_score": 0,
            "best_score": 0,
            "latest_attempt_score": 0,
            "total_questions_solved": 0,
            "total_correct": 0,
            "accuracy": 0,
            "score_trend": [],
            "trend_direction": "stable",
            "by_type": {},
            "weakest_type": None,
            "recent_results": [],
            "assigned_recommendations": assigned_recommendations,
            "recommendations": assigned_recommendations + recommendations,
        }

    # =====================================================
    # 2) 시험별 최고 점수만 반영
    # =====================================================
    subquery = (
        db.query(
            models.ExamAttempt.problem_set_id,
            func.max(models.ExamAttempt.score).label("best_score"),
        )
        .filter(models.ExamAttempt.user_id == user_id)
        .group_by(models.ExamAttempt.problem_set_id)
        .subquery()
    )

    raw_best_attempts = (
        db.query(models.ExamAttempt)
        .join(
            subquery,
            (models.ExamAttempt.problem_set_id == subquery.c.problem_set_id)
            & (models.ExamAttempt.score == subquery.c.best_score),
        )
        .filter(models.ExamAttempt.user_id == user_id)
        .order_by(models.ExamAttempt.created_at.desc())
        .all()
    )

    best_attempts = []
    seen_problem_sets = set()

    for attempt in raw_best_attempts:
        if attempt.problem_set_id not in seen_problem_sets:
            best_attempts.append(attempt)
            seen_problem_sets.add(attempt.problem_set_id)

    total_exams = len(best_attempts)

    scores = [a.score or 0 for a in best_attempts]
    average_score = round(sum(scores) / total_exams, 2) if total_exams else 0
    best_score = max(scores) if scores else 0
    latest_attempt_score = attempts[0].score or 0

    total_questions_solved = sum(a.total_questions or 0 for a in attempts)
    total_correct = sum(a.correct_count or 0 for a in attempts)

    overall_accuracy = (
        round((total_correct / total_questions_solved) * 100, 2)
        if total_questions_solved > 0
        else 0
    )

    # =====================================================
    # 3) 최근 점수 흐름
    # =====================================================
    recent_attempts = attempts[:5]
    score_trend = [
        {
            "attempt_id": a.id,
            "problem_set_id": a.problem_set_id,
            "score": a.score or 0,
            "created_at": str(a.created_at),
        }
        for a in reversed(recent_attempts)
    ]

    trend_direction = "stable"
    if len(score_trend) >= 2:
        if score_trend[-1]["score"] > score_trend[-2]["score"]:
            trend_direction = "up"
        elif score_trend[-1]["score"] < score_trend[-2]["score"]:
            trend_direction = "down"

    # =====================================================
    # 4) 유형별 정답률 분석
    # =====================================================
    attempt_ids = [a.id for a in attempts]

    answers = (
        db.query(models.StudentAnswer)
        .join(models.Question, models.StudentAnswer.question_id == models.Question.id)
        .filter(models.StudentAnswer.attempt_id.in_(attempt_ids))
        .all()
    )

    by_type = defaultdict(lambda: {
        "total": 0,
        "correct": 0,
        "wrong": 0,
        "accuracy": 0.0,
    })

    for ans in answers:
        q_type = ans.question.question_type or "기타"
        by_type[q_type]["total"] += 1
        if ans.is_correct:
            by_type[q_type]["correct"] += 1
        else:
            by_type[q_type]["wrong"] += 1

    weakest_type = None
    lowest_accuracy = float("inf")
    weak_types = []

    for q_type, data in by_type.items():
        if data["total"] > 0:
            data["accuracy"] = round(
                (data["correct"] / data["total"]) * 100,
                2,
            )
            if data["accuracy"] < lowest_accuracy:
                lowest_accuracy = data["accuracy"]
                weakest_type = _type_label(q_type)

    weak_types = [
        _type_label(q_type)
        for q_type, data in sorted(by_type.items(), key=lambda item: item[1]["accuracy"])
        if data["total"] > 0 and data["accuracy"] < 70
    ][:3]

    # =====================================================
    # 5) 최근 결과 요약
    # =====================================================
    recent_results = [
        {
            "attempt_id": a.id,
            "problem_set_id": a.problem_set_id,
            "score": a.score or 0,
            "correct_count": a.correct_count or 0,
            "total_questions": a.total_questions or 0,
            "created_at": str(a.created_at),
        }
        for a in recent_attempts
    ]

    view_dates = [
        view.viewed_at
        for view in (
            db.query(models.FinalTouchView)
            .filter(models.FinalTouchView.user_id == user_id)
            .all()
        )
        if view.viewed_at
    ]
    recommendations = _build_recommendations(
        db=db,
        user_id=user_id,
        weak_types=weak_types,
        average_score=average_score,
        recent_dates=[attempt.created_at for attempt in attempts if attempt.created_at]
        + view_dates,
    )
    assigned_recommendations = _assigned_recommendations(db, user_id)

    return {
        "student_id": user_id,
        "total_attempts": len(attempts),
        "total_exams": total_exams,
        "average_score": average_score,
        "best_score": best_score,
        "latest_attempt_score": latest_attempt_score,
        "total_questions_solved": total_questions_solved,
        "total_correct": total_correct,
        "accuracy": overall_accuracy,
        "score_trend": score_trend,
        "trend_direction": trend_direction,
        "by_type": dict(by_type),
        "weakest_type": weakest_type,
        "weak_types": weak_types,
        "recent_results": recent_results,
        "assigned_recommendations": assigned_recommendations,
        "recommendations": assigned_recommendations + recommendations,
    }
