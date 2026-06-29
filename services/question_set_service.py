# services/question_set_service.py
from __future__ import annotations

from typing import Dict, Any
from sqlalchemy.orm import Session

from models import Passage, ProblemSet, Question, Option
from schemas.problem_set import ProblemSetGenerateRequest

# 🔥 통합 GPT 엔진
from services.question_generation_service import generate_full_questions


# =====================================================
# 🔥 Passage 본문 가져오기 helper
# =====================================================
def get_passage_content(passage: Passage) -> str:
    """
    프로젝트 내 Passage 모델 컬럼명이 content/text 등으로 다를 수 있어 안전하게 처리.
    현재 프로젝트에서는 passage.content를 주로 사용하지만,
    analysis.py에서 text 컬럼 가능성도 있었으므로 방어 처리.
    """
    content = getattr(passage, "content", None)

    if content:
        return content

    text = getattr(passage, "text", None)

    if text:
        return text

    return ""


# =====================================================
# 🔥 정답 인덱스 보정 함수
# =====================================================
def normalize_answer_index(q: Dict[str, Any]) -> int:
    """
    GPT answer 값을 DB 저장용 answer_index로 변환한다.

    기준:
    - GPT answer가 1~5이면 → 0~4로 변환
    - GPT answer가 이미 0~4이면 → 그대로 사용 가능하도록 방어
    - 이상한 값이면 → 0으로 처리
    """

    raw_answer = q.get("answer", 1)

    try:
        raw_answer = int(raw_answer)
    except Exception:
        raw_answer = 1

    # 기본 가정: GPT answer는 1~5
    correct_index = raw_answer - 1

    # 범위를 벗어난 경우 방어 처리
    if correct_index < 0 or correct_index > 4:
        # 혹시 GPT가 이미 0~4 기준으로 준 경우
        if 0 <= raw_answer <= 4:
            correct_index = raw_answer
        else:
            correct_index = 0

    return correct_index


# =====================================================
# 🔥 ProblemSet 생성 (분석 + 10문제 통합)
# =====================================================
def create_problem_set_with_questions(
    db: Session,
    req: ProblemSetGenerateRequest,
) -> ProblemSet:

    # 1️⃣ 지문 가져오기
    passage = db.query(Passage).filter(Passage.id == req.passage_id).first()
    if not passage:
        raise ValueError(f"Passage {req.passage_id} not found")

    passage_content = get_passage_content(passage)

    if not passage_content:
        raise ValueError(f"Passage {req.passage_id} has no content/text")

    # 🔥 파이널터치 분석값
    # text_analysis_hub_screen.dart에서 analysis를 같이 보내면 여기에 들어옴
    final_touch_analysis = req.analysis or {}

    print("🔥 FINAL TOUCH ANALYSIS RECEIVED:", final_touch_analysis)

    # 2️⃣ 🔥 GPT 통합 생성
    # 핵심: analysis를 generate_full_questions로 전달
    gpt_result = generate_full_questions(
        passage_content,
        analysis=final_touch_analysis,
    )

    # ✅ 핵심: questions_json 먼저 정의
    questions_json = gpt_result.get("questions", [])

    # 🔥 디버그
    print("🔥 GPT QUESTIONS COUNT:", len(questions_json))
    print("🔥 TYPE:", type(questions_json))
    print("🔥 RAW:", questions_json)

    # 🔥 dict → list 변환 (혹시 대비)
    if isinstance(questions_json, dict):
        questions_json = [questions_json]

    if not questions_json:
        raise ValueError("GPT returned empty questions")

    print("🔥 최종 문제 수:", len(questions_json))

    # 3️⃣ ProblemSet 생성
    folder_id = req.folder_id or getattr(passage, "folder_id", None)

    ps = ProblemSet(
        passage_id=passage.id,
        folder_id=folder_id,
        name=req.name,
        description="Auto-generated full set (analysis + 10 questions)",
        created_by=req.created_by,
        mode=req.mode,
    )

    db.add(ps)
    db.flush()

    saved_count = 0

    # =====================================================
    # 4️⃣ Question / Option 저장
    # =====================================================
    for idx, q in enumerate(questions_json):
        print(f"🔥 LOOP: {idx}")

        question_text = q.get("question_text", "")
        explanation = q.get("explanation", "")
        question_type = q.get("question_type", "unknown")

        options = q.get("options") or q.get("choices") or []

        if not options:
            print("❌ 옵션 없음:", q)
            continue

        # ✅ 선택지 5개까지만 저장
        options = options[:5]

        # ✅ 정답 index 보정
        correct_index = normalize_answer_index(q)

        # 선택지가 5개 미만인 경우에도 안전 처리
        if correct_index >= len(options):
            correct_index = 0

        print(
            f"✅ ANSWER CHECK | type: {question_type} | raw_answer: {q.get('answer')} "
            f"→ saved answer_index: {correct_index}"
        )

        # 🔥 topic/title/gist 정답 텍스트 확인용 로그
        if question_type in ["topic", "title", "gist"]:
            try:
                print(
                    f"🎯 FINAL TOUCH CHECK | {question_type} correct option:",
                    options[correct_index].get("text", ""),
                )
            except Exception:
                pass

        question = Question(
            question_type=question_type,
            text=question_text,
            explanation=explanation,
            order=idx + 1,
            answer_index=correct_index,
            passage_id=passage.id,
            problem_set_id=ps.id,
        )

        db.add(question)
        db.flush()

        # 🔥 선택지 저장
        labels = ["①", "②", "③", "④", "⑤"]

        for i, opt in enumerate(options):
            option_text = ""

            if isinstance(opt, dict):
                option_text = opt.get("text", "")
            else:
                option_text = str(opt)

            db.add(
                Option(
                    question_id=question.id,
                    label=labels[i] if i < len(labels) else "",
                    text=option_text,
                )
            )

        saved_count += 1

    # 🔥 반드시 for문 밖
    db.commit()
    db.refresh(ps)

    print(f"✅ DB 저장 완료 | ProblemSet ID: {ps.id} | saved questions: {saved_count}")

    return ps
