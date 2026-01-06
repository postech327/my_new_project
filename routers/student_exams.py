from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func
from collections import Counter
from pydantic import BaseModel

from db import get_db
import models
from utils.gpt_explanation import generate_wrong_answer_explanation
from utils.study_report import update_study_report

router = APIRouter(
    prefix="/student/exams",
    tags=["student_exams"],
)

# =====================================================
# Pydantic Schemas
# =====================================================
class CheckAnswerRequest(BaseModel):
    question_id: int
    selected_option_id: int


# =====================================================
# ① 학생 시험 로딩 (지문 + 문제)
# GET /student/exams/{problem_set_id}
# =====================================================
@router.get("/{problem_set_id}")
def get_student_exam(
    problem_set_id: int,
    db: Session = Depends(get_db),
):
    problem_set = (
        db.query(models.ProblemSet)
        .filter(
            models.ProblemSet.id == problem_set_id,
            models.ProblemSet.mode == "student",
        )
        .first()
    )

    if not problem_set:
        raise HTTPException(status_code=404, detail="학생 시험 세트 없음")

    questions = (
        db.query(models.Question)
        .filter(models.Question.problem_set_id == problem_set_id)
        .order_by(models.Question.order)
        .all()
    )

    passage = problem_set.passage

    return {
        "problem_set_id": problem_set.id,
        "title": problem_set.name,
        "passage_title": passage.title if passage else None,
        "passage_content": passage.content if passage else "",
        "questions": [
            {
                "id": q.id,
                "order": q.order,
                "question_type": q.question_type,
                "text": q.text,
                "options": [
                    {
                        "id": o.id,
                        "label": o.label,
                        "text": o.text,
                    }
                    for o in q.options
                ],
            }
            for q in questions
        ],
    }


# =====================================================
# ② 단일 문제 정답 체크 (🔥 Flutter 실시간 채점 핵심)
# POST /student/exams/check-answer
# =====================================================
@router.post("/check-answer")
def check_answer(
    payload: CheckAnswerRequest,
    db: Session = Depends(get_db),
):
    question = db.query(models.Question).get(payload.question_id)
    if not question:
        raise HTTPException(status_code=404, detail="문제 없음")

    selected_option = db.query(models.Option).get(payload.selected_option_id)
    if not selected_option:
        raise HTTPException(status_code=404, detail="선택한 보기 없음")

    # ✅ B안: question.answer_index = 정답 option id
    is_correct = payload.selected_option_id == question.answer_index

    return {
        "question_id": question.id,
        "selected_option_id": payload.selected_option_id,
        "correct": is_correct,
        "correct_option_id": question.answer_index,
    }


# =====================================================
# ③ 시험 전체 제출 + 자동 채점 + GPT 오답 해설
# =====================================================
@router.post("/{problem_set_id}/submit")
def submit_exam(
    problem_set_id: int,
    payload: dict,
    db: Session = Depends(get_db),
):
    user_id = payload.get("user_id")
    answers = payload.get("answers")

    if not user_id or not answers:
        raise HTTPException(status_code=400, detail="user_id와 answers는 필수입니다.")

    correct_count = 0

    for a in answers:
        question = (
            db.query(models.Question)
            .filter(
                models.Question.id == a["question_id"],
                models.Question.problem_set_id == problem_set_id,
            )
            .first()
        )
        if not question:
            continue

        selected_option_id = a["selected_option_id"]
        is_correct = selected_option_id == question.answer_index
        if is_correct:
            correct_count += 1

        gpt_explanation = None
        error_type = None

        if not is_correct:
            gpt_explanation = generate_wrong_answer_explanation(
                question_text=question.text,
                options=[opt.text for opt in question.options],
                correct_index=question.answer_index,
                selected_index=selected_option_id,
            )
            error_type = question.question_type

        student_answer = (
            db.query(models.StudentAnswer)
            .filter(
                models.StudentAnswer.user_id == user_id,
                models.StudentAnswer.question_id == question.id,
            )
            .first()
        )

        if student_answer:
            student_answer.selected_index = selected_option_id
            student_answer.is_correct = is_correct
            student_answer.gpt_explanation = gpt_explanation
            student_answer.error_type = error_type
        else:
            student_answer = models.StudentAnswer(
                user_id=user_id,
                question_id=question.id,
                selected_index=selected_option_id,
                is_correct=is_correct,
                gpt_explanation=gpt_explanation,
                error_type=error_type,
            )
            db.add(student_answer)

        db.commit()
        db.refresh(student_answer)

        update_study_report(db, student_answer)
        db.commit()

    total = len(answers)
    return {
        "problem_set_id": problem_set_id,
        "total_questions": total,
        "correct_count": correct_count,
        "accuracy_rate": round((correct_count / total) * 100, 2) if total else 0,
    }


# =====================================================
# ④ 시험 결과 다시 보기
# =====================================================
@router.get("/{problem_set_id}/result")
def get_exam_result(
    problem_set_id: int,
    user_id: int,
    db: Session = Depends(get_db),
):
    problem_set = db.query(models.ProblemSet).get(problem_set_id)
    if not problem_set:
        raise HTTPException(status_code=404, detail="시험지를 찾을 수 없습니다.")

    rows = (
        db.query(models.Question, models.StudentAnswer)
        .join(models.StudentAnswer)
        .filter(
            models.Question.problem_set_id == problem_set_id,
            models.StudentAnswer.user_id == user_id,
        )
        .order_by(models.Question.order)
        .all()
    )

    if not rows:
        raise HTTPException(status_code=404, detail="제출 기록이 없습니다.")

    correct = sum(1 for _, a in rows if a.is_correct)
    total = len(rows)

    return {
        "problem_set_id": problem_set_id,
        "title": problem_set.name,
        "total_questions": total,
        "correct_count": correct,
        "accuracy_rate": round((correct / total) * 100, 2),
        "questions": [
            {
                "question_id": q.id,
                "order": q.order,
                "question_type": q.question_type,
                "text": q.text,
                "correct_option_id": q.answer_index,
                "selected_option_id": a.selected_index,
                "is_correct": a.is_correct,
                "gpt_explanation": a.gpt_explanation,
            }
            for q, a in rows
        ],
    }


# =====================================================
# ⑤ 학생 약점 유형 집계
# =====================================================
@router.get("/weak-types")
def get_student_weak_types(
    user_id: int,
    db: Session = Depends(get_db),
):
    answers = (
        db.query(models.StudentAnswer)
        .filter(
            models.StudentAnswer.user_id == user_id,
            models.StudentAnswer.is_correct == False,
            models.StudentAnswer.error_type.isnot(None),
        )
        .all()
    )

    counter = Counter(a.error_type for a in answers)
    return {"user_id": user_id, "weak_types": counter.most_common()}


# =====================================================
# ⑥ 약점 유형 기반 추천 문제
# =====================================================
@router.get("/recommend")
def recommend_questions(
    user_id: int,
    error_type: str | None = None,
    limit: int = 5,
    db: Session = Depends(get_db),
):
    if not error_type:
        rows = (
            db.query(
                models.StudentAnswer.error_type,
                func.count(models.StudentAnswer.id),
            )
            .filter(
                models.StudentAnswer.user_id == user_id,
                models.StudentAnswer.is_correct == False,
            )
            .group_by(models.StudentAnswer.error_type)
            .order_by(func.count(models.StudentAnswer.id).desc())
            .all()
        )
        if not rows:
            raise HTTPException(status_code=404, detail="추천할 약점 유형이 없습니다.")
        error_type = rows[0][0]

    questions = (
        db.query(models.Question)
        .filter(models.Question.question_type == error_type)
        .order_by(func.random())
        .limit(limit)
        .all()
    )

    return {
        "error_type": error_type,
        "questions": [
            {
                "id": q.id,
                "text": q.text,
                "question_type": q.question_type,
                "options": [
                    {
                        "id": o.id,
                        "label": o.label,
                        "text": o.text,
                    }
                    for o in q.options
                ],
            }
            for q in questions
        ],
    }