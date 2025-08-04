from fastapi import FastAPI
from pydantic import BaseModel
from structure_analyzer import analyze_structure
from openai import OpenAI
import os
from dotenv import load_dotenv

load_dotenv()

app = FastAPI()
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

class TextInput(BaseModel):
    text: str

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
3. Gist (1 sentence, 10–20 words summarizing the author’s main point)

Return format:
Topic: ...
Title: ...
Gist: ...
Korean Gist: (Korean translation of the Gist)

Passage:
\"\"\"{input.text}\"\"\"
"""
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