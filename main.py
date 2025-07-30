from fastapi import FastAPI
from pydantic import BaseModel
import os
from dotenv import load_dotenv
from openai import OpenAI

# .env 파일에서 환경변수 불러오기
load_dotenv()
openai_api_key = os.getenv("OPENAI_API_KEY")

# OpenAI 클라이언트 생성
client = OpenAI(api_key=openai_api_key)

# FastAPI 인스턴스 생성
app = FastAPI()

# 요청 body 스키마 정의
class AnalyzeRequest(BaseModel):
    text: str

# 분석 API 엔드포인트
@app.post("/analyze")
def analyze_text(req: AnalyzeRequest):
    response = client.chat.completions.create(
        model="gpt-4",
        messages=[
            {"role": "system", "content": "너는 영어 문장 분석 전문가야. 주제, 제목, 요지를 영어와 한국어로 설명해줘."},
            {"role": "user", "content": req.text}
        ]
    )
    return {"result": response.choices[0].message.content}

print()