# routers/word_mcq_api.py
from fastapi import APIRouter
from pydantic import BaseModel
from typing import List
import random

router = APIRouter(prefix="", tags=["word-mcq"])

# ---------- 공용 스키마 ----------
class WordMcqIn(BaseModel):
    word: str

class WordMcqOut(BaseModel):
    text: str  # 앱에서는 이 문자열을 그대로 출력

class McqItem(BaseModel):
    stem: str               # 문제 지문(빈칸 포함)
    choices: List[str]      # 보기 5개
    answer_index: int       # 0~4 (정답 인덱스)
    explanation: str        # 정답/해설(한글 등)

# ---------- 1) 문자열 포맷 응답 ----------
@router.post("/word-mcq", response_model=WordMcqOut)
async def generate_word_mcq(payload: WordMcqIn) -> WordMcqOut:
    w = payload.word.strip()
    if not w:
        return WordMcqOut(text="단어가 비어 있습니다.")

    # 샘플 distractor 후보들 (나중에 LLM/사전 연동 시 교체)
    distractors_pool = [
        "respect", "enhance", "forecast", "enlighten", "discern", "legitimately"
    ]

    # 중복 제거 + 대상단어 제외
    pool = [c for c in distractors_pool if c.lower() != w.lower()]
    random.shuffle(pool)

    # 안전하게 4개 확보 (부족시 패딩)
    while len(pool) < 4:
        pool.append(random.choice(distractors_pool))

    choices = pool[:4] + [w]
    random.shuffle(choices)

    # ①~⑤ 표기를 위해 +1
    answer_idx = choices.index(w) + 1

    sample = f"""①~⑤ 중 빈칸에 알맞은 단어를 고르세요.

The hasty changes to the schedule severely ______ our workflow.

① {choices[0]}    ② {choices[1]}    ③ {choices[2]}    ④ {choices[3]}    ⑤ {choices[4]}

정답: {answer_idx} {w}
👉 해석) 성급한 일정 변경은 우리의 작업 흐름을 '{w}'했다(의미 예시).
"""
    return WordMcqOut(text=sample)

# ---------- 2) 구조화된 응답 ----------
@router.post("/word-mcq-struct", response_model=McqItem)
async def generate_word_mcq_struct(payload: WordMcqIn) -> McqItem:
    w = payload.word.strip()
    if not w:
        return McqItem(
            stem="(단어가 비어 있습니다.) ______",
            choices=["-", "-", "-", "-", "-"],
            answer_index=0,
            explanation="단어 입력이 필요합니다.",
        )

    # 지문 샘플 (필요 시 템플릿 확장)
    stem = "The hasty changes to the schedule severely ______ our workflow."

    # 간단한 distractor 맵 (샘플). 이후 LLM/사전으로 대체/보강 가능
    distractors_map = {
        "disrupt": ["respect", "enhance", "forecast", "enlighten"],
        "respect": ["ignore", "violate", "distort", "misuse"],
    }
    base = distractors_map.get(w.lower(), ["respect", "enhance", "forecast", "enlighten"])

    # 중복/대소문자 회피 + 섞기
    filtered = [d for d in base if d.lower() != w.lower()]
    random.shuffle(filtered)

    # 항상 4개 확보
    while len(filtered) < 4:
        filtered.append(random.choice(["discern", "legitimately", "predict", "improve"]))

    choices = (filtered[:4] + [w])[:5]
    random.shuffle(choices)

    answer_index = choices.index(w)
    explanation = (
        f"정답: {answer_index+1} {choices[answer_index]}\n"
        f"👉 해석) 성급한 일정 변경은 우리의 작업 흐름을 '{w}'했다(의미 예시)."
    )

    return McqItem(
        stem=stem,
        choices=choices,
        answer_index=answer_index,
        explanation=explanation,
    )