# schemas.py
from typing import Optional, Literal, Any, List
from datetime import datetime
from pydantic import BaseModel, Field, ConfigDict

class StudentProblemSetSummary(BaseModel):
    id: int
    title: str
    question_type: str
    num_questions: int
    created_at: datetime

    # SQLAlchemy 모델에서 바로 읽어올 수 있게 설정
    model_config = ConfigDict(from_attributes=True)

# ───────── Analysis 기록 ─────────

# 레코드 생성용
class AnalysisCreate(BaseModel):
    kind: Literal["paragraph", "topic", "words", "chat"] = Field(
        ..., description="분석 종류"
    )
    input_text: Optional[str] = None
    result_text: Optional[str] = None
    result_json: Optional[dict[str, Any]] = None


# 단건 조회/응답용
class AnalysisOut(BaseModel):
    id: int
    kind: str
    input_text: Optional[str]
    result_text: Optional[str]
    result_json: Optional[dict]
    created_at: datetime

    class Config:
        from_attributes = True  # SQLAlchemy ORM -> Pydantic 변환 허용


# ───────── Passage ─────────

class PassageBase(BaseModel):
    title: Optional[str] = None
    content: str
    source: Optional[str] = None
    level: Optional[str] = None
    created_by: Optional[str] = None


class PassageCreate(PassageBase):
    pass


class PassageOut(PassageBase):
    id: int

    class Config:
        from_attributes = True


# ───────── ProblemSet ─────────

class ProblemSetBase(BaseModel):
    passage_id: int
    name: str
    description: Optional[str] = None
    created_by: Optional[str] = None


class ProblemSetCreate(ProblemSetBase):
    pass


class ProblemSetOut(ProblemSetBase):
    id: int

    class Config:
        from_attributes = True


# ───────── Option ─────────

class OptionBase(BaseModel):
    label: Optional[str] = None
    text: str
    is_correct: bool = False


class OptionCreate(OptionBase):
    pass


class OptionOut(OptionBase):
    id: int

    class Config:
        from_attributes = True


# ───────── Question ─────────

class QuestionBase(BaseModel):
    question_type: str
    stem: str
    extra_info: Optional[str] = None
    explanation: Optional[str] = None
    order_index: Optional[int] = None


class QuestionCreate(QuestionBase):
    passage_id: int
    problem_set_id: Optional[int] = None
    options: List[OptionCreate] = []


class QuestionOut(QuestionBase):
    id: int
    passage_id: int
    problem_set_id: Optional[int] = None
    options: List[OptionOut] = []

    class Config:
        from_attributes = True


# ───────── Student Quiz View ─────────

# 학생에게 내려줄 보기 (정답 여부는 숨김)
class StudentOptionOut(BaseModel):
    id: int
    label: Optional[str] = None
    text: str

    # SQLAlchemy 객체 → Pydantic 자동 변환
    model_config = ConfigDict(from_attributes=True)


class StudentQuestionOut(BaseModel):
    id: int
    # (필요해서 id들 추가해 둠 – 기존 용도에는 영향 없음)
    passage_id: int
    problem_set_id: int

    question_type: str
    stem: str
    extra_info: Optional[str] = None
    order_index: Optional[int] = None
    options: List[StudentOptionOut]

    model_config = ConfigDict(from_attributes=True)


class StudentQuestionSetOut(BaseModel):
    """학생 모드에서 사용할 '지문 + 문제 세트' 응답용 스키마"""

    passage_id: int
    passage_title: Optional[str] = None
    passage_content: str
    problem_set_id: int
    questions: List[StudentQuestionOut]


# ───────── Bulk 생성용 ─────────

class QuestionWithOptionsCreate(QuestionBase):
    options: List[OptionCreate] = []


class QuestionBulkCreate(BaseModel):
    passage_id: int
    problem_set_id: Optional[int] = None
    questions: List[QuestionWithOptionsCreate]


# ───────── 학생 모드용 채점 스키마 ─────────

class StudentAnswerCheckRequest(BaseModel):
    question_id: int
    selected_option_id: int


class StudentAnswerCheckResult(BaseModel):
    question_id: int
    selected_option_id: int
    correct: bool
    correct_option_id: int
    explanation: Optional[str] = None


# ───────── Teacher: question set save/load (기존 버전) ─────────

class QuestionSetSaveRequest(BaseModel):
    """
    선생님 모드에서 지문 + 여러 문항을 한 번에 저장할 때 사용하는 요청 바디
    """
    passage_title: Optional[str] = None
    passage_content: str

    # 어떤 세트 이름으로 저장할지 (예: '샘플 세트 1', '중3 3과 테스트' 등)
    problem_set_name: str = "샘플 세트"

    # 나중에 '전체 / 주제 / 제목 ...' 구분을 하고 싶으면 여기에 넣어도 됨
    description: Optional[str] = None

    # 🔹 GPT 자동생성용: 만들고 싶은 문항 개수 (기본 1)
    num_questions: int = Field(1, ge=1, le=10)

    # 실제 문항 리스트 (없어도 저장 가능하도록 기본값 []))
    questions: List[QuestionWithOptionsCreate] = []


class QuestionSetSaveResult(BaseModel):
    """
    저장이 끝난 뒤, Flutter 에게 돌려줄 응답
    """
    passage: PassageOut
    problem_set: ProblemSetOut

    # 🔹 Flutter에서 바로 쓰는 ID (teacher_api.dart 에서 사용)
    problem_set_id: int

    class Config:
        from_attributes = True


# ───────── 🆕 Teacher 전용 스키마 (새 라우터용) ─────────

class TeacherQuestionCreate(BaseModel):
    """
    GPT로 생성되거나, 선생님이 직접 입력하는 문항 한 개
    """
    question_type: str = "mcq"
    stem: str
    extra_info: Optional[str] = None
    options: List[OptionCreate]
    # 정답 선택지의 label (예: "B")
    correct_option_label: str


class TeacherQuestionSetCreate(BaseModel):
    """
    /teacher/question-sets 에서 사용할 요청 스키마
    (지문 + 문제세트 + 문항들)
    """
    passage_title: Optional[str] = None
    passage_content: str

    problem_set_name: str = "샘플 세트"
    description: Optional[str] = None

    # 🔹 GPT 자동 생성용 문항 개수
    num_questions: int = Field(1, ge=1, le=10)

    # 🔹 직접 문항을 넣고 싶으면 여기 사용, 비어 있으면 GPT로 생성
    questions: List[TeacherQuestionCreate] = []
    
    # 🔥 추가: 문제 유형 (topic / title / gist / summary / cloze / insertion / order / all)
    question_type: Optional[str] = "all"


class TeacherQuestionSetOut(BaseModel):
    """
    /teacher/question-sets 응답 스키마
    """
    passage: PassageOut
    problem_set: ProblemSetOut
    problem_set_id: int

    class Config:
        from_attributes = True


# ───────── GPT 단일/다중 문항 생성 테스트용 스키마 ─────────

class RunQuestionRequest(BaseModel):
    """
    /teacher/run_question 요청 바디

    실제 GPT 호출에는 passage_content, num_questions만 사용하지만,
    나중에 확장 가능하도록 몇 가지 메타정보도 같이 둠.
    """
    passage_content: str
    num_questions: int = Field(1, ge=1, le=10)

    # 아래 필드들은 지금은 선택사항(백엔드에서 바로 쓰진 않음)
    passage_title: Optional[str] = None
    problem_set_name: str = "샘플 세트"
    description: Optional[str] = None
    question_type: str = "mcq"


class RunQuestionResponse(BaseModel):
    """
    /teacher/run_question 응답
    - questions: QuestionWithOptionsCreate 형식의 리스트
    """
    questions: List[QuestionWithOptionsCreate]
    
    
class AuthorSummary(BaseModel):
    id: int
    nickname: str
    region: Optional[str] = None
    role: str
    level: int

    class Config:
        orm_mode = True


class CommunityPostBase(BaseModel):
    title: str
    content: str
    nickname: str
    region: Optional[str] = None
    category: str


class CommunityPostOut(CommunityPostBase):
    id: int
    created_at: datetime
    author: Optional[AuthorSummary] = None  # ✅ 작성자 정보

    class Config:
        orm_mode = True