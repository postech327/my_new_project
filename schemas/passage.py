# schemas/passage.py
from __future__ import annotations

from typing import Any, List, Optional
from pydantic import BaseModel


# ───────── 요청 모델 ─────────
class PassageAnalyzeRequest(BaseModel):
    title: str
    content: str
    source: Optional[str] = None
    level: Optional[str] = None
    created_by: Optional[str] = None  # 로그인 유저 이메일/닉네임 등 (선택)


# ───────── 분석 결과 내부 구조 ─────────
class StructureItem(BaseModel):
    sentence: str
    bracketed: str
    note: Optional[str] = None


class FlowSummary(BaseModel):
    intro: Any | None = None
    body: Any | None = None
    conclusion: Any | None = None


class VocabItem(BaseModel):
    word: str
    meaning_ko: str
    synonyms: List[str]


# ───────── 응답 모델 ─────────
class PassageAnalysisData(BaseModel):
    topic_en: Optional[str] = None
    topic_ko: Optional[str] = None
    title_en: Optional[str] = None
    title_ko: Optional[str] = None
    gist_en: Optional[str] = None
    gist_ko: Optional[str] = None
    summary_en: Optional[str] = None
    summary_ko: Optional[str] = None

    structure: List[StructureItem] | None = None
    flow: FlowSummary | None = None
    vocab: List[VocabItem] | None = None


class PassageAnalyzeResponse(BaseModel):
    passage_id: int
    analysis: PassageAnalysisData