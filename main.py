import os
from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv
from openai import OpenAI

# .env에서 OpenAI API 키 불러오기
load_dotenv()
api_key = os.getenv("OPENAI_API_KEY")
client = OpenAI(api_key=api_key)

app = FastAPI()

# CORS 설정 (필요시)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 입력 모델 정의
class TextInput(BaseModel):
    text: str

@app.post("/analyze")
async def analyze_text(request: TextInput):
    text = request.text

    prompt = f"""
다음 영어 지문을 분석하여 아래 형식으로 출력해줘. 출력은 반드시 영어와 한글 모두 포함되어야 해.

1. 제목 (Title): 영어 제목과 그에 대한 한글 번역을 모두 제시해줘.
2. 주제 (Topic): 글의 주제를 한 명사구(5-10단어)의 영어 명사구로 설명한 후, 그 문장을 한국어로 번역해줘.
3. 요지 (Gist 또는 Main Point): 글쓴이의 중심 주장 또는 요지를 **한 문장(10~20단어)**의 영어 문장으로 요약하고, 그에 대한 한국어 해석도 함께 제시해줘.

아래는 지문이야:
{text}
"""

    try:
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.5,
        )
        output = response.choices[0].message.content.strip()
        return {"한글+영어 결과": output}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"GPT 호출 실패: {str(e)}")