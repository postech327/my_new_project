from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from structure_analyzer import analyze_structure
from openai import OpenAI
import os
from dotenv import load_dotenv

load_dotenv()

app = FastAPI()
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

class LoginRequest(BaseModel):
    username: str
    password: str

class TextInput(BaseModel):
    text: str

class WordRequest(BaseModel):
    words: list[str]

class ChatRequest(BaseModel):
    question: str

@app.post("/login")
def login(data: LoginRequest):
    if data.username == "admin" and data.password == "1234":
        return {"message": "login success"}
    else:
        raise HTTPException(status_code=401, detail="invalid credentials")

@app.post("/analyze_structure")
def analyze_text(input: TextInput):
    try:
        analyzed = analyze_structure(input.text)
        return {"문장 구조 분석 결과": analyzed}
    except Exception as e:
        return {"error": str(e)}

@app.post("/analyze_topic_title_summary")
def analyze_topic_title_summary(input: TextInput):
    prompt = f"""You are an English text analyzer.
Task: Given the passage below, extract the following 3 things:

1. Topic (about 3-5 words, noun phrase only)
2. Title (about 5-8 words, concise and informative)
3. Gist (1 sentence, 10–20 words summarizing the author's main point)

Return format:
Topic: ...
Title: ...
Gist: ...
Korean Gist: (Korean translation of the Gist)

Passage:
{input.text}"""
    try:
        completion = client.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.4
        )
        output = completion.choices[0].message.content
        return {"주제·제목·요지 분석 결과": output}
    except Exception as e:
        return {"error": f"GPT 요청 중 오류: {str(e)}"}

@app.post("/word_synonyms")
def get_word_synonyms(request: WordRequest):
    prompt = f"""
You are a vocabulary assistant. For each English word below, return:
- its meaning in Korean
- three English synonyms
- Korean translations of the synonyms

Format:
Word: ...
Meaning: ...
Synonyms:
1. ... - ...
2. ... - ...
3. ... - ...

Words:
{', '.join(request.words)}
"""
    try:
        completion = client.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3
        )
        return {"단어 분석 결과": completion.choices[0].message.content}
    except Exception as e:
        return {"error": f"GPT 처리 오류: {str(e)}"}

@app.post("/chat")
def chat_with_gpt(req: ChatRequest):
    prompt = req.question
    try:
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.5
        )
        return {"챗봇 응답": response.choices[0].message.content.strip()}
    except Exception as e:
        return {"error": f"챗봇 처리 오류: {str(e)}"}
