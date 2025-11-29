# services/gpt_question_generator.py
from openai import OpenAI
import json
from typing import List, Dict, Any

from .gpt_prompts import build_prompt

client = OpenAI()


def _strip_json_fence(text: str) -> str:
    """GPT가 ```json ... ``` 으로 감싸 보낼 때를 대비한 처리."""
    text = text.strip()
    if text.startswith("```"):
        # ```json\n ... \n```
        first_newline = text.find("\n")
        if first_newline != -1:
            text = text[first_newline + 1 :]
        if text.endswith("```"):
            text = text[: -3]
    return text.strip()


async def generate_mcq_questions_from_passage(
    passage_content: str,
    num_questions: int = 3,
    question_type: str = "all",
) -> List[Dict[str, Any]]:
    """
    passage를 기반으로 GPT에게 MCQ(또는 삽입/순서형) 문제를 생성하도록 요청.
    question_type 에 따라 다른 프롬프트 사용.
    """

    prompt = build_prompt(question_type, passage_content, num_questions)

    resp = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {
                "role": "system",
                "content": "You generate Korean CSAT-style English questions strictly in JSON.",
            },
            {"role": "user", "content": prompt},
        ],
        temperature=0.2,
    )

    raw_text = resp.choices[0].message.content or ""
    raw_text = _strip_json_fence(raw_text)

    try:
        data = json.loads(raw_text)
    except Exception:
        # 디버깅용으로 raw 출력도 같이 던져줌
        raise ValueError(f"GPT JSON parsing failed. Raw output: {raw_text!r}")

    if not isinstance(data, list):
        raise ValueError("GPT JSON must be a list of question objects.")

    return data