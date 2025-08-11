# main.py
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from openai import OpenAI
from dotenv import load_dotenv
import os

# (옵션) 문장 구조 분석기가 있다면 임포트
try:
    from structure_analyzer import analyze_structure
except Exception:
    analyze_structure = None

load_dotenv()

app = FastAPI(title="English Analyzer API", version="1.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 개발 단계: 전체 허용
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

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

# ---------- Routes ----------
@app.get("/")
def root():
    return JSONResponse(
        content={"message": "OK"},
        media_type="application/json; charset=utf-8",
    )

@app.post("/login")
def login(req: LoginRequest):
    ok = (req.username == "admin" and req.password == "1234")
    if not ok:
        raise HTTPException(status_code=401, detail="invalid credentials")
    return JSONResponse(
        content={"message": "login success"},
        media_type="application/json; charset=utf-8",
    )

@app.post("/analyze_structure")
def analyze_text(input: TextInput):
    if analyze_structure is None:
        result = input.text  # 대체 동작
    else:
        result = analyze_structure(input.text)

    return JSONResponse(
        content={"문장 구조 분석 결과": result},
        media_type="application/json; charset=utf-8",
    )

@app.post("/analyze_topic_title_summary")
def analyze_topic_title_summary(input: TextInput):
    """
    GPT가 주제/제목/요지를 JSON 필드로 반환
    """
    prompt = f"""
You are an English text analyzer. From the passage below, extract:
1) Topic (3–5 words, noun phrase)
2) Title (5–8 words, concise)
3) Gist (10–20 words, 1 sentence, English)
Then translate the Gist into Korean.

Return STRICT JSON with keys: topic, title, gist_en, gist_ko
No markdown. No extra text.

Passage:
\"\"\"{input.text}\"\"\"
"""
    try:
        r = client.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
        )
        raw = r.choices[0].message.content.strip()
        # 혹시 JSON이 아닐 때를 대비해 best‑effort 파싱
        import json, re
        try:
            data = json.loads(raw)
        except Exception:
            body = re.sub(r"^```json|```$", "", raw.strip(), flags=re.M)
            data = json.loads(body)

        payload = {
            "topic": data.get("topic", ""),
            "title": data.get("title", ""),
            "gist_en": data.get("gist_en", ""),
            "gist_ko": data.get("gist_ko", ""),
        }
        return JSONResponse(
            content=payload,
            media_type="application/json; charset=utf-8",
        )
    except Exception as e:
        return JSONResponse(
            content={"error": f"GPT 오류: {str(e)}"},
            media_type="application/json; charset=utf-8",
            status_code=500,
        )

@app.post("/word_synonyms")
def word_synonyms(req: WordRequest):
    prompt = f"""
For each English word, give:
- Meaning (Korean)
- Three synonyms (English) with Korean translations

Return plain text list. Words: {', '.join(req.words)}
"""
    try:
        r = client.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.2,
        )
        txt = r.choices[0].message.content.strip()
        return JSONResponse(
            content={"단어 분석 결과": txt},
            media_type="application/json; charset=utf-8",
        )
    except Exception as e:
        return JSONResponse(
            content={"error": f"GPT 오류: {str(e)}"},
            media_type="application/json; charset=utf-8",
            status_code=500,
        )

@app.post("/chat")
def chat(req: ChatRequest):
    """
    EN+KR 이중 언어 응답. UTF‑8 명시.
    """
    try:
        r = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": "You are an English tutor. Answer in English then Korean."},
                {"role": "user", "content": req.question},
            ],
            temperature=0.4,
        )
        answer = r.choices[0].message.content.strip()
        return JSONResponse(
            content={"챗봇 응답": answer},
            media_type="application/json; charset=utf-8",
        )
    except Exception as e:
        return JSONResponse(
            content={"챗봇 응답": f"❌ 서버 오류: {str(e)}"},
            media_type="application/json; charset=utf-8",
            status_code=500,
        )