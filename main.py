# main.py
from __future__ import annotations

import os
import re
import json
import logging
from typing import Generator, Optional, List

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session
from openai import OpenAI
from db import engine, Base, get_db


# --- DB / Models ---
# ✅ 여기만 변경: SessionLocal, init_db 대신 engine, Base, get_db 사용
from db import engine, Base, get_db
import models
from models import AnalysisRecord

# --- Routers (공통 스타일 통일) ---
from routers.auth import router as auth_router
from routers.structure import router as structure_router
from routers.paragraph import router as paragraph_router
from routers.word_mcq_api import router as word_mcq_router
from routers.dashboard_api import router as dashboard_router
from routers.export import router as export_router
from routers import analysis                  # analysis는 모듈로 불러서 .router 사용
from routers.question_maker_api import router as question_maker_router  # ✅ 추가(정상 경로)
from routers.student import router as student_router   # ✅ 추가
from routers import teacher_sets
from routers import teacher      # ⬅️ 요 줄 추가
from routers import community  # ← 새로 추가


# ---------- 초기화 ----------
load_dotenv()
logger = logging.getLogger("uvicorn.error")

# ✅ DB 테이블 생성: 앱 로딩 시 한 번만
Base.metadata.create_all(bind=engine)

app = FastAPI(title="English Analyzer API", version="1.2.0")

# 인증 라우터 (prefix 고정)
app.include_router(auth_router, prefix="/auth", tags=["auth"])

# 🔹 Flutter 웹(dev)에서 접근하는 Origin들
origins = [
    "http://localhost",
    "http://localhost:10513",   # flutter run -d chrome 로 뜬 포트 (다를 수 있음)
    "http://127.0.0.1:10513",
    "http://localhost:5214",    # DevTools 등 다른 포트도 필요하면 추가
    "http://127.0.0.1:5214",
]


# ---------- CORS: 일단 완전 개방 (디버그용) ----------
# ✅ CORS: 완전 오픈 (로컬 개발용)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],        # 모든 Origin 허용
    allow_credentials=False,    # "*" 쓸 때는 False 여야 CORS 에러가 안 남
    allow_methods=["*"],
    allow_headers=["*"],
)

# ❌ 이 부분은 더 이상 필요 없음 (init_db 사용 X)
# @app.on_event("startup")
# def on_startup() -> None:
#     try:
#         init_db()
#         logger.info("✅ DB initialized")
#     except Exception as e:
#         logger.exception("DB init error: %s", e)

# ❌ 여기서 직접 SessionLocal로 get_db 만들던 부분도 삭제
# def get_db() -> Generator:
#     db = SessionLocal()
#     try:
#         yield db
#     finally:
#         db.close()

# ---------- OpenAI ----------
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o")

if not OPENAI_API_KEY:
    logger.warning("⚠️ OPENAI_API_KEY is not set. GPT endpoints will fail.")

client = OpenAI(api_key=OPENAI_API_KEY)

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

# ---------- 유틸 ----------
_JSON_BLOCK_RE = re.compile(r"^```(?:json)?\s*|```$", re.M)

def _best_effort_json_parse(s: str) -> dict:
    """GPT가 코드펜스/앞뒤 텍스트를 붙여도 최대한 JSON으로 파싱."""
    raw = s.strip()
    raw = _JSON_BLOCK_RE.sub("", raw).strip()  # ```json ... ``` 제거
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

# ---------- Features ----------
# 문장 구조
try:
    from structure_analyzer import analyze_structure  # 선택 기능
except Exception:
    analyze_structure = None

@app.post("/analyze_structure")
def analyze_text(input: TextInput):
    if analyze_structure is None:
        result = input.text  # 구조 분석기 없을 때 대체
    else:
        try:
            result = analyze_structure(input.text)
        except Exception as e:
            logger.exception("structure_analyzer error: %s", e)
            result = input.text
    return _json({"문장 구조 분석 결과": result})

# 주제/제목/요지
@app.post("/analyze_topic_title_summary")
def analyze_topic_title_summary(input: TextInput):
    if not OPENAI_API_KEY:
        return _json({"error": "OPENAI_API_KEY not set"}, 500)

    prompt = f"""
You are an English text analyzer. From the passage below, extract:
1) Topic (3–5 words, noun phrase)
2) Title (5–8 words, concise)
3) Gist (10–20 words, 1 sentence, English)
Then translate the Gist into Korean.

Return STRICT JSON with keys exactly: topic, title, gist_en, gist_ko
No markdown. No extra words.

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
            "topic": data.get("topic", ""),
            "title": data.get("title", ""),
            "gist_en": data.get("gist_en", ""),
            "gist_ko": data.get("gist_ko", ""),
        }
        return _json(payload)
    except Exception as e:
        logger.exception("GPT error: %s", e)
        return _json({"error": f"GPT 오류: {str(e)}"}, 500)

# 단어 유의어
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

# 챗봇
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

# ---------- 라우터 등록 ----------
app.include_router(structure_router)
app.include_router(paragraph_router)
app.include_router(word_mcq_router)
app.include_router(dashboard_router)
app.include_router(export_router)
app.include_router(analysis.router)        # 요지+문단+괄호 동시
app.include_router(question_maker_router)  # ✅ 신규
app.include_router(student_router)   # ✅ 추가
app.include_router(teacher_sets.router)
app.include_router(teacher.router)   # prefix는 teacher.py 안에서 이미 /teacher 로 줬으니 여기선 안 줘도 됨
app.include_router(community.router)  # ✅ 커뮤니티 라우터 연결

# -------------------- Analyses: 저장/조회 CRUD --------------------
from schemas import AnalysisCreate, AnalysisOut

@app.post("/analyses", response_model=AnalysisOut)
def create_analysis(payload: AnalysisCreate, db: Session = Depends(get_db)):
    rec = AnalysisRecord(
        # ⚠️ 여기 필드명은 models.AnalysisRecord / schemas.AnalysisCreate에 맞게 맞춰야 함
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