# routers/student.py
from __future__ import annotations

from typing import Any, Dict, List

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from db import get_db
import models

router = APIRouter(
    prefix="/student",
    tags=["student"],
)

# ─────────────────────────────────────────────
# Utils
# ─────────────────────────────────────────────
def _db_get(db: Session, model, obj_id: int):
    """
    SQLAlchemy 버전 호환용 get 함수
    """
    get_fn = getattr(db, "get", None)
    if callable(get_fn):
        return db.get(model, obj_id)
    return db.query(model).filter(model.id == obj_id).first()


# ─────────────────────────────────────────────
# 1) 학생용: 문제 세트 목록 조회
# ─────────────────────────────────────────────
@router.get("/problem_sets")
def list_problem_sets(db: Session = Depends(get_db)) -> List[Dict[str, Any]]:
    """
    학생 대시보드:
    - 학생용 문제 세트 목록
    """

    problem_sets = (
        db.query(models.ProblemSet)
        .filter(models.ProblemSet.mode == "student")   # ✅ 핵심 수정
        .order_by(models.ProblemSet.created_at.desc())
        .all()
    )

    results: List[Dict[str, Any]] = []

    for ps in problem_sets:
        num_questions = (
            db.query(models.Question)
            .filter(models.Question.problem_set_id == ps.id)
            .count()
        )

        results.append({
            "id": ps.id,
            "title": ps.name,
            "question_type": ps.description,  # 또는 meta에서 가져와도 됨
            "numQuestions": num_questions,
        })

    return results


# ─────────────────────────────────────────────
# 2) 학생용: 특정 문제 세트 조회 (정답 숨김)
# ─────────────────────────────────────────────
@router.get("/problem_sets/{problem_set_id}")
def get_problem_set_for_student(
    problem_set_id: int,
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """
    학생용 문제 세트 조회
    - 정답(answer_index) 절대 노출 ❌
    """

    ps = _db_get(db, models.ProblemSet, problem_set_id)
    if not ps:
        raise HTTPException(status_code=404, detail="ProblemSet not found")

    if not ps.is_published:
        raise HTTPException(status_code=403, detail="ProblemSet not published")

    passage = ps.passage

    questions = (
        db.query(models.Question)
        .filter(models.Question.problem_set_id == ps.id)
        .order_by(models.Question.order.asc(), models.Question.id.asc())
        .all()
    )

    out_questions: List[Dict[str, Any]] = []

    for q in questions:
        out_questions.append(
            {
                "id": q.id,
                "passage_id": q.passage_id,
                "problem_set_id": ps.id,
                "question_type": q.question_type,
                "stem": q.text,          # DB text → Student stem
                "order_index": q.order,
                "options": [
                    {
                        "id": o.id,
                        "label": o.label,
                        "text": o.text,
                    }
                    for o in q.options
                ],
            }
        )

    return {
        "passage_id": passage.id,
        "passage_title": passage.title,
        "passage_content": passage.content,
        "problem_set_id": ps.id,
        "questions": out_questions,
    }


# ─────────────────────────────────────────────
# 3) 학생용: 정답 제출 & 채점 & 저장 (StudentAnswer)
# ─────────────────────────────────────────────
class SubmitAnswerReq(BaseModel):
    question_id: int
    selected_index: int = Field(ge=0)


class SubmitAnswerRes(BaseModel):
    id: int
    question_id: int
    selected_index: int
    is_correct: bool

    class Config:
        orm_mode = True


@router.post("/answers", response_model=SubmitAnswerRes)
def submit_answer(
    req: SubmitAnswerReq,
    db: Session = Depends(get_db),
    user_id: int = 1,  # 🔴 임시값: 로그인(JWT) 연동 시 교체
):
    """
    학생 정답 제출
    1) 서버 채점
    2) StudentAnswer 테이블에 기록 저장
    """

    # 1) Question 조회
    q = _db_get(db, models.Question, req.question_id)
    if not q:
        raise HTTPException(status_code=404, detail="Question not found")

    # 2) 객관식 여부 확인
    if q.answer_index is None:
        raise HTTPException(
            status_code=400,
            detail="This question does not support objective grading",
        )

    # 3) 선택지 범위 검증
    options_count = len(q.options)
    if req.selected_index < 0 or req.selected_index >= options_count:
        raise HTTPException(
            status_code=400,
            detail=f"selected_index out of range (0~{options_count - 1})",
        )

    # 4) 채점 (B안 핵심)
    is_correct = (req.selected_index == q.answer_index)

    # 5) 기존 풀이 기록 확인 (user_id + question_id)
    answer = (
        db.query(models.StudentAnswer)
        .filter(
            models.StudentAnswer.user_id == user_id,
            models.StudentAnswer.question_id == q.id,
        )
        .first()
    )

    if answer:
        # 이미 풀었던 문제 → 업데이트
        answer.selected_index = req.selected_index
        answer.is_correct = is_correct
    else:
        # 최초 풀이 → 새로 저장
        answer = models.StudentAnswer(
            user_id=user_id,
            question_id=q.id,
            selected_index=req.selected_index,
            is_correct=is_correct,
        )
        db.add(answer)

    db.commit()
    db.refresh(answer)

    return answer

# ─────────────────────────────────────────────
# 4) 학생용: 오답노트 조회
# ─────────────────────────────────────────────
@router.get("/wrong-notes")
def get_wrong_notes(
    db: Session = Depends(get_db),
    user_id: int = 1,  # 🔴 임시값 (로그인/JWT 연동 시 교체)
):
    """
    학생 오답노트
    - 내가 틀린 문제만 조회
    """

    answers = (
        db.query(models.StudentAnswer)
        .filter(
            models.StudentAnswer.user_id == user_id,
            models.StudentAnswer.is_correct == False,
        )
        .order_by(models.StudentAnswer.created_at.desc())
        .all()
    )

    results: List[Dict[str, Any]] = []

    for ans in answers:
        q = ans.question
        ps = q.problem_set
        passage = q.passage

        results.append(
            {
                "answer_id": ans.id,
                "question_id": q.id,
                "problem_set_id": ps.id if ps else None,
                "question_type": q.question_type,
                "stem": q.text,
                "options": [
                    {
                        "id": o.id,
                        "label": o.label,
                        "text": o.text,
                    }
                    for o in q.options
                ],
                "selected_index": ans.selected_index,
                "selected_label": (
                    q.options[ans.selected_index].label
                    if 0 <= ans.selected_index < len(q.options)
                    else None
                ),
                "answered_at": ans.created_at,
            }
        )

    return results