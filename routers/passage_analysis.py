# routers/passage_analysis.py
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from db import get_db
from models import PassageAnalysis
from schemas.passage import PassageAnalyzeRequest, PassageAnalyzeResponse
from services.passage_service import get_or_create_passage
from services.analysis_service import call_gpt_passage_analysis

router = APIRouter(
    prefix="/teacher/passage",
    tags=["teacher-passage"],
)


@router.post("/analyze_and_save", response_model=PassageAnalyzeResponse)
def analyze_and_save_passage(
    req: PassageAnalyzeRequest,
    db: Session = Depends(get_db),
):
    # 1) 지문 Passage 확보 (있으면 재사용, 없으면 생성)
    passage = get_or_create_passage(
        db,
        title=req.title,
        content=req.content,
        source=req.source,
        level=req.level,
        created_by=req.created_by,
    )

    # 2) GPT로 분석 허브 생성
    analysis_data = call_gpt_passage_analysis(passage.content)

    # 3) PassageAnalysis upsert
    analysis = (
        db.query(PassageAnalysis)
        .filter(PassageAnalysis.passage_id == passage.id)
        .first()
    )

    if not analysis:
        analysis = PassageAnalysis(passage_id=passage.id)
        db.add(analysis)

    analysis.topic_en = analysis_data.topic_en
    analysis.topic_ko = analysis_data.topic_ko
    analysis.title_en = analysis_data.title_en
    analysis.title_ko = analysis_data.title_ko
    analysis.gist_en = analysis_data.gist_en
    analysis.gist_ko = analysis_data.gist_ko
    analysis.summary_en = analysis_data.summary_en
    analysis.summary_ko = analysis_data.summary_ko

    if analysis_data.structure is not None:
        analysis.structure_json = [item.dict() for item in analysis_data.structure]
    if analysis_data.flow is not None:
        analysis.flow_json = analysis_data.flow.dict()
    if analysis_data.vocab is not None:
        analysis.vocab_json = [item.dict() for item in analysis_data.vocab]

    db.commit()
    db.refresh(analysis)

    return PassageAnalyzeResponse(
        passage_id=passage.id,
        analysis=analysis_data,
    )