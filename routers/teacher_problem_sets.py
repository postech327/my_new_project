# routers/teacher_problem_sets.py

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from datetime import datetime

from db import get_db
import models
from utils.security import require_role
from services.problem_set_service import (
    create_problem_set_from_analysis,
    create_problem_set_from_text,
)

router = APIRouter(
    prefix="/teacher/problem_sets",
    tags=["teacher_problem_sets"],
)

# =====================================================
# 1️⃣ 기존: Analysis 기반 자동 생성
# =====================================================
@router.post("/auto")
def auto_generate_problem_set(
    analysis_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_role("teacher")),
):

    analysis = (
        db.query(models.AnalysisRecord)
        .filter(models.AnalysisRecord.id == analysis_id)
        .first()
    )
    if not analysis:
        raise HTTPException(status_code=404, detail="AnalysisRecord not found")

    if not analysis.passage_id:
        raise HTTPException(status_code=400, detail="AnalysisRecord has no passage")

    passage = (
        db.query(models.Passage)
        .filter(models.Passage.id == analysis.passage_id)
        .first()
    )
    if not passage:
        raise HTTPException(status_code=404, detail="Passage not found")

    problem_set = create_problem_set_from_analysis(
        db=db,
        passage=passage,
        analysis=analysis,
        created_by=current_user["sub"],
    )

    # 🔥 자동 배정 추가
    students = db.query(models.User).filter(models.User.role == "student").all()

    for student in students:
        assignment = models.ExamAssignment(
            user_id=student.id,  # ⚠ student_id 아님!
            problem_set_id=problem_set.id,
            assigned_at=datetime.utcnow(),
            is_completed=False,
        )
        db.add(assignment)

    db.commit()

    return {
        "ok": True,
        "problem_set": {
            "id": problem_set.id,
            "name": problem_set.name,
            "question_count": len(problem_set.questions),
        },
    }


# =====================================================
# 🔥 2️⃣ 지문 직접 입력 → 시험지 생성 + 자동 배정
# =====================================================
@router.post("/from_text")
def generate_problem_set_from_text(
    title: str,
    content: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_role("teacher")),
):

    # 1️⃣ Teacher 조회
    teacher = (
        db.query(models.User)
        .filter(models.User.id == int(current_user["sub"]))
        .first()
    )

    if not teacher:
        raise HTTPException(status_code=404, detail="Teacher not found")

    # 2️⃣ Passage 생성
    passage = models.Passage(
        teacher_id=teacher.id,
        source_title=title,
        text=content,
        visibility="private",
    )

    db.add(passage)
    db.commit()
    db.refresh(passage)

    # 3️⃣ ProblemSet 생성
    problem_set = create_problem_set_from_text(
        db=db,
        passage=passage,
        created_by=current_user["sub"],
    )

    # 🔥 4️⃣ 자동 배정 (여기가 핵심!)
    students = db.query(models.User).filter(models.User.role == "student").all()

    for student in students:
        assignment = models.ExamAssignment(
            user_id=student.id,  # ⚠ 반드시 user_id
            problem_set_id=problem_set.id,
            assigned_at=datetime.utcnow(),
            is_completed=False,
        )
        db.add(assignment)

    db.commit()

    return {
        "ok": True,
        "passage_id": passage.id,
        "problem_set": {
            "id": problem_set.id,
            "name": problem_set.name,
            "question_count": len(problem_set.questions),
        },
    }


# =====================================================
# 교사 문제지 목록
# =====================================================
@router.get("/list")
def get_teacher_problem_sets(
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_role("teacher")),
):
    problem_sets = (
        db.query(models.ProblemSet)
        .filter(models.ProblemSet.created_by == current_user["sub"])
        .all()
    )

    return problem_sets