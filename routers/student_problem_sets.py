# routers/student_problem_sets.py

import re

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from db import get_db
import models
from utils.security import require_role

router = APIRouter(
    prefix="/student",
    tags=["student_problem_sets"],
)

BLANK_MARK = "[          ]"
UNFILED_NAME = "미분류"
DIRECT_BUCKET_NAME = "기타 자료"

TYPE_LABELS = {
    "topic": "주제",
    "title": "제목",
    "gist": "요지",
    "summary": "요약",
    "cloze": "빈칸",
    "blank": "빈칸",
    "order": "순서",
    "insertion": "삽입",
    "mismatch": "불일치",
    "content": "불일치",
    "grammar": "어법",
    "vocabulary": "어휘",
}

TYPE_ORDER = [
    "topic",
    "title",
    "gist",
    "summary",
    "cloze",
    "blank",
    "order",
    "insertion",
    "mismatch",
    "content",
    "grammar",
    "vocabulary",
]

MOCK_TYPE_LABELS = {
    "purpose": "목적",
    "mood": "심경/분위기",
    "claim": "주장",
    "implication": "함의",
    "gist": "요지",
    "topic": "주제",
    "title": "제목",
    "content_match": "일치",
    "grammar": "어법",
    "vocabulary": "어휘",
    "blank": "빈칸",
    "irrelevant": "무관한 문장",
    "order": "순서",
    "insertion": "삽입",
    "summary": "요약",
}


def _visible_blank(text: str) -> str:
    return re.sub(r"_{3,}", BLANK_MARK, text or "")


def _replace_case_insensitive(text: str, target: str, replacement: str) -> str | None:
    if not target.strip():
        return None

    pattern = re.compile(re.escape(target.strip()), flags=re.IGNORECASE)
    match = pattern.search(text)
    if not match:
        return None

    return text[:match.start()] + replacement + text[match.end():]


def _replace_answer_phrase(passage: str, answer_text: str) -> str | None:
    direct = _replace_case_insensitive(passage, answer_text, BLANK_MARK)
    if direct:
        return direct

    words = [
        re.escape(word)
        for word in re.findall(r"[A-Za-z]+(?:'[A-Za-z]+)?", answer_text or "")
        if word.strip()
    ]

    if len(words) < 2:
        return None

    pattern = r"\s+(?:the\s+|a\s+|an\s+)?".join(words)
    match = re.search(pattern, passage, flags=re.IGNORECASE)
    if not match:
        return None

    return passage[:match.start()] + BLANK_MARK + passage[match.end():]


def _merge_question_blank_into_passage(passage: str, question_text: str) -> str | None:
    blanked = _visible_blank(question_text)
    if BLANK_MARK not in blanked:
        return None

    prefix = blanked.split(BLANK_MARK, 1)[0].strip()
    if len(prefix) < 12:
        return None

    start = passage.lower().find(prefix.lower())
    if start == -1:
        return None

    sentence_end = passage.find(".", start)
    end = len(passage) if sentence_end == -1 else sentence_end + 1
    return passage[:start] + blanked + passage[end:]


def _build_blanked_passage(passage: str, question, options) -> str | None:
    q_type = (question.question_type or "").lower().strip()
    if q_type not in {"cloze", "blank"}:
        return None

    question_text = question.text or ""

    answer_index = question.answer_index
    answer_text = ""

    if answer_index is not None and 0 <= answer_index < len(options):
        answer_text = options[answer_index].text or ""

    replaced = _replace_answer_phrase(passage, answer_text)
    if replaced:
        return replaced

    merged = _merge_question_blank_into_passage(passage, question_text)
    if merged:
        return merged

    return None


def _problem_set_folder_id(problem_set: models.ProblemSet):
    return getattr(problem_set, "folder_id", None) or getattr(
        problem_set.passage, "folder_id", None
    )


def _folder_name(db: Session, folder_id):
    if folder_id is None:
        return UNFILED_NAME
    folder = db.query(models.Folder).filter(models.Folder.id == folder_id).first()
    return folder.name if folder else UNFILED_NAME


def _children(db: Session, parent_id: int | None):
    query = db.query(models.Folder)
    if parent_id is None:
        query = query.filter(models.Folder.parent_id.is_(None))
    else:
        query = query.filter(models.Folder.parent_id == parent_id)
    return query.all()


def _sort_key(name: str):
    match = re.search(r"\d+", name or "")
    number = int(match.group()) if match else 9999
    return (number, name or "")


def _count_map(problem_sets):
    counts: dict[int | None, int] = {}
    for ps in problem_sets:
        fid = _problem_set_folder_id(ps)
        counts[fid] = counts.get(fid, 0) + 1
    return counts


def _folder_total_count(db: Session, folder_id: int, counts: dict[int | None, int]):
    total = counts.get(folder_id, 0)
    for child in _children(db, folder_id):
        total += counts.get(child.id, 0)
    return total


def _serialize_problem_set_summary(db: Session, ps: models.ProblemSet):
    folder_id = _problem_set_folder_id(ps)
    return {
        "problem_set_id": ps.id,
        "folder_id": folder_id,
        "folder_name": _folder_name(db, folder_id),
        "name": ps.name,
        "description": ps.description,
        "question_count": len(ps.questions or []),
        "created_at": ps.created_at.isoformat() if ps.created_at else None,
        "is_completed": False,
    }


def _latest_attempts_by_user(attempts):
    def attempt_key(attempt):
        created_at = attempt.created_at.timestamp() if attempt.created_at else 0
        return (created_at, attempt.id or 0)

    latest = {}
    for attempt in attempts:
        existing = latest.get(attempt.user_id)
        if existing is None:
            latest[attempt.user_id] = attempt
            continue

        if attempt_key(attempt) > attempt_key(existing):
            latest[attempt.user_id] = attempt
    return list(latest.values())


def _latest_attempts_by_problem_set(attempts):
    def attempt_key(attempt):
        created_at = attempt.created_at.timestamp() if attempt.created_at else 0
        return (created_at, attempt.id or 0)

    latest = {}
    for attempt in attempts:
        existing = latest.get(attempt.problem_set_id)
        if existing is None or attempt_key(attempt) > attempt_key(existing):
            latest[attempt.problem_set_id] = attempt
    return list(latest.values())


def _type_label(question_type: str):
    return TYPE_LABELS.get((question_type or "").lower(), question_type or "문제")


def _type_sort_key(item):
    q_type = item["type"]
    try:
        return TYPE_ORDER.index(q_type)
    except ValueError:
        return len(TYPE_ORDER)


def _linked_analysis_record(db: Session, problem_set: models.ProblemSet):
    direct_id = getattr(problem_set, "analysis_record_id", None)
    if direct_id:
        record = (
            db.query(models.AnalysisRecord)
            .filter(models.AnalysisRecord.id == direct_id)
            .first()
        )
        if record:
            return record

    if problem_set.passage_id:
        record = (
            db.query(models.AnalysisRecord)
            .filter(models.AnalysisRecord.passage_id == problem_set.passage_id)
            .order_by(
                models.AnalysisRecord.created_at.desc(),
                models.AnalysisRecord.id.desc(),
            )
            .first()
        )
        if record:
            return record

    folder_id = _problem_set_folder_id(problem_set)
    if folder_id is None:
        return None

    passage_source = (
        getattr(problem_set.passage, "source_title", None) if problem_set.passage else None
    )
    records = (
        db.query(models.AnalysisRecord)
        .filter(models.AnalysisRecord.folder_id == folder_id)
        .order_by(models.AnalysisRecord.created_at.desc(), models.AnalysisRecord.id.desc())
        .all()
    )

    if passage_source:
        source_key = passage_source.strip().lower()
        for record in records:
            record_source = (
                getattr(record.passage, "source_title", "") if record.passage else ""
            )
            if record_source.strip().lower() == source_key:
                return record

    return records[0] if records else None


def _problem_set_result_items(db: Session, student_id: int):
    attempts = (
        db.query(models.ExamAttempt)
        .filter(models.ExamAttempt.user_id == student_id)
        .order_by(models.ExamAttempt.created_at.desc(), models.ExamAttempt.id.desc())
        .all()
    )
    latest_attempts = _latest_attempts_by_problem_set(attempts)
    latest_attempts.sort(
        key=lambda attempt: (
            attempt.created_at.timestamp() if attempt.created_at else 0,
            attempt.id or 0,
        ),
        reverse=True,
    )

    results = []
    for attempt in latest_attempts:
        problem_set = (
            db.query(models.ProblemSet)
            .filter(models.ProblemSet.id == attempt.problem_set_id)
            .first()
        )
        if not problem_set:
            continue

        rows = (
            db.query(models.StudentAnswer, models.Question)
            .join(models.Question, models.StudentAnswer.question_id == models.Question.id)
            .filter(models.StudentAnswer.attempt_id == attempt.id)
            .order_by(models.Question.order.asc(), models.Question.id.asc())
            .all()
        )

        total_count = attempt.total_questions or len(rows) or len(problem_set.questions or [])
        correct_count = attempt.correct_count
        if not correct_count and rows:
            correct_count = sum(1 for answer, _question in rows if answer.is_correct)
        score = (
            attempt.score
            if attempt.score is not None
            else int(round((correct_count / total_count) * 100)) if total_count else 0
        )

        weak_type_codes = []
        weak_type_labels = []
        for answer, question in rows:
            if answer.is_correct:
                continue
            q_type = (question.question_type or "unknown").lower()
            if q_type in weak_type_codes:
                continue
            weak_type_codes.append(q_type)
            weak_type_labels.append(_type_label(q_type))

        source = None
        if problem_set.passage:
            source = getattr(problem_set.passage, "source_title", None)
        if not source:
            source = problem_set.description

        results.append({
            "attempt_id": attempt.id,
            "problem_set_id": problem_set.id,
            "problem_set_name": problem_set.name or f"Problem Set #{problem_set.id}",
            "source": source,
            "submitted_at": attempt.created_at.isoformat() if attempt.created_at else None,
            "score": score or 0,
            "correct_count": correct_count or 0,
            "total_count": total_count or 0,
            "weak_types": weak_type_labels,
            "weak_type_codes": weak_type_codes,
        })

    return results


def _score_text(value):
    if value is None:
        return 0
    score = float(value)
    return int(score) if score.is_integer() else round(score, 1)


def _average_score(items):
    scores = [float(item.get("score") or 0) for item in items]
    return _score_text(sum(scores) / len(scores)) if scores else 0


def _top_weak_types(labels):
    counts = {}
    for label in labels:
        if not label:
            continue
        counts[label] = counts.get(label, 0) + 1
    return [
        label
        for label, _count in sorted(
            counts.items(),
            key=lambda item: (-item[1], item[0]),
        )[:3]
    ]


def _mock_weak_types_for_attempt(attempt: models.MockAttempt):
    seen = set()
    weak = []
    answered_question_ids = set()
    for answer in sorted(attempt.answers or [], key=lambda item: item.id):
        answered_question_ids.add(answer.mock_question_id)
        if answer.is_correct:
            continue
        label = MOCK_TYPE_LABELS.get(answer.question_type, answer.question_type)
        if label not in seen:
            seen.add(label)
            weak.append(label)

    questions = (
        sorted(attempt.mock_exam.questions or [], key=lambda item: item.number)
        if attempt.mock_exam
        else []
    )
    for question in questions:
        if question.id in answered_question_ids:
            continue
        label = MOCK_TYPE_LABELS.get(question.question_type, question.question_type)
        if label not in seen:
            seen.add(label)
            weak.append(label)
    return weak


def _mock_exam_result_items(db: Session, student_id: int):
    attempts = (
        db.query(models.MockAttempt)
        .filter(models.MockAttempt.user_id == student_id)
        .order_by(models.MockAttempt.submitted_at.desc(), models.MockAttempt.id.desc())
        .all()
    )

    items = []
    for attempt in attempts:
        exam = attempt.mock_exam
        items.append({
            "id": attempt.id,
            "mock_exam_id": attempt.mock_exam_id,
            "title": exam.title if exam else "삭제된 모의고사",
            "source": (
                f"{exam.grade} · {exam.year}년 {exam.month}월"
                if exam
                else None
            ),
            "submitted_at": attempt.submitted_at.isoformat()
            if attempt.submitted_at
            else None,
            "score": _score_text(attempt.score),
            "correct_count": attempt.correct_count,
            "total_count": attempt.total_questions,
            "weak_types": _mock_weak_types_for_attempt(attempt),
        })
    return items


def _integrated_recommendations(
    problem_average,
    mock_average,
    common_weak_types,
    problem_weak_types,
    mock_weak_types,
):
    recommendations = []
    if common_weak_types:
        target = common_weak_types[0]
        recommendations.append(
            f"내신과 모의고사 모두 {target} 유형에서 약점이 보입니다. "
            f"{target} 유형을 우선 복습해 보세요."
        )
    if problem_average and float(problem_average) < 70:
        recommendations.append(
            "내신 문제세트 점수가 낮은 편입니다. Final Touch 자료를 다시 보고 오답을 복습해 보세요."
        )
    if mock_average and float(mock_average) < 70:
        recommendations.append(
            "모의고사 점수가 낮은 편입니다. 실전 유형 풀이와 시간 관리 연습을 함께 진행해 보세요."
        )
    if not common_weak_types and mock_weak_types:
        recommendations.append(
            f"모의고사에서는 {', '.join(mock_weak_types[:2])} 유형 보완이 필요합니다."
        )
    if not recommendations and problem_weak_types:
        recommendations.append(
            f"내신 대비에서는 {', '.join(problem_weak_types[:2])} 유형을 한 번 더 점검해 보세요."
        )
    if not recommendations:
        recommendations.append(
            "현재 결과가 안정적입니다. 최근 오답을 유지 복습하면서 다음 세트로 확장해 보세요."
        )
    return recommendations


@router.get("/problem-set-results")
def list_problem_set_results(
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_role("student")),
):
    return _problem_set_result_items(db, int(current_user["sub"]))


@router.get("/integrated-report")
def get_integrated_report(
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_role("student")),
):
    student_id = int(current_user["sub"])
    problem_results = _problem_set_result_items(db, student_id)
    mock_results = _mock_exam_result_items(db, student_id)

    problem_weak_types = _top_weak_types(
        label for item in problem_results for label in item.get("weak_types", [])
    )
    mock_weak_types = _top_weak_types(
        label for item in mock_results for label in item.get("weak_types", [])
    )
    common_weak_types = [
        label for label in problem_weak_types if label in set(mock_weak_types)
    ]

    problem_average = _average_score(problem_results)
    mock_average = _average_score(mock_results)
    all_scores = problem_results + mock_results
    overall_average = _average_score(all_scores)

    return {
        "problem_set_attempt_count": len(problem_results),
        "mock_exam_attempt_count": len(mock_results),
        "problem_set_average_score": problem_average,
        "mock_exam_average_score": mock_average,
        "overall_average_score": overall_average,
        "latest_problem_set_score": problem_results[0]["score"]
        if problem_results
        else None,
        "latest_mock_exam_score": mock_results[0]["score"] if mock_results else None,
        "problem_set_weak_types": problem_weak_types,
        "mock_exam_weak_types": mock_weak_types,
        "common_weak_types": common_weak_types,
        "recent_problem_set_results": problem_results[:3],
        "recent_mock_exam_results": mock_results[:3],
        "recommendations": _integrated_recommendations(
            problem_average,
            mock_average,
            common_weak_types,
            problem_weak_types,
            mock_weak_types,
        ),
    }

# =====================================================
# 1️⃣ 학생이 배정받은 시험 목록 조회
# =====================================================
@router.get("/problem_sets")
def list_problem_sets(
    folder_id: int | None = None,
    unfiled: bool = False,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_role("student")),
):
    problem_sets = (
        db.query(models.ProblemSet)
        .order_by(models.ProblemSet.created_at.desc(), models.ProblemSet.id.desc())
        .all()
    )
    if unfiled:
        problem_sets = [ps for ps in problem_sets if _problem_set_folder_id(ps) is None]
    elif folder_id is not None:
        problem_sets = [
            ps for ps in problem_sets if _problem_set_folder_id(ps) == folder_id
        ]

    return [_serialize_problem_set_summary(db, ps) for ps in problem_sets]


@router.get("/problem_sets/folders")
def list_problem_set_folders(
    parent_id: int | None = None,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_role("student")),
):
    problem_sets = db.query(models.ProblemSet).all()
    counts = _count_map(problem_sets)
    folders = _children(db, parent_id)

    items = []
    if parent_id is None and counts.get(None, 0) > 0:
        items.append({
            "folder_id": None,
            "parent_id": None,
            "folder_name": UNFILED_NAME,
            "count": counts[None],
            "has_children": False,
            "is_unfiled": True,
            "is_direct_bucket": False,
        })

    if parent_id is not None and counts.get(parent_id, 0) > 0:
        items.append({
            "folder_id": parent_id,
            "parent_id": parent_id,
            "folder_name": DIRECT_BUCKET_NAME,
            "count": counts[parent_id],
            "has_children": False,
            "is_unfiled": False,
            "is_direct_bucket": True,
        })

    for folder in folders:
        child_count = len(_children(db, folder.id))
        total = _folder_total_count(db, folder.id, counts)
        if total <= 0 and child_count <= 0:
            continue
        items.append({
            "folder_id": folder.id,
            "parent_id": folder.parent_id,
            "folder_name": folder.name,
            "count": total,
            "has_children": child_count > 0,
            "is_unfiled": False,
            "is_direct_bucket": False,
        })

    items.sort(key=lambda item: (item["is_unfiled"], _sort_key(item["folder_name"])))
    return {"items": items}

# =====================================================
# 2️⃣ 학생이 시험 열기
# =====================================================
@router.get("/problem_sets/{problem_set_id}")
def open_problem_set(
    problem_set_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_role("student")),
):
    student_id = int(current_user["sub"])

    # 1) ProblemSet 조회
    problem_set = (
        db.query(models.ProblemSet)
        .filter(models.ProblemSet.id == problem_set_id)
        .first()
    )

    if not problem_set:
        raise HTTPException(status_code=404, detail="ProblemSet not found")

    # 2) 문제 조회
    questions = (
        db.query(models.Question)
        .filter(models.Question.problem_set_id == problem_set.id)
        .order_by(models.Question.order)
        .all()
    )

    print("🔥 TOTAL QUESTIONS:", len(questions))

    # 3) 문제 + 선택지 구성
    questions_list = []

    for q in questions:
        options = (
            db.query(models.Option)
            .filter(models.Option.question_id == q.id)
            .order_by(models.Option.label)
            .all()
        )

        print("🔥 OPTION COUNT:", len(options), "question_id:", q.id)

        blanked_passage = _build_blanked_passage(
            problem_set.passage.content if problem_set.passage else "",
            q,
            options,
        )

        item = {
            "question_id": q.id,
            "question_type": q.question_type,
            "question_text": q.text,
            "order": q.order,
            "answer_index": q.answer_index,
            "options": [
                {
                    "option_id": opt.id,
                    "label": opt.label,
                    "text": opt.text,
                }
                for opt in options
            ],
        }

        if blanked_passage:
            item["blanked_passage"] = blanked_passage

        questions_list.append(item)

    print("🔥 RETURN QUESTIONS COUNT:", len(questions_list))

    # 4) 반환
    return {
        "problem_set_id": problem_set.id,
        "title": problem_set.name,
        "passage_content": problem_set.passage.content if problem_set.passage else None,
        "questions": questions_list,
    }


# =====================================================
# 3️⃣ 문제 정답 체크
# =====================================================
@router.get("/problem_sets/{problem_set_id}/result-summary")
def get_problem_set_result_summary(
    problem_set_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_role("student")),
):
    student_id = int(current_user["sub"])

    problem_set = (
        db.query(models.ProblemSet)
        .filter(models.ProblemSet.id == problem_set_id)
        .first()
    )
    if not problem_set:
        raise HTTPException(status_code=404, detail="ProblemSet not found")

    questions = (
        db.query(models.Question)
        .filter(models.Question.problem_set_id == problem_set_id)
        .order_by(models.Question.order.asc(), models.Question.id.asc())
        .all()
    )

    attempts = (
        db.query(models.ExamAttempt)
        .filter(models.ExamAttempt.problem_set_id == problem_set_id)
        .all()
    )
    latest_attempts = _latest_attempts_by_user(attempts)
    my_attempt = next(
        (attempt for attempt in latest_attempts if attempt.user_id == student_id),
        None,
    )

    if my_attempt is None:
        my_attempt = (
            db.query(models.ExamAttempt)
            .filter(
                models.ExamAttempt.problem_set_id == problem_set_id,
                models.ExamAttempt.user_id == student_id,
            )
            .order_by(models.ExamAttempt.created_at.desc(), models.ExamAttempt.id.desc())
            .first()
        )

    if not my_attempt:
        raise HTTPException(status_code=404, detail="No attempt found")

    answers = (
        db.query(models.StudentAnswer)
        .filter(models.StudentAnswer.attempt_id == my_attempt.id)
        .all()
    )
    answer_map = {answer.question_id: answer for answer in answers}

    total_questions = len(questions) or (my_attempt.total_questions or 0)
    correct_count = sum(1 for answer in answers if answer.is_correct)
    if total_questions == 0:
        total_questions = my_attempt.total_questions or len(answers)
    if correct_count == 0 and my_attempt.correct_count:
        correct_count = my_attempt.correct_count

    my_score = (
        int(round((correct_count / total_questions) * 100))
        if total_questions > 0
        else my_attempt.score or 0
    )

    scores = [attempt.score or 0 for attempt in latest_attempts if attempt.total_questions]
    participant_count = len(scores)
    average_score = int(round(sum(scores) / participant_count)) if scores else my_score
    above_average = my_score - average_score
    better_count = len([score for score in scores if score > my_score])
    rank_percentile = (
        int(round((better_count / participant_count) * 100))
        if participant_count > 0
        else 0
    )

    grouped = {}
    wrong_questions = []
    for question in questions:
        q_type = (question.question_type or "unknown").lower()
        answer = answer_map.get(question.id)
        bucket = grouped.setdefault(
            q_type,
            {
                "type": q_type,
                "label": _type_label(q_type),
                "correct": True,
                "correct_count": 0,
                "total": 0,
            },
        )
        bucket["total"] += 1
        is_correct = bool(answer and answer.is_correct)
        if is_correct:
            bucket["correct_count"] += 1
        else:
            bucket["correct"] = False
            sorted_options = sorted(question.options or [], key=lambda option: option.label)
            selected_index = answer.selected_index if answer else None

            def option_text(index):
                if index is None or index < 0 or index >= len(sorted_options):
                    return None
                return sorted_options[index].text

            wrong_questions.append({
                "question_id": question.id,
                "order": question.order,
                "question_type": q_type,
                "label": _type_label(q_type),
                "question_text": question.text,
                "selected_index": selected_index,
                "correct_index": question.answer_index,
                "selected_text": option_text(selected_index),
                "correct_text": option_text(question.answer_index),
                "explanation": question.explanation,
            })

    type_results = sorted(grouped.values(), key=_type_sort_key)
    weak_types = [item["label"] for item in type_results if not item["correct"]]
    linked_record = _linked_analysis_record(db, problem_set)

    return {
        "problem_set_id": problem_set_id,
        "problem_set_name": problem_set.name,
        "passage_id": problem_set.passage_id,
        "folder_id": _problem_set_folder_id(problem_set),
        "analysis_record_id": linked_record.id if linked_record else None,
        "final_touch_id": linked_record.id if linked_record else None,
        "my_score": my_score,
        "total_questions": total_questions,
        "correct_count": correct_count,
        "incorrect_count": max(total_questions - correct_count, 0),
        "participant_count": participant_count,
        "average_score": average_score,
        "rank_percentile": rank_percentile,
        "above_average": above_average,
        "type_results": type_results,
        "weak_types": weak_types,
        "wrong_questions": wrong_questions,
        "recommendation": (
            f"{', '.join(weak_types[:2])} 유형을 다시 풀어보세요."
            if weak_types
            else "잘했습니다. 같은 단원의 다른 문제세트로 확장해 보세요."
        ),
    }


@router.post("/check-answer")
def check_answer(
    payload: dict,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_role("student")),
):
    student_id = int(current_user["sub"])

    question_id = payload.get("question_id")
    selected_option_id = payload.get("selected_option_id")

    if not question_id or not selected_option_id:
        raise HTTPException(status_code=400, detail="Invalid payload")

    question = db.query(models.Question).filter(
        models.Question.id == question_id
    ).first()

    if not question:
        raise HTTPException(status_code=404, detail="Question not found")

    option = db.query(models.Option).filter(
        models.Option.id == selected_option_id
    ).first()

    if not option:
        raise HTTPException(status_code=404, detail="Option not found")

    # 정답 계산
    correct_index = question.answer_index

    # 옵션 정렬 기준 통일
    sorted_options = sorted(question.options, key=lambda o: o.label)
    selected_index = next(
        (i for i, opt in enumerate(sorted_options) if opt.id == selected_option_id),
        None,
    )

    is_correct = (correct_index == selected_index)

    correct_option = sorted_options[correct_index]
    correct_option_id = correct_option.id

    return {
        "question_id": question_id,
        "correct": is_correct,
        "correct_option_id": correct_option_id,
        "explanation": None,
    }
    
@router.post("/submit-exam")
def submit_exam(
    payload: dict,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_role("student")),
):
    student_id = int(current_user["sub"])

    problem_set_id = payload.get("problem_set_id")
    answers = payload.get("answers")

    if not problem_set_id or not answers:
        raise HTTPException(status_code=400, detail="Invalid payload")

    # 1️⃣ 배정 확인
    assignment = (
        db.query(models.ExamAssignment)
        .filter(
            models.ExamAssignment.user_id == student_id,
            models.ExamAssignment.problem_set_id == problem_set_id,
        )
        .first()
    )

    

    # 👉 재응시 허용하려면 아래 줄은 제거 가능
    # if assignment.is_completed:
    #     raise HTTPException(status_code=400, detail="Exam already submitted")

    total_questions = 0
    correct_count = 0

    for item in answers:
        question_id = item["question_id"]
        selected_option_id = item["selected_option_id"]

        question = db.query(models.Question).filter(
            models.Question.id == question_id
        ).first()

        if not question:
            continue

        total_questions += 1

        # 보기 정렬
        sorted_options = sorted(question.options, key=lambda o: o.label)

        # 선택 index 계산
        selected_index = next(
            (i for i, opt in enumerate(sorted_options) if opt.id == selected_option_id),
            None,
        )

        if selected_index is None:
            continue

        is_correct = (selected_index == question.answer_index)

        if is_correct:
            correct_count += 1

        # 🔥 기존 답안 확인
        existing_answer = (
            db.query(models.StudentAnswer)
            .filter(
                models.StudentAnswer.user_id == student_id,
                models.StudentAnswer.question_id == question_id,
            )
            .first()
        )

        if existing_answer:
            # ✅ UPDATE
            existing_answer.selected_index = selected_index
            existing_answer.is_correct = is_correct
        else:
            # ✅ INSERT
            new_answer = models.StudentAnswer(
                user_id=student_id,
                question_id=question_id,
                selected_index=selected_index,
                is_correct=is_correct,
            )
            db.add(new_answer)

    # 시험 완료 처리 (항상 true 유지)
    assignment.is_completed = True

    score = int((correct_count / total_questions) * 100) if total_questions > 0 else 0

    db.commit()

    return {
        "problem_set_id": problem_set_id,
        "score": score,
        "correct_count": correct_count,
        "total_questions": total_questions,
    }
    
@router.get("/exam-result/{problem_set_id}")
def get_exam_result(
    problem_set_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_role("student")),
):
    student_id = int(current_user["sub"])

    # 1️⃣ 배정 확인
    assignment = (
        db.query(models.ExamAssignment)
        .filter(
            models.ExamAssignment.user_id == student_id,
            models.ExamAssignment.problem_set_id == problem_set_id,
        )
        .first()
    )

    

    # 2️⃣ 해당 문제 세트의 문제들 조회
    questions = (
        db.query(models.Question)
        .filter(models.Question.problem_set_id == problem_set_id)
        .all()
    )

    total_questions = len(questions)

    # 3️⃣ 학생 답안 조회
    student_answers = (
        db.query(models.StudentAnswer)
        .filter(models.StudentAnswer.user_id == student_id)
        .all()
    )

    answer_map = {a.question_id: a for a in student_answers}

    correct_count = 0
    detailed_results = []

    for q in questions:
        student_answer = answer_map.get(q.id)

        if not student_answer:
            continue

        if student_answer.is_correct:
            correct_count += 1

        sorted_options = sorted(q.options, key=lambda o: o.label)

        selected_option = sorted_options[student_answer.selected_index]
        correct_option = sorted_options[q.answer_index]

        detailed_results.append({
            "question_id": q.id,
            "question_text": q.text,
            "selected_option_id": selected_option.id,
            "correct_option_id": correct_option.id,
            "is_correct": student_answer.is_correct
        })

    score = int((correct_count / total_questions) * 100) if total_questions > 0 else 0

    return {
        "problem_set_id": problem_set_id,
        "score": score,
        "correct_count": correct_count,
        "total_questions": total_questions,
        "details": detailed_results
    }
    
    
@router.get("/retry-wrong/{problem_set_id}")
def retry_wrong_questions(
    problem_set_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_role("student")),
):
    student_id = int(current_user["sub"])

    wrong_answers = (
        db.query(models.StudentAnswer)
        .join(models.Question, models.StudentAnswer.question_id == models.Question.id)
        .filter(
            models.StudentAnswer.user_id == student_id,
            models.Question.problem_set_id == problem_set_id,
            models.StudentAnswer.is_correct == False,
        )
        .all()
    )

    print("WRONG ANSWERS FOUND:", wrong_answers)

    if not wrong_answers:
        return {
            "problem_set_id": problem_set_id,
            "message": "No wrong answers 🎉",
            "questions": []
        }

    result_questions = []

    for answer in wrong_answers:
        q = db.query(models.Question).filter(
            models.Question.id == answer.question_id
        ).first()

        sorted_options = sorted(q.options, key=lambda o: o.label)

        result_questions.append({
    "question_id": q.id,
    "question_type": q.question_type,
    "question_text": q.text,
    "options": [
        {"option_id": opt.id, "label": opt.label, "text": opt.text}
        for opt in sorted_options
    ]
})

    return {
        "problem_set_id": problem_set_id,
        "wrong_count": len(result_questions),
        "questions": result_questions
    }
