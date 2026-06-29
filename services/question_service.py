from sqlalchemy.orm import Session
import models


def save_questions(
    *,
    db: Session,
    problem_set: models.ProblemSet,
    questions: list[dict],
):
    saved = []

    for q in questions:
        question = models.Question(
            problem_set_id=problem_set.id,
            q_type=q["type"],
            question=q["question"],
            answer=q["answer"],
        )
        db.add(question)
        saved.append(question)

    db.commit()

    return saved