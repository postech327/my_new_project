# main.py
from __future__ import annotations

import os
import re
import json
import logging
from typing import Optional, List

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from db import engine, Base, get_db
import models
from models import AnalysisRecord, Passage  # Passage는 이후 확장용으로 import

# --- Routers (✅ 전부 "파일에서 router 직접 import"로 통일) ---
from routers.auth import router as auth_router
from routers.structure import router as structure_router
from routers.paragraph import router as paragraph_router
from routers.word_mcq_api import router as word_mcq_router
from routers.dashboard_api import router as dashboard_router
from routers.export import router as export_router

from routers.analysis import router as analysis_router
from routers.question_maker_api import router as question_maker_router
from routers.student import router as student_router
from routers.teacher import router as teacher_router
from routers.community import router as community_router

from routers.users import router as users_router
# from routers.passage_analysis import router as passage_analysis_router
from routers.problem_sets_api import router as problem_sets_api_router
from routers.teacher_problem_sets import router as teacher_problem_sets_router
from routers.statistics import router as statistics_router
from routers.student_review import router as student_review_router
from routers.reports import router as reports_router
from routers.admin_dashboard import router as admin_dashboard_router
from routers.admin_charts import router as admin_charts_router
from routers.admin_students import router as admin_students_router
from routers.admin_difficulty import router as admin_difficulty_router
from routers.admin_exam_generator import router as admin_exam_router
from routers.admin_personal_exam import router as admin_personal_exam_router
from routers.student_learning_flow import router as student_learning_flow_router
from routers.student_review_generator import router as student_review_router
from routers.student_gpt_explain import router as student_gpt_explain_router
from routers import recommendation
from routers import admin_student_recommendation
from routers import student_exams
from routers import study_reports
from routers import concepts
from routers import student_exam_builder


# ---------- 초기화 ----------
load_dotenv()
logger = logging.getLogger("uvicorn.error")

# ---------- OpenAI ----------
from config import OPENAI_API_KEY, OPENAI_MODEL
from openai import OpenAI

client = OpenAI(api_key=OPENAI_API_KEY)

# 🔥 허브 결과를 임시로 들고 있는 in-memory DB
FAKE_HUB_DB: dict[int, dict] = {}
NEXT_HUB_ID: int = 1

Base.metadata.create_all(bind=engine)

app = FastAPI(title="English Analyzer API", version="1.3.0")

# 인증 라우터
app.include_router(auth_router, prefix="/auth", tags=["auth"])

# CORS (dev)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------- Schemas ----------
class LoginRequest(BaseModel):
    username: str
    password: str


class TextInput(BaseModel):
    text: str


class ChatRequest(BaseModel):
    question: str


class WordRequest(BaseModel):
    words: list[str]


# 🔥 통합 허브 응답 모델: 요약 EN/KR + id
class TextAnalysisHubResponse(BaseModel):
    id: int                 # 허브 분석 id (in-memory + AnalysisRecord에 함께 저장된 항목)
    structure: str          # 괄호 포함 문장 구조
    topic: str              # 주제
    title: str              # 제목
    gist_en: str            # 요지 (영어 1문장)
    gist_ko: str            # 요지 한국어
    summary_en: str         # 요약 (영어 2~3문장)
    summary_ko: str         # 요약 한국어
    vocab: str              # 단어/유의어 텍스트 블럭


# ---------- 유틸 ----------
_JSON_BLOCK_RE = re.compile(r"^```(?:json)?\s*|```$", re.M)


def _best_effort_json_parse(s: str) -> dict:
    raw = s.strip()
    raw = _JSON_BLOCK_RE.sub("", raw).strip()
    try:
        return json.loads(raw)
    except Exception:
        pass
    m = re.search(r"\{.*\}", raw, flags=re.S)
    if m:
        try:
            return json.loads(m.group(0))
        except Exception:
            pass
    return {}


def _json(content: dict | str, status_code: int = 200):
    return JSONResponse(
        content=content,
        media_type="application/json; charset=utf-8",
        status_code=status_code,
    )


# ---------- Basic Routes ----------
@app.get("/")
def root():
    return _json({"message": "OK"})


@app.get("/healthz")
def healthz():
    return _json({"status": "healthy"})


@app.post("/login")
def login(req: LoginRequest):
    ok = (req.username == "admin" and req.password == "1234")
    if not ok:
        raise HTTPException(status_code=401, detail="invalid credentials")
    return _json({"message": "login success"})


# ---------- 문장 구조 ----------
try:
    from structure_analyzer import analyze_structure
except Exception:
    analyze_structure = None


@app.post("/analyze_structure")
def analyze_text(input: TextInput):
    if analyze_structure is None:
        result = input.text
    else:
        try:
            result = analyze_structure(input.text)
        except Exception as e:
            logger.exception("structure_analyzer error: %s", e)
            result = input.text
    return _json({"문장 구조 분석 결과": result})


# ---------- 주제/제목/요지/요약 단독 엔드포인트 ----------
@app.post("/analyze_topic_title_summary")
def analyze_topic_title_summary(input: TextInput):
    if not OPENAI_API_KEY:
        return _json({"error": "OPENAI_API_KEY not set"}, 500)

    prompt = f"""
You are an English text analyzer. From the passage below, extract:
1) Topic – 3–5 words (noun phrase)
2) Title – 5–8 words (natural title)
3) Gist – 1 sentence (10–20 words, English)
4) Summary – 2–3 sentences (English)
Then translate BOTH the Gist and the Summary into Korean.

Return STRICT JSON with keys:
topic, title, gist_en, gist_ko, summary_en, summary_ko
No markdown. No explanations.

Passage:
\"\"\"{input.text}\"\"\""""

    try:
        r = client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
        )
        raw = r.choices[0].message.content or ""
        data = _best_effort_json_parse(raw)

        payload = {
            "topic": data.get("topic", "") or "",
            "title": data.get("title", "") or "",
            "gist_en": data.get("gist_en", "") or "",
            "gist_ko": data.get("gist_ko", "") or "",
            "summary_en": data.get("summary_en", "") or "",
            "summary_ko": data.get("summary_ko", "") or "",
        }
        return _json(payload)
    except Exception as e:
        logger.exception("GPT error: %s", e)
        return _json({"error": f"GPT 오류: {str(e)}"}, 500)


# ---------- 단어 유의어 ----------
@app.post("/word_synonyms")
def word_synonyms(req: WordRequest):
    if not OPENAI_API_KEY:
        return _json({"error": "OPENAI_API_KEY not set"}, 500)

    words_joined = ", ".join(req.words)
    prompt = f"""
For each English word, give:
- Meaning (Korean)
- Three synonyms (English) with Korean translations

Return a clean bullet list text (no Markdown code fences), for these words: {words_joined}
"""
    try:
        r = client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.2,
        )
        txt = (r.choices[0].message.content or "").strip()
        return _json({"단어 분석 결과": txt})
    except Exception as e:
        logger.exception("GPT error: %s", e)
        return _json({"error": f"GPT 오류: {str(e)}"}, 500)


# ---------- 챗봇 ----------
@app.post("/chat")
def chat(req: ChatRequest):
    if not OPENAI_API_KEY:
        return _json({"챗봇 응답": "❌ 서버 오류: OPENAI_API_KEY not set"}, 500)
    try:
        r = client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=[
                {
                    "role": "system",
                    "content": "You are an English tutor. Answer in English first, then provide a Korean translation.",
                },
                {"role": "user", "content": req.question},
            ],
            temperature=0.4,
        )
        answer = (r.choices[0].message.content or "").strip()
        return _json({"챗봇 응답": answer})
    except Exception as e:
        logger.exception("Chat error: %s", e)
        return _json({"챗봇 응답": f"❌ 서버 오류: {str(e)}"}, 500)


# 🔥🔥 지문 분석 허브 통합 API (최종 버전) 🔥🔥
@app.post("/text_analysis_hub", response_model=TextAnalysisHubResponse)
def text_analysis_hub(input: TextInput, db: Session = Depends(get_db)):
    """
    한 번에:
    - 문장 구조(괄호 표시)
    - 주제/제목/요지/요약(영/한)
    - 지문 기반 단어/유의어 분석
    을 모두 반환하는 엔드포인트
    """

    # 1) 문장 구조 -----------------------------------------
    if analyze_structure is None:
        raw_struct = input.text
    else:
        try:
            raw_struct = analyze_structure(input.text)
        except Exception as e:
            logger.exception("structure_analyzer error in hub: %s", e)
            raw_struct = input.text

    # dict 로 오는 경우 방어적으로 문자열로 변환
    if isinstance(raw_struct, dict):
        structure_result = (
            raw_struct.get("analyzed_text")
            or raw_struct.get("result")
            or raw_struct.get("text")
            or json.dumps(raw_struct, ensure_ascii=False)
        )
    else:
        structure_result = str(raw_struct)

    # 2) 주제/제목/요지/요약 -------------------------------
    topic = title = gist_en = gist_ko = ""
    summary_en = summary_ko = ""

    if not OPENAI_API_KEY:
        logger.warning("OPENAI_API_KEY not set – topic/title/gist/summary skipped")
    else:
        prompt = f"""
You are an English text analyzer. From the passage below, extract:

1) Topic  – 3–5 words (noun phrase)
2) Title  – 5–8 words (natural title)
3) Gist   – 1 sentence (10–20 words, English)
4) Summary – 2–3 sentences (English)

Then translate BOTH the Gist and the Summary into Korean.

Return STRICT JSON with keys:
topic, title, gist_en, gist_ko, summary_en, summary_ko

No markdown. No explanations.

Passage:
\"\"\"{input.text}\"\"\""""
        try:
            r = client.chat.completions.create(
                model=OPENAI_MODEL,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,
            )
            raw = r.choices[0].message.content or ""
            data = _best_effort_json_parse(raw)

            topic = data.get("topic", "") or ""
            title = data.get("title", "") or ""
            gist_en = data.get("gist_en", "") or ""
            gist_ko = data.get("gist_ko", "") or ""
            summary_en = data.get("summary_en", "") or ""
            summary_ko = data.get("summary_ko", "") or ""
        except Exception as e:
            logger.exception("GPT error in hub (topic/title/gist/summary): %s", e)

    # 3) 지문 기반 단어/유의어 분석 -------------------------
    vocab_text = ""
    if not OPENAI_API_KEY:
        logger.warning("OPENAI_API_KEY not set – vocab analysis skipped")
    else:
        vocab_prompt = f"""
You are an English teacher for Korean high school students.

From the passage below, choose about 10 important content words (no duplicates).
For each word, provide:
1) the English word
2) a short Korean meaning
3) three English synonyms with short Korean meanings.

Format the answer as a clear bullet-style text.
Do NOT use Markdown code fences.

Passage:
\"\"\"{input.text}\"\"\""""
        try:
            r2 = client.chat.completions.create(
                model=OPENAI_MODEL,
                messages=[{"role": "user", "content": vocab_prompt}],
                temperature=0.3,
            )
            vocab_text = (r2.choices[0].message.content or "").strip()
        except Exception as e:
            logger.exception("GPT error in hub (vocab): %s", e)

    # 4) 공통 딕셔너리 구성 --------------------------------
    analysis_dict = {
        "structure": structure_result,
        "topic": topic,
        "title": title,
        "gist_en": gist_en,
        "gist_ko": gist_ko,
        "summary_en": summary_en,
        "summary_ko": summary_ko,
        "vocab": vocab_text,
    }

    # 5) ID 발급 + in-memory DB 저장 -----------------------
    global NEXT_HUB_ID, FAKE_HUB_DB
    hub_id = NEXT_HUB_ID
    NEXT_HUB_ID += 1

    FAKE_HUB_DB[hub_id] = {
        "id": hub_id,
        "text": input.text,
        **analysis_dict,
    }

    # 6) AnalysisRecord 테이블에도 저장 --------------------
    try:
        rec = AnalysisRecord(
            kind="text_analysis_hub",
            input_text=input.text,
            result_text=analysis_dict.get("summary_en") or "",
            result_json=json.dumps(
                {"hub_id": hub_id, **analysis_dict},
                ensure_ascii=False,
            ),
        )
        db.add(rec)
        db.commit()
        db.refresh(rec)
        logger.info(f"Saved hub analysis as AnalysisRecord id={rec.id}")
    except Exception as e:
        logger.exception("DB save error for text_analysis_hub: %s", e)

    # 7) 응답 반환 -----------------------------------------
    return TextAnalysisHubResponse(
        id=hub_id,
        **analysis_dict,
    )


# ---------- 라우터 등록 (✅ 모두 router 변수로만 include) ----------
app.include_router(structure_router)
app.include_router(paragraph_router)
app.include_router(word_mcq_router)
app.include_router(dashboard_router)
app.include_router(export_router)

app.include_router(analysis_router)
app.include_router(question_maker_router)
app.include_router(student_router)
app.include_router(teacher_router)
app.include_router(community_router)

app.include_router(users_router)
# app.include_router(passage_analysis_router)
app.include_router(problem_sets_api_router)
app.include_router(teacher_problem_sets_router)
app.include_router(statistics_router)
app.include_router(student_review_router)
app.include_router(reports_router)
app.include_router(admin_dashboard_router)
app.include_router(admin_charts_router)
app.include_router(admin_students_router)
app.include_router(admin_difficulty_router)
app.include_router(admin_exam_router)
app.include_router(admin_personal_exam_router)
app.include_router(student_learning_flow_router)
app.include_router(student_review_router)
app.include_router(student_gpt_explain_router)
app.include_router(recommendation.router)
app.include_router(admin_student_recommendation.router)
app.include_router(student_exams.router)
app.include_router(study_reports.router)
app.include_router(concepts.router)
app.include_router(student_exam_builder.router)

# ---------- Analyses CRUD ----------
from schemas import AnalysisCreate, AnalysisOut


@app.post("/analyses", response_model=AnalysisOut)
def create_analysis(payload: AnalysisCreate, db: Session = Depends(get_db)):
    rec = AnalysisRecord(
        kind=payload.kind,
        input_text=payload.input_text,
        result_text=payload.result_text,
        result_json=payload.result_json,
    )
    db.add(rec)
    db.commit()
    db.refresh(rec)
    return rec


@app.get("/analyses", response_model=List[AnalysisOut])
def list_analyses(
    kind: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
    db: Session = Depends(get_db),
):
    q = db.query(AnalysisRecord).order_by(AnalysisRecord.created_at.desc())
    if kind:
        q = q.filter(AnalysisRecord.kind == kind)
    return q.offset(offset).limit(limit).all()


@app.get("/analyses/{rec_id}", response_model=AnalysisOut)
def get_analysis(rec_id: int, db: Session = Depends(get_db)):
    rec = db.query(AnalysisRecord).get(rec_id)
    if not rec:
        raise HTTPException(status_code=404, detail="not found")
    return rec


@app.delete("/analyses/{rec_id}")
def delete_analysis(rec_id: int, db: Session = Depends(get_db)):
    rec = db.query(AnalysisRecord).get(rec_id)
    if not rec:
        raise HTTPException(status_code=404, detail="not found")
    db.delete(rec)
    db.commit()
    return _json({"deleted": rec_id})