# routers/teacher.py
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from db import get_db
import models, schemas
from services.gpt_question_generator import generate_mcq_questions_from_passage

router = APIRouter(
    prefix="/teacher",
    tags=["teacher"],
)

# ───────────────────────────
# Passage
# ───────────────────────────


@router.post(
    "/passages",
    response_model=schemas.PassageOut,
    status_code=status.HTTP_201_CREATED,
)
def create_passage(
    passage: schemas.PassageCreate,
    db: Session = Depends(get_db),
):
    try:
        db_passage = models.Passage(
            title=passage.title,
            content=passage.content,
            source=passage.source,
            level=passage.level,
            created_by=passage.created_by,
        )
        db.add(db_passage)
        db.commit()
        db.refresh(db_passage)

        return {
            "id": db_passage.id,
            "title": db_passage.title,
            "content": db_passage.content,
            "source": db_passage.source,
            "level": db_passage.level,
            "created_by": db_passage.created_by,
        }
    except Exception as e:
        print("create_passage error:", repr(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/passages", response_model=List[schemas.PassageOut])
def list_passages(
    db: Session = Depends(get_db),
    skip: int = 0,
    limit: int = Query(50, le=200),
):
    passages = (
        db.query(models.Passage)
        .order_by(models.Passage.id.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )

    return [
        {
            "id": p.id,
            "title": p.title,
            "content": p.content,
            "source": p.source,
            "level": p.level,
            "created_by": p.created_by,
        }
        for p in passages
    ]


@router.get("/passages/{passage_id}", response_model=schemas.PassageOut)
def get_passage(passage_id: int, db: Session = Depends(get_db)):
    passage = (
        db.query(models.Passage)
        .filter(models.Passage.id == passage_id)
        .first()
    )
    if not passage:
        raise HTTPException(status_code=404, detail="Passage not found")

    return {
        "id": passage.id,
        "title": passage.title,
        "content": passage.content,
        "source": passage.source,
        "level": passage.level,
        "created_by": passage.created_by,
    }


# ───────────────────────────
# ProblemSet
# ───────────────────────────


@router.post(
    "/problem-sets",
    response_model=schemas.ProblemSetOut,
    status_code=status.HTTP_201_CREATED,
)
def create_problem_set(
    problem_set: schemas.ProblemSetCreate,
    db: Session = Depends(get_db),
):
    try:
        passage = (
            db.query(models.Passage)
            .filter(models.Passage.id == problem_set.passage_id)
            .first()
        )
        if not passage:
            raise HTTPException(status_code=404, detail="Passage not found")

        db_ps = models.ProblemSet(
            passage_id=problem_set.passage_id,
            name=problem_set.name,
            description=problem_set.description,
            created_by=problem_set.created_by,
        )
        db.add(db_ps)
        db.commit()
        db.refresh(db_ps)

        return {
            "id": db_ps.id,
            "passage_id": db_ps.passage_id,
            "name": db_ps.name,
            "description": db_ps.description,
            "created_by": db_ps.created_by,
        }
    except HTTPException:
        raise
    except Exception as e:
        print("create_problem_set error:", repr(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/problem-sets", response_model=List[schemas.ProblemSetOut])
def list_problem_sets(
    db: Session = Depends(get_db),
    passage_id: Optional[int] = None,
    skip: int = 0,
    limit: int = Query(50, le=200),
):
    q = db.query(models.ProblemSet)
    if passage_id is not None:
        q = q.filter(models.ProblemSet.passage_id == passage_id)

    rows = (
        q.order_by(models.ProblemSet.id.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )

    return [
        {
            "id": ps.id,
            "passage_id": ps.passage_id,
            "name": ps.name,
            "description": ps.description,
            "created_by": ps.created_by,
        }
        for ps in rows
    ]


# ───────────────────────────
# Question / Option
# ───────────────────────────


@router.post(
    "/questions",
    response_model=schemas.QuestionOut,
    status_code=status.HTTP_201_CREATED,
)
def create_question(
    question: schemas.QuestionCreate,
    db: Session = Depends(get_db),
):
    try:
        passage = (
            db.query(models.Passage)
            .filter(models.Passage.id == question.passage_id)
            .first()
        )
        if not passage:
            raise HTTPException(status_code=404, detail="Passage not found")

        if question.problem_set_id is not None:
            ps = (
                db.query(models.ProblemSet)
                .filter(models.ProblemSet.id == question.problem_set_id)
                .first()
            )
            if not ps:
                raise HTTPException(status_code=404, detail="ProblemSet not found")

        db_question = models.Question(
            passage_id=question.passage_id,
            problem_set_id=question.problem_set_id,
            question_type=question.question_type,
            stem=question.stem,
            extra_info=question.extra_info,
            explanation=question.explanation,
            order_index=question.order_index,
        )
        db.add(db_question)
        db.flush()  # question.id 확보

        correct_option_id = None
        for opt in question.options:
            db_opt = models.QuestionOption(
                question_id=db_question.id,
                label=opt.label,
                text=opt.text,
                is_correct=opt.is_correct,
            )
            db.add(db_opt)
            db.flush()
            if opt.is_correct:
                correct_option_id = db_opt.id

        if correct_option_id is not None:
            db_question.correct_option_id = correct_option_id

        db.commit()
        db.refresh(db_question)

        return {
            "id": db_question.id,
            "passage_id": db_question.passage_id,
            "problem_set_id": db_question.problem_set_id,
            "question_type": db_question.question_type,
            "stem": db_question.stem,
            "extra_info": db_question.extra_info,
            "explanation": db_question.explanation,
            "order_index": db_question.order_index,
            "options": [
                {
                    "id": opt.id,
                    "label": opt.label,
                    "text": opt.text,
                    "is_correct": opt.is_correct,
                }
                for opt in db_question.options
            ],
        }
    except HTTPException:
        raise
    except Exception as e:
        print("create_question error:", repr(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.post(
    "/questions/bulk",
    response_model=List[schemas.QuestionOut],
    status_code=status.HTTP_201_CREATED,
)
def create_questions_bulk(
    payload: schemas.QuestionBulkCreate,
    db: Session = Depends(get_db),
):
    try:
        passage = (
            db.query(models.Passage)
            .filter(models.Passage.id == payload.passage_id)
            .first()
        )
        if not passage:
            raise HTTPException(status_code=404, detail="Passage not found")

        if payload.problem_set_id is not None:
            ps = (
                db.query(models.ProblemSet)
                .filter(models.ProblemSet.id == payload.problem_set_id)
                .first()
            )
            if not ps:
                raise HTTPException(status_code=404, detail="ProblemSet not found")

        created_questions: List[models.Question] = []

        for q in payload.questions:
            db_q = models.Question(
                passage_id=payload.passage_id,
                problem_set_id=payload.problem_set_id,
                question_type=q.question_type,
                stem=q.stem,
                extra_info=q.extra_info,
                explanation=q.explanation,
                order_index=q.order_index,
            )
            db.add(db_q)
            db.flush()

            correct_option_id = None
            for opt in q.options:
                db_opt = models.QuestionOption(
                    question_id=db_q.id,
                    label=opt.label,
                    text=opt.text,
                    is_correct=opt.is_correct,
                )
                db.add(db_opt)
                db.flush()
                if opt.is_correct:
                    correct_option_id = db_opt.id

            if correct_option_id is not None:
                db_q.correct_option_id = correct_option_id

            created_questions.append(db_q)

        db.commit()
        for q in created_questions:
            db.refresh(q)

        return [
            {
                "id": q.id,
                "passage_id": q.passage_id,
                "problem_set_id": q.problem_set_id,
                "question_type": q.question_type,
                "stem": q.stem,
                "extra_info": q.extra_info,
                "explanation": q.explanation,
                "order_index": q.order_index,
                "options": [
                    {
                        "id": opt.id,
                        "label": opt.label,
                        "text": opt.text,
                        "is_correct": opt.is_correct,
                    }
                    for opt in q.options
                ],
            }
            for q in created_questions
        ]
    except HTTPException:
        raise
    except Exception as e:
        print("create_questions_bulk error:", repr(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/questions", response_model=List[schemas.QuestionOut])
def list_questions(
    db: Session = Depends(get_db),
    passage_id: Optional[int] = None,
    problem_set_id: Optional[int] = None,
    question_type: Optional[str] = None,
    skip: int = 0,
    limit: int = Query(100, le=300),
):
    q = db.query(models.Question)

    if passage_id is not None:
        q = q.filter(models.Question.passage_id == passage_id)
    if problem_set_id is not None:
        q = q.filter(models.Question.problem_set_id == problem_set_id)
    if question_type is not None:
        q = q.filter(models.Question.question_type == question_type)

    q = q.order_by(
        models.Question.problem_set_id.asc().nullsfirst(),
        models.Question.order_index.asc().nullslast(),
        models.Question.id.asc(),
    )

    rows = q.offset(skip).limit(limit).all()

    return [
        {
            "id": row.id,
            "passage_id": row.passage_id,
            "problem_set_id": row.problem_set_id,
            "question_type": row.question_type,
            "stem": row.stem,
            "extra_info": row.extra_info,
            "explanation": row.explanation,
            "order_index": row.order_index,
            "options": [
                {
                    "id": opt.id,
                    "label": opt.label,
                    "text": opt.text,
                    "is_correct": opt.is_correct,
                }
                for opt in row.options
            ],
        }
        for row in rows
    ]


# ───────────────────────────
# Teacher: Question Set + GPT
# ───────────────────────────


@router.post("/question-sets", response_model=schemas.TeacherQuestionSetOut)
async def create_question_set(
    payload: schemas.TeacherQuestionSetCreate,
    db: Session = Depends(get_db),
):
    """
    선생님 모드에서:
    - 지문(Passage)
    - ProblemSet
    - Question + QuestionOption 들
    을 한 번에 저장하는 엔드포인트.

    동작 방식
    1) payload.questions 가 비어 있지 않으면 → 그 내용을 그대로 저장
    2) 비어 있으면 → GPT로 num_questions 개 자동 생성 후 저장
    """

    # 1) Passage 생성
    passage = models.Passage(
        title=payload.passage_title,
        content=payload.passage_content,
        source=None,
        level=None,
        created_by="teacher",
    )
    db.add(passage)
    db.flush()  # passage.id 확보

    # 2) ProblemSet 생성
    problem_set = models.ProblemSet(
        passage_id=passage.id,
        name=payload.problem_set_name or "샘플 세트",
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
                question_type=payload.question_type or "all",  # ← 추가
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

    # 4) Question + QuestionOption 저장
    for order_idx, q in enumerate(question_dicts, start=1):
        options = q.get("options", [])

        question = models.Question(
            passage_id=passage.id,
            problem_set_id=problem_set.id,
            question_type=q.get("question_type", "mcq"),
            stem=q.get("stem", ""),
            extra_info=q.get("extra_info"),
            explanation=q.get("explanation"),
            order_index=order_idx,
        )
        db.add(question)
        db.flush()  # question.id 확보

        # 우선순위: correct_option_label > options 중 is_correct=True
        correct_label = q.get("correct_option_label")
        if not correct_label:
            correct_label = next(
                (opt.get("label") for opt in options if opt.get("is_correct")),
                None,
            )

        correct_option_id = None
        for opt in options:
            db_opt = models.QuestionOption(
                question_id=question.id,
                label=opt.get("label"),
                text=opt.get("text"),
                is_correct=(
                    opt.get("label") == correct_label
                    or bool(opt.get("is_correct"))
                ),
            )
            db.add(db_opt)
            db.flush()
            if db_opt.is_correct:
                correct_option_id = db_opt.id

        if correct_option_id is not None:
            question.correct_option_id = correct_option_id

    # 5) 커밋 + 응답
    db.commit()
    db.refresh(passage)
    db.refresh(problem_set)

    return schemas.TeacherQuestionSetOut(
        passage=passage,
        problem_set=problem_set,
        problem_set_id=problem_set.id,
    )


# ───────────────────────────
# GPT로 문제 미리보기(run_question)
# ───────────────────────────


@router.post("/run_question", response_model=schemas.RunQuestionResponse)
async def run_question(
    payload: schemas.RunQuestionRequest,
    db: Session = Depends(get_db),  # 지금은 사용 안 하지만 나중 확장 대비
):
    """
    선생님이 보낸 지문을 가지고 GPT로 객관식 문제들을 생성해서 돌려주는 엔드포인트.
    - DB 저장 X, 미리보기용
    - 프런트에서는 이 응답을 받아서 화면에 표시만 하고,
      '확정' 버튼을 누르면 /teacher/question-sets 로 저장 요청을 보내는 구조로 사용 가능.
    """

    # GPT 호출 (유형 포함)
    raw_questions = await generate_mcq_questions_from_passage(
        passage_content=payload.passage_content,
        num_questions=payload.num_questions,
        question_type=payload.question_type,
    )

    # Dict → Pydantic QuestionWithOptionsCreate 로 변환
    questions = [
        schemas.QuestionWithOptionsCreate(**q) for q in raw_questions
    ]

    return schemas.RunQuestionResponse(questions=questions)