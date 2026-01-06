from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from openai import OpenAI

from db import get_db
import models

router = APIRouter(
    prefix="/student/explain",
    tags=["student_gpt_explain"],
)

client = OpenAI()

# =====================================================
# 🤖 GPT 오답 설명 생성
# =====================================================
@router.post("/wrong")
def explain_wrong_answer(
    user_id: int,
    question_id: int,
    db: Session = Depends(get_db),
):
    # 1️⃣ 학생 / 문제 확인
    user = db.get(models.User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    q = db.get(models.Question, question_id)
    if not q:
        raise HTTPException(status_code=404, detail="Question not found")

    # 2️⃣ 학생의 가장 최근 답안 확인
    sa = (
        db.query(models.StudentAnswer)
        .filter(
            models.StudentAnswer.user_id == user_id,
            models.StudentAnswer.question_id == question_id,
        )
        .order_by(models.StudentAnswer.created_at.desc())
        .first()
    )

    if not sa or sa.is_correct:
        raise HTTPException(
            status_code=400,
            detail="This question is not a wrong answer for the user",
        )

    # 3️⃣ 보기 구성
    options = q.options
    correct_option = options[q.answer_index]
    selected_option = options[sa.selected_index]

    # 4️⃣ GPT 프롬프트
    prompt = f"""
너는 학생의 영어 학습을 도와주는 친절한 AI 튜터야.

[문제]
{q.text}

[학생이 고른 답]
{selected_option.label}. {selected_option.text}

[정답]
{correct_option.label}. {correct_option.text}

다음을 포함해서 한국어로 설명해줘:
1. 이 문제에서 무엇을 묻고 있는지
2. 학생이 왜 이 선택지를 골랐을 가능성이 있는지
3. 정답이 되는 핵심 이유
4. 다음에 비슷한 문제를 풀 때 기억하면 좋은 팁

설명은 중학생~고등학생 눈높이에 맞게 4~6문장으로 작성해줘.
"""

    completion = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": "You are an English tutor."},
            {"role": "user", "content": prompt},
        ],
        temperature=0.5,
        max_tokens=400,
    )

    explanation = completion.choices[0].message.content.strip()

    return {
        "question_id": q.id,
        "question_type": q.question_type,
        "gpt_explanation": explanation,
    }