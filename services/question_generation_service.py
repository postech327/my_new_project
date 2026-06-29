# services/question_generation_service.py
from __future__ import annotations

from openai import OpenAI
from config import OPENAI_API_KEY, OPENAI_MODEL

import json
import re
import random
from typing import Dict, Any, Optional, List


client = OpenAI(api_key=OPENAI_API_KEY)


# =====================================================
# 공통 JSON 정리 / 호출
# =====================================================
def clean_json(raw: str) -> str:
    raw = raw.strip()

    raw = re.sub(r"```json", "", raw, flags=re.IGNORECASE)
    raw = re.sub(r"```", "", raw)
    raw = raw.strip()

    match = re.search(r"\{.*\}", raw, re.DOTALL)
    if match:
        raw = match.group()

    # trailing comma 제거
    raw = re.sub(r",\s*([\]}])", r"\1", raw)

    return raw.strip()


def call_gpt_json(prompt: str, temperature: float = 0.2) -> Dict[str, Any]:
    response = client.chat.completions.create(
        model=OPENAI_MODEL,
        messages=[
            {
                "role": "system",
                "content": "You are a strict JSON generator. Return ONLY valid JSON.",
            },
            {
                "role": "user",
                "content": prompt,
            },
        ],
        temperature=temperature,
    )

    raw = response.choices[0].message.content or ""

    if not raw:
        raise Exception("GPT returned empty response")

    raw = clean_json(raw)

    try:
        return json.loads(raw)
    except Exception as e:
        print("❌ JSON 파싱 실패:", e)
        print("❌ RAW:", raw)

        fixed_raw = re.sub(r",\s*([\]}])", r"\1", raw)

        try:
            data = json.loads(fixed_raw)
            print("✅ JSON 재파싱 성공")
            return data
        except Exception as e2:
            print("❌ JSON 재파싱도 실패:", e2)
            print("❌ FIXED RAW:", fixed_raw)
            raise


# =====================================================
# 공통 보정 함수
# =====================================================
def safe_answer_number(q: Dict[str, Any]) -> int:
    raw_answer = q.get("answer", 1)

    try:
        answer = int(raw_answer)
    except Exception:
        answer = 1

    if answer < 1 or answer > 5:
        answer = 1

    return answer


def normalize_question_type(q: Dict[str, Any]) -> str:
    q_type = str(q.get("question_type", "")).lower().strip()

    aliases = {
        "main idea": "topic",
        "main_idea": "topic",
        "subject": "topic",
        "theme": "topic",
        "heading": "title",
        "central idea": "gist",
        "central_idea": "gist",
        "blank": "cloze",
        "fill-in-the-blank": "cloze",
        "fill_blank": "cloze",
        "sequence": "order",
        "ordering": "order",
        "paragraph_order": "order",
        "sentence insertion": "insertion",
        "sentence_insertion": "insertion",
        "insert": "insertion",
        "irrelevant": "mismatch",
        "not true": "mismatch",
        "incorrect": "mismatch",
        "content mismatch": "mismatch",
    }

    q_type = aliases.get(q_type, q_type)

    if not q_type:
        q_type = "unknown"

    q["question_type"] = q_type
    return q_type


def normalize_choices(q: Dict[str, Any]) -> List[Dict[str, Any]]:
    raw_choices = q.get("choices") or q.get("options") or []
    fixed_choices: List[Dict[str, Any]] = []

    for i, c in enumerate(raw_choices[:5]):
        if isinstance(c, dict):
            text = c.get("text", "")
        else:
            text = str(c)

        fixed_choices.append(
            {
                "number": i + 1,
                "text": text,
            }
        )

    while len(fixed_choices) < 5:
        fixed_choices.append(
            {
                "number": len(fixed_choices) + 1,
                "text": f"Option {len(fixed_choices) + 1}",
            }
        )

    return fixed_choices


# =====================================================
# 파이널터치 정답 고정
# =====================================================
def force_fixed_answer_and_shuffle(
    q: Dict[str, Any],
    fixed_answer: str,
) -> Dict[str, Any]:
    fixed_answer = (fixed_answer or "").strip()

    if not fixed_answer:
        return q

    choices = normalize_choices(q)

    old_answer_number = safe_answer_number(q)
    old_answer_index = old_answer_number - 1

    if old_answer_index < 0 or old_answer_index >= len(choices):
        old_answer_index = 0

    choices[old_answer_index]["text"] = fixed_answer

    for i, choice in enumerate(choices):
        choice["_is_correct"] = i == old_answer_index

    random.shuffle(choices)

    new_answer_number = 1

    for i, choice in enumerate(choices):
        if choice.get("_is_correct"):
            new_answer_number = i + 1

        choice.pop("_is_correct", None)
        choice["number"] = i + 1

    q["choices"] = choices
    q["answer"] = new_answer_number

    return q


def apply_final_touch_answers_to_basic(
    questions: List[Dict[str, Any]],
    analysis: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, Any]]:
    if not analysis:
        return questions

    topic_answer = (analysis.get("topic_en") or "").strip()
    title_answer = (analysis.get("title_en") or "").strip()
    gist_answer = (analysis.get("gist_en") or "").strip()

    applied = {
        "topic": False,
        "title": False,
        "gist": False,
    }

    for q in questions:
        q_type = normalize_question_type(q)

        if q_type == "topic" and topic_answer and not applied["topic"]:
            force_fixed_answer_and_shuffle(q, topic_answer)
            applied["topic"] = True
            print("✅ 파이널터치 topic 정답 반영:", topic_answer)

        elif q_type == "title" and title_answer and not applied["title"]:
            force_fixed_answer_and_shuffle(q, title_answer)
            applied["title"] = True
            print("✅ 파이널터치 title 정답 반영:", title_answer)

        elif q_type == "gist" and gist_answer and not applied["gist"]:
            force_fixed_answer_and_shuffle(q, gist_answer)
            applied["gist"] = True
            print("✅ 파이널터치 gist 정답 반영:", gist_answer)

    return questions


# =====================================================
# order / insertion 선택지 고정
# =====================================================
def normalize_order_question(q: Dict[str, Any]) -> Dict[str, Any]:
    if str(q.get("question_type", "")).lower().strip() != "order":
        return q

    allowed_choices = [
        "(A)-(C)-(B)",
        "(B)-(A)-(C)",
        "(B)-(C)-(A)",
        "(C)-(A)-(B)",
        "(C)-(B)-(A)",
    ]

    old_choices = q.get("choices") or []
    old_answer = safe_answer_number(q)
    old_answer_index = old_answer - 1

    correct_text = ""

    if 0 <= old_answer_index < len(old_choices):
        old_correct = old_choices[old_answer_index]
        if isinstance(old_correct, dict):
            correct_text = str(old_correct.get("text", "")).strip()
        else:
            correct_text = str(old_correct).strip()

    if correct_text in allowed_choices:
        new_answer = allowed_choices.index(correct_text) + 1
    else:
        # GPT가 이미 1~5 중 하나로 제대로 줬다고 보고 유지
        new_answer = old_answer
        if new_answer < 1 or new_answer > 5:
            new_answer = 1

    q["choices"] = [
        {"number": i + 1, "text": text}
        for i, text in enumerate(allowed_choices)
    ]
    q["answer"] = new_answer

    return q


ORDER_CHOICES = [
    "(A)-(C)-(B)",
    "(B)-(A)-(C)",
    "(B)-(C)-(A)",
    "(C)-(A)-(B)",
    "(C)-(B)-(A)",
]


def split_passage_for_order(passage: str) -> List[str]:
    text = re.sub(r"\s+", " ", passage or "").strip()
    if not text:
        return []

    units = [
        item.strip()
        for item in re.split(r"(?<=[.!?])\s+(?=[A-Z\"'(\[])", text)
        if item.strip()
    ]

    if len(units) >= 6:
        return units

    expanded: List[str] = []
    for unit in units:
        parts = [
            item.strip()
            for item in re.split(
                r"(?<=[;:])\s+|(?<=,)\s+(?=(?:and|but|because|while|although|when|which|that|where|whereas)\b)",
                unit,
                flags=re.IGNORECASE,
            )
            if item.strip()
        ]
        useful_parts = [
            part
            for part in parts
            if len(re.findall(r"[A-Za-z]+(?:'[A-Za-z]+)?", part)) >= 5
        ]
        expanded.extend(useful_parts if len(useful_parts) >= 2 else [unit])

    return expanded


def _join_units(units: List[str]) -> str:
    return " ".join(unit.strip() for unit in units if unit.strip()).strip()


def _split_contiguous_blocks(units: List[str]) -> List[str]:
    if len(units) < 3:
        raise Exception(
            f"order generation failed: not enough remaining sentence units ({len(units)})"
        )

    base = len(units) // 3
    extra = len(units) % 3
    sizes = [base + (1 if i < extra else 0) for i in range(3)]

    blocks: List[str] = []
    cursor = 0
    for size in sizes:
        blocks.append(_join_units(units[cursor: cursor + size]))
        cursor += size

    return blocks


def _order_partition(units: List[str], variant: int) -> tuple[str, List[str]]:
    total = len(units)

    if total < 6:
        raise Exception(
            f"order generation failed: passage has only {total} usable sentence units"
        )

    if variant % 2 == 0:
        given_count = 2 if total >= 7 else 1
    else:
        given_count = 1 if total >= 7 else 2

    if total - given_count < 3:
        given_count = max(1, total - 3)

    given_text = _join_units(units[:given_count])
    blocks = _split_contiguous_blocks(units[given_count:])

    return given_text, blocks


def _build_order_question_from_units(
    units: List[str],
    variant: int,
) -> Dict[str, Any]:
    given_text, original_blocks = _order_partition(units, variant)

    if variant % 2 == 0:
        label_to_block = {
            "A": original_blocks[1],
            "B": original_blocks[2],
            "C": original_blocks[0],
        }
        correct_order = "(C)-(A)-(B)"
    else:
        label_to_block = {
            "A": original_blocks[2],
            "B": original_blocks[0],
            "C": original_blocks[1],
        }
        correct_order = "(B)-(C)-(A)"

    question_text = (
        "[Given Text]\n"
        f"{given_text}\n\n"
        f"(A) {label_to_block['A']}\n\n"
        f"(B) {label_to_block['B']}\n\n"
        f"(C) {label_to_block['C']}"
    )

    return {
        "question_type": "order",
        "question_text": question_text,
        "given_text": given_text,
        "order_blocks": label_to_block,
        "choices": [
            {"number": i + 1, "text": text}
            for i, text in enumerate(ORDER_CHOICES)
        ],
        "answer": ORDER_CHOICES.index(correct_order) + 1,
        "explanation": "원문 문장 덩어리의 실제 흐름을 기준으로 배열합니다.",
    }


def generate_order_questions_from_passage(
    passage: str,
    expected_count: int = 2,
) -> List[Dict[str, Any]]:
    units = split_passage_for_order(passage)

    if len(units) < 6:
        raise Exception(
            "order generation failed: "
            f"expected at least 6 sentence units, actual {len(units)}"
        )

    questions = [
        _build_order_question_from_units(units, variant=i)
        for i in range(expected_count)
    ]

    return normalize_questions(questions)


def extract_insertion_sentence(text: str) -> str:
    if not text:
        return ""

    text = text.strip()

    patterns = [
        r"'([^']+)'",
        r'"([^"]+)"',
        r"“([^”]+)”",
        r"‘([^’]+)’",
    ]

    for pattern in patterns:
        m = re.search(pattern, text, flags=re.DOTALL)
        if m:
            extracted = m.group(1).strip()
            if extracted:
                return extracted

    lowered = text.lower()
    markers = [
        "following sentence",
        "given sentence",
        "sentence to insert",
        "주어진 문장",
    ]

    for marker in markers:
        idx = lowered.find(marker)
        if idx != -1:
            candidate = text[idx + len(marker):].strip(" :\n\t")
            if candidate:
                return candidate

    return text


def normalize_insertion_question(q: Dict[str, Any]) -> Dict[str, Any]:
    if str(q.get("question_type", "")).lower().strip() != "insertion":
        return q

    raw_text = (q.get("question_text") or q.get("text") or "").strip()
    insertion_sentence = extract_insertion_sentence(raw_text)

    q["question_text"] = insertion_sentence

    q["choices"] = [
        {"number": 1, "text": "( ① )"},
        {"number": 2, "text": "( ② )"},
        {"number": 3, "text": "( ③ )"},
        {"number": 4, "text": "( ④ )"},
        {"number": 5, "text": "( ⑤ )"},
    ]

    q["answer"] = safe_answer_number(q)

    return q


# =====================================================
# 원문 포함 여부 검증
# =====================================================
def normalize_for_match(text: str) -> str:
    if not text:
        return ""

    text = text.lower()
    text = text.replace("“", '"').replace("”", '"')
    text = text.replace("‘", "'").replace("’", "'")
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def text_exists_in_passage(target: str, passage: str) -> bool:
    target_norm = normalize_for_match(target)
    passage_norm = normalize_for_match(passage)

    if not target_norm or not passage_norm:
        return False

    if target_norm in passage_norm:
        return True

    # 긴 복문 분리 가능성 고려: 앞 8단어 기준으로도 확인
    words = target_norm.split()
    if len(words) >= 8:
        short_target = " ".join(words[:8])
        return short_target in passage_norm

    return False


def _visible_blank(text: str) -> str:
    return re.sub(r"_{3,}", "[          ]", text or "")


def _question_blank_maps_to_passage(question_text: str, passage: str) -> bool:
    blanked = _visible_blank(question_text)
    if "[          ]" not in blanked:
        return False

    prefix = blanked.split("[          ]", 1)[0].strip()
    if len(prefix) < 12:
        return False

    return prefix.lower() in passage.lower()


def _answer_text_exists_in_passage(answer_text: str, passage: str) -> bool:
    answer_text = (answer_text or "").strip()
    if not answer_text:
        return False

    if answer_text.lower() in passage.lower():
        return True

    words = [
        re.escape(word)
        for word in re.findall(r"[A-Za-z]+(?:'[A-Za-z]+)?", answer_text)
        if word.strip()
    ]

    if len(words) < 2:
        return False

    pattern = r"\s+(?:the\s+|a\s+|an\s+)?".join(words)
    return re.search(pattern, passage, flags=re.IGNORECASE) is not None


def validate_cloze_questions(
    questions: List[Dict[str, Any]],
    passage: str,
) -> bool:
    for idx, q in enumerate(questions):
        q_type = str(q.get("question_type", "")).lower().strip()

        if q_type != "cloze":
            continue

        question_text = str(q.get("question_text", "")).strip()
        choices = q.get("choices") or []
        answer_index = safe_answer_number(q) - 1
        answer_text = ""

        if 0 <= answer_index < len(choices):
            choice = choices[answer_index]
            answer_text = str(
                choice.get("text", "") if isinstance(choice, dict) else choice
            ).strip()

        if _question_blank_maps_to_passage(
            question_text,
            passage,
        ) and _answer_text_exists_in_passage(answer_text, passage):
            return True

        print("❌ cloze가 원문 기반이 아님")
        print("❌ 문제 번호:", idx + 1)
        print("❌ question_text:", question_text)
        print("❌ answer_text:", answer_text)
        return False

    return True


def validate_insertion_questions(
    questions: List[Dict[str, Any]],
    passage: str,
) -> bool:
    for idx, q in enumerate(questions):
        q_type = str(q.get("question_type", "")).lower().strip()

        if q_type != "insertion":
            continue

        insertion_sentence = str(q.get("question_text", "")).strip()

        if not text_exists_in_passage(insertion_sentence, passage):
            print("❌ insertion 문장이 원문에 없음")
            print("❌ 문제 번호:", idx + 1)
            print("❌ insertion_sentence:", insertion_sentence)
            return False

    return True


def is_valid_mismatch_question(q: Dict[str, Any]) -> bool:
    q_type = str(q.get("question_type", "")).lower().strip()

    if q_type != "mismatch":
        return False

    choices = q.get("choices") or []
    if len(choices) != 5:
        print("❌ mismatch 선택지 수 오류:", len(choices))
        return False

    for choice in choices:
        text = str(choice.get("text", "") if isinstance(choice, dict) else choice).strip()
        words = re.findall(r"[A-Za-z]+(?:'[A-Za-z]+)?", text)

        if len(words) < 8 or len(words) > 20:
            print("❌ mismatch 선택지 길이 오류:", text)
            return False

        if not re.search(r"[.!?]$", text):
            print("❌ mismatch 선택지가 문장 형태가 아님:", text)
            return False

    return True


def validate_mismatch_questions(questions: List[Dict[str, Any]]) -> bool:
    for q in questions:
        q_type = str(q.get("question_type", "")).lower().strip()

        if q_type != "mismatch":
            continue

        if not is_valid_mismatch_question(q):
            return False

    return True


# =====================================================
# 전체 normalize
# =====================================================
def normalize_questions(questions: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    normalized: List[Dict[str, Any]] = []

    for q in questions:
        if not isinstance(q, dict):
            continue

        normalize_question_type(q)

        raw_text = q.get("question_text") or q.get("text") or ""

        if (not raw_text) or ("문제 생성 오류" in raw_text):
            q["question_text"] = "Which of the following best describes the passage?"
        else:
            q["question_text"] = raw_text

        q["choices"] = normalize_choices(q)
        q["answer"] = safe_answer_number(q)

        q = normalize_order_question(q)
        q = normalize_insertion_question(q)

        if not q.get("explanation"):
            q["explanation"] = "지문을 기반으로 판단해야 합니다."

        normalized.append(q)

    return normalized


# =====================================================
# 검증 함수
# =====================================================
def validate_questions_count(
    questions: List[Dict[str, Any]],
    expected_counts: Dict[str, int],
) -> bool:
    if not isinstance(questions, list):
        print("❌ questions가 list가 아님")
        return False

    type_counts: Dict[str, int] = {}

    for q in questions:
        q_type = str(q.get("question_type", "")).lower().strip()
        type_counts[q_type] = type_counts.get(q_type, 0) + 1

    print("🔥 QUESTION TYPE COUNTS:", type_counts)

    total_expected = sum(expected_counts.values())

    if len(questions) != total_expected:
        print(f"❌ 문제 수 오류: expected {total_expected}, actual {len(questions)}")
        return False

    for q_type, expected in expected_counts.items():
        actual = type_counts.get(q_type, 0)
        if actual != expected:
            print(f"❌ {q_type} 문제 수 오류: expected {expected}, actual {actual}")
            return False

    return True


def validate_final_question_set(questions: List[Dict[str, Any]]) -> bool:
    expected_counts = {
        "topic": 1,
        "title": 1,
        "gist": 1,
        "cloze": 1,
        "order": 2,
        "insertion": 2,
        "mismatch": 2,
    }

    return validate_questions_count(questions, expected_counts)


def question_count_detail(
    questions: List[Dict[str, Any]],
    expected_counts: Dict[str, int],
) -> str:
    actual_counts: Dict[str, int] = {}

    for q in questions:
        q_type = str(q.get("question_type", "")).lower().strip()
        actual_counts[q_type] = actual_counts.get(q_type, 0) + 1

    missing = {
        q_type: expected - actual_counts.get(q_type, 0)
        for q_type, expected in expected_counts.items()
        if actual_counts.get(q_type, 0) < expected
    }

    return (
        f"expected={expected_counts}, actual={actual_counts}, "
        f"missing={missing}, total={len(questions)}"
    )


# =====================================================
# 프롬프트: 기본 4문제
# =====================================================
def build_final_touch_guidance(analysis: Optional[Dict[str, Any]]) -> str:
    if not analysis:
        return ""

    def short(value: Any, limit: int = 220) -> str:
        text = str(value or "").strip()
        if len(text) <= limit:
            return text
        return text[:limit].rstrip() + "..."

    sentence_lines: List[str] = []
    for item in (analysis.get("sentence_details") or [])[:10]:
        if not isinstance(item, dict):
            continue
        sentence_no = item.get("sentence_no", "")
        role = short(item.get("sentence_role"), 80)
        original = short(item.get("original"), 180)
        question_point = short(item.get("question_point"), 180)
        blank = item.get("is_blank_candidate") is True
        sentence_lines.append(
            f"- S{sentence_no} role={role} blank_candidate={blank} | "
            f"original={original} | question_point={question_point}"
        )

    grammar_lines: List[str] = []
    for item in (analysis.get("grammar_points") or [])[:12]:
        if not isinstance(item, dict):
            continue
        grammar_lines.append(
            "- "
            + " | ".join(
                part
                for part in [
                    f"S{item.get('sentence_no', '')}",
                    short(item.get("target"), 80),
                    short(item.get("label"), 80),
                    short(item.get("explanation"), 160),
                ]
                if part.strip()
            )
        )

    return f"""
[FINAL TOUCH ANALYSIS GUIDANCE]
Use this analysis as structured guidance. Do not create questions unrelated to the passage.
Use topic/title/gist/summary to create topic, title, and main idea questions.
Use sentence_details.question_point to choose suitable evidence and avoid overusing one sentence.
Use blank_candidate sentences for cloze questions when appropriate.
Use grammar_points only when they naturally support a grammar accuracy question or explanation.
Store the correct answer through the question answer field; the DB will save it as questions.answer_index.

Core analysis:
- topic_en: {short(analysis.get("topic_en"))}
- topic_ko: {short(analysis.get("topic_ko"))}
- title_en: {short(analysis.get("title_en"))}
- title_ko: {short(analysis.get("title_ko"))}
- gist_en: {short(analysis.get("gist_en"))}
- gist_ko: {short(analysis.get("gist_ko"))}
- summary_en: {short(analysis.get("summary_en"))}
- summary_ko: {short(analysis.get("summary_ko"))}
- teacher_topic_sentence: {short(analysis.get("teacher_topic_sentence"))}

Sentence question points:
{chr(10).join(sentence_lines) if sentence_lines else "- none"}

Grammar points:
{chr(10).join(grammar_lines) if grammar_lines else "- none"}
"""


def build_basic_prompt(
    passage: str,
    analysis: Optional[Dict[str, Any]] = None,
) -> str:
    final_touch_guidance = build_final_touch_guidance(analysis)
    return f"""
You are a Korean CSAT English exam expert.

Create EXACTLY 4 multiple choice questions from the passage.

[Question Types]
1 topic
1 title
1 gist
1 cloze

[Rules]
- Each question must have exactly 5 choices.
- answer must be 1~5.
- Include explanation in Korean.
- Return ONLY valid JSON.
- Use question_type exactly as one of: topic, title, gist, cloze.
- Use question_text, not text.
- Use the Final Touch guidance below when it is provided.
- Do not create questions unrelated to the passage.
- Do not overuse the same sentence as the basis for multiple questions.

[GIST RULES]
- The gist question must ask for the writer's main point.
- All five gist choices must be full sentences.
- All five gist choices must be similar in length.
- Each gist choice should be about 9 to 15 words.
- Do not make the correct answer noticeably longer or more specific than the distractors.

[CLOZE RULES]
- Make one blank question.
- The blank must remove an exact key word, phrase, or clause from the original passage.
- The question_text must be an exact sentence from the original passage with only that expression replaced by ______.
- Do NOT create a new summary sentence such as "In the passage, ...".
- Do NOT paraphrase the original sentence.
- The correct answer must be the exact removed expression from the original passage.
- If the answer is a phrase, all distractors should be similar phrase forms.
- Keep all five choices similar in length and grammatical form.
- Do not blank a trivial function word or a very minor detail.

Return JSON ONLY:
{{
  "questions": [
    {{
      "question_type": "topic",
      "question_text": "...",
      "choices": [
        {{"number": 1, "text": "..."}},
        {{"number": 2, "text": "..."}},
        {{"number": 3, "text": "..."}},
        {{"number": 4, "text": "..."}},
        {{"number": 5, "text": "..."}}
      ],
      "answer": 1,
      "explanation": "..."
    }}
  ]
}}

PASSAGE:
{passage}
"""


# =====================================================
# 프롬프트: 순서 2문제
# =====================================================
def build_order_prompt(passage: str) -> str:
    return f"""
You are a Korean CSAT English exam expert.

Create EXACTLY 2 paragraph ordering questions.

[Must Follow]
- Return ONLY valid JSON.
- The JSON must contain exactly 2 questions.
- Both questions must have question_type: "order".
- Use ONLY the original passage.
- Do NOT invent content.
- Do NOT summarize.
- Do NOT create a simple concept-ordering question.

[Question Structure]
Each order question must have this structure in question_text:

[Given Text]
Opening sentence group from the original passage.

(A) Sentence group from the original passage.
(B) Sentence group from the original passage.
(C) Sentence group from the original passage.

[Content Rule]
- [Given Text] must come before (A), (B), and (C) in the original passage.
- (A), (B), and (C) must be made from the remaining original passage.
- [Given Text] + the correct order of (A), (B), and (C) should cover the passage as much as possible.
- Do not omit the final sentence if possible.
- If the passage is short, split long complex sentences naturally.
- Keep the original wording as much as possible.

[Answer Choice Rule]
The choices must be EXACTLY these five:
1. "(A)-(C)-(B)"
2. "(B)-(A)-(C)"
3. "(B)-(C)-(A)"
4. "(C)-(A)-(B)"
5. "(C)-(B)-(A)"

Do NOT include "(A)-(B)-(C)" as a choice.
The correct answer must be one of 1, 2, 3, 4, or 5.

[JSON FORMAT]
{{
  "questions": [
    {{
      "question_type": "order",
      "question_text": "[Given Text] ...\\n\\n(A) ...\\n\\n(B) ...\\n\\n(C) ...",
      "choices": [
        {{"number": 1, "text": "(A)-(C)-(B)"}},
        {{"number": 2, "text": "(B)-(A)-(C)"}},
        {{"number": 3, "text": "(B)-(C)-(A)"}},
        {{"number": 4, "text": "(C)-(A)-(B)"}},
        {{"number": 5, "text": "(C)-(B)-(A)"}}
      ],
      "answer": 4,
      "explanation": "..."
    }},
    {{
      "question_type": "order",
      "question_text": "[Given Text] ...\\n\\n(A) ...\\n\\n(B) ...\\n\\n(C) ...",
      "choices": [
        {{"number": 1, "text": "(A)-(C)-(B)"}},
        {{"number": 2, "text": "(B)-(A)-(C)"}},
        {{"number": 3, "text": "(B)-(C)-(A)"}},
        {{"number": 4, "text": "(C)-(A)-(B)"}},
        {{"number": 5, "text": "(C)-(B)-(A)"}}
      ],
      "answer": 5,
      "explanation": "..."
    }}
  ]
}}

PASSAGE:
{passage}
"""


# =====================================================
# 프롬프트: 삽입 2문제
# =====================================================
def build_insertion_prompt(passage: str) -> str:
    return f"""
You are a Korean CSAT English exam expert.

Create EXACTLY 2 Korean CSAT-style sentence insertion questions.

[Core Rules]
- Use ONLY the original passage.
- Do NOT invent new sentences.
- Do NOT paraphrase the sentence to insert.
- The sentence to insert must be an exact sentence or exact sentence unit from the original passage.
- If the original passage has fewer than 6 sentences, split long complex or compound sentences into natural shorter sentence units.
- When splitting, preserve the original wording as much as possible.
- The selected insertion sentence must be removed from the marked passage.
- Marked passage should have five insertion positions.
- Place insertion markers only after complete sentence units, preferably after a period.
- Do NOT place insertion markers in the middle of a clause.

[Question Text Rule]
- question_text should contain ONLY the sentence to insert.
- Do NOT include the whole passage in question_text.
- Do NOT include "Where would..." or similar guide text in question_text.

[Choices]
Choices must be EXACTLY:
1. "( ① )"
2. "( ② )"
3. "( ③ )"
4. "( ④ )"
5. "( ⑤ )"

Return JSON ONLY:
{{
  "questions": [
    {{
      "question_type": "insertion",
      "question_text": "Exact sentence from the passage to insert.",
      "choices": [
        {{"number": 1, "text": "( ① )"}},
        {{"number": 2, "text": "( ② )"}},
        {{"number": 3, "text": "( ③ )"}},
        {{"number": 4, "text": "( ④ )"}},
        {{"number": 5, "text": "( ⑤ )"}}
      ],
      "answer": 3,
      "explanation": "..."
    }}
  ]
}}

PASSAGE:
{passage}
"""


# =====================================================
# 프롬프트: 불일치 2문제
# =====================================================
def build_mismatch_prompt(passage: str) -> str:
    return f"""
You are a Korean CSAT English exam expert.

Create EXACTLY 2 mismatch questions from the passage.

[Rules]
- Use question_type exactly as "mismatch".
- Each question asks which statement is NOT consistent with the passage.
- Each question has exactly 5 choices.
- Each choice must be a complete English sentence, not a keyword or phrase.
- Each choice should be about 12 to 18 words and must not exceed 20 words.
- Avoid overly long compound sentences.
- Arrange choices in the same order as the passage flow:
  choice 1 from the early part, choice 2 from the next part,
  choice 3 from the middle, choice 4 from the later part,
  choice 5 from the final part.
- Keep the correct mismatch similar in length and structure to the other choices.
- Do NOT use one-word choices such as "Perception", "Memory", or "Imagination".
- answer must be 1~5.
- Include explanation in Korean.
- Return ONLY valid JSON.

Return JSON ONLY:
{{
  "questions": [
    {{
      "question_type": "mismatch",
      "question_text": "Which statement is NOT consistent with the passage?",
      "choices": [
        {{"number": 1, "text": "..."}},
        {{"number": 2, "text": "..."}},
        {{"number": 3, "text": "..."}},
        {{"number": 4, "text": "..."}},
        {{"number": 5, "text": "..."}}
      ],
      "answer": 1,
      "explanation": "..."
    }}
  ]
}}

PASSAGE:
{passage}

{final_touch_guidance}
"""


def _passage_units(passage: str) -> List[str]:
    units = [
        item.strip()
        for item in re.split(r"(?<=[.!?])\s+|\n+", passage or "")
        if item.strip()
    ]

    if len(units) >= 5:
        return units

    expanded: List[str] = []
    for unit in units:
        parts = [
            item.strip()
            for item in re.split(r"(?<=[,;:])\s+", unit)
            if item.strip()
        ]
        expanded.extend(parts if len(parts) > 1 else [unit])

    return expanded or units


def _sentence_like_statement(text: str, fallback: str) -> str:
    words = re.findall(r"[A-Za-z]+(?:'[A-Za-z]+)?|[0-9]+", text or "")

    if not words:
        words = re.findall(r"[A-Za-z]+(?:'[A-Za-z]+)?|[0-9]+", fallback)

    if len(words) < 8:
        words = (words + fallback.split())[:12]

    words = words[:18]
    sentence = " ".join(words).strip()

    if not sentence:
        sentence = fallback

    sentence = sentence[0].upper() + sentence[1:] if len(sentence) > 1 else sentence.upper()

    if not sentence.endswith((".", "!", "?")):
        sentence += "."

    return sentence


def fallback_mismatch_question(
    passage: str,
    variant: int = 0,
) -> Dict[str, Any]:
    units = _passage_units(passage)
    fallback_true = [
        "The passage develops its main idea through connected details and examples.",
        "The passage presents information in a clear order for the reader.",
        "The passage explains an important relationship between two related ideas.",
        "The passage supports its central point with specific supporting information.",
        "The passage ends by reinforcing the main idea for the reader.",
    ]

    choices: List[Dict[str, Any]] = []

    for i in range(5):
        source = units[min(i, len(units) - 1)] if units else fallback_true[i]
        choices.append(
            {
                "number": i + 1,
                "text": _sentence_like_statement(source, fallback_true[i]),
            }
        )

    false_index = 2 if variant % 2 == 0 else 3
    false_options = [
        "The passage says this topic has no connection to the central discussion.",
        "The passage argues that the main process is unnecessary for understanding the topic.",
    ]
    choices[false_index]["text"] = false_options[variant % len(false_options)]

    return {
        "question_type": "mismatch",
        "question_text": "Which statement is NOT consistent with the passage?",
        "choices": choices,
        "answer": false_index + 1,
        "explanation": "부족한 불일치 문항을 보완하기 위해 원문 흐름을 바탕으로 생성한 기본 문항입니다.",
        "_fallback": True,
    }


def generate_mismatch_questions(
    passage: str,
    expected_count: int = 2,
    max_attempts: int = 3,
) -> List[Dict[str, Any]]:
    collected: List[Dict[str, Any]] = []
    seen_keys: set[str] = set()
    last_error = None

    for attempt in range(1, max_attempts + 1):
        if len(collected) >= expected_count:
            break

        print(
            f"🔥 mismatch 생성 시도: {attempt}/{max_attempts} "
            f"| 현재 확보 {len(collected)}/{expected_count}"
        )

        try:
            data = call_gpt_json(build_mismatch_prompt(passage), temperature=0.2)

            if "questions" not in data:
                raise Exception("mismatch: Invalid GPT response format")

            questions = normalize_questions(data.get("questions", []))
            print("🔥 mismatch RAW NORMALIZED QUESTIONS COUNT:", len(questions))

            for q in questions:
                if str(q.get("question_type", "")).lower().strip() != "mismatch":
                    continue

                if not is_valid_mismatch_question(q):
                    continue

                key = "|".join(
                    str(choice.get("text", "")).strip()
                    for choice in q.get("choices", [])
                    if isinstance(choice, dict)
                )

                if key in seen_keys:
                    continue

                seen_keys.add(key)
                collected.append(q)

                if len(collected) >= expected_count:
                    break

            if len(collected) < expected_count:
                print(
                    f"⚠️ mismatch 부족: expected {expected_count}, "
                    f"current {len(collected)} → 부족분 재시도"
                )

        except Exception as e:
            print(f"❌ mismatch 생성 실패 attempt {attempt}:", e)
            last_error = e

    while len(collected) < expected_count:
        missing_number = len(collected) + 1
        print(
            f"⚠️ mismatch fallback 생성: {missing_number}/{expected_count} "
            f"| last_error={last_error}"
        )
        collected.append(
            fallback_mismatch_question(
                passage,
                variant=missing_number - 1,
            )
        )

    return collected[:expected_count]


# =====================================================
# 그룹별 생성 공통
# =====================================================
def generate_group_questions(
    group_name: str,
    prompt: str,
    expected_counts: Dict[str, int],
    passage: str,
    max_attempts: int = 3,
) -> List[Dict[str, Any]]:
    last_error = None

    for attempt in range(1, max_attempts + 1):
        print(f"🔥 {group_name} 생성 시도: {attempt}/{max_attempts}")

        try:
            data = call_gpt_json(prompt, temperature=0.2)

            if "questions" not in data:
                raise Exception(f"{group_name}: Invalid GPT response format")

            questions = data.get("questions", [])
            questions = normalize_questions(questions)

            print(
                f"🔥 {group_name} RAW NORMALIZED QUESTIONS COUNT:",
                len(questions),
            )
            for idx, q in enumerate(questions):
                print(
                    f"🔥 {group_name} Q{idx + 1} type:",
                    q.get("question_type"),
                    "| text preview:",
                    str(q.get("question_text", ""))[:80],
                )

            if not validate_questions_count(questions, expected_counts):
                print(f"❌ {group_name} 구성 검증 실패 → 재시도")
                last_error = Exception(f"{group_name} validation failed")
                continue

            if expected_counts.get("insertion", 0) > 0:
                if not validate_insertion_questions(questions, passage):
                    print(f"❌ {group_name} 삽입 문장 원문 검증 실패 → 재시도")
                    last_error = Exception(f"{group_name} insertion validation failed")
                    continue

            if expected_counts.get("cloze", 0) > 0:
                if not validate_cloze_questions(questions, passage):
                    print(f"❌ {group_name} 빈칸 원문 검증 실패 → 재시도")
                    last_error = Exception(f"{group_name} cloze validation failed")
                    continue

            if expected_counts.get("mismatch", 0) > 0:
                if not validate_mismatch_questions(questions):
                    print(f"❌ {group_name} 불일치 선택지 검증 실패 → 재시도")
                    last_error = Exception(f"{group_name} mismatch validation failed")
                    continue

            print(f"✅ {group_name} 생성 성공")
            return questions

        except Exception as e:
            print(f"❌ {group_name} 생성 실패 attempt {attempt}:", e)
            last_error = e

    raise Exception(f"{group_name} generation failed after {max_attempts} attempts: {last_error}")


# =====================================================
# 최종 통합 생성
# =====================================================
def generate_full_questions(
    passage: str,
    analysis: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    분리 생성 버전:
    1. basic: topic/title/gist/cloze 4개
    2. order: order 2개
    3. insertion: insertion 2개
    4. mismatch: mismatch 2개
    최종 10문제 반환
    """

    print("🔥 분리 생성 시작")

    basic_questions = generate_group_questions(
        group_name="basic",
        prompt=build_basic_prompt(passage, analysis=analysis),
        expected_counts={
            "topic": 1,
            "title": 1,
            "gist": 1,
            "cloze": 1,
        },
        passage=passage,
    )

    basic_questions = apply_final_touch_answers_to_basic(
        basic_questions,
        analysis=analysis,
    )
    basic_questions = normalize_questions(basic_questions)

    order_questions = generate_order_questions_from_passage(
        passage=passage,
        expected_count=2,
    )

    insertion_questions = generate_group_questions(
        group_name="insertion",
        prompt=build_insertion_prompt(passage),
        expected_counts={
            "insertion": 2,
        },
        passage=passage,
        max_attempts=5,
    )

    mismatch_questions = generate_mismatch_questions(
        passage=passage,
        expected_count=2,
        max_attempts=3,
    )

    questions = (
        basic_questions
        + order_questions
        + insertion_questions
        + mismatch_questions
    )

    questions = normalize_questions(questions)

    expected_final_counts = {
        "topic": 1,
        "title": 1,
        "gist": 1,
        "cloze": 1,
        "order": 2,
        "insertion": 2,
        "mismatch": 2,
    }

    if not validate_final_question_set(questions):
        raise Exception(
            "Final question set validation failed: "
            + question_count_detail(questions, expected_final_counts)
        )

    print("✅ 최종 10문제 생성 완료")

    for idx, q in enumerate(questions):
        print(
            f"🔥 Q{idx + 1} | type: {q.get('question_type')} "
            f"| answer: {q.get('answer')}"
        )

    return {
        "questions": questions,
    }
