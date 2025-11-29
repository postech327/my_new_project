from __future__ import annotations
from fastapi import APIRouter
from pydantic import BaseModel
from typing import Optional, Dict, Any
import httpx
import os
import re

router = APIRouter(prefix="/analyze", tags=["analyze"])

API_BASE = os.getenv("WORD_API_BASE", "http://127.0.0.1:8000").rstrip("/")

# --- 유틸: 괄호 존재 여부 ---
_BR_RE = re.compile(r"[\[\]\(\)\{\}]")
def has_brackets(s: str) -> bool:
    return bool(_BR_RE.search(s or ""))

# --- 구조분석 호출 ---
async def fetch_bracketed(text: str) -> str:
    url = f"{API_BASE}/analyze_structure"
    async with httpx.AsyncClient(timeout=40) as client:
        r = await client.post(url, json={"text": text})
        r.raise_for_status()
        data = r.json()
    # 유연 추출
    def pick(d: Any) -> Optional[str]:
        if isinstance(d, str):
            return d.strip()
        if isinstance(d, dict):
            for k in ("bracketed","processed_text","result","output","text"):
                v = d.get(k)
                if isinstance(v, str) and v.strip():
                    return v.strip()
            for k in ("data","payload","response"):
                v = d.get(k)
                if isinstance(v, dict):
                    for kk in ("bracketed","processed_text","result","output","text"):
                        vv = v.get(kk)
                        if isinstance(vv, str) and vv.strip():
                            return vv.strip()
        return None
    picked = pick(data)
    if not picked:
        raise ValueError("Unsupported /analyze_structure response format")
    return picked

# --- 단순 서/본/결 나누기(원하는 로직으로 교체 가능) ---
def simple_outline(text: str) -> Dict[str, str]:
    n = max(len(text), 3)
    a = int(n * 0.33); b = int(n * 0.66)
    return {
        "intro": text[:a].strip(),
        "body": text[a:b].strip(),
        "conclusion": text[b:].strip()
    }

# --- 요지/제목/주제 스텁(원 서비스로 교체) ---
def tts_stub(text: str) -> Dict[str, str]:
    return {
        "topic_en": "kitten rescue from predators",
        "topic_ko": "포식자로부터 새끼 고양이 구조",
        "title_en": "Protecting Kittens from Predators in the Wild",
        "title_ko": "야생에서 새끼 고양이를 지키는 법",
        "gist_en": "Rescuing a squeaking kitten quickly can prevent predators from being attracted to it.",
        "gist_ko": "울부짖는 새끼 고양이를 신속히 구조하면 포식자가 접근하는 것을 막을 수 있습니다.",
    }

class In(BaseModel):
    passage: str
    force_analyze: bool = True   # 괄호가 없어도 강제 분석 (기본 True)

class Out(BaseModel):
    passage_bracketed: str
    outline: Dict[str, str]      # {intro, body, conclusion}
    topic_en: str
    topic_ko: str
    title_en: str
    title_ko: str
    gist_en: str
    gist_ko: str

@router.post("/summary_flow", response_model=Out)
async def summary_flow(payload: In):
    text = payload.passage or ""
    # 1) 괄호 없으면 구조분석, 있으면 그대로 사용 (force_analyze=True면 무조건 분석)
    if payload.force_analyze or not has_brackets(text):
        try:
            bracketed = await fetch_bracketed(text)
        except Exception:
            bracketed = text
    else:
        bracketed = text

    # 2) 요지/제목/주제
    tts = tts_stub(bracketed)

    # 3) 서/본/결 (괄호 반영된 텍스트 기준)
    outline = simple_outline(bracketed)

    return Out(
        passage_bracketed=bracketed,
        outline=outline,
        **tts
    )