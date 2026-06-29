# schemas/student_exam.py

from pydantic import BaseModel, Field
from typing import List, Dict


# =========================
# 공통: 학생 답안 입력
# =========================
class StudentAnswerIn(BaseModel):
    question_id: int
    selected_index: int


# =========================
# 1️⃣ 시험 최초 제출
# =========================
class StudentExamSubmitRequest(BaseModel):
    problem_set_id: int
    answers: List[StudentAnswerIn]


class QuestionResultOut(BaseModel):
    question_id: int
    selected_index: int
    correct_index: int
    is_correct: bool


class StudentExamSubmitResponse(BaseModel):
    total_questions: int
    correct_count: int
    wrong_count: int
    accuracy: float
    score: float
    results: List[QuestionResultOut]   # ⭐ 여기 수정됨


# =========================
# 2️⃣ 오답 재도전 제출
# =========================
class RetrySubmitRequest(BaseModel):
    answers: List[StudentAnswerIn]


class RetrySubmitResponse(BaseModel):
    total: int
    correct: int
    accuracy: float
    score: float | None = None   # 🔥 나중 확장 대비


# =========================
# 3️⃣ 시험 결과 요약
# =========================
class TypeStatistics(BaseModel):
    total: int = Field(..., ge=0)
    wrong: int = Field(..., ge=0)


class ExamSummaryResponse(BaseModel):
    problem_set_id: int
    user_id: int

    total_questions: int = Field(..., ge=0)
    correct: int = Field(..., ge=0)
    wrong: int = Field(..., ge=0)
    accuracy: int = Field(..., ge=0, le=100)

    by_type: Dict[str, TypeStatistics]