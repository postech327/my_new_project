# routers/student_review.py
from __future__ import annotations

from typing import Any, Dict, List

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from sqlalchemy import func

from db import get_db
import models

# 🔹 OpenAI
from openai import OpenAI

client = OpenAI()

router = APIRouter(
    prefix="/student/review-sets",
    tags=["student_review"],
)

# ─────────────────────────────────────────────
# Utils
# ─────────────────────────────────────────────
def _db_get(db: Session, model, obj_id: int):
    get_fn = getattr(db, "get", None)
    if callable(get_fn):
        return db.get(model, obj_id)
    return db.query(model).filter(model.id == obj_id).first()


# ─────────────────────────────────────────────
# 1️⃣ 복습 세트 목록 조회
# ─────────────────────────────────────────────
@router.get("")
def list_review_sets(db: Session = Depends(get_db)):
    sets = (
        db.query(models.ProblemSet)
        .filter(
            models.ProblemSet.mode == "student",
            models.ProblemSet.created_by == "system",
            models.ProblemSet.is_published == True,
        )
        .order_by(models.ProblemSet.created_at.desc())
        .all()
    )

    results = []
    for ps in sets:
        count = (
            db.query(func.count(models.Question.id))
            .filter(models.Question.problem_set_id == ps.id)
            .scalar()
            or 0
        )

        results.append(
            {
                "problem_set_id": ps.id,
                "name": ps.name,
                "question_count": count,
                "created_at": ps.created_at,
            }
        )

    return results


# ─────────────────────────────────────────────
# 2️⃣ 복습 세트 시작
# ─────────────────────────────────────────────
@router.post("/{problem_set_id}/start")
def start_review_set(problem_set_id: int, db: Session = Depends(get_db)):
    ps = _db_get(db, models.ProblemSet, problem_set_id)
    if not ps or ps.mode != "student":
        raise HTTPException(status_code=404, detail="Review set not found")

    total = (
        db.query(func.count(models.Question.id))
        .filter(models.Question.problem_set_id == ps.id)
        .scalar()
        or 0
    )

    return {
        "problem_set_id": ps.id,
        "total_questions": total,
        "current_order": 1,
    }


# ─────────────────────────────────────────────
# 3️⃣ 복습 요약 + 유형별 성취 변화
# ─────────────────────────────────────────────
@router.get("/{problem_set_id}/summary")
def review_summary(
    problem_set_id: int,
    db: Session = Depends(get_db),
    user_id: int = 1,  # 🔴 임시
):
    questions = (
        db.query(models.Question)
        .filter(models.Question.problem_set_id == problem_set_id)
        .all()
    )

    if not questions:
        raise HTTPException(status_code=404, detail="Review set not found")

    q_ids = [q.id for q in questions]
    types = list({q.question_type for q in questions})

    answers = (
        db.query(models.StudentAnswer)
        .filter(
            models.StudentAnswer.user_id == user_id,
            models.StudentAnswer.question_id.in_(q_ids),
        )
        .all()
    )

    total = len(q_ids)
    correct = sum(1 for a in answers if a.is_correct)
    accuracy = round((correct / total) * 100, 2) if total else 0.0

    by_type = []
    for qt in types:
        prev = (
            db.query(models.StudentAnswer)
            .join(models.Question)
            .filter(
                models.StudentAnswer.user_id == user_id,
                models.Question.question_type == qt,
                models.StudentAnswer.question_id.notin_(q_ids),
            )
            .all()
        )

        prev_total = len(prev)
        prev_correct = sum(1 for a in prev if a.is_correct)
        prev_acc = (
            round((prev_correct / prev_total) * 100, 2) if prev_total else None
        )

        cur = [a for a in answers if a.question.question_type == qt]
        cur_total = len(cur)
        cur_correct = sum(1 for a in cur if a.is_correct)
        cur_acc = round((cur_correct / cur_total) * 100, 2) if cur_total else 0.0

        by_type.append(
            {
                "question_type": qt,
                "previous_accuracy": prev_acc,
                "current_accuracy": cur_acc,
                "improved": prev_acc is not None and cur_acc > prev_acc,
            }
        )

    return {
        "problem_set_id": problem_set_id,
        "accuracy_rate": accuracy,
        "by_type": by_type,
    }


# ─────────────────────────────────────────────
# 4️⃣ ⭐ GPT 코치 멘트 자동 생성 API
# ─────────────────────────────────────────────
class CoachMessageReq(BaseModel):
    problem_set_id: int
    summary: Dict[str, Any]


class CoachMessageRes(BaseModel):
    coach_message: str


@router.post("/coach-message", response_model=CoachMessageRes)
def generate_coach_message(
    req: CoachMessageReq,
):
    """
    복습 요약 결과를 바탕으로 GPT 코치 멘트 생성
    """

    summary = req.summary
    by_type = summary.get("by_type", [])

    prompt = f"""
너는 중고등학생 영어 학습을 도와주는 친절하고 전문적인 영어 코치야.

아래는 한 학생의 '복습 학습 결과 요약'이야.
이 결과를 바탕으로:
- 잘한 점은 칭찬하고
- 아직 부족한 유형은 구체적인 학습 조언을 해줘
- 전체 분량은 3~5문장
- 말투는 따뜻하고 동기부여 중심
- 한국어로 작성

[복습 요약 데이터]
{by_type}
"""

    completion = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": "You are a helpful English learning coach."},
            {"role": "user", "content": prompt},
        ],
        temperature=0.7,
        max_tokens=300,
    )

    message = completion.choices[0].message.content.strip()

    return {"coach_message": message}