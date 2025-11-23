# routers/paragraph.py
from fastapi import APIRouter
from pydantic import BaseModel
from typing import List, Dict, Any
from structure_analyzer import analyze_structure

# 문장 분리: spaCy 있으면 사용, 없으면 정규식 폴백
try:
    import spacy  # type: ignore
    _NLP = spacy.load("en_core_web_sm")
except Exception:
    _NLP = None

router = APIRouter(prefix="/analyze_paragraph", tags=["paragraph"])

class TextInput(BaseModel):
    text: str

def _split_sentences(text: str) -> List[str]:
    if not text.strip():
        return []
    if _NLP:
        doc = _NLP(text)
        sents = [s.text.strip() for s in doc.sents if s.text.strip()]
        if sents:
            return sents
    # 폴백: 마침표/물음표/느낌표 뒤 공백 + 대문자(또는 따옴표) 시작 기준
    import re
    parts = re.split(r'(?<=[.!?])\s+(?=[A-Z"])', text.strip())
    out, buf = [], ""
    for p in parts:
        p = p.strip()
        if not p:
            continue
        buf = f"{buf} {p}".strip() if buf else p
        if re.search(r'[.!?]["\')\]]*$', buf):
            out.append(buf); buf = ""
    if buf:
        out.append(buf)
    return out

def _normalize_result(r: Any, original_text: str) -> Dict[str, Any]:
    if isinstance(r, dict):
        return {
            "text": r.get("text", original_text),
            "analyzed_text": r.get("analyzed_text", r.get("text", original_text)),
            "spans": r.get("spans", []),
        }
    return {"text": original_text, "analyzed_text": str(r), "spans": []}

@router.post("")
def analyze_paragraph(req: TextInput) -> Dict[str, Any]:
    sentences = _split_sentences(req.text)
    results: List[Dict[str, Any]] = []
    for i, s in enumerate(sentences, 1):
        raw = analyze_structure(s)  # dict 또는 str
        norm = _normalize_result(raw, s)
        norm["index"] = i
        results.append(norm)

    return {
        "ok": True,
        "sentences": results,
        "full": {
            "text": req.text,
            "analyzed_text": "\n".join(x["analyzed_text"] for x in results)
        }
    }