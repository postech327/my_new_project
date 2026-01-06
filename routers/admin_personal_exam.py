from typing import Dict, List
import random
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func, case

from db import get_db
import models

router = APIRouter(
    prefix="/admin/exams",
    tags=["admin_personal_exam"],
)

# =====================================================
# 학생 개인 맞춤 시험지 자동 생성
# =====================================================
@router.post("/personal/{user_id}")
def generate_personal_exam(
    user_id: int,
    title: str = "개인 맞춤 시험지",
    question_count: int = 20,
    created_by: str = "admin",
    db: Session = Depends(get_db),
):
    # 1️⃣ 학생 확인
    user = db.get(models.User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # 2️⃣ 유형별 성취도 분석
    rows = (
        db.query(
            models.Question.question_type,
            func.count(models.StudentAnswer.id).label("total"),
            func.sum(
                case(
                    (models.StudentAnswer.is_correct == True, 1),
                    else_=0,
                )
            ).label("correct"),
        )
        .join(models.StudentAnswer)
        .filter(models.StudentAnswer.user_id == user_id)
        .group_by(models.Question.question_type)
        .all()
    )

    if not rows:
        raise HTTPException(status_code=400, detail="No study data for this user")

    type_accuracy: Dict[str, float] = {}
    for r in rows:
        rate = round((r.correct / r.total) * 100, 2)
        type_accuracy[r.question_type] = rate

    # 3️⃣ 약점 → 강점 유형 분류
    sorted_types = sorted(type_accuracy.items(), key=lambda x: x[1])

    weak_types = [t for t, _ in sorted_types[:1]]
    mid_types = [t for t, _ in sorted_types[1:3]]
    strong_types = [t for t, _ in sorted_types[3:]]

    # 4️⃣ 유형별 출제 개수
    type_distribution = {
        "weak": int(question_count * 0.5),
        "mid": int(question_count * 0.3),
        "strong": question_count - int(question_count * 0.8),
    }

    selected_questions: List[models.Question] = []

    def pick_questions(types: List[str], count: int):
        pool = (
            db.query(models.Question)
            .filter(
                models.Question.question_type.in_(types),
                models.Question.difficulty_level.in_(["hard", "medium"]),
            )
            .all()
        )
        if len(pool) < count:
            raise HTTPException(
                status_code=400,
                detail=f"Not enough questions for types={types}",
            )
        return random.sample(pool, count)

    # 5️⃣ 문제 선택
    selected_questions.extend(pick_questions(weak_types, type_distribution["weak"]))
    if mid_types:
        selected_questions.extend(pick_questions(mid_types, type_distribution["mid"]))
    if strong_types:
        selected_questions.extend(
            pick_questions(strong_types, type_distribution["strong"])
        )

    # 6️⃣ Passage 생성
    passage = models.Passage(
        title=f"{user.nickname} 개인 맞춤 시험지",
        content="(학생 개인 성취도 기반 자동 생성 시험지)",
        created_by=created_by,
    )
    db.add(passage)
    db.flush()

    # 7️⃣ ProblemSet 생성
    problem_set = models.ProblemSet(
        passage_id=passage.id,
        name=title,
        description=f"{user.nickname} 맞춤 시험지",
        created_by=created_by,
        mode="teacher",
        is_published=False,
    )
    db.add(problem_set)
    db.flush()

    # 8️⃣ 문제 연결
    random.shuffle(selected_questions)
    for order, q in enumerate(selected_questions, start=1):
        q.problem_set_id = problem_set.id
        q.passage_id = passage.id
        q.order = order

    db.commit()

    return {
        "user_id": user.id,
        "nickname": user.nickname,
        "problem_set_id": problem_set.id,
        "total_questions": len(selected_questions),
        "weak_types": weak_types,
        "message": "Personalized exam generated successfully",
    }