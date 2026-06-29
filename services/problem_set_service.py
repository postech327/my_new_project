from sqlalchemy.orm import Session

from models import (
    Passage,
    AnalysisRecord,
    ProblemSet,
    Question,
    Option,
)

# ✅ 진짜 GPT 함수 사용
from services.question_generation_service import generate_full_questions


def _answer_to_index(value) -> int:
    try:
        answer = int(value)
    except Exception:
        answer = 1
    return max(0, min(answer - 1, 4))


# =====================================================
# 1️⃣ Analysis 기반 문제 생성
# =====================================================
def create_problem_set_from_analysis(
    *,
    db: Session,
    passage: Passage,
    analysis: AnalysisRecord,
    created_by: str,
) -> ProblemSet:

    problem_set = ProblemSet(
        name=f"Auto ProblemSet (Analysis {analysis.id})",
        mode="teacher",
        created_by=created_by,
        description="Generated from AnalysisRecord",
        passage=passage,
    )

    db.add(problem_set)
    db.flush()

    # ✅ content 사용 (이미 잘 수정함 👍)
    gpt_result = generate_full_questions(passage.content)

    print("🔥 GPT RESULT:", gpt_result)

    questions = gpt_result.get("questions", [])

    for idx, q in enumerate(questions):

        options = q.get("options") or q.get("choices") or []

        if not options:
            print("❌ 옵션 없음:", q)
            continue

        try:
            correct_index = next(
                i for i, opt in enumerate(options) if opt.get("is_correct")
            )
        except StopIteration:
            correct_index = _answer_to_index(q.get("answer", 1))

        question_text = q.get("question_text", "")

        question = Question(
            question_type=q.get("question_type", "unknown"),
            text=question_text,
            explanation=q.get("explanation", ""),
            order=idx + 1,
            answer_index=correct_index,
            passage=passage,
            problem_set=problem_set,
        )

        db.add(question)
        db.flush()

        labels = ["①", "②", "③", "④", "⑤"]

        labels = ["①", "②", "③", "④", "⑤"]

        for i, opt in enumerate(options):
            db.add(
                Option(
                    question_id=question.id,
                    label=labels[i] if i < len(labels) else "",
                    text=opt.get("text", ""),
                )
            )

    db.commit()
    db.refresh(problem_set)

    return problem_set


# =====================================================
# 2️⃣ TEXT 기반 문제 생성
# =====================================================
def create_problem_set_from_text(
    *,
    db: Session,
    passage: Passage,
    created_by: str,
) -> ProblemSet:

    problem_set = ProblemSet(
        name=f"Auto ProblemSet (Text {passage.id})",
        mode="teacher",
        created_by=created_by,
        description="Generated from raw text input",
        passage=passage,
    )

    db.add(problem_set)
    db.flush()

    gpt_result = generate_full_questions(passage.content)

    print("🔥 GPT RESULT (TEXT):", gpt_result)

    questions = gpt_result.get("questions", [])

    for idx, q in enumerate(questions):

        options = q.get("options") or q.get("choices") or []

        if not options:
            print("❌ 옵션 없음:", q)
            continue

        try:
            correct_index = next(
                i for i, opt in enumerate(options) if opt.get("is_correct")
            )
        except StopIteration:
            correct_index = _answer_to_index(q.get("answer", 1))

        question_text = q.get("question_text", "")

        question = Question(
            question_type=q.get("question_type", "unknown"),
            text=question_text,
            explanation=q.get("explanation", ""),
            order=idx + 1,
            answer_index=correct_index,
            passage=passage,
            problem_set=problem_set,
        )

        db.add(question)
        db.flush()

        labels = ["①", "②", "③", "④", "⑤"]

        for i, opt in enumerate(options):
            db.add(
                Option(
                    question_id=question.id,
                    label=labels[i] if i < len(labels) else "",
                    text=opt.get("text", ""),
                )
            )

    db.commit()
    db.refresh(problem_set)

    return problem_set
