# routers/word_mcq_api.py
from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(prefix="", tags=["word-mcq"])

class WordMcqIn(BaseModel):
    word: str

class WordMcqOut(BaseModel):
    text: str  # 앱에서는 이 문자열을 그대로 출력

@router.post("/word-mcq", response_model=WordMcqOut)
def generate_word_mcq(payload: WordMcqIn) -> WordMcqOut:
    w = payload.word.strip()
    if not w:
        return WordMcqOut(text="단어가 비어 있습니다.")

    # TODO: 여기서 실제 생성 로직을 붙입니다. (LLM 또는 규칙 기반)
    # 아래는 샘플 포맷 (앱에서 SelectableText로 그대로 보여줌)
    sample = f"""①~⑤ 중 빈칸에 알맞은 단어를 고르세요.

The hasty changes to the schedule severely ______ our workflow.

① respect    ② enhance    ③ {w}    ④ forecast    ⑤ enlighten

정답: ③ {w}
👉 해석) 성급한 일정 변경은 우리의 작업 흐름을 '방해했다'.
"""
    return WordMcqOut(text=sample)