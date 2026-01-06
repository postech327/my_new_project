# services/question_set_service.py
from __future__ import annotations

import json
from typing import List, Dict, Any

from openai import OpenAI
from sqlalchemy.orm import Session

from config import OPENAI_API_KEY, OPENAI_MODEL
from models import Passage, ProblemSet, Question, Option
from schemas.problem_set import ProblemSetGenerateRequest

client = OpenAI(api_key=OPENAI_API_KEY)


def build_question_prompt(passage_text: str, types: List[str]) -> str:
    """
    지문 + 문제유형을 전달해서 GPT가 JSON 문제 세트를 생성하도록 하는 프롬프트.
    필요하면 나중에 네가 쓰던 프롬프트로 바꿔도 됨.
    """
    types_str = ", ".join(types)
    return f"""
You are an English exam item writer for Korean high school students.

Based on the passage below, create multiple-choice questions for the following types:
{types_str}

For each type, create exactly ONE question with FIVE options (①~⑤), only ONE correct.

Return STRICT JSON with this structure:

{{
  "questions": [
    {{
      "question_type": "topic" | "title" | "gist" | "summary" | "cloze" | "insertion" | "order",
      "stem": "question sentence in Korean or English",
      "explanation": "short explanation in Korean (for teacher)",
      "options": [
        {{
          "label": "①",
          "text": "option text",
          "is_correct": true or false
        }},
        ...
      ]
    }}
  ]
}}

RULES:
- Do NOT include any markdown fences.
- Use circled digits ① ② ③ ④ ⑤ for labels.
- Avoid copying long chunks of the passage in the options.

Passage:
\"\"\"{passage_text}\"\"\"
    """.strip()


def call_gpt_generate_questions(passage_text: str, types: List[str]) -> List[Dict[str, Any]]:
    """
    GPT를 호출해서 questions 리스트(JSON)를 그대로 반환.
    """
    prompt = build_question_prompt(passage_text, types)

    resp = client.chat.completions.create(
        model=OPENAI_MODEL,
        messages=[
            {
                "role": "system",
                "content": "You are a professional English exam item writer. Output ONLY valid JSON.",
            },
            {"role": "user", "content": prompt},
        ],
        temperature=0.4,
    )

    raw = resp.choices[0].message.content or ""
    raw = raw.strip()

    # 혹시 ```json ... ``` 이 오면 제거
    if raw.startswith("```"):
        lines = raw.splitlines()
        if len(lines) >= 3 and lines[-1].strip().startswith("```"):
            lines = lines[1:-1]
        raw = "\n".join(lines).strip()

    data = json.loads(raw)

    questions = data.get("questions", [])
    if not isinstance(questions, list):
        raise ValueError("questions must be a list")

    return questions


def create_problem_set_with_questions(
    db: Session,
    req: ProblemSetGenerateRequest,
) -> ProblemSet:
    """
    1) passage_id로 지문 가져오기
    2) GPT로 questions JSON 생성
    3) ProblemSet / Question / Option 모두 저장 후 ProblemSet 반환
    """
    passage = db.query(Passage).filter(Passage.id == req.passage_id).first()
    if not passage:
        raise ValueError(f"Passage {req.passage_id} not found")

    # 1. GPT 호출해서 문제 생성
    questions_json = call_gpt_generate_questions(passage.content, req.types)

    # 2. ProblemSet 생성
    ps = ProblemSet(
        passage_id=passage.id,
        name=req.name,
        description=None,
        created_by=req.created_by,
        types_json=req.types,
        mode=req.mode,
        is_published=False,
    )
    db.add(ps)
    db.flush()  # ps.id 확보

    # 3. Question / Option 생성
    order_counter = 1
    for q in questions_json:
        q_type = q.get("question_type", "")
        stem = q.get("stem", "")
        explanation = q.get("explanation", "")

        question = Question(
            question_type=q_type,
            text=stem,
            explanation=explanation,
            order=order_counter,
            passage_id=passage.id,
            problem_set_id=ps.id,
        )
        db.add(question)
        db.flush()  # question.id 확보

        for opt in q.get("options", []):
            label = opt.get("label", "")
            text = opt.get("text", "")
            is_correct = bool(opt.get("is_correct", False))

            option = Option(
                question_id=question.id,
                label=label,
                text=text,
                is_correct=is_correct,
            )
            db.add(option)

        order_counter += 1

    db.commit()
    db.refresh(ps)
    return ps