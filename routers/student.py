# routers/student.py

from typing import List, Optional
import random
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from db import get_db
import models
import schemas

router = APIRouter(
    prefix="/student",
    tags=["student"],
)


# ─────────────────────────────────────────────
# 0) 학생용: 문제 세트 목록 조회 (+ 유형 필터)
# ─────────────────────────────────────────────
@router.get(
    "/problem_sets",
    response_model=List[schemas.StudentProblemSetSummary],
    summary="학생용 문제 세트 목록 조회",
)
def list_student_problem_sets(
    question_type: Optional[str] = Query(
        default=None,
        description="문제 유형 필터: topic/title/gist/summary/cloze/insertion/order/all. 비우면 전체.",
    ),
    db: Session = Depends(get_db),
):
    """
    학생 모드에서 풀 수 있는 문제 세트 목록 조회 엔드포인트.

    ⚙️ 전제:
    - ProblemSet 모델에는 최소한 id, passage_id 정도만 있다고 가정.
    - question_type, title, created_at 등은 없을 수 있음.
    - 각 ProblemSet 안의 Question 들은 보통 같은 question_type 을 가진다고 가정.
    """

    # 1) 기본 ProblemSet 쿼리
    query = db.query(models.ProblemSet)

    # 2) question_type 필터가 들어오면 Question 기준으로 필터링
    if question_type and question_type != "all":
        # 해당 question_type 을 가진 Question 의 problem_set_id 목록을 추출
        rows = (
            db.query(models.Question.problem_set_id)
            .filter(models.Question.question_type == question_type)
            .distinct()
            .all()
        )
        ps_ids = [r[0] for r in rows]

        if not ps_ids:
            # 해당 유형의 세트가 없으면 빈 리스트 반환
            return []

        query = query.filter(models.ProblemSet.id.in_(ps_ids))

    # 3) id 기준으로 최신순 정렬
    problem_sets: List[models.ProblemSet] = (
        query.order_by(models.ProblemSet.id.desc()).all()
    )

    results: List[schemas.StudentProblemSetSummary] = []

    for ps in problem_sets:
        # (1) 문제 수
        num_q = (
            db.query(models.Question)
            .filter(models.Question.problem_set_id == ps.id)
            .count()
        )

        # (2) 제목: ProblemSet에 title이 있으면 사용, 없으면 기본 문자열
        title = getattr(ps, "title", None)
        if not title:
            title = f"Problem Set {ps.id}"

        # (3) created_at: 있으면 사용, 없으면 현재 시각으로 대체
        created = getattr(ps, "created_at", None)
        if created is None:
            created = datetime.utcnow()

        # (4) question_type: 해당 세트의 첫 번째 Question 기준
        first_q = (
            db.query(models.Question)
            .filter(models.Question.problem_set_id == ps.id)
            .order_by(models.Question.id.asc())
            .first()
        )
        if first_q is not None:
            q_type = first_q.question_type
        else:
            q_type = "mixed"  # 혹시 질문이 하나도 없으면 임시 값

        results.append(
            schemas.StudentProblemSetSummary(
                id=ps.id,
                title=title,
                question_type=q_type,
                num_questions=num_q,
                created_at=created,
            )
        )

    return results


# ─────────────────────────────────────────────
# 1) 학생용: 문제 세트 불러오기
# ─────────────────────────────────────────────
@router.get("/questions", response_model=schemas.StudentQuestionSetOut)
def get_student_questions(
    problem_set_id: int = Query(..., description="문제 세트 ID"),
    shuffle: bool = Query(False, description="문항 순서를 섞을지 여부"),
    db: Session = Depends(get_db),
):
    """
    학생 모드에서 사용하는
    특정 problem_set_id 에 대한 '지문 + 전체 문항' 조회 엔드포인트
    """

    # 1) ProblemSet & Passage 확인
    problem_set = (
        db.query(models.ProblemSet)
        .filter(models.ProblemSet.id == problem_set_id)
        .first()
    )
    if not problem_set:
        raise HTTPException(status_code=404, detail="Problem set not found")

    passage = problem_set.passage  # models.ProblemSet.passage 관계 사용
    if not passage:
        raise HTTPException(status_code=500, detail="Passage not found for this set")

    # 2) 질문 목록 조회
    questions: List[models.Question] = (
        db.query(models.Question)
        .filter(models.Question.problem_set_id == problem_set_id)
        .order_by(models.Question.id.asc())
        .all()
    )

    if not questions:
        raise HTTPException(status_code=404, detail="No questions in this set")

    # 필요하면 섞기
    if shuffle:
        random.shuffle(questions)

    # 3) Pydantic 스키마로 변환
    question_items: List[schemas.StudentQuestionOut] = []

    for q in questions:
        option_items = [
            schemas.StudentOptionOut(
                id=opt.id,
                label=opt.label,
                text=opt.text,
            )
            for opt in q.options
        ]

        question_items.append(
            schemas.StudentQuestionOut(
                id=q.id,
                passage_id=q.passage_id,
                problem_set_id=q.problem_set_id,
                question_type=q.question_type,
                # ✅ DB 컬럼 이름은 text 이므로 여기서 text → stem 으로 매핑
                stem=q.text,
                extra_info=None,
                order_index=None,
                options=option_items,
            )
        )

    # 4) 최종 응답
    return schemas.StudentQuestionSetOut(
        passage_id=passage.id,
        passage_title=passage.title,
        passage_content=passage.content,
        problem_set_id=problem_set.id,
        questions=question_items,
    )


# ─────────────────────────────────────────────
# 2) 학생용: 정답 확인 엔드포인트
# ─────────────────────────────────────────────
# Flutter 에서 호출하는 경로: POST /student/check-answer
@router.post("/check-answer", response_model=schemas.StudentAnswerCheckResult)
# 혹시 나중에 언더스코어 버전으로도 호출할 수 있게 alias 추가 (Swagger에는 안 보이게)
@router.post(
    "/check_answer",
    response_model=schemas.StudentAnswerCheckResult,
    include_in_schema=False,
)
def check_student_answer(
    payload: schemas.StudentAnswerCheckRequest,
    db: Session = Depends(get_db),
):
    """
    선택한 보기의 정답 여부를 확인하는 엔드포인트
    """

    # 1) 질문 존재 여부 확인
    question = (
        db.query(models.Question)
        .filter(models.Question.id == payload.question_id)
        .first()
    )
    if not question:
        raise HTTPException(status_code=404, detail="Question not found")

    # 2) 선택한 보기 확인 (해당 질문의 보기인지도 체크)
    selected_option = (
        db.query(models.Option)
        .filter(
            models.Option.id == payload.selected_option_id,
            models.Option.question_id == question.id,
        )
        .first()
    )
    if not selected_option:
        raise HTTPException(status_code=404, detail="Option not found")

    # 3) 정답 보기 찾기
    correct_option = (
        db.query(models.Option)
        .filter(
            models.Option.question_id == question.id,
            models.Option.is_correct.is_(True),
        )
        .first()
    )

    is_correct = bool(selected_option.is_correct)
    correct_option_id = correct_option.id if correct_option else selected_option.id

    # 지금 Question 모델에는 explanation 컬럼이 없으니 일단 None으로 내려줌
    return schemas.StudentAnswerCheckResult(
        question_id=question.id,
        selected_option_id=payload.selected_option_id,
        correct=is_correct,
        correct_option_id=correct_option_id,
        explanation=None,
    )