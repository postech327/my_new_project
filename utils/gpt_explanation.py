# utils/gpt_explanation.py
from openai import OpenAI
import os
import json

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))


def generate_wrong_answer_explanation(
    question_text: str,
    options: list[str],
    correct_index: int,
    selected_index: int,
) -> str:
    """
    ❌ 오답에 대해 GPT가 구조화된 해설(JSON 문자열)을 생성
    - explanation
    - error_type
    - key_sentence
    - tip
    """

    prompt = f"""
너는 중학생을 가르치는 친절한 영어 선생님이다.

다음은 영어 객관식 문제이다.

[문제]
{question_text}

[선택지]
{chr(10).join([f"{i+1}. {opt}" for i, opt in enumerate(options)])}

학생이 선택한 답: {selected_index + 1}
정답: {correct_index + 1}

요구사항:
1. 왜 학생의 선택이 틀렸는지 설명
2. 왜 정답이 맞는지 설명
3. 학생이 꼭 기억해야 할 핵심 문장 1개
4. 다음에 틀리지 않기 위한 짧은 학습 팁 1개
5. 실수 유형을 아래 중 하나로 분류

실수 유형(error_type):
- grammar
- vocabulary
- inference
- context
- trap

⚠️ 반드시 아래 JSON 형식으로만 출력해라. 다른 설명은 하지 마라.

{
  "explanation": "오답과 정답에 대한 설명 (한국어, 5~7문장)",
  "error_type": "grammar | vocabulary | inference | context | trap",
  "key_sentence": "학생이 외워야 할 핵심 문장",
  "tip": "다음에 틀리지 않기 위한 한 줄 팁"
}
"""

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "system",
                    "content": "너는 영어 시험 오답 해설을 구조화해서 제공하는 전문가이다."
                },
                {
                    "role": "user",
                    "content": prompt
                },
            ],
            temperature=0.3,
        )

        content = response.choices[0].message.content.strip()

        # ✅ JSON 유효성 최소 검증
        json.loads(content)

        return content

    except Exception as e:
        # ❗ GPT 실패해도 시스템은 멈추지 않게
        print("❌ GPT explanation error:", e)
        return json.dumps({
            "explanation": "해설을 생성하지 못했습니다.",
            "error_type": "unknown",
            "key_sentence": "",
            "tip": "",
        }, ensure_ascii=False)