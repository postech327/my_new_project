# lib/routers/question_maker_api.py

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
import os, json, re, random
from openai import OpenAI

router = APIRouter(prefix="/question_maker", tags=["question_maker"])

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o")
client = OpenAI(api_key=OPENAI_API_KEY) if OPENAI_API_KEY else None

class QmBody(BaseModel):
    passage: str
    items: int = 1
    extra: dict | None = None

def _circled(i: int) -> str:
    return chr(0x2460 + (i - 1))

@router.post("/summary_ab")
def make_summary_ab(b: QmBody):
    ...
    def _fallback_two_sent():
        # 2문장 + A/B 분리 보장용 아주 단순 폴백
        A = ["enhances", "simplifies", "interrupts", "reinforces", "refines"]
        B = ["accurate", "fixed", "objective", "neutral", "inconsistent"]
        ans = random.randrange(5)
        summary = (
            "Humans perceive through functional relations, which _____(A)_____ our ability to see reality as it is. "
            "By contrast, a camera offers a _____(B)_____ perspective."
        )
        return summary, A, B, ans

    def _ensure_two_sentence_summary(s: str) -> str:
        """
        - 반드시 마침표 1개 이상 -> 2문장 이상 되게 정리
        - (A)는 1번째 문장, (B)는 2번째 문장에 들어가도록 보정
        """
        s = s.strip().replace("…", ".").replace("..", ".")
        # 기본 분할
        parts = re.split(r"\s*(?<=\.|\?|!)\s+", s)
        parts = [p.strip() for p in parts if p.strip()]
        # (A)/(B) 유무 체크
        hasA = "_____(A)_____" in s
        hasB = "_____(B)_____" in s

        # 문장이 1개뿐이면 쉼표/세미콜론 등으로 적당히 쪼개기
        if len(parts) == 1:
            # 콤마 기준으로 쪼개서 2개로
            tmp = re.split(r"\s*(?:;|,|\band\b|\bbut\b)\s+", parts[0], maxsplit=1)
            if len(tmp) == 2:
                parts = [tmp[0].strip() + ".", tmp[1].strip() + "."]
            else:
                # 못쪼개면 강제로 대조문 삽입
                parts = [parts[0], "By contrast, a camera provides a different perspective."]

        # (A)/(B) 배치 강제
        p1, p2 = parts[0], parts[1]
        if hasA and "_____(A)_____" not in p1:
            # A가 1문장에 없으면 A를 1문장으로 옮김
            sA = re.sub(r"_____\([AB]\)_____", "", p1)
            p1 = p1 if "_____(A)_____" in p1 else sA + " _____(A)_____"
        if hasB and "_____(B)_____" not in p2:
            sB = re.sub(r"_____\([AB]\)_____", "", p2)
            p2 = p2 if "_____(B)_____" in p2 else sB + " _____(B)_____"

        # 혹시 둘 중 하나가 아예 없으면 기본 문구로 채우기
        if "_____(A)_____" not in p1:
            p1 = p1.rstrip(".") + " _____(A)_____."
        if "_____(B)_____" not in p2:
            p2 = p2.rstrip(".") + " _____(B)_____."

        return (p1.rstrip(".") + ". " + p2.rstrip(".") + ".")

    if client is None:
        summary, A, B, ans = _fallback_two_sent()
    else:
        prompt = f"""
You will create a **two-sentence summary** with two blanks labeled (A) and (B).

STRICT rules:
- Output EXACTLY TWO SENTENCES.
- Put the blank "_____(A)_____" in the FIRST sentence.
- Put the blank "_____(B)_____" in the SECOND sentence.
- Do not add any extra sentences.
- Then produce 5 options for A (1 correct + 4 distractors) and 5 options for B.
- Return STRICT JSON (no markdown) with keys:
  summary, A_correct, A_distractors, B_correct, B_distractors

Passage:
\"\"\"{passage}\"\"\"
"""
        try:
            r = client.chat.completions.create(
                model=OPENAI_MODEL,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,
            )
            raw = r.choices[0].message.content or ""
            def best(s: str) -> dict:
                s = s.strip()
                s = re.sub(r"^```(?:json)?\s*|```$", "", s, flags=re.M).strip()
                try:
                    return json.loads(s)
                except:
                    m = re.search(r"\{.*\}", s, flags=re.S)
                    return json.loads(m.group(0)) if m else {}
            data = best(raw)

            summary = (data.get("summary") or "").strip()
            A_correct = (data.get("A_correct") or "").strip()
            B_correct = (data.get("B_correct") or "").strip()
            A_d = [str(x).strip() for x in (data.get("A_distractors") or [])]
            B_d = [str(x).strip() for x in (data.get("B_distractors") or [])]

            ok = summary and A_correct and B_correct and len(A_d) >= 4 and len(B_d) >= 4
            if not ok:
                summary, A, B, ans = _fallback_two_sent()
            else:
                # 5행 만들기: 정답 행을 랜덤 위치로
                ans = random.randrange(5)
                A = A_d[:4]; B = B_d[:4]
                A.insert(ans, A_correct)
                B.insert(ans, B_correct)

                # ✅ 두 문장 & A/B 분리 강제 후처리
                summary = _ensure_two_sentence_summary(summary)

        except Exception:
            summary, A, B, ans = _fallback_two_sent()
    ...