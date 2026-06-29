from typing import List, Dict

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from db import get_db
import models
from utils.auth_jwt import get_current_user

router = APIRouter(
    prefix="/student/learning",
    tags=["student_learning_flow"],
)

# =====================================================
# 1️⃣ 학습 시작: 개인 맞춤 시험지 불러오기
# =====================================================
@router.get("/start/{problem_set_id}")
def start_learning(
    problem_set_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),  # ✅ JWT 인증
):
    ps = db.get(models.ProblemSet, problem_set_id)
    if not ps:
        raise HTTPException(status_code=404, detail="ProblemSet not found")

    passage = ps.passage

    questions = (
        db.query(models.Question)
        .filter(models.Question.problem_set_id == ps.id)
        .order_by(models.Question.order.asc())
        .all()
    )

    return {
        "problem_set_id": ps.id,
        "title": ps.name,
        "passage": {
            "title": passage.title,
            "content": passage.content,
        },
        "questions": [
            {
                "question_id": q.id,
                "question_type": q.question_type,
                "stem": q.text,
                "options": [
                    {
                        "option_id": o.id,
                        "label": o.label,
                        "text": o.text,
                    }
                    for o in q.options
                ],
            }
            for q in questions
        ],
    }


# =====================================================
# 2️⃣ 답안 제출 & 자동 채점
# =====================================================
@router.post("/submit")
def submit_answers(
    answers: List[Dict],  # [{question_id, selected_index}]
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),  # ✅ JWT 인증
):
    user_id = int(current_user["sub"])

    user = db.get(models.User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    results = []

    for a in answers:
        q = db.get(models.Question, a["question_id"])
        if not q:
            continue

        is_correct = q.answer_index == a["selected_index"]

        sa = models.StudentAnswer(
            user_id=user.id,
            question_id=q.id,
            selected_index=a["selected_index"],
            is_correct=is_correct,
        )
        db.add(sa)

        results.append(
            {
                "question_id": q.id,
                "is_correct": is_correct,
            }
        )

    db.commit()

    return {
        "user_id": user.id,
        "submitted": len(results),
        "results": results,
    }


# =====================================================
# 3️⃣ 학습 결과 요약
# =====================================================
@router.get("/result/{problem_set_id}")
def learning_result(
    problem_set_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),  # ✅ JWT 인증
):
    user_id = int(current_user["sub"])

    answers = (
        db.query(models.StudentAnswer)
        .join(models.Question)
        .filter(
            models.StudentAnswer.user_id == user_id,
            models.Question.problem_set_id == problem_set_id,
        )
        .all()
    )


    if not answers:
        raise HTTPException(status_code=400, detail="No answers found")

    total = len(answers)
    correct = sum(1 for a in answers if a.is_correct)
    accuracy = round((correct / total) * 100, 2)

    # ----------------------------------
    # 유형별 성취도
    # ----------------------------------
    by_type: Dict[str, Dict] = {}
    for a in answers:
        qt = a.question.question_type
        by_type.setdefault(qt, {"total": 0, "correct": 0})
        by_type[qt]["total"] += 1
        if a.is_correct:
            by_type[qt]["correct"] += 1

    type_stats = {
        k: round((v["correct"] / v["total"]) * 100, 2)
        for k, v in by_type.items()
    }

    weak_types = [k for k, v in type_stats.items() if v < 60]

    # =====================================================
    # ✅ STEP 5-3: StudyReport 저장
    # =====================================================
    report = models.StudyReport(
        user_id=user_id,
        problem_set_id=problem_set_id,
        accuracy_rate=accuracy,
        weakest_type=weak_types[0] if weak_types else None,
    )
    db.add(report)
    db.commit()

    # ----------------------------------
    # 응답
    # ----------------------------------
    return {
        "problem_set_id": problem_set_id,
        "total_questions": total,
        "correct": correct,
        "accuracy": accuracy,
        "type_accuracy": type_stats,
        "weak_types": weak_types,
        "next_step": "review" if weak_types else "advance",
    }