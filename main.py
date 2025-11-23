# main.py
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from openai import OpenAI
from dotenv import load_dotenv
import os
import json
import re
import logging

# (옵션) 문장 구조 분석기가 있다면 임포트
try:
    from structure_analyzer import analyze_structure
except Exception:
    analyze_structure = None

# ---------- 초기화 ----------
load_dotenv()
logger = logging.getLogger("uvicorn.error")

app = FastAPI(title="English Analyzer API", version="1.2.0")

# ---------- CORS (환경변수 기반) ----------
# ALLOW_ORIGINS = "http://localhost:4671,https://example.com"
_raw = os.getenv("ALLOW_ORIGINS", "*").strip()
if _raw == "*" or _raw == "":
    allow_origins = ["*"]
else:
    allow_origins = [o.strip() for o in _raw.split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allow_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------- OpenAI ----------
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o")

if not OPENAI_API_KEY:
    logger.warning("⚠️ OPENAI_API_KEY is not set. GPT endpoints will fail.")

client = OpenAI(api_key=OPENAI_API_KEY)

# ---------- Data Models ----------
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
    """
    GPT가 코드펜스나 앞뒤 텍스트를 붙여 보내도 최대한 JSON으로 파싱한다.
    """
    raw = s.strip()
    # ```json ... ``` 제거
    raw = _JSON_BLOCK_RE.sub("", raw).strip()

    # 바로 시도
    try:
        return json.loads(raw)
    except Exception:
        pass

    # JSON 객체처럼 보이는 부분만 추출 시도
    m = re.search(r"\{.*\}", raw, flags=re.S)
    if m:
        try:
            return json.loads(m.group(0))
        except Exception:
            pass

    # 실패하면 빈 dict
    return {}

def _json(content: dict | str, status_code: int = 200):
    return JSONResponse(
        content=content,
        media_type="application/json; charset=utf-8",
        status_code=status_code,
    )

# ---------- Routes ----------
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

@app.post("/analyze_structure")
def analyze_text(input: TextInput):
    if analyze_structure is None:
        result = input.text  # 구조 분석기 없을 때 대체 동작
    else:
        try:
            result = analyze_structure(input.text)
        except Exception as e:
            logger.exception("structure_analyzer error: %s", e)
            result = input.text

    return _json({"문장 구조 분석 결과": result})

@app.post("/analyze_topic_title_summary")
def analyze_topic_title_summary(input: TextInput):
    """
    GPT가 주제/제목/요지를 JSON 필드로 반환
    """
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

@app.post("/chat")
def chat(req: ChatRequest):
    """
    EN+KR 이중 언어 응답. UTF‑8 명시.
    """
    if not OPENAI_API_KEY:
        return _json({"챗봇 응답": "❌ 서버 오류: OPENAI_API_KEY not set"}, 500)

    try:
        r = client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are an English tutor. "
                        "Answer in English first, then provide a Korean translation."
                    ),
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
    
# ---------- 라우터 등록 (문장 구조 분석) ----------
from routers.structure import router as structure_router
app.include_router(structure_router)


# ⬇️ 이 줄 추가
from routers.paragraph import router as paragraph_router
app.include_router(paragraph_router)

from routers.word_mcq_api import router as word_mcq_router
app.include_router(word_mcq_router)