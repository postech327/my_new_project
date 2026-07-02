import unittest

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import models
from db import Base
from routers.vocabulary import (
    VocabularyAnswerIn,
    VocabularyAttemptIn,
    VocabularyAssignIn,
    VocabularyBulkItemsIn,
    VocabularyItemIn,
    VocabularySetCreate,
    assign_vocabulary_set,
    bulk_save_vocabulary_items,
    create_teacher_vocabulary_set,
    get_student_vocabulary_set,
    list_student_vocabulary_sets,
    submit_vocabulary_attempt,
)


class VocabularyFlowTest(unittest.TestCase):
    def test_create_publish_and_score(self):
        engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
        )
        Base.metadata.create_all(bind=engine)
        db = sessionmaker(bind=engine)()
        teacher = {"sub": "101"}
        student = {"sub": "202"}
        db.add_all(
            [
                models.User(
                    id=101,
                    email="teacher@test.local",
                    password_hash="test",
                    nickname="teacher",
                    role="teacher",
                ),
                models.User(
                    id=202,
                    email="student@test.local",
                    password_hash="test",
                    nickname="student",
                    role="student",
                ),
                models.User(
                    id=303,
                    email="student3@test.local",
                    password_hash="test",
                    nickname="student3",
                    role="student",
                ),
            ]
        )
        db.commit()

        created = create_teacher_vocabulary_set(
            VocabularySetCreate(title="Test words", status="published"),
            db,
            teacher,
        )
        saved = bulk_save_vocabulary_items(
            created["set_id"],
            VocabularyBulkItemsIn(
                replace=True,
                items=[
                    VocabularyItemIn(word="goal", meaning_ko="목표"),
                    VocabularyItemIn(word="recently", meaning_ko="최근에"),
                ],
            ),
            db,
            teacher,
        )

        self.assertEqual(saved["item_count"], 2)
        assigned = assign_vocabulary_set(
            created["set_id"],
            VocabularyAssignIn(student_ids=[202, 202]),
            db,
            teacher,
        )
        self.assertEqual(assigned["assigned_count"], 1)
        duplicate = assign_vocabulary_set(
            created["set_id"],
            VocabularyAssignIn(student_ids=[202]),
            db,
            teacher,
        )
        self.assertEqual(duplicate["skipped_count"], 1)
        self.assertEqual(
            len(list_student_vocabulary_sets(db, student)["items"]),
            1,
        )
        self.assertEqual(
            len(list_student_vocabulary_sets(db, {"sub": "303"})["items"]),
            0,
        )
        detail = get_student_vocabulary_set(created["set_id"], db, student)
        attempt = submit_vocabulary_attempt(
            VocabularyAttemptIn(
                set_id=created["set_id"],
                answers=[
                    VocabularyAnswerIn(
                        item_id=detail["items"][0]["item_id"],
                        student_answer="목표",
                    ),
                    VocabularyAnswerIn(
                        item_id=detail["items"][1]["item_id"],
                        student_answer="오답",
                    ),
                ],
            ),
            db,
            student,
        )

        self.assertEqual(attempt["total_count"], 2)
        self.assertEqual(attempt["correct_count"], 1)
        self.assertEqual(attempt["score"], 50.0)
        db.close()
        engine.dispose()


if __name__ == "__main__":
    unittest.main()
