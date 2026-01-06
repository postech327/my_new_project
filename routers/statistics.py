# routers/statistics.py
from __future__ import annotations

from typing import Dict, List

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import func, case

from db import get_db
import models

router = APIRouter(
    prefix="/statistics",
    tags=["statistics"],
)

# ======================================================
# 1️⃣ 학생 개인별 약점 유형 추출 (내부 공용 로직)
# ======================================================
def _get_weak_question_types(db: Session, user_id: int, threshold: float = 60.0) -> List[str]:
    rows = (
        db.query(
            models.Question.question_type.label("question_type"),
            func.count(models.StudentAnswer.id).label("total_attempts"),
            func.sum(
                case(
                    (models.StudentAnswer.is_correct == True, 1),
                    else_=0,
                )
            ).label("correct_attempts"),
        )
        .join(models.Question, models.StudentAnswer.question_id == models.Question.id)
        .filter(models.StudentAnswer.user_id == user_id)
        .group_by(models.Question.question_type)
        .all()
    )

    weak_types: List[str] = []

    for r in rows:
        total = r.total_attempts or 0
        correct = r.correct_attempts or 0
        accuracy = (correct / total) * 100 if total else 0.0

        if accuracy < threshold:
            weak_types.append(r.question_type)

    return weak_types


# ======================================================
# 2️⃣ 추천 문제로 자동 복습 세트 생성 API ⭐⭐⭐
# ======================================================
@router.post("/students/{user_id}/auto-review-set")
def create_auto_review_problem_set(
    user_id: int,
    limit: int = Query(10, ge=3, le=30),
    db: Session = Depends(get_db),
) -> Dict:
    """
    학생 약점 유형 기반 자동 복습 ProblemSet 생성
    """

    user = db.get(models.User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # 1️⃣ 약점 유형 추출
    weak_types = _get_weak_question_types(db, user_id)

    if not weak_types:
        raise HTTPException(
            status_code=400,
            detail="No weak question types detected",
        )

    # 2️⃣ 추천 문제 선택
    questions = (
        db.query(models.Question)
        .filter(models.Question.question_type.in_(weak_types))
        .order_by(models.Question.id.desc())
        .limit(limit)
        .all()
    )

    if not questions:
        raise HTTPException(status_code=400, detail="No questions found for weak types")

    # 3️⃣ 대표 Passage 선택 (첫 문제 기준)
    base_passage = questions[0].passage

    # 4️⃣ ProblemSet 생성
    ps = models.ProblemSet(
        passage_id=base_passage.id,
        name=f"Auto Review Set ({', '.join(weak_types)})",
        description="Automatically generated review set based on your weak question types.",
        created_by="system",
        types_json=weak_types,
        mode="student",
        is_published=True,
    )
    db.add(ps)
    db.flush()  # ps.id 확보

    # 5️⃣ Question + Option 복사
    for idx, q in enumerate(questions, start=1):
        new_q = models.Question(
            question_type=q.question_type,
            text=q.text,
            explanation=q.explanation,
            order=idx,
            answer_index=q.answer_index,
            passage_id=base_passage.id,
            problem_set_id=ps.id,
        )
        db.add(new_q)
        db.flush()  # new_q.id

        for opt in q.options:
            db.add(
                models.Option(
                    question_id=new_q.id,
                    label=opt.label,
                    text=opt.text,
                )
            )

    db.commit()

    return {
        "message": "Auto review problem set created",
        "problem_set_id": ps.id,
        "weak_types": weak_types,
        "question_count": len(questions),
    }