from typing import List
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from db import get_db
import models

router = APIRouter(
    prefix="/student/review",
    tags=["student_review_generator"],
)

# =====================================================
# ❌ 틀린 문제 기반 자동 복습 세트 생성
# =====================================================
@router.post("/auto-generate")
def generate_review_set(
    user_id: int,
    problem_set_id: int,
    db: Session = Depends(get_db),
):
    # 1️⃣ 학생 / 시험지 확인
    user = db.get(models.User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    origin_ps = db.get(models.ProblemSet, problem_set_id)
    if not origin_ps:
        raise HTTPException(status_code=404, detail="ProblemSet not found")

    # 2️⃣ 틀린 문제 조회
    wrong_answers = (
        db.query(models.StudentAnswer)
        .join(models.Question)
        .filter(
            models.StudentAnswer.user_id == user_id,
            models.Question.problem_set_id == problem_set_id,
            models.StudentAnswer.is_correct == False,
        )
        .all()
    )

    if not wrong_answers:
        return {
            "message": "No wrong questions. Review set not created.",
            "review_created": False,
        }

    wrong_questions: List[models.Question] = [
        a.question for a in wrong_answers
    ]

    # 3️⃣ 복습용 Passage 생성
    passage = models.Passage(
        title=f"{user.nickname} 오답 복습",
        content="(자동 생성된 오답 복습 세트)",
        created_by="system",
    )
    db.add(passage)
    db.flush()

    # 4️⃣ 복습용 ProblemSet 생성
    review_ps = models.ProblemSet(
        passage_id=passage.id,
        name="오답 복습 세트",
        description="틀린 문제 자동 복습",
        created_by="system",
        mode="student",
        is_published=True,
    )
    db.add(review_ps)
    db.flush()

    # 5️⃣ 문제 연결
    for order, q in enumerate(wrong_questions, start=1):
        q.problem_set_id = review_ps.id
        q.passage_id = passage.id
        q.order = order

    db.commit()

    return {
        "review_created": True,
        "review_problem_set_id": review_ps.id,
        "wrong_question_count": len(wrong_questions),
        "message": "Review problem set created successfully",
    }