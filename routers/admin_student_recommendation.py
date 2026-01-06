# routers/admin_student_recommendation.py

from typing import Dict, List
import random

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func, case

from db import get_db
import models

router = APIRouter(
    prefix="/admin/students",
    tags=["admin_student_recommendation"],
)

# =====================================================
# 1️⃣ 학생 유형별 약점 분석
# =====================================================
@router.get("/{user_id}/weak-types")
def get_student_weak_types(
    user_id: int,
    db: Session = Depends(get_db),
):
    rows = (
        db.query(
            models.Question.question_type,
            func.count(models.StudentAnswer.id).label("total"),
            func.sum(
                case(
                    (models.StudentAnswer.is_correct == False, 1),
                    else_=0,
                )
            ).label("wrong"),
        )
        .join(models.StudentAnswer)
        .filter(models.StudentAnswer.user_id == user_id)
        .group_by(models.Question.question_type)
        .all()
    )

    result = []
    for r in rows:
        if r.total == 0:
            continue
        result.append({
            "question_type": r.question_type,
            "wrong_rate": round((r.wrong / r.total) * 100, 2),
        })

    result.sort(key=lambda x: x["wrong_rate"], reverse=True)
    return result


# =====================================================
# 2️⃣ 🔥 학생 약점 기반 시험지 자동 생성 (STEP B-2)
# =====================================================
@router.post("/{user_id}/auto-exam")
def auto_generate_exam_for_student(
    user_id: int,
    title: str = "학생 맞춤 시험지",
    question_count: int = 20,
    db: Session = Depends(get_db),
):
    weak_types = get_student_weak_types(user_id, db)

    if not weak_types:
        raise HTTPException(status_code=400, detail="학생 데이터 부족")

    target_types = weak_types[:3]
    total_wrong = sum(t["wrong_rate"] for t in target_types)

    type_counts = {
        t["question_type"]: max(
            1,
            int(question_count * (t["wrong_rate"] / total_wrong))
        )
        for t in target_types
    }

    selected_questions = []

    for q_type, count in type_counts.items():
        pool = (
            db.query(models.Question)
            .filter(models.Question.question_type == q_type)
            .all()
        )
        if len(pool) < count:
            continue
        selected_questions.extend(random.sample(pool, count))

    if not selected_questions:
        raise HTTPException(status_code=400, detail="문제 부족")

    passage = models.Passage(
        title=title,
        content="(학생 약점 기반 자동 시험지)",
        created_by="admin",
    )
    db.add(passage)
    db.flush()

    problem_set = models.ProblemSet(
        passage_id=passage.id,
        name=title,
        description="학생 약점 기반 자동 시험지",
        created_by="admin",
        mode="teacher",
        is_published=False,
    )
    db.add(problem_set)
    db.flush()

    for idx, q in enumerate(selected_questions, start=1):
        q.problem_set_id = problem_set.id
        q.passage_id = passage.id
        q.order = idx

    db.commit()

    return {
        "problem_set_id": problem_set.id,
        "used_types": type_counts,
        "total_questions": len(selected_questions),
    }