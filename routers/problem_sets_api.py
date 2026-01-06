# routers/problem_sets_api.py
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from db import get_db
from models import ProblemSet, Question, Option
from schemas.problem_set import (
    ProblemSetGenerateRequest,
    ProblemSetOut,
    QuestionOut,
    OptionOut,
)
from services.question_set_service import create_problem_set_with_questions

router = APIRouter(
    prefix="/teacher/problem_sets",
    tags=["teacher-problem-sets"],
)


@router.post("/generate_and_save", response_model=ProblemSetOut)
def generate_and_save_problem_set(
    req: ProblemSetGenerateRequest,
    db: Session = Depends(get_db),
):
    """
    1) passage_id 지문으로 GPT에 문제 생성 요청
    2) ProblemSet / Question / Option DB 저장
    3) 방금 저장된 세트 + 문제/보기 목록 반환
    """
    try:
        ps = create_problem_set_with_questions(db, req)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    # 응답용으로 questions/options를 한 번에 구성
    questions_out: list[QuestionOut] = []
    for q in ps.questions:
        options_out = [
            OptionOut(label=o.label, text=o.text, is_correct=o.is_correct)
            for o in q.options
        ]
        questions_out.append(
            QuestionOut(
                id=q.id,
                question_type=q.question_type,
                text=q.text,
                explanation=q.explanation,
                order=q.order,
                options=options_out,
            )
        )

    return ProblemSetOut(
        id=ps.id,
        passage_id=ps.passage_id,
        name=ps.name,
        types=ps.types_json or [],
        mode=ps.mode,
        questions=questions_out,
    )