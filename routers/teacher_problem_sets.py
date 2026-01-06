# routers/teacher_problem_sets.py
from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from db import get_db
import models

router = APIRouter(
    prefix="/teacher",
    tags=["teacher_problem_sets"],
)

# ----------------------------
# Utils
# ----------------------------
_CIRCLED = ["①", "②", "③", "④", "⑤", "⑥", "⑦", "⑧", "⑨", "⑩"]


def _label_for(idx: int) -> str:
    if 0 <= idx < len(_CIRCLED):
        return _CIRCLED[idx]
    return str(idx + 1)


def _ensure_options(options: List[str]) -> List[str]:
    cleaned = [o.strip() for o in options if o and o.strip()]
    if len(cleaned) < 2:
        raise HTTPException(status_code=400, detail="options must have at least 2 items")
    return cleaned


def _db_get(db: Session, model, obj_id: int):
    get_fn = getattr(db, "get", None)
    if callable(get_fn):
        return db.get(model, obj_id)
    return db.query(model).filter(model.id == obj_id).first()


# ----------------------------
# Schemas (요청/응답 전용)
# ----------------------------
class SaveItem(BaseModel):
    stem: str
    options: List[str]
    answer_index: int = Field(ge=0)
    meta: Dict[str, Any] = Field(default_factory=dict)
    explanation: Optional[str] = None
    order: Optional[int] = None


class SaveProblemSetReq(BaseModel):
    analysis_id: int
    question_type: str
    name: str = "Problem Set"
    description: Optional[str] = None
    created_by: Optional[str] = "teacher"
    types_json: Optional[List[str]] = None
    mode: str = "teacher"
    is_published: bool = False

    items: List[SaveItem]


class SaveProblemSetRes(BaseModel):
    passage_id: int
    problem_set_id: int
    question_count: int


# ----------------------------
# POST: 문제세트 저장 (B안)
# ----------------------------
@router.post("/problem_sets", response_model=SaveProblemSetRes)
def create_problem_set(req: SaveProblemSetReq, db: Session = Depends(get_db)):
    if not req.items:
        raise HTTPException(status_code=400, detail="items is empty")

    # 1) AnalysisRecord → Passage
    rec = _db_get(db, models.AnalysisRecord, req.analysis_id)
    if not rec:
        raise HTTPException(status_code=404, detail="AnalysisRecord not found")

    passage_content = (rec.input_text or "").strip()
    if not passage_content:
        raise HTTPException(status_code=400, detail="analysis.input_text is empty")

    passage = models.Passage(
        title=f"(from analysis {req.analysis_id})",
        content=passage_content,
        created_by=req.created_by,
    )
    db.add(passage)
    db.flush()

    # 2) ProblemSet
    types_json = req.types_json if req.types_json else [req.question_type]
    ps = models.ProblemSet(
        passage_id=passage.id,
        name=req.name,
        description=req.description,
        created_by=req.created_by,
        types_json=types_json,
        mode=req.mode,
        is_published=req.is_published,
    )
    db.add(ps)
    db.flush()

    # 3) Question + Option
    for i, item in enumerate(req.items):
        stem = (item.stem or "").strip()
        if not stem:
            raise HTTPException(status_code=400, detail=f"item[{i}].stem is empty")

        options = _ensure_options(item.options)
        if item.answer_index >= len(options):
            raise HTTPException(
                status_code=400,
                detail=f"item[{i}].answer_index out of range",
            )

        explanation = (
            (item.explanation or "").strip()
            or item.meta.get("explain")
            or item.meta.get("explanation")
        )

        q = models.Question(
            question_type=req.question_type,
            text=stem,
            explanation=explanation if explanation else None,
            order=item.order if item.order is not None else (i + 1),
            answer_index=item.answer_index,   # ✅ B안 핵심
            passage_id=passage.id,
            problem_set_id=ps.id,
        )
        db.add(q)
        db.flush()

        for opt_idx, opt_text in enumerate(options):
            db.add(
                models.Option(
                    question_id=q.id,
                    label=_label_for(opt_idx),
                    text=opt_text,
                )
            )

    db.commit()

    return SaveProblemSetRes(
        passage_id=passage.id,
        problem_set_id=ps.id,
        question_count=len(req.items),
    )


# ----------------------------
# GET: Teacher 미리보기
# ----------------------------
@router.get("/problem_sets/{problem_set_id}")
def get_problem_set(problem_set_id: int, db: Session = Depends(get_db)) -> Dict[str, Any]:
    ps = _db_get(db, models.ProblemSet, problem_set_id)
    if not ps:
        raise HTTPException(status_code=404, detail="ProblemSet not found")

    passage = ps.passage

    questions = (
        db.query(models.Question)
        .filter(models.Question.problem_set_id == ps.id)
        .order_by(models.Question.order.asc(), models.Question.id.asc())
        .all()
    )

    return {
        "problem_set": {
            "id": ps.id,
            "name": ps.name,
            "description": ps.description,
            "created_by": ps.created_by,
            "types_json": ps.types_json,
            "mode": ps.mode,
            "is_published": ps.is_published,
            "created_at": ps.created_at,
        },
        "passage": {
            "id": passage.id,
            "title": passage.title,
            "content": passage.content,
        },
        "questions": [
            {
                "id": q.id,
                "question_type": q.question_type,
                "text": q.text,
                "explanation": q.explanation,
                "order": q.order,
                "answer_index": q.answer_index,  # ✅ Teacher만 확인
                "options": [
                    {
                        "id": o.id,
                        "label": o.label,
                        "text": o.text,
                    }
                    for o in q.options
                ],
            }
            for q in questions
        ],
    }