# services/analysis_service.py
from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from openai import OpenAI

from config import OPENAI_API_KEY, OPENAI_MODEL
from schemas.passage import (
    PassageAnalysisData,
    StructureItem,
    FlowSummary,
    VocabItem,
)

# OpenAI 클라이언트 (main.py와 같은 방식)
client = OpenAI(api_key=OPENAI_API_KEY)


def build_passage_analysis_prompt(content: str) -> str:
    """
    지문 분석 허브용 프롬프트.
    나중에 네 스타일에 맞게 수정해도 OK.
    """
    return f"""
You are an expert English reading instructor for Korean middle and high school students.

Analyze the following passage and output STRICT JSON in the following format:

{{
  "topic_en": "...",
  "topic_ko": "...",
  "title_en": "...",
  "title_ko": "...",
  "gist_en": "...",
  "gist_ko": "...",
  "summary_en": "...",
  "summary_ko": "...",
  "structure": [
    {{
      "sentence": "...",
      "bracketed": "...",
      "note": "..."
    }}
  ],
  "flow": {{
    "intro": {{ "main_idea": "...", "summary_ko": "..." }},
    "body": [
      {{ "point": 1, "main_idea": "...", "summary_ko": "..." }}
    ],
    "conclusion": {{ "main_idea": "...", "summary_ko": "..." }}
  }},
  "vocab": [
    {{
      "word": " ... ",
      "meaning_ko": " ... ",
      "synonyms": ["...", "...", "..."]
    }}
  ]
}}

Passage:
\"\"\"{content}\"\"\"
    """.strip()


def _extract_json_from_content(raw: str) -> str:
    """
    GPT가 ```json ... ``` 같은 코드블록으로 감싸줄 수도 있어서
    그럴 경우를 대비해 코드블록을 벗겨내는 보조 함수.
    """
    raw = raw.strip()

    # ```json ... ``` 또는 ``` ... ``` 제거
    if raw.startswith("```"):
        # 첫 줄 제거
        lines = raw.splitlines()
        # 첫 줄( ``` 또는 ```json ) 제거, 마지막 줄( ``` ) 제거
        if len(lines) >= 3 and lines[-1].strip().startswith("```"):
            lines = lines[1:-1]
        raw = "\n".join(lines).strip()

    return raw


def call_gpt_passage_analysis(content: str) -> PassageAnalysisData:
    """
    OpenAI GPT를 호출해서 PassageAnalysisData 형태로 반환.
    routers.passage_analysis 에서 import 하는 함수.
    """
    prompt = build_passage_analysis_prompt(content)

    response = client.chat.completions.create(
        model=OPENAI_MODEL,  # .env에서 지정한 모델 사용 (없으면 config 기본값)
        messages=[
            {
                "role": "system",
                "content": "You are a helpful assistant for English reading analysis.",
            },
            {
                "role": "user",
                "content": prompt,
            },
        ],
        temperature=0.2,
    )

    raw_content = response.choices[0].message.content or ""
    json_text = _extract_json_from_content(raw_content)

    data = json.loads(json_text)

    # structure
    structure_items: Optional[List[StructureItem]] = None
    if isinstance(data.get("structure"), list):
        structure_items = [StructureItem(**item) for item in data["structure"]]

    # flow
    flow_data: Optional[FlowSummary] = None
    if isinstance(data.get("flow"), dict):
        flow_data = FlowSummary(**data["flow"])

    # vocab
    vocab_items: Optional[List[VocabItem]] = None
    if isinstance(data.get("vocab"), list):
        vocab_items = [VocabItem(**item) for item in data["vocab"]]

    return PassageAnalysisData(
        topic_en=data.get("topic_en"),
        topic_ko=data.get("topic_ko"),
        title_en=data.get("title_en"),
        title_ko=data.get("title_ko"),
        gist_en=data.get("gist_en"),
        gist_ko=data.get("gist_ko"),
        summary_en=data.get("summary_en"),
        summary_ko=data.get("summary_ko"),
        structure=structure_items,
        flow=flow_data,
        vocab=vocab_items,
    )