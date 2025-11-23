# routers/structure.py
from fastapi import APIRouter
from pydantic import BaseModel
from typing import Any, Dict, List
from structure_analyzer import analyze_structure

router = APIRouter(prefix="/analyze_structure", tags=["structure"])

class TextInput(BaseModel):
    text: str

def _normalize_result(r: Any, original_text: str) -> Dict[str, Any]:
    """
    analyze_structure가 dict 또는 str 중 무엇을 반환하더라도
    항상 {text, analyzed_text, spans} 로 맞춘다.
    """
    if isinstance(r, dict):
        return {
            "text": r.get("text", original_text),
            "analyzed_text": r.get("analyzed_text", r.get("text", original_text)),
            "spans": r.get("spans", []),
            "legend": r.get("legend", {"[]":"clauses","()":"phrases","{}":"non-finite"}),
        }
    # 문자열(옛 버전)인 경우
    return {
        "text": original_text,
        "analyzed_text": str(r),
        "spans": [],
        "legend": {"[]":"clauses","()":"phrases","{}":"non-finite"},
    }

@router.post("")
def analyze(req: TextInput):
    raw = analyze_structure(req.text)
    result = _normalize_result(raw, req.text)
    return {"ok": True, "result": result}