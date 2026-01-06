# schemas.py
from __future__ import annotations

from datetime import datetime
from typing import List, Optional, Any

from pydantic import BaseModel, Field


# ─────────────────────────────
# 0. 공통: AnalysisRecord용 스키마
#   - main.py, routers/analysis 등이 사용
# ─────────────────────────────
class AnalysisBase(BaseModel):
    kind: str                          # "paragraph" / "topic" / "words" / "chat"
    input_text: Optional[str] = None
    result_text: Optional[str] = None
    result_json: Optional[str] = None  # JSON 문자열


class AnalysisCreate(AnalysisBase):
    """분석 기록 생성 요청"""
    pass


class AnalysisOut(AnalysisBase):
    """분석 기록 조회 응답"""
    id: int
    created_at: datetime

    class Config:
        orm_mode = True

# ─────────────────────────────
# 1. 지문 / 문제세트 (선생님 모드 + 학생 모드 공용)
# ─────────────────────────────
class PassageOut(BaseModel):
    id: int
    title: str
    content: str
    source: Optional[str] = None
    level: Optional[str] = None
    created_by: Optional[str] = None

    class Config:
        orm_mode = True

class PassageAnalysisOut(BaseModel):
    topic_en: Optional[str]
    topic_ko: Optional[str]

    title_en: Optional[str]
    title_ko: Optional[str]

    gist_en: Optional[str]
    gist_ko: Optional[str]

    summary_en: Optional[str]
    summary_ko: Optional[str]

    structure_json: Optional[Any]
    flow_json: Optional[Any]
    vocab_json: Optional[Any]

    class Config:
        orm_mode = True


# ─────────────────────────────
# 2. ProblemSet (공용)
# ─────────────────────────────
class ProblemSetOut(BaseModel):
    id: int
    passage_id: int
    name: str
    description: Optional[str] = None
    created_by: Optional[str] = None
    mode: str
    is_published: bool
    created_at: datetime

    class Config:
        orm_mode = True
        
class QuestionSetSaveResult(BaseModel):
    """선생님이 문제세트를 저장한 뒤 받는 요약 응답"""
    passage: PassageOut
    problem_set: ProblemSetOut
    problem_set_id: int

# ─────────────────────────────
# 3. Option (공통)
# ─────────────────────────────
class OptionOut(BaseModel):
    id: int
    label: str          # "①", "②", ...
    text: str

    class Config:
        orm_mode = True


# ─────────────────────────────
# 4. Teacher용 Question (answer_index 포함)
# ─────────────────────────────
class TeacherQuestionOut(BaseModel):
    id: int
    passage_id: int
    problem_set_id: Optional[int]
    question_type: str
    text: str
    explanation: Optional[str]
    order: int
    answer_index: Optional[int]
    options: List[OptionOut]
    
    class Config:
        orm_mode = True


class TeacherProblemSetOut(BaseModel):
    problem_set: ProblemSetOut
    questions: List[TeacherQuestionOut]
    
    class Config:
        orm_mode = True


# ─────────────────────────────
# 5. Student용 Question (정답 정보 완전 제거)
# ─────────────────────────────
class StudentOptionOut(BaseModel):
    id: int
    label: str
    text: str

    class Config:
        orm_mode = True


class StudentQuestionOut(BaseModel):
    id: int
    passage_id: int
    problem_set_id: int

    question_type: str

    # 기존 프론트/라우터 호환
    stem: str

    order_index: Optional[int] = None

    options: List[StudentOptionOut]

    class Config:
        orm_mode = True


class StudentQuestionSetOut(BaseModel):
    passage_id: int
    passage_title: str
    passage_content: str

    problem_set_id: int
    questions: List[StudentQuestionOut]


# ─────────────────────────────
# 6. 학생 대시보드용 요약
# ─────────────────────────────


class StudentProblemSetSummary(BaseModel):
    problem_set_id: int
    passage_title: str
    problem_set_name: str
    num_questions: int
    created_at: datetime
    
class StudentAnswerCreate(BaseModel):
    question_id: int
    selected_index: int


class StudentAnswerOut(BaseModel):
    id: int
    question_id: int
    selected_index: int
    is_correct: bool
    created_at: datetime

    class Config:
        orm_mode = True