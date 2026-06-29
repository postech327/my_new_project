from sqlalchemy.orm import Session
from typing import List, Dict, Any
from datetime import datetime

import models
from schemas.student_exam import StudentAnswerIn


# =====================================================
# 1️⃣ 시험 최초 제출 (🔥 score 포함 최종 버전)
# =====================================================
def submit_student_exam(
    *,
    db: Session,
    user_id: int,
    problem_set_id: int,
    answers: List[StudentAnswerIn],
) -> Dict[str, Any]:

    # 1️⃣ attempt_number 계산
    previous_attempts = (
        db.query(models.ExamAttempt)
        .filter(
            models.ExamAttempt.user_id == user_id,
            models.ExamAttempt.problem_set_id == problem_set_id,
        )
        .count()
    )

    attempt = models.ExamAttempt(
        user_id=user_id,
        problem_set_id=problem_set_id,
        attempt_number=previous_attempts + 1,
        score=0,
        correct_count=0,
        total_questions=0,
    )

    db.add(attempt)
    db.flush()  # attempt.id 확보

    results: List[Dict[str, Any]] = []
    correct_count = 0

    for ans in answers:

        question = (
            db.query(models.Question)
            .filter(
                models.Question.id == ans.question_id,
                models.Question.problem_set_id == problem_set_id,
            )
            .first()
        )

        if not question:
            raise ValueError(
                f"Question {ans.question_id} not found in problem_set {problem_set_id}"
            )

        is_correct = ans.selected_index == question.answer_index

        if is_correct:
            correct_count += 1

        student_answer = models.StudentAnswer(
            attempt_id=attempt.id,
            question_id=question.id,
            selected_index=ans.selected_index,
            is_correct=is_correct,
        )

        db.add(student_answer)

        results.append(
            {
                "question_id": question.id,
                "selected_index": ans.selected_index,
                "correct_index": question.answer_index,
                "is_correct": is_correct,
            }
        )

    total = len(results)
    score = round((correct_count / total) * 100, 2) if total else 0.0

    # 2️⃣ attempt 정보 업데이트
    attempt.score = score
    attempt.correct_count = correct_count
    attempt.total_questions = total

    db.commit()

    return {
        "total_questions": total,
        "correct_count": correct_count,
        "wrong_count": total - correct_count,
        "accuracy": score,
        "score": score,
        "results": results,
    }


# =====================================================
# 2️⃣ 오답 재도전 문제 제공
# =====================================================
def get_retry_questions(
    *,
    db: Session,
    problem_set_id: int,
    user_id: int,
    limit: int = 5,
):

    # 1️⃣ 가장 최근 attempt 찾기
    last_attempt = (
        db.query(models.ExamAttempt)
        .filter(
            models.ExamAttempt.user_id == user_id,
            models.ExamAttempt.problem_set_id == problem_set_id,
        )
        .order_by(models.ExamAttempt.attempt_number.desc())
        .first()
    )

    if not last_attempt:
        raise ValueError("이전에 응시한 시험이 없습니다.")

    # 2️⃣ 해당 attempt에서 오답만 조회
    wrong_answers = (
        db.query(models.StudentAnswer)
        .filter(
            models.StudentAnswer.attempt_id == last_attempt.id,
            models.StudentAnswer.is_correct == False,
        )
        .limit(limit)
        .all()
    )

    if not wrong_answers:
        raise ValueError("재도전할 오답이 없습니다.")

    question_ids = [wa.question_id for wa in wrong_answers]

    # 3️⃣ Question 조회
    questions = (
        db.query(models.Question)
        .filter(models.Question.id.in_(question_ids))
        .all()
    )

    return {
        "count": len(questions),
        "questions": [
            {
                "question_id": q.id,
                "order": q.order,
                "text": q.text,
                "question_type": q.question_type,
                "options": [
                    {
                        "id": opt.id,
                        "label": opt.label,
                        "text": opt.text,
                    }
                    for opt in q.options
                ],
            }
            for q in questions
        ],
    }


# =====================================================
# 3️⃣ 오답 재도전 제출
# =====================================================
def submit_retry_answers(
    *,
    db: Session,
    problem_set_id: int,
    user_id: int,
    answers: List[StudentAnswerIn],
) -> Dict[str, Any]:

    if not answers:
        raise ValueError("제출할 답안이 없습니다.")

    # 1️⃣ attempt_number 계산
    previous_attempts = (
        db.query(models.ExamAttempt)
        .filter(
            models.ExamAttempt.user_id == user_id,
            models.ExamAttempt.problem_set_id == problem_set_id,
        )
        .count()
    )

    attempt = models.ExamAttempt(
        user_id=user_id,
        problem_set_id=problem_set_id,
        attempt_number=previous_attempts + 1,
        score=0,
        correct_count=0,
        total_questions=0,
    )

    db.add(attempt)
    db.flush()  # attempt.id 확보

    correct = 0
    results = []

    for ans in answers:

        question = (
            db.query(models.Question)
            .filter(
                models.Question.id == ans.question_id,
                models.Question.problem_set_id == problem_set_id,
            )
            .first()
        )

        if not question:
            raise ValueError(
                f"Question {ans.question_id} not found in problem_set {problem_set_id}"
            )

        is_correct = ans.selected_index == question.answer_index

        if is_correct:
            correct += 1

        student_answer = models.StudentAnswer(
            attempt_id=attempt.id,
            question_id=question.id,
            selected_index=ans.selected_index,
            is_correct=is_correct,
        )

        db.add(student_answer)

        results.append({
            "question_id": question.id,
            "selected_index": ans.selected_index,
            "correct_index": question.answer_index,
            "is_correct": is_correct,
        })

    total = len(answers)
    score = round((correct / total) * 100, 2) if total else 0.0

    # 2️⃣ attempt 정보 업데이트
    attempt.score = score
    attempt.correct_count = correct
    attempt.total_questions = total

    db.commit()

    return {
        "total": total,
        "correct": correct,
        "accuracy": score,
        "score": score,
        "results": results,
    }


# =====================================================
# 4️⃣ 시험 결과 요약
# =====================================================
def get_exam_summary(
    db: Session,
    problem_set_id: int,
    user_id: int,
):

    answers = (
        db.query(models.StudentAnswer, models.Question)
        .join(models.Question, models.StudentAnswer.question_id == models.Question.id)
        .filter(
            models.StudentAnswer.user_id == user_id,
            models.Question.problem_set_id == problem_set_id,
        )
        .all()
    )

    total = len(answers)
    correct = sum(1 for a, _ in answers if a.is_correct)
    wrong = total - correct
    score = int((correct / total) * 100) if total else 0

    by_type: Dict[str, Dict[str, int]] = {}

    for a, q in answers:
        qtype = q.question_type
        if qtype not in by_type:
            by_type[qtype] = {"total": 0, "wrong": 0}

        by_type[qtype]["total"] += 1
        if not a.is_correct:
            by_type[qtype]["wrong"] += 1

    return {
        "problem_set_id": problem_set_id,
        "user_id": user_id,
        "total_questions": total,
        "correct": correct,
        "wrong": wrong,
        "accuracy": score,
        "score": score,  # 🔥 통일
        "by_type": by_type,
    }