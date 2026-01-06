from typing import Dict, List
import random

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from db import get_db
import models

router = APIRouter(
    prefix="/admin/exams",
    tags=["admin_exam_generator"],
)

# =====================================================
# 1️⃣ 난이도 기반 시험지 자동 생성
# =====================================================
@router.post("/auto-generate")
def auto_generate_exam(
    title: str,
    question_count: int = 20,
    distribution: Dict[str, float] = {
        "hard": 0.5,
        "medium": 0.3,
        "easy": 0.2,
    },
    created_by: str = "admin",
    db: Session = Depends(get_db),
):
    """
    난이도 비율에 따라 문제를 자동 선택하여
    시험지(Passage + ProblemSet)를 생성한다.
    """

    # 1️⃣ 분포 검증
    if not distribution:
        raise HTTPException(status_code=400, detail="Distribution must not be empty")

    total_ratio = round(sum(distribution.values()), 2)
    if total_ratio != 1.0:
        raise HTTPException(
            status_code=400,
            detail="Distribution ratios must sum to 1.0",
        )

    for level in distribution.keys():
        if level not in ["easy", "medium", "hard"]:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid difficulty level: {level}",
            )

    # 2️⃣ 난이도별 문제 개수 계산
    counts: Dict[str, int] = {
        level: int(question_count * ratio)
        for level, ratio in distribution.items()
    }

    # 반올림 오차 보정
    while sum(counts.values()) < question_count:
        counts["hard"] += 1

    # 3️⃣ 문제 추출
    selected_questions: List[models.Question] = []

    for level, count in counts.items():
        if count == 0:
            continue

        pool = (
            db.query(models.Question)
            .filter(
                models.Question.difficulty_level == level,
                models.Question.difficulty_score.isnot(None),
            )
            .all()
        )

        if len(pool) < count:
            raise HTTPException(
                status_code=400,
                detail=f"Not enough '{level}' questions "
                       f"(required={count}, available={len(pool)})",
            )

        selected_questions.extend(random.sample(pool, count))

    # 4️⃣ Passage 생성
    passage = models.Passage(
        title=title,
        content="(난이도 기반 자동 생성 시험지)",
        created_by=created_by,
    )
    db.add(passage)
    db.flush()

    # 5️⃣ ProblemSet 생성
    problem_set = models.ProblemSet(
        passage_id=passage.id,
        name=title,
        description="난이도 기반 자동 생성 시험지",
        created_by=created_by,
        mode="teacher",
        is_published=False,
    )
    db.add(problem_set)
    db.flush()

    # 6️⃣ Question 연결
    random.shuffle(selected_questions)
    for order, q in enumerate(selected_questions, start=1):
        q.problem_set_id = problem_set.id
        q.passage_id = passage.id
        q.order = order

    db.commit()

    return {
        "problem_set_id": problem_set.id,
        "title": title,
        "total_questions": len(selected_questions),
        "distribution": counts,
    }


# =====================================================
# 2️⃣ 시험지 배정 (NEW)
# =====================================================
@router.post("/{problem_set_id}/assign")
def assign_exam_to_student(
    problem_set_id: int,
    user_id: int,
    db: Session = Depends(get_db),
):
    """
    생성된 시험지를 특정 학생에게 배정
    """

    # 시험지 존재 확인
    problem_set = db.query(models.ProblemSet).get(problem_set_id)
    if not problem_set:
        raise HTTPException(status_code=404, detail="ProblemSet not found")

    # 학생 존재 확인
    user = db.query(models.User).get(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # 중복 배정 방지
    exists = (
        db.query(models.ExamAssignment)
        .filter(
            models.ExamAssignment.user_id == user_id,
            models.ExamAssignment.problem_set_id == problem_set_id,
        )
        .first()
    )

    if exists:
        raise HTTPException(
            status_code=400,
            detail="This exam is already assigned to the student",
        )

    assignment = models.ExamAssignment(
        user_id=user_id,
        problem_set_id=problem_set_id,
    )

    db.add(assignment)
    db.commit()

    return {
        "message": "Exam assigned successfully",
        "user_id": user_id,
        "problem_set_id": problem_set_id,
    }