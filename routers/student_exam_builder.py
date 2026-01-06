from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from db import get_db
import models

router = APIRouter(
    prefix="/student/exams",
    tags=["student_exams"],
)


@router.post("/from-teacher/{teacher_problem_set_id}")
def create_student_exam_from_teacher(
    teacher_problem_set_id: int,
    db: Session = Depends(get_db),
):
    # 0️⃣ 교사용 문제 세트 조회
    teacher_set = db.query(models.ProblemSet).get(teacher_problem_set_id)
    if not teacher_set:
        raise HTTPException(status_code=404, detail="교사용 문제 세트 없음")

    # 1️⃣ student 시험용 problem_set 생성
    student_set = models.ProblemSet(
        name=teacher_set.name,
        mode="student",
        created_by="teacher",
        description=teacher_set.description,
        passage_id=teacher_set.passage_id,  # ✅ 핵심
    )
    db.add(student_set)
    db.commit()
    db.refresh(student_set)

    # 2️⃣ 문제 복사
    teacher_questions = (
        db.query(models.Question)
        .filter(models.Question.problem_set_id == teacher_problem_set_id)
        .order_by(models.Question.order)
        .all()
    )

    for q in teacher_questions:
        new_q = models.Question(
            problem_set_id=student_set.id,
            passage_id=q.passage_id,
            question_type=q.question_type,
            text=q.text,                  # ✅ stem → text
            explanation=q.explanation,
            answer_index=q.answer_index,
            order=q.order,
        )
        db.add(new_q)
        db.flush()  # new_q.id 확보

        # 보기 복사
        for opt in q.options:
            db.add(
                models.Option(
                    question_id=new_q.id,
                    label=opt.label,
                    text=opt.text,
                )
            )

    db.commit()

    return {
        "student_problem_set_id": student_set.id,
        "message": "학생 시험 세트 생성 완료",
    }