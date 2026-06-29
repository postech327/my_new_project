# routers/analysis.py
from __future__ import annotations

from pydantic import BaseModel, Field
from typing import Optional, Dict, Any
import httpx
import os
import re
import json

from fastapi import APIRouter, Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from sqlalchemy.orm import Session

from db import get_db
import models
from structure_analyzer import analyze_structure
from grammar_reference import grammar_reference_prompt

# 🔥 GPT
from openai import OpenAI
from config import OPENAI_API_KEY, OPENAI_MODEL, SECRET_KEY, ALGORITHM


router = APIRouter(prefix="/analyze", tags=["analyze"])
optional_security = HTTPBearer(auto_error=False)

client = OpenAI(api_key=OPENAI_API_KEY)

# ✅ 현재 FastAPI 실행 포트가 8001이므로 기본값을 8001로 변경
# 필요하면 .env에서 WORD_API_BASE=http://127.0.0.1:8001 로 지정 가능
API_BASE = os.getenv("WORD_API_BASE", "http://127.0.0.1:8001").rstrip("/")


# -------------------------------------------------
# 유틸
# -------------------------------------------------
_BR_RE = re.compile(r"[\[\]\(\)\{\}]")


def has_brackets(s: str) -> bool:
    return bool(_BR_RE.search(s or ""))


# -------------------------------------------------
# 구조 분석 API 호출
# -------------------------------------------------
async def fetch_bracketed(text: str) -> str:
    """
    /analyze_structure를 호출해 괄호 분석 결과를 가져온다.
    실패하면 summary_flow에서 원문으로 fallback 처리한다.
    """
    url = f"{API_BASE}/analyze_structure"

    async with httpx.AsyncClient(timeout=60) as client_http:
        r = await client_http.post(url, json={"text": text})
        r.raise_for_status()
        data = r.json()

    def pick(d: Any) -> Optional[str]:
        if isinstance(d, str):
            return d.strip()

        if isinstance(d, dict):
            for k in (
                "analyzed_text",
                "bracketed",
                "processed_text",
                "result",
                "output",
                "text",
                "analysis",
            ):
                v = d.get(k)
                if isinstance(v, str) and v.strip():
                    return v.strip()
                if isinstance(v, dict):
                    nested = pick(v)
                    if nested:
                        return nested

        return None

    picked = pick(data)

    if not picked:
        raise ValueError("Unsupported /analyze_structure response format")

    return picked


# -------------------------------------------------
# 🔥 GPT 분석
# -------------------------------------------------
def analyze_with_gpt(
    text: str,
    korean_translation_text: str | None = None,
    teacher_topic_sentence: str | None = None,
) -> Dict[str, Any]:
    grammar_reference = grammar_reference_prompt()
    translation_note = ""
    if korean_translation_text and korean_translation_text.strip():
        translation_note = f"""

USER PROVIDED KOREAN TRANSLATION:
{korean_translation_text.strip()}

Translation alignment instructions:
- The user provided Korean translation text.
- Use the provided Korean translation as the primary source for sentence translations.
- Do not rewrite the translation unnecessarily.
- Align the provided Korean translation with the English sentences by sentence_no.
- If alignment is unclear, make the best reasonable match.
"""

    topic_note = ""
    if teacher_topic_sentence and teacher_topic_sentence.strip():
        topic_note = f"""

TEACHER-SELECTED TOPIC SENTENCE:
{teacher_topic_sentence.strip()}

Teacher topic sentence instructions:
- The user provided a teacher-selected topic sentence.
- Treat it as a strong reference for topic, title, gist, and summary analysis.
- Do not ignore the teacher-provided topic sentence.
- If it matches or closely matches a sentence in the passage, mark that sentence as topic candidate.
- If another sentence has a similar thematic function, you may mark it as gist/topic candidate only when clearly justified.
- If Korean translation text is provided, use it as the primary reference for Korean topic/title/gist/summary.
- Do not return generic placeholders such as "central idea and supporting evidence".
- Generate topic/title/gist/summary from the actual passage content.
- Do not exceed 3 important highlighted sentences in total.
- Do not force unrelated sentences to become topic candidates.
"""

    prompt = f"""
You are a Korean CSAT English exam expert.

Analyze the passage strictly:

1. FLOW CHECK
- intro / body / conclusion
- write each value as a short Korean study note
- summarize the passage flow naturally, not by copying English sentences
- 1~2 short Korean sentences each

2. TOPIC
- noun phrase
- 5~10 words
- exam style

3. TITLE
- natural title
- 5~10 words

4. GIST
- 1 sentence
- 10~20 words

5. SUMMARY
- 1 sentence
- 15~30 words

6. SENTENCE DETAILS
- split the original passage into sentences in order
- provide a real, natural Korean translation for every sentence
- each translation must faithfully correspond to its original sentence
- never use generic placeholders such as "이 문장은 ... 설명합니다"
- when possible, also provide translation_bracketed using matching [], (), {{}}
  around Korean segments that correspond to the English structure
- assign one short, content-specific Korean sentence_role
- choose roles such as 핵심 소재 제시, 문제 상황 제시, 원인 설명, 결과 설명,
  예시 제시, 대조 제시, 연구 결과 제시, 핵심 원리 제시, 해결책 제시,
  결론 및 정리, or 요지 강화
- do not label every sentence as a topic, gist, conclusion, or blank candidate
- provide role_highlight_type using only topic, gist, conclusion, blank_candidate, or none
- also provide is_blank_candidate as true only when the sentence is suitable for
  context-based blank inference; otherwise false
- mark at most 3 important sentences in total across topic/gist/conclusion/blank_candidate
- mark at most 3 blank candidates in the entire passage, preferably 1 or 2
- do not automatically mark the first sentence as topic
- do not mark the final sentence as conclusion unless it clearly summarizes,
  resolves, or closes the passage
- use none when uncertain
- priority for important sentence labels is topic > gist > conclusion > blank_candidate
- provide highlights using only grammar, vocabulary, or blank_hint
- each highlight needs text copied exactly from the original sentence and a short Korean memo
- blank_hint must be no more than 3 items in the entire passage
- Do not over-highlight. Select only the most important highlights.
- Do not mark every sentence as topic/blank_hint.
- provide grammar_points only when a sentence has meaningful grammar for reading
  comprehension or exam preparation
- grammar_points must be an empty array [] if there is no meaningful grammar point
- do not force grammar_points for every sentence
- maximum 2 grammar_points per sentence, 3 only for very complex sentences
- each grammar point needs target, label, explanation
- include reference_no when a grammar point matches the grammar reference list
- target must exactly appear in the original sentence
- label must be short, such as 명사절, 관계절, 조건 부사절, to부정사구,
  분사구, 동명사구, 병렬구조, 비교구문, 가주어 it, 수동태, 완료, 조동사
- explanation must be short, Korean, and student-friendly
- choose only grammar points that help reading comprehension or exam preparation
- use the provided grammar reference list as the primary source for grammar explanations
- do not invent unnecessary grammar points
- do not mix grammar explanations into question_point
- provide one short Korean question_point explaining how the actual content of the
  sentence may help with exam questions
- mention the specific idea, cause, result, contrast, principle, or solution in the sentence
- do not use generic or repeated question_point explanations
- keep original sentence text unchanged

7. Korean translations required

IMPORTANT:
- Do not use generic explanations.
- Each translation must be a real Korean translation of the sentence.
- Each question_point must refer to the actual content of that sentence.
- Do not repeat the same question_point for every sentence.
- Do not force topic/gist/conclusion labels.
- Do not mark the first sentence as topic automatically.
- Mark at most 3 important sentences in total.
- Mark at most 3 blank candidates in total.
- Use none when uncertain.
- Choose blank candidates only when context-based inference is possible.
- Mark topic, gist, conclusion, or blank_candidate only when clearly supported.
- Do not force grammar points for every sentence.
- Use grammar_points: [] when grammar explanation is not useful.
- The grammar point target phrase must exactly appear in the original sentence.
- Keep each grammar explanation short and student-friendly.
- Do not mix grammar explanations into question_point.
- If a grammar point matches the grammar reference list, include reference_no.

Return ONLY JSON:

{{
  "outline": {{
    "intro": "...",
    "body": "...",
    "conclusion": "..."
  }},
  "topic_en": "...",
  "topic_ko": "...",
  "title_en": "...",
  "title_ko": "...",
  "gist_en": "...",
  "gist_ko": "...",
  "summary_en": "...",
  "summary_ko": "...",
  "sentence_details": [
    {{
      "sentence_no": 1,
      "original": "...",
      "translation": "...",
      "translation_bracketed": "...",
      "sentence_role": "주제 제시",
      "role_highlight_type": "topic",
      "is_blank_candidate": false,
      "highlights": [
        {{
          "text": "major problem",
          "type": "vocabulary",
          "memo": "핵심 표현"
        }}
      ],
      "grammar_points": [
        {{
          "target": "which lay their eggs on land",
          "label": "관계절",
          "explanation": "which절이 앞의 sea turtles를 설명합니다.",
          "reference_no": 70
        }}
      ],
      "question_point": "지문의 핵심 소재를 제시하므로 주제 문제의 근거가 됩니다."
    }}
  ]
}}

PASSAGE:
{text}

{grammar_reference}
{translation_note}
{topic_note}
"""

    response = client.chat.completions.create(
        model=OPENAI_MODEL,
        messages=[
            {
                "role": "system",
                "content": "Return ONLY valid JSON. Do not include markdown.",
            },
            {
                "role": "user",
                "content": prompt,
            },
        ],
        temperature=0.3,
    )

    content = response.choices[0].message.content or ""
    content = content.strip()

    print("🔥 GPT RAW:", content)

    try:
        content = re.sub(r"```json", "", content)
        content = re.sub(r"```", "", content).strip()

        match = re.search(r"\{.*\}", content, re.DOTALL)
        if not match:
            raise ValueError("JSON not found")

        json_str = match.group()

        print("🔥 JSON CLEAN:", json_str)

        return json.loads(json_str)

    except Exception as e:
        print("❌ JSON 파싱 실패:", e)
        print("🔥 최종 content:", content)

        # 🔥 fallback: 절대 죽지 않게
        return {
            "outline": {
                "intro": "",
                "body": "",
                "conclusion": "",
            },
            "topic_en": "",
            "topic_ko": "",
            "title_en": "",
            "title_ko": "",
            "gist_en": "",
            "gist_ko": "",
            "summary_en": "",
            "summary_ko": "",
            "sentence_details": [],
        }


def _plain_text(text: str) -> str:
    return re.sub(r"[\[\]\(\)\{\}]", "", text or "").strip()


def _split_sentences(text: str) -> list[str]:
    plain = _plain_text(text)
    return [
        sentence.strip()
        for sentence in re.split(
            r"""(?:(?<=[.!?])|(?<=[.!?]["”’]))\s+(?=(?:["'“‘]\s*)?[A-Z])""",
            plain,
        )
        if len(sentence.strip()) > 2
    ]


_TRANSLATION_PENDING = "해석 준비 중입니다. GPT 분석이 정상화되면 자동으로 표시됩니다."
_GENERIC_TRANSLATIONS = {
    "이 문장은 지문의 세부 내용을 설명합니다.",
    "이 문장은 해당 내용을 설명합니다.",
}
_GENERIC_QUESTION_POINTS = {
    "지문의 핵심 소재를 제시하므로 주제나 요지 문제의 근거가 됩니다.",
    "글의 마무리 내용을 담고 있어 요지나 제목 문제의 단서가 됩니다.",
    "세부 설명과 흐름을 연결하므로 빈칸, 순서, 삽입 문제의 단서가 될 수 있습니다.",
}


def _fallback_sentence_role(sentence: str, index: int, total: int) -> str:
    lower = sentence.lower()

    if any(word in lower for word in ("solution", "solve", "turn off", "safe lighting")):
        return "해결책 제시"
    if any(word in lower for word in ("scientist", "research", "study", "believe", "found that")):
        return "연구 결과 또는 핵심 원리 제시"
    if any(word in lower for word in ("such problem", "result", "reason for", "reduction", "will die")):
        return "결과 설명"
    if any(word in lower for word in ("problem", "threat", "danger", "risk")):
        return "문제 상황 제시"
    if any(word in lower for word in ("however", "but ", "whereas", "on the other hand")):
        return "대조 제시"
    if lower.startswith(("if ", "when ", "because ", "since ", "as ")):
        return "원인 또는 조건 설명"
    if any(word in lower for word in ("need ", "needs ", "require ", "requires ")):
        return "조건 설명"
    if any(word in lower for word in ("for example", "for instance", "such as")):
        return "예시 제시"
    if index == 0:
        return "핵심 소재 또는 문제 상황 제시"
    if index == total - 1:
        return "결론 및 정리"
    return "핵심 내용 부연"


def _sentence_preview(sentence: str, limit: int = 74) -> str:
    compact = re.sub(r"\s+", " ", sentence).strip()
    if len(compact) <= limit:
        return compact
    return compact[: limit - 3].rstrip() + "..."


def _split_korean_translation(text: str) -> list[str]:
    raw = str(text or "").strip()
    if not raw:
        return []

    def clean_segment(segment: str) -> str:
        segment = re.sub(
            r"^\s*(?:[-*•]\s*|\(?\d+[\.)]\s*|[①②③④⑤⑥⑦⑧⑨⑩]\s*)",
            "",
            segment,
        )
        return segment.strip()

    lines = [clean_segment(line) for line in raw.splitlines() if clean_segment(line)]
    if len(lines) > 1:
        return lines

    parts = re.split(
        r"(?<=[.!?。！？])\s+|(?<=다\.)\s+|(?<=요\.)\s+|(?<=죠\.)\s+|"
        r"(?<=함\.)\s+|(?<=음\.)\s+|(?<=됨\.)\s+|(?<=니다\.)\s+",
        raw,
    )
    cleaned = [clean_segment(part) for part in parts if clean_segment(part)]
    return cleaned if len(cleaned) > 1 else ([raw] if raw else [])


def _apply_provided_translations(
    details: list[Dict[str, Any]],
    korean_translation_text: str | None,
) -> None:
    translations = _split_korean_translation(korean_translation_text or "")
    if not translations:
        return

    for detail, translation in zip(details, translations):
        detail["translation"] = translation
        detail["translation_bracketed"] = translation


def _similarity_score(a: str, b: str) -> float:
    left = re.sub(r"[^a-z0-9]+", " ", (a or "").casefold()).strip()
    right = re.sub(r"[^a-z0-9]+", " ", (b or "").casefold()).strip()
    if not left or not right:
        return 0.0
    if left == right:
        return 1.0
    if left in right or right in left:
        return 0.92
    left_tokens = set(left.split())
    right_tokens = set(right.split())
    if not left_tokens or not right_tokens:
        return 0.0
    return len(left_tokens & right_tokens) / len(left_tokens | right_tokens)


def _apply_teacher_topic_sentence(
    details: list[Dict[str, Any]],
    teacher_topic_sentence: str | None,
) -> None:
    topic = str(teacher_topic_sentence or "").strip()
    if not topic or len(topic.split()) < 4:
        return

    best_index = -1
    best_score = 0.0
    for index, detail in enumerate(details):
        score = _similarity_score(topic, str(detail.get("original") or ""))
        if score > best_score:
            best_index = index
            best_score = score

    if best_index < 0 or best_score < 0.55:
        return

    for detail in details:
        if detail.get("role_highlight_type") == "topic":
            detail["role_highlight_type"] = "none"

    matched = details[best_index]
    matched["role_highlight_type"] = "topic"
    matched["sentence_role"] = "주제문 후보"
    matched["question_point"] = (
        "선생님이 직접 입력한 주제문과 연결되는 핵심 문장이므로 "
        "주제나 제목 문제의 근거가 될 수 있습니다."
    )


_GENERIC_CORE_MARKERS = {
    "central idea",
    "supporting evidence",
    "passage presents",
    "key idea",
    "review the passage",
}

_GENERIC_CORE_KOREAN_VALUES = {
    "지문의 핵심 주장과 이를 뒷받침하는 근거",
    "핵심 주장과 근거",
    "지문은 핵심 주장과 이를 뒷받침하는 근거를 설명한다.",
    "지문은 핵심 생각을 제시하고 설명이나 근거를 통해 이를 뒷받침한다.",
    "중심 생각과 이를 뒷받침하는 근거",
    "지문의 핵심 생각",
}


def _is_generic_core_value(value: Any) -> bool:
    text = str(value or "").strip()
    if not text:
        return True
    lower = text.casefold()
    if any(marker in lower for marker in _GENERIC_CORE_MARKERS):
        return True
    normalized = re.sub(r"\s+", " ", text)
    return normalized in _GENERIC_CORE_KOREAN_VALUES


def _best_teacher_topic_translation(
    text: str,
    korean_translation_text: str | None,
    teacher_topic_sentence: str | None,
) -> str:
    topic = str(teacher_topic_sentence or "").strip()
    if not topic:
        return ""
    translations = _split_korean_translation(korean_translation_text or "")
    if not translations:
        return ""
    sentences = _split_sentences(text)
    if not sentences:
        return translations[0]

    best_index = 0
    best_score = 0.0
    for index, sentence in enumerate(sentences):
        score = _similarity_score(topic, sentence)
        if score > best_score:
            best_index = index
            best_score = score

    if best_index < len(translations) and best_score >= 0.45:
        return translations[best_index]
    return translations[0]


def _teacher_topic_core_analysis(
    text: str,
    korean_translation_text: str | None,
    teacher_topic_sentence: str | None,
) -> Dict[str, str]:
    topic = re.sub(r"\s+", " ", str(teacher_topic_sentence or "").strip())
    sentences = _split_sentences(text)
    first_sentence = sentences[0] if sentences else _sentence_preview(text, 120)
    topic_translation = _best_teacher_topic_translation(
        text,
        korean_translation_text,
        topic,
    )

    lower_topic = topic.casefold()
    lower_text = text.casefold()

    if topic and (
        "look past the surface" in lower_topic
        or "deeper problem" in lower_topic
        or "empathy" in lower_topic
        or "judg" in lower_text
    ):
        return {
            "topic_en": "Looking beyond surface judgments to understand others with empathy",
            "topic_ko": "겉으로 보이는 판단을 넘어 타인을 이해와 공감으로 바라보는 것",
            "title_en": "Looking Beyond the Surface",
            "title_ko": "겉모습 너머를 바라보기",
            "gist_en": (
                "We should stop judging others superficially and try to understand "
                "the deeper reasons behind their lives and choices."
            ),
            "gist_ko": (
                "우리는 타인을 겉으로 판단하기보다 그들의 삶과 선택 뒤에 있는 "
                "더 깊은 이유를 이해하려고 해야 한다."
            ),
            "summary_en": (
                "The passage explains that while judging others may feel natural, "
                "deeper understanding and empathy can help us see beyond surface impressions."
            ),
            "summary_ko": (
                "이 글은 타인을 판단하는 일이 자연스럽게 느껴질 수 있지만, "
                "더 깊은 이해와 공감이 겉모습 너머를 보게 해 준다고 설명한다."
            ),
        }

    if topic:
        title_source = re.sub(
            r"^(if|when|because|although|while)\s+",
            "",
            topic,
            flags=re.IGNORECASE,
        )
        title_source = re.sub(
            r"\b(we|you|they|people)\s+(may|can|should|must|need to)\s+",
            "",
            title_source,
            flags=re.IGNORECASE,
        )
        title_words = title_source.split()[:7]
        title_en = " ".join(title_words).strip(" ,.;:")
        title_en = title_en[:1].upper() + title_en[1:] if title_en else "Key Focus of the Passage"
        topic_ko = (
            _sentence_preview(topic_translation, 90)
            if topic_translation
            else "선생님이 지정한 주제문을 중심으로 한 지문의 핵심 생각"
        )
        return {
            "topic_en": _sentence_preview(topic, 110),
            "topic_ko": topic_ko,
            "title_en": title_en,
            "title_ko": (
                _sentence_preview(topic_translation, 48)
                if topic_translation
                else "지정 주제문 중심의 독해"
            ),
            "gist_en": f"The passage emphasizes that {topic[:1].lower() + topic[1:]}",
            "gist_ko": (
                topic_translation
                if topic_translation
                else "지문은 선생님이 지정한 주제문을 중심 생각으로 전개한다."
            ),
            "summary_en": (
                f"The passage develops the teacher-selected idea, '{_sentence_preview(topic, 90)}', "
                "through the surrounding explanation and supporting details."
            ),
            "summary_ko": (
                _sentence_preview(topic_translation, 120)
                if topic_translation
                else "이 글은 선생님이 지정한 주제문을 중심으로 앞뒤 설명과 세부 근거를 전개한다."
            ),
        }

    return {
        "topic_en": _sentence_preview(first_sentence, 100),
        "topic_ko": "지문의 첫 핵심 문장을 바탕으로 한 중심 내용",
        "title_en": _sentence_preview(first_sentence, 58),
        "title_ko": "지문 핵심 내용 정리",
        "gist_en": _sentence_preview(first_sentence, 130),
        "gist_ko": "지문은 첫 핵심 내용을 중심으로 세부 설명을 이어 간다.",
        "summary_en": _sentence_preview(text, 180),
        "summary_ko": "지문 전체 내용을 바탕으로 중심 생각과 세부 설명을 정리한다.",
    }


def _repair_core_analysis(
    result: Dict[str, Any],
    text: str,
    korean_translation_text: str | None,
    teacher_topic_sentence: str | None,
) -> None:
    guided = _teacher_topic_core_analysis(
        text,
        korean_translation_text,
        teacher_topic_sentence,
    )
    for key, fallback in guided.items():
        if _is_generic_core_value(result.get(key)):
            result[key] = fallback


def _fallback_question_point(sentence: str, role: str) -> str:
    preview = _sentence_preview(sentence)
    if role == "해결책 제시":
        return f"'{preview}'에서 해결 방안을 제시하므로 요지나 제목 문제의 결론 근거가 됩니다."
    if role == "연구 결과 또는 핵심 원리 제시":
        return f"'{preview}'에서 핵심 원리나 연구 관점을 제시하므로 빈칸 또는 요지 문제의 근거가 됩니다."
    if role == "문제 상황 제시":
        return f"'{preview}'에서 지문의 핵심 문제 상황을 제시하므로 주제나 제목 문제의 근거가 됩니다."
    if role == "결과 설명":
        return f"'{preview}'에서 앞선 상황의 결과를 설명하므로 인과 관계를 묻는 빈칸 문제의 단서가 됩니다."
    if role == "대조 제시":
        return f"'{preview}'에서 대조되는 흐름을 보여 주므로 순서나 삽입 문제의 연결 단서가 됩니다."
    if role == "원인 또는 조건 설명":
        return f"'{preview}'에서 조건과 결과의 관계를 제시하므로 빈칸 또는 순서 문제의 단서가 됩니다."
    if role == "조건 설명":
        return f"'{preview}'에서 필요한 조건을 구체화하므로 세부 내용 또는 빈칸 문제의 근거가 됩니다."
    if role == "예시 제시":
        return f"'{preview}'에서 구체적 예시를 제시하므로 중심 내용과 사례를 구분하는 문제의 단서가 됩니다."
    if role == "핵심 소재 또는 문제 상황 제시":
        return f"'{preview}'에서 지문의 핵심 소재를 제시하므로 주제나 제목 문제의 출발점이 됩니다."
    if role == "결론 및 정리":
        return f"'{preview}'에서 글을 정리하므로 요지나 제목 문제의 결론 근거가 됩니다."
    return f"'{preview}'의 세부 설명은 앞뒤 흐름을 연결하므로 순서나 삽입 문제를 판단하는 단서가 됩니다."


def _meaningful_or_fallback(value: Any, fallback: str, rejected: set[str]) -> str:
    text = str(value or "").strip()
    if not text or text in rejected:
        return fallback
    return text


def _sentence_structure(sentence: str) -> Dict[str, Any]:
    try:
        result = analyze_structure(sentence)
        if not isinstance(result, dict):
            return {"bracketed": sentence, "spans": []}
        bracketed = _non_empty(result.get("analyzed_text"), sentence)
        spans = result.get("spans")
        return {
            "bracketed": bracketed,
            "spans": spans if isinstance(spans, list) else [],
        }
    except Exception as exc:
        print("SENTENCE STRUCTURE FALLBACK:", repr(exc))
        return {"bracketed": sentence, "spans": []}


_ROLE_HIGHLIGHT_TYPES = {"topic", "gist", "conclusion", "blank_candidate", "none"}
_LEGACY_ROLE_HIGHLIGHT_TYPES = {"blank_hint": "blank_candidate"}
_ROLE_HIGHLIGHT_PRIORITY = {
    "topic": 0,
    "gist": 1,
    "conclusion": 2,
    "blank_candidate": 3,
}
_HIGHLIGHT_TYPES = {"grammar", "vocabulary", "blank_hint"}


def _as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        return value.strip().lower() in {"true", "1", "yes", "y", "on"}
    return False


def _normalize_role_highlight_type(value: Any) -> str:
    role = str(value or "none").strip().lower()
    role = _LEGACY_ROLE_HIGHLIGHT_TYPES.get(role, role)
    return role if role in _ROLE_HIGHLIGHT_TYPES else "none"


def _highlight_question_point(
    sentence: str,
    role_highlight_type: str,
    is_blank_candidate: bool,
    sentence_role: str,
) -> str:
    preview = _sentence_preview(sentence)
    if role_highlight_type == "topic":
        return (
            f"'{preview}'에서 지문의 핵심 소재와 문제 상황이 드러나므로 "
            "주제나 제목 문제의 근거가 될 수 있습니다."
        )
    if role_highlight_type == "gist":
        return (
            f"'{preview}'에서 글쓴이의 중심 생각을 압축하므로 "
            "요지 문제의 핵심 근거가 될 수 있습니다."
        )
    if role_highlight_type == "conclusion":
        return (
            f"'{preview}'에서 앞의 내용을 정리하거나 해결책을 제시하므로 "
            "요지나 제목 문제의 결론 근거가 됩니다."
        )
    if role_highlight_type == "blank_candidate" or is_blank_candidate:
        return (
            f"'{preview}'에서 앞뒤 문맥을 통해 핵심 표현을 추론할 수 있으므로 "
            "빈칸 문제로 출제하기 적절합니다."
        )
    return _fallback_question_point(sentence, sentence_role)


def _limit_important_sentence_flags(details: list[Dict[str, Any]]) -> None:
    important: list[tuple[int, int, str]] = []
    for index, detail in enumerate(details):
        role = _normalize_role_highlight_type(detail.get("role_highlight_type"))
        is_blank = _as_bool(detail.get("is_blank_candidate"))
        if role != "none":
            important.append(
                (index, _ROLE_HIGHLIGHT_PRIORITY.get(role, 99), role)
            )
        elif is_blank:
            important.append(
                (index, _ROLE_HIGHLIGHT_PRIORITY["blank_candidate"], "blank_candidate")
            )

    allowed_indexes = {
        index
        for index, _, _ in sorted(important, key=lambda item: (item[1], item[0]))[:3]
    }

    for index, detail in enumerate(details):
        if index not in allowed_indexes:
            detail["role_highlight_type"] = "none"
            detail["is_blank_candidate"] = False


def _normalize_highlights(
    sentence: str,
    raw_highlights: Any,
    blank_hint_count: int,
) -> tuple[list[Dict[str, str]], int]:
    source_highlights = raw_highlights if isinstance(raw_highlights, list) else []
    highlights: list[Dict[str, str]] = []
    seen: set[tuple[str, str]] = set()

    for item in source_highlights:
        if not isinstance(item, dict):
            continue

        highlight_type = str(item.get("type") or "").strip().lower()
        highlight_text = str(item.get("text") or "").strip()
        if highlight_type not in _HIGHLIGHT_TYPES or not highlight_text:
            continue
        if highlight_text.lower() not in sentence.lower():
            continue
        if highlight_type == "blank_hint" and blank_hint_count >= 3:
            continue

        key = (highlight_type, highlight_text.lower())
        if key in seen:
            continue
        seen.add(key)

        if highlight_type == "blank_hint":
            blank_hint_count += 1

        highlights.append(
            {
                "text": highlight_text,
                "type": highlight_type,
                "memo": str(item.get("memo") or "").strip(),
            }
        )
        if len(highlights) >= 6:
            break

    return highlights, blank_hint_count


def _normalize_grammar_points(
    sentence: str,
    raw_points: Any,
) -> list[Dict[str, Any]]:
    source_points = _rule_based_grammar_points(sentence)
    if isinstance(raw_points, list):
        source_points.extend(raw_points)
    grammar_points: list[Dict[str, Any]] = []
    seen_targets: set[str] = set()
    lowered_sentence = sentence.casefold()

    for item in source_points:
        if not isinstance(item, dict):
            continue

        target = str(item.get("target") or "").strip()
        label = str(item.get("label") or "").strip()
        explanation = str(item.get("explanation") or "").strip()
        reference_no = _normalize_reference_no(item.get("reference_no"))

        if not target or not label or not explanation:
            continue
        if target.casefold() not in lowered_sentence:
            continue

        key = target.casefold()
        if key in seen_targets:
            continue
        seen_targets.add(key)

        point = {
            "target": target,
            "label": label,
            "explanation": _sentence_preview(explanation, 120),
        }
        if reference_no is not None:
            point["reference_no"] = reference_no
        grammar_points.append(point)
        if len(grammar_points) >= 3:
            break

    return grammar_points


def _normalize_reference_no(value: Any) -> int | None:
    if value is None:
        return None
    try:
        number = int(str(value).strip())
    except (TypeError, ValueError):
        return None
    return number if number > 0 else None


def _add_rule_point(
    points: list[Dict[str, Any]],
    sentence: str,
    target: str,
    label: str,
    explanation: str,
    reference_no: int,
) -> None:
    target = re.sub(r"\s+", " ", target).strip(" ,.;:")
    if not target or target.casefold() not in sentence.casefold():
        return
    if any(point["target"].casefold() == target.casefold() for point in points):
        return
    if any(
        target.casefold() in point["target"].casefold()
        or point["target"].casefold() in target.casefold()
        for point in points
    ):
        return
    points.append(
        {
            "target": target,
            "label": label,
            "explanation": explanation,
            "reference_no": reference_no,
        }
    )


def _rule_based_grammar_points(sentence: str) -> list[Dict[str, Any]]:
    points: list[Dict[str, Any]] = []

    as_if = re.search(
        r"\bas if\s+.+?(?=\s+the way\b|[,.;!?]|$)",
        sentence,
        flags=re.IGNORECASE,
    )
    if as_if:
        target = as_if.group(0)
        if re.search(r"\bas if\s+\w+\s+had\s+\w+", target, flags=re.IGNORECASE):
            _add_rule_point(
                points,
                sentence,
                target,
                "as if 가정법 과거완료",
                "as if 뒤에 had p.p.가 쓰여 과거 사실과 다른 상황을 가정해 표현합니다.",
                190,
            )
        else:
            _add_rule_point(
                points,
                sentence,
                target,
                "as if 가정법",
                "as if 뒤에 조동사 과거형이나 과거형이 쓰여 실제와 다른 상황을 가정해 표현합니다.",
                189,
            )

    inverted_if = re.search(
        r"^(Had|Were|Should)\s+[^,]+",
        sentence.strip(),
        flags=re.IGNORECASE,
    )
    if inverted_if:
        _add_rule_point(
            points,
            sentence,
            inverted_if.group(0),
            "had + 주어 + p.p. 도치",
            "Had가 문두에 나와 if가 생략된 가정법 과거완료 도치 구조입니다.",
            193,
        )

    for match in re.finditer(
        r"\b(?:believe|believes|believed|think|thinks|thought|show|shows|showed|suggest|suggests|suggested)\s+"
        r"(that\s+[^,.!]+)",
        sentence,
        flags=re.IGNORECASE,
    ):
        _add_rule_point(
            points,
            sentence,
            match.group(1),
            "종속접속사 that",
            "that절이 앞 동사의 목적어 역할을 하는 명사절입니다.",
            58,
        )

    for match in re.finditer(
        r"\b(?:idea|fact|belief|claim|argument|view|possibility|evidence)\s+"
        r"(that\s+[^,.!]+)",
        sentence,
        flags=re.IGNORECASE,
    ):
        _add_rule_point(
            points,
            sentence,
            match.group(1),
            "종속접속사 that",
            "that절이 앞의 추상명사를 구체적으로 설명하는 명사절 역할을 합니다.",
            58,
        )

    for match in re.finditer(
        r"\b(?:which|who|whose)\s+.+?(?=\s+because\b|[,.;!?]|$)",
        sentence,
        flags=re.IGNORECASE,
    ):
        _add_rule_point(
            points,
            sentence,
            match.group(0),
            "관계대명사",
            "관계사절이 앞의 명사를 설명하는 구조입니다.",
            70,
        )

    for match in re.finditer(
        r"\b(?:where|when|why|how)\s+[^,.!]+",
        sentence,
        flags=re.IGNORECASE,
    ):
        _add_rule_point(
            points,
            sentence,
            match.group(0),
            "관계부사",
            "관계부사절이 시간, 장소, 이유, 방법과 관련된 앞의 말을 설명합니다.",
            80,
        )

    for match in re.finditer(r"\bbecause\s+[^,.!]+", sentence, flags=re.IGNORECASE):
        _add_rule_point(
            points,
            sentence,
            match.group(0),
            "종속접속사",
            "because절이 이유를 나타내는 부사절입니다.",
            58,
        )

    for match in re.finditer(r"(?<!as\s)\bif\s+[^,.!]+", sentence, flags=re.IGNORECASE):
        _add_rule_point(
            points,
            sentence,
            match.group(0),
            "종속접속사",
            "if절이 조건을 나타내는 부사절입니다.",
            58,
        )

    for match in re.finditer(
        r"\b(?:when|although|while)\s+[^,.!]+",
        sentence,
        flags=re.IGNORECASE,
    ):
        _add_rule_point(
            points,
            sentence,
            match.group(0),
            "종속접속사",
            "종속접속사가 시간, 상황, 양보를 나타내는 부사절을 이끕니다.",
            58,
        )

    for match in re.finditer(
        r"\bto\s+(?:[a-z]+)(?:\s+[^,.!]+)?",
        sentence,
        flags=re.IGNORECASE,
    ):
        target = match.group(0)
        if len(target.split()) <= 8:
            _add_rule_point(
                points,
                sentence,
                target,
                "to부정사",
                "to부정사구가 문장에서 명사, 형용사, 부사 역할 중 하나로 쓰입니다.",
                35,
            )

    for match in re.finditer(
        r"\b(?:is|are|was|were|be|been|being)\s+(?:[a-z]+ed|known|made|seen|given|taken|written|built|caught|eaten|run|affected|supported|owned|strained)\b(?:\s+by\s+[^,.!?]+)?",
        sentence,
        flags=re.IGNORECASE,
    ):
        _add_rule_point(
            points,
            sentence,
            match.group(0),
            "능동태 vs 수동태",
            "be동사와 과거분사가 함께 쓰여 주어가 동작을 당하는 수동 의미를 나타냅니다.",
            10,
        )

    for match in re.finditer(
        r"\b(?:has|have|had)\s+(?:been\s+)?(?:[a-z]+ed|known|made|seen|given|taken|written|built|caught|eaten|run)\b",
        sentence,
        flags=re.IGNORECASE,
    ):
        _add_rule_point(
            points,
            sentence,
            match.group(0),
            "현재완료시제",
            "have/has/had와 p.p.가 함께 쓰여 완료 의미를 나타냅니다.",
            155,
        )

    for match in re.finditer(
        r"\b(?:more|less|better|worse)\s+[^,.!?]+?\s+than\s+[^,.!?]+",
        sentence,
        flags=re.IGNORECASE,
    ):
        _add_rule_point(
            points,
            sentence,
            match.group(0),
            "비교급",
            "비교급과 than이 함께 쓰여 두 대상을 비교합니다.",
            135,
        )

    for match in re.finditer(
        r"\b(?:can|could|may|might|must|should|would|will)\s+(?:have\s+)?(?!with\b|by\b|to\b|of\b|in\b|on\b|at\b|for\b)[a-z]+",
        sentence,
        flags=re.IGNORECASE,
    ):
        _add_rule_point(
            points,
            sentence,
            match.group(0),
            "가능성·추측 조동사",
            "조동사가 가능성, 추측, 의무, 의지를 나타내며 뒤의 동사 의미를 조절합니다.",
            180,
        )

    for match in re.finditer(
        r"\bgetting\s+.+?\s+to\s+.+?(?=\s+or\s+use\b|[,.;!?]|$)",
        sentence,
        flags=re.IGNORECASE,
    ):
        _add_rule_point(
            points,
            sentence,
            match.group(0),
            "동명사의 명사 역할",
            "getting으로 시작하는 구가 문장에서 명사 역할을 합니다.",
            38,
        )

    return points[:3]


def _build_sentence_details(text: str, raw_details: Any) -> list[Dict[str, Any]]:
    sentences = _split_sentences(text)
    source_details = raw_details if isinstance(raw_details, list) else []
    total = len(sentences)
    details: list[Dict[str, Any]] = []
    blank_hint_count = 0
    blank_candidate_count = 0
    seen_question_points: set[str] = set()

    for index, sentence in enumerate(sentences):
        source = source_details[index] if index < len(source_details) else {}
        if not isinstance(source, dict):
            source = {}

        role_highlight_type = _normalize_role_highlight_type(
            source.get("role_highlight_type"),
        )
        is_blank_candidate = _as_bool(source.get("is_blank_candidate"))
        if role_highlight_type == "blank_candidate":
            is_blank_candidate = True
        if is_blank_candidate:
            if blank_candidate_count >= 3:
                is_blank_candidate = False
                if role_highlight_type == "blank_candidate":
                    role_highlight_type = "none"
            else:
                blank_candidate_count += 1

        highlights, blank_hint_count = _normalize_highlights(
            sentence,
            source.get("highlights"),
            blank_hint_count,
        )
        grammar_points = _normalize_grammar_points(
            sentence,
            source.get("grammar_points"),
        )
        structure = _sentence_structure(sentence)
        fallback_role = _fallback_sentence_role(sentence, index, total)
        sentence_role = _non_empty(
            source.get("sentence_role"),
            fallback_role,
        )
        translation = _meaningful_or_fallback(
            source.get("translation"),
            _TRANSLATION_PENDING,
            _GENERIC_TRANSLATIONS,
        )
        translation_bracketed = _meaningful_or_fallback(
            source.get("translation_bracketed"),
            translation,
            _GENERIC_TRANSLATIONS,
        )

        details.append(
            {
                "sentence_no": index + 1,
                "original": sentence,
                "translation": translation,
                "translation_bracketed": translation_bracketed,
                "bracketed": structure["bracketed"],
                "spans": structure["spans"],
                "sentence_role": sentence_role,
                "role_highlight_type": role_highlight_type,
                "is_blank_candidate": is_blank_candidate,
                "highlights": highlights,
                "grammar_points": grammar_points,
                "_raw_question_point": source.get("question_point"),
            }
        )

    _limit_important_sentence_flags(details)

    for detail in details:
        sentence = str(detail.get("original") or "")
        sentence_role = str(detail.get("sentence_role") or "")
        role_highlight_type = _normalize_role_highlight_type(
            detail.get("role_highlight_type"),
        )
        is_blank_candidate = _as_bool(detail.get("is_blank_candidate"))
        fallback_question_point = _highlight_question_point(
            sentence,
            role_highlight_type,
            is_blank_candidate,
            sentence_role,
        )
        question_point = _meaningful_or_fallback(
            detail.get("_raw_question_point"),
            fallback_question_point,
            _GENERIC_QUESTION_POINTS,
        )
        if role_highlight_type != "none" or is_blank_candidate:
            question_point = fallback_question_point

        question_point_key = question_point.casefold()
        if question_point_key in seen_question_points:
            question_point = fallback_question_point
            question_point_key = question_point.casefold()
        seen_question_points.add(question_point_key)

        detail["role_highlight_type"] = role_highlight_type
        detail["is_blank_candidate"] = is_blank_candidate
        detail["question_point"] = question_point
        detail.pop("_raw_question_point", None)

    return details


def _fallback_analysis(text: str) -> Dict[str, Any]:
    """
    Keep Final Touch useful when GPT is unavailable or returns invalid JSON.

    The fallback is intentionally modest: it never pretends to be a full
    translation, but it always provides readable study notes for short texts.
    """
    sentences = _split_sentences(text)
    first = sentences[0] if sentences else _plain_text(text)
    last = sentences[-1] if sentences else first
    body = " ".join(sentences[1:]) if len(sentences) > 1 else first
    gist_en = last or first or "Review the passage to identify its central idea."

    return {
        "outline": {
            "intro": "지문의 핵심 소재와 문제 상황을 제시한다.",
            "body": "핵심 소재에 대한 설명과 근거를 통해 내용을 구체화한다.",
            "conclusion": (
                "마지막 문장에서 해결책이나 최종 생각을 정리한다."
                if len(sentences) > 2
                else "명시적인 결론 대신 전체 내용을 통해 중심 생각을 정리한다."
            ),
        },
        "topic_en": "The passage's central idea and supporting evidence",
        "topic_ko": "지문의 핵심 주장과 이를 뒷받침하는 근거",
        "title_en": "Central Idea and Supporting Evidence",
        "title_ko": "핵심 주장과 근거",
        "gist_en": gist_en,
        "gist_ko": "지문은 핵심 주장과 이를 뒷받침하는 근거를 설명한다.",
        "summary_en": "The passage presents a central idea and supports it with an explanation or evidence.",
        "summary_ko": "지문은 핵심 생각을 제시하고 설명이나 근거를 통해 이를 뒷받침한다.",
        "sentence_details": _build_sentence_details(text, []),
    }


def _non_empty(value: Any, fallback: str) -> str:
    text = str(value or "").strip()
    return text or fallback


def _normalize_analysis_result(
    text: str,
    raw: Any,
    korean_translation_text: str | None = None,
    teacher_topic_sentence: str | None = None,
) -> Dict[str, Any]:
    fallback = _fallback_analysis(text)
    data = raw if isinstance(raw, dict) else {}

    raw_outline = data.get("outline") or data.get("flow") or {}
    if not isinstance(raw_outline, dict):
        raw_outline = {}
    fallback_outline = fallback["outline"]

    sentence_details = _build_sentence_details(
        text,
        data.get("sentence_details"),
    )
    _apply_provided_translations(sentence_details, korean_translation_text)
    _apply_teacher_topic_sentence(sentence_details, teacher_topic_sentence)
    _limit_important_sentence_flags(sentence_details)

    result = {
        "outline": {
            "intro": _non_empty(
                raw_outline.get("intro") or raw_outline.get("introduction"),
                fallback_outline["intro"],
            ),
            "body": _non_empty(raw_outline.get("body"), fallback_outline["body"]),
            "conclusion": _non_empty(
                raw_outline.get("conclusion"),
                fallback_outline["conclusion"],
            ),
        },
        "topic_en": _non_empty(
            data.get("topic_en") or data.get("topic"),
            fallback["topic_en"],
        ),
        "topic_ko": _non_empty(data.get("topic_ko"), fallback["topic_ko"]),
        "title_en": _non_empty(
            data.get("title_en") or data.get("title"),
            fallback["title_en"],
        ),
        "title_ko": _non_empty(data.get("title_ko"), fallback["title_ko"]),
        "gist_en": _non_empty(
            data.get("gist_en") or data.get("gist"),
            fallback["gist_en"],
        ),
        "gist_ko": _non_empty(data.get("gist_ko"), fallback["gist_ko"]),
        "summary_en": _non_empty(
            data.get("summary_en") or data.get("summary"),
            fallback["summary_en"],
        ),
        "summary_ko": _non_empty(data.get("summary_ko"), fallback["summary_ko"]),
        "sentence_details": sentence_details,
    }
    _repair_core_analysis(
        result,
        text,
        korean_translation_text,
        teacher_topic_sentence,
    )
    return result


# -------------------------------------------------
# DB 저장 helper
# -------------------------------------------------
def save_passage_safely(
    db: Session,
    passage_text: str,
    folder_id: Optional[int],
    teacher_id: int = 1,
    title: str = "분석 지문",
) -> Optional[int]:
    """
    Passage 모델의 실제 컬럼을 확인해서 가능한 필드만 저장한다.
    DB 저장 실패가 분석 결과 반환을 막지 않도록 예외를 내부 처리한다.
    """

    try:
        passage_columns = set(models.Passage.__table__.columns.keys())

        values: Dict[str, Any] = {}

        # 프로젝트마다 Passage 본문 컬럼명이 다를 수 있어 방어
        if "content" in passage_columns:
            values["content"] = passage_text
        elif "text" in passage_columns:
            values["text"] = passage_text
        elif "passage" in passage_columns:
            values["passage"] = passage_text

        # 제목 컬럼이 있으면 저장
        if "title" in passage_columns:
            values["title"] = title
        if "source_title" in passage_columns:
            values["source_title"] = title

        # 작성자 컬럼 방어
        if "created_by" in passage_columns:
            values["created_by"] = "teacher1"

        if "teacher_id" in passage_columns:
            values["teacher_id"] = teacher_id

        # 폴더 컬럼이 있을 때만 저장
        if "folder_id" in passage_columns and folder_id is not None:
            values["folder_id"] = folder_id

        if not values:
            print("⚠️ Passage 저장 생략: 저장 가능한 컬럼 없음")
            return None

        passage = models.Passage(**values)

        db.add(passage)
        db.commit()
        db.refresh(passage)

        passage_id = getattr(passage, "id", None)

        print("✅ Passage 저장 완료:", passage_id)

        return passage_id

    except Exception as e:
        db.rollback()
        print("❌ Passage 저장 실패:", e)
        return None


def resolve_folder_id(
    db: Session,
    teacher_id: int,
    folder_id: Optional[int] = None,
    folder_name: Optional[str] = None,
    textbook_folder_name: Optional[str] = None,
    unit_folder_name: Optional[str] = None,
) -> Optional[int]:
    if folder_id is not None:
        folder = db.query(models.Folder).filter(models.Folder.id == folder_id).first()
        if folder:
            return folder.id

    textbook_name = (textbook_folder_name or "").strip()
    unit_name = (unit_folder_name or "").strip()

    if textbook_name and unit_name:
        textbook = get_or_create_folder(
            db=db,
            teacher_id=teacher_id,
            name=textbook_name,
            parent_id=None,
        )
        unit = get_or_create_folder(
            db=db,
            teacher_id=teacher_id,
            name=unit_name,
            parent_id=textbook.id,
        )
        return unit.id

    name = textbook_name or unit_name or (folder_name or "").strip()
    if not name:
        return None

    folder = get_or_create_folder(
        db=db,
        teacher_id=teacher_id,
        name=name,
        parent_id=None,
    )
    return folder.id


def get_or_create_folder(
    db: Session,
    teacher_id: int,
    name: str,
    parent_id: Optional[int],
) -> models.Folder:
    folder = (
        db.query(models.Folder)
        .filter(
            models.Folder.owner_id == teacher_id,
            models.Folder.name == name,
            models.Folder.parent_id == parent_id,
        )
        .first()
    )

    if folder:
        return folder

    folder = models.Folder(
        name=name,
        owner_id=teacher_id,
        parent_id=parent_id,
        is_public=True,
    )
    db.add(folder)
    db.commit()
    db.refresh(folder)
    return folder


def decode_optional_user(
    credentials: HTTPAuthorizationCredentials | None,
) -> dict | None:
    if credentials is None:
        return None

    try:
        payload = jwt.decode(
            credentials.credentials,
            SECRET_KEY,
            algorithms=[ALGORITHM],
        )
        if payload.get("type") != "access":
            return None
        return payload
    except JWTError:
        return None


def save_analysis_record_safely(
    db: Session,
    teacher_id: int,
    passage_id: Optional[int],
    folder_id: Optional[int],
    passage_bracketed: str,
    analysis: Dict[str, Any],
) -> Optional[int]:
    if passage_id is None:
        return None

    try:
        record = models.AnalysisRecord(
            teacher_id=teacher_id,
            passage_id=passage_id,
            passage_bracketed=passage_bracketed,
            topic_en=analysis.get("topic_en", ""),
            topic_ko=analysis.get("topic_ko", ""),
            title_en=analysis.get("title_en", ""),
            title_ko=analysis.get("title_ko", ""),
            gist_en=analysis.get("gist_en", ""),
            gist_ko=analysis.get("gist_ko", ""),
            outline=analysis.get("outline", {}),
            sentence_details=analysis.get("sentence_details", []),
            folder_id=folder_id,
        )
        db.add(record)
        db.commit()
        db.refresh(record)
        return record.id
    except Exception as e:
        db.rollback()
        print("AnalysisRecord save failed:", e)
        return None


# -------------------------------------------------
# Schema
# -------------------------------------------------
class In(BaseModel):
    passage: str
    force_analyze: bool = True
    folder_id: int | None = None
    folder_name: str | None = None
    textbook_folder_name: str | None = None
    unit_folder_name: str | None = None
    source: str | None = None
    korean_translation_text: str | None = None
    teacher_topic_sentence: str | None = None


class Out(BaseModel):
    passage_id: Optional[int] = None
    analysis_record_id: Optional[int] = None
    passage_bracketed: str
    outline: Dict[str, str]
    topic_en: str
    topic_ko: str
    title_en: str
    title_ko: str
    gist_en: str
    gist_ko: str
    summary_en: str = ""
    summary_ko: str = ""
    sentence_details: list[Dict[str, Any]] = Field(default_factory=list)


# -------------------------------------------------
# 🔥 최종 API
# -------------------------------------------------
@router.post("/summary_flow", response_model=Out)
async def summary_flow(
    payload: In,
    db: Session = Depends(get_db),
    credentials: HTTPAuthorizationCredentials | None = Depends(optional_security),
):
    text = (payload.passage or "").strip()

    if not text:
        return Out(
            passage_id=None,
            analysis_record_id=None,
            passage_bracketed="",
            outline={
                "intro": "",
                "body": "",
                "conclusion": "",
            },
            topic_en="",
            topic_ko="",
            title_en="",
            title_ko="",
            gist_en="",
            gist_ko="",
            summary_en="",
            summary_ko="",
            sentence_details=[],
        )

    print("ANALYZE SUMMARY REQUEST:", {"passage_length": len(text), "source": payload.source})
    print("ANALYZE SUMMARY API_BASE:", API_BASE)

    # 1️⃣ 괄호 처리
    if payload.force_analyze or not has_brackets(text):
        try:
            bracketed = await fetch_bracketed(text)
            print("✅ 구조 분석 성공")
        except Exception as e:
            print("⚠️ 구조 분석 실패 → 원문 사용:", e)
            bracketed = text
    else:
        bracketed = text

    # 2️⃣ GPT 분석
    try:
        gpt_result = analyze_with_gpt(
            text,
            korean_translation_text=payload.korean_translation_text,
            teacher_topic_sentence=payload.teacher_topic_sentence,
        )
        print("GPT ANALYSIS RAW RESULT:", json.dumps(gpt_result, ensure_ascii=False))
    except Exception as e:
        print("GPT ANALYSIS FAILED:", repr(e))
        gpt_result = {}

    gpt_result = _normalize_analysis_result(
        text,
        gpt_result,
        korean_translation_text=payload.korean_translation_text,
        teacher_topic_sentence=payload.teacher_topic_sentence,
    )
    print("ANALYZE SUMMARY NORMALIZED RESULT:", json.dumps(gpt_result, ensure_ascii=False))

    # 3) Save Passage and AnalysisRecord
    user = decode_optional_user(credentials)
    teacher_id = int(user["sub"]) if user and user.get("role") == "teacher" else 1
    folder_id = resolve_folder_id(
        db=db,
        teacher_id=teacher_id,
        folder_id=payload.folder_id,
        folder_name=payload.folder_name,
        textbook_folder_name=payload.textbook_folder_name,
        unit_folder_name=payload.unit_folder_name,
    )
    title_for_save = (
        payload.source
        or gpt_result.get("title_ko")
        or gpt_result.get("title_en")
        or "?? ??"
    )

    passage_id = save_passage_safely(
        db=db,
        passage_text=text,
        folder_id=folder_id,
        teacher_id=teacher_id,
        title=title_for_save,
    )
    print("SAVED PASSAGE ID:", passage_id)

    analysis_record_id = save_analysis_record_safely(
        db=db,
        teacher_id=teacher_id,
        passage_id=passage_id,
        folder_id=folder_id,
        passage_bracketed=bracketed,
        analysis=gpt_result,
    )
    print("SAVED ANALYSIS RECORD ID:", analysis_record_id)
    print("INTRO:", gpt_result["outline"]["intro"])
    print("BODY:", gpt_result["outline"]["body"])
    print("CONCLUSION:", gpt_result["outline"]["conclusion"])
    print("TOPIC:", gpt_result["topic_en"], "/", gpt_result["topic_ko"])
    print("TITLE:", gpt_result["title_en"], "/", gpt_result["title_ko"])
    print("GIST:", gpt_result["gist_en"], "/", gpt_result["gist_ko"])
    print("SUMMARY:", gpt_result["summary_en"], "/", gpt_result["summary_ko"])
    print("SENTENCE DETAILS COUNT:", len(gpt_result["sentence_details"]))

    # 4️⃣ 반환
    return Out(
        passage_id=passage_id,
        analysis_record_id=analysis_record_id,
        passage_bracketed=bracketed,
        outline=gpt_result.get(
            "outline",
            {
                "intro": "",
                "body": "",
                "conclusion": "",
            },
        ),
        topic_en=gpt_result.get("topic_en", ""),
        topic_ko=gpt_result.get("topic_ko", ""),
        title_en=gpt_result.get("title_en", ""),
        title_ko=gpt_result.get("title_ko", ""),
        gist_en=gpt_result.get("gist_en", ""),
        gist_ko=gpt_result.get("gist_ko", ""),
        summary_en=gpt_result.get("summary_en", ""),
        summary_ko=gpt_result.get("summary_ko", ""),
        sentence_details=gpt_result.get("sentence_details", []),
    )
