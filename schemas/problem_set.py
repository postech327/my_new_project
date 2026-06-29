# schemas/problem_set.py
from __future__ import annotations

from typing import List, Optional, Dict, Any
from pydantic import BaseModel


# ----- 요청 모델 -----
class ProblemSetGenerateRequest(BaseModel):
    passage_id: int
    name: str  # 세트 이름 (예: "수특 28강 3번 - 유형 종합")
    types: list[str] | None = None
    mode: str = "teacher"  # "teacher" / "student"
    created_by: Optional[str] = None
    folder_id: Optional[int] = None
    folder_name: Optional[str] = None

    # 🔥 파이널터치 분석 결과 전달용
    # 예:
    # {
    #   "topic_en": "Ethical considerations of human gene editing",
    #   "title_en": "The Ethical Dilemma of Gene Editing",
    #   "gist_en": "Gene editing in humans raises ethical concerns about altering genes for perfection."
    # }
    analysis: Optional[Dict[str, Any]] = None


# ----- 응답 모델 -----
class OptionOut(BaseModel):
    label: str
    text: str
    is_correct: bool


class QuestionOut(BaseModel):
    id: int
    question_type: str
    question_text: str
    explanation: Optional[str] = None
    order: int
    options: List[OptionOut]


class ProblemSetOut(BaseModel):
    id: int
    passage_id: int
    name: str
    types: List[str]
    mode: str
    questions: List[QuestionOut]

    class Config:
        from_attributes = True  # pydantic v2


# ----- Step 3-4-3: 미리보기 전용 -----
class PreviewQuestionOut(BaseModel):
    order: int
    question_type: str
    question_text: str
    options: list[str]
    answer_index: int


class PreviewProblemSetResponse(BaseModel):
    name: str
    passage_title: str | None = None
    passage_content: str
    questions: list[PreviewQuestionOut]


class AutoGenerateCommitResponse(BaseModel):
    problem_set_id: int
    name: str
    total_questions: int


# ===============================
# Step 3-3 / 3-4 자동 시험지 생성
# ===============================
class AutoGenerateProblemSetRequest(BaseModel):
    analysis_id: int
    name: str
    total_questions: int
    distribution: dict[str, float]
    mode: str = "teacher"


class AutoGenerateProblemSetResponse(BaseModel):
    problem_set_id: int
    name: str
    total_questions: int
