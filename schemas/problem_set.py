# schemas/problem_set.py
from __future__ import annotations

from typing import List, Optional
from pydantic import BaseModel


# ----- 요청 모델 -----
class ProblemSetGenerateRequest(BaseModel):
    passage_id: int
    name: str  # 세트 이름 (예: "수특 28강 3번 - 유형 종합")
    types: List[str]  # ["topic", "title", "gist", "summary", "cloze", ...]
    mode: str = "teacher"  # "teacher" / "student"
    created_by: Optional[str] = None


# ----- 응답 모델 -----
class OptionOut(BaseModel):
    label: str
    text: str
    is_correct: bool


class QuestionOut(BaseModel):
    id: int
    question_type: str
    text: str
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