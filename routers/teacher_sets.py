# routers/teacher_sets.py
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from db import get_db
import models
import schemas
from services.gpt_question_generator import generate_mcq_questions_from_passage

router = APIRouter(
    prefix="/teacher",
    tags=["teacher_question_sets"],
)


@router.post("/question-sets", response_model=schemas.QuestionSetSaveResult)
async def save_question_set(
    payload: schemas.TeacherQuestionSetCreate,
    db: Session = Depends(get_db),
):
    """
    선생님이 만든 지문 + 문제세트를 DB에 저장하고,
    저장된 passage / problem_set 정보를 돌려주는 엔드포인트

    동작 방식:
    - payload.questions 가 비어 있으면 → GPT로 num_questions 개 자동 생성
    - payload.questions 가 있으면 → 그대로 저장
    """

    # 1) 지문 저장 (passage)
    passage = models.Passage(
        title=payload.passage_title,
        content=payload.passage_content,
        source=None,
        level=None,
        created_by="teacher",  # TODO: 나중에 실제 선생님 ID
    )
    db.add(passage)
    db.flush()  # passage.id 확보

    # 2) 문제 세트 저장 (problem_set)
    problem_set = models.ProblemSet(
        passage_id=passage.id,
        name=payload.problem_set_name or "자동 생성 세트",
        description=payload.description,
        created_by="teacher",
    )
    db.add(problem_set)
    db.flush()  # problem_set.id 확보

    # 3) 저장할 question 데이터 준비
    question_dicts: List[dict] = []

    if payload.questions:
        # 선생님이 직접 만든 문제
        question_dicts = [q.dict() for q in payload.questions]
    else:
        # GPT 자동 생성
        try:
            question_dicts = await generate_mcq_questions_from_passage(
                passage_content=payload.passage_content,
                num_questions=payload.num_questions,
                question_type=payload.question_type or "all",
            )
        except Exception as e:
            db.rollback()
            raise HTTPException(
                status_code=500,
                detail=f"Failed to generate questions from GPT: {e}",
            )

    if not question_dicts:
        db.rollback()
        raise HTTPException(status_code=400, detail="No questions to save.")

    # 4) Question + Option 저장
    for q in question_dicts:
        options = q.get("options", [])

        # GPT 스키마: "stem" 또는 "text" 중 하나를 사용할 수 있으니 둘 다 체크
        stem_or_text = q.get("stem") or q.get("text") or ""

        question = models.Question(
            passage_id=passage.id,
            problem_set_id=problem_set.id,
            question_type=q.get("question_type", "mcq"),
            text=stem_or_text,
        )
        db.add(question)
        db.flush()  # question.id 확보

        # 정답 라벨(있으면)
        correct_label = q.get("correct_option_label")
        if not correct_label:
            correct_label = next(
                (opt.get("label") for opt in options if opt.get("is_correct")),
                None,
            )

        for opt in options:
            is_correct_flag = (
                opt.get("label") == correct_label
                or bool(opt.get("is_correct"))
            )

            db_opt = models.Option(
                question_id=question.id,
                label=opt.get("label"),
                text=opt.get("text"),
                is_correct=is_correct_flag,
            )
            db.add(db_opt)

    # 5) 커밋 + 응답
    db.commit()
    db.refresh(passage)
    db.refresh(problem_set)

    passage_out = schemas.PassageOut.model_validate(passage)
    problem_set_out = schemas.ProblemSetOut.model_validate(problem_set)

    return schemas.QuestionSetSaveResult(
        passage=passage_out,
        problem_set=problem_set_out,
        problem_set_id=problem_set.id,
    )


@router.get(
    "/question-sets/{problem_set_id}",
    response_model=schemas.StudentQuestionSetOut,
)
def get_question_set_for_preview(
    problem_set_id: int,
    db: Session = Depends(get_db),
):
    """
    선생님/학생 모드에서 둘 다 재사용할 수 있는
    '지문 + 문항 전체' 조회용 엔드포인트
    (구조는 /student/questions 와 동일한 StudentQuestionSetOut 사용)
    """

    problem_set = (
        db.query(models.ProblemSet)
        .filter(models.ProblemSet.id == problem_set_id)
        .first()
    )
    if not problem_set:
        raise HTTPException(status_code=404, detail="Problem set not found")

    passage = problem_set.passage

    questions = (
        db.query(models.Question)
        .filter(models.Question.problem_set_id == problem_set_id)
        .order_by(models.Question.id.asc())
        .all()
    )

    question_items: list[schemas.StudentQuestionOut] = []
    for q in questions:
        options = [
            schemas.StudentOptionOut(
                id=opt.id,
                label=opt.label,
                text=opt.text,
            )
            for opt in q.options
        ]

        # DB의 text → 응답의 stem 으로 매핑
        question_items.append(
            schemas.StudentQuestionOut(
                id=q.id,
                passage_id=q.passage_id,
                problem_set_id=problem_set.id,
                question_type=q.question_type,
                stem=q.text,
                extra_info=None,
                order_index=None,
                options=options,
            )
        )

    return schemas.StudentQuestionSetOut(
        passage_id=passage.id,
        passage_title=passage.title,
        passage_content=passage.content,
        problem_set_id=problem_set.id,
        questions=question_items,
    )