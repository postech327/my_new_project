from __future__ import annotations

from datetime import datetime
from sqlalchemy import (
    Column,
    Integer,
    String,
    Text,
    Boolean,
    DateTime,
    ForeignKey,
    Float,
    UniqueConstraint,
    JSON,
)
from sqlalchemy.orm import relationship

from db import Base


# =====================================================
# User
# =====================================================
class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)

    email = Column(String(255), unique=True, index=True, nullable=False)
    password_hash = Column(String(255), nullable=False)

    nickname = Column(String(50), nullable=False)
    role = Column(String(20), default="student")

    region = Column(String(50), nullable=True)
    level = Column(Integer, default=1)

    points = Column(Integer, default=0)
    coins = Column(Integer, default=0)

    created_at = Column(DateTime, default=datetime.utcnow)

    # 🔥 시험 배정
    exam_assignments = relationship(
        "ExamAssignment",
        back_populates="user",
        cascade="all, delete-orphan",
    )

    # 🔥 클래스 (학생)
    class_memberships = relationship(
        "ClassStudent",
        back_populates="student",
        cascade="all, delete-orphan",
    )

    # 🔥 클래스 (교사)
    teaching_classes = relationship(
        "Class",
        back_populates="teacher",
        cascade="all, delete-orphan",
    )


# =====================================================
# Teacher (선택적 확장)
# =====================================================
class Teacher(Base):
    __tablename__ = "teachers"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    school_name = Column(String)
    subscription_type = Column(String, default="free")
    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User")


# =====================================================
# Classes
# =====================================================
class Class(Base):
    __tablename__ = "classes"

    id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False)

    teacher_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )

    join_code = Column(String(20), unique=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    teacher = relationship("User", back_populates="teaching_classes")

    students = relationship(
        "ClassStudent",
        back_populates="class_",
        cascade="all, delete-orphan",
    )


# =====================================================
# Class Student (중간 테이블)
# =====================================================
class ClassStudent(Base):
    __tablename__ = "class_students"

    id = Column(Integer, primary_key=True)

    class_id = Column(
        Integer,
        ForeignKey("classes.id", ondelete="CASCADE"),
    )

    student_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
    )

    joined_at = Column(DateTime, default=datetime.utcnow)

    class_ = relationship("Class", back_populates="students")
    student = relationship("User", back_populates="class_memberships")

    __table_args__ = (
        UniqueConstraint("class_id", "student_id", name="uq_class_student"),
    )


# =====================================================
# ProblemSet
# =====================================================
class ProblemSet(Base):
    __tablename__ = "problem_sets"

    id = Column(Integer, primary_key=True)
    name = Column(String)
    mode = Column(String, index=True)
    created_by = Column(String, index=True)
    description = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)

    passage_id = Column(Integer, ForeignKey("passages.id"))
    folder_id = Column(Integer, ForeignKey("folders.id"), nullable=True, index=True)

    passage = relationship("Passage", back_populates="problem_sets")
    folder = relationship("Folder")

    questions = relationship(
        "Question",
        back_populates="problem_set",
        cascade="all, delete-orphan",
    )

    assignments = relationship(
        "ExamAssignment",
        back_populates="problem_set",
        cascade="all, delete-orphan",
    )



# =====================================================
# Question
# =====================================================
class Question(Base):
    __tablename__ = "questions"

    id = Column(Integer, primary_key=True, index=True)

    question_type = Column(String(50), nullable=False)
    text = Column(Text, nullable=False)
    explanation = Column(Text)
    order = Column(Integer, default=1)

    answer_index = Column(Integer)

    difficulty_score = Column(Float)
    difficulty_level = Column(String(20))

    passage_id = Column(
        Integer,
        ForeignKey("passages.id", ondelete="CASCADE"),
    )

    problem_set_id = Column(
        Integer,
        ForeignKey("problem_sets.id", ondelete="CASCADE"),
    )

    passage = relationship("Passage", back_populates="questions")
    problem_set = relationship("ProblemSet", back_populates="questions")

    options = relationship(
        "Option",
        back_populates="question",
        cascade="all, delete-orphan",
    )


# =====================================================
# Option
# =====================================================
class Option(Base):
    __tablename__ = "options"

    id = Column(Integer, primary_key=True)
    label = Column(String(5), nullable=False)
    text = Column(Text, nullable=False)

    question_id = Column(
        Integer,
        ForeignKey("questions.id", ondelete="CASCADE"),
    )

    question = relationship("Question", back_populates="options")

    __table_args__ = (
        UniqueConstraint("question_id", "label", name="uq_question_label"),
    )


# =====================================================
# ExamAssignment
# =====================================================
class ExamAssignment(Base):
    __tablename__ = "exam_assignments"

    id = Column(Integer, primary_key=True)

    user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
    )

    problem_set_id = Column(
        Integer,
        ForeignKey("problem_sets.id", ondelete="CASCADE"),
    )

    assigned_at = Column(DateTime, default=datetime.utcnow)
    is_completed = Column(Boolean, default=False)

    user = relationship("User", back_populates="exam_assignments")
    problem_set = relationship("ProblemSet", back_populates="assignments")

    __table_args__ = (
        UniqueConstraint("user_id", "problem_set_id", name="uq_user_problemset"),
    )
    

# =====================================================
# Passages
# =====================================================

class Passage(Base):
    __tablename__ = "passages"

    id = Column(Integer, primary_key=True, index=True)

    # 🔥 teacher는 users.id 기준으로 통일
    teacher_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )

    source_title = Column(String(255), nullable=True)
    content = Column(Text, nullable=False)
    source_type = Column(String(100), nullable=True)

    grade_level = Column(String(50), nullable=True)
    difficulty = Column(String(50), nullable=True)

    folder_id = Column(Integer, nullable=True)
    
    visibility = Column(String(20), default="private")

    created_at = Column(DateTime, default=datetime.utcnow)

    # 🔥 관계 설정
    teacher = relationship("User")

    problem_sets = relationship(
        "ProblemSet",
        back_populates="passage",
        cascade="all, delete-orphan"
    )

    questions = relationship(
        "Question",
        back_populates="passage",
        cascade="all, delete-orphan"
    )
    
# =====================================================
# AnalysisRecord
# =====================================================

class AnalysisRecord(Base):
    __tablename__ = "analysis_records"

    id = Column(Integer, primary_key=True, index=True)

    teacher_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    passage_id = Column(
        Integer,
        ForeignKey("passages.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    passage_bracketed = Column(Text, nullable=False)

    topic_en = Column(String(255), nullable=False)
    topic_ko = Column(String(255), nullable=False)

    title_en = Column(String(255), nullable=False)
    title_ko = Column(String(255), nullable=False)

    gist_en = Column(Text, nullable=False)
    gist_ko = Column(Text, nullable=False)

    outline = Column(JSON, nullable=True)
    sentence_details = Column(JSON, nullable=True)
    folder_id = Column(Integer, ForeignKey("folders.id"), nullable=True, index=True)

    created_at = Column(DateTime, default=datetime.utcnow)

    teacher = relationship("User")
    passage = relationship("Passage")
    folder = relationship("Folder")
    

# =====================================================
# StudentAnswer
# =====================================================

class StudentAnswer(Base):
    __tablename__ = "student_answers"

    id = Column(Integer, primary_key=True, index=True)

    attempt_id = Column(
        Integer,
        ForeignKey("exam_attempts.id", ondelete="CASCADE"),
        nullable=False,
    )

    question_id = Column(
        Integer,
        ForeignKey("questions.id", ondelete="CASCADE"),
        nullable=False,
    )

    selected_index = Column(Integer, nullable=False)
    is_correct = Column(Boolean, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    # 관계
    attempt = relationship("ExamAttempt", back_populates="answers")
    question = relationship("Question")   # 👈 이 줄 추가
    
from datetime import datetime

class ExamAttempt(Base):
    __tablename__ = "exam_attempts"

    id = Column(Integer, primary_key=True, index=True)

    user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )

    problem_set_id = Column(
        Integer,
        ForeignKey("problem_sets.id", ondelete="CASCADE"),
        nullable=False,
    )

    # ✅ 이거 하나만!
    attempt_number = Column(Integer, nullable=False, default=1)

    score = Column(Integer, nullable=False, default=0)
    correct_count = Column(Integer, nullable=False, default=0)
    total_questions = Column(Integer, nullable=False, default=0)

    created_at = Column(DateTime, default=datetime.utcnow)

    answers = relationship("StudentAnswer", back_populates="attempt")


class FinalTouchView(Base):
    __tablename__ = "final_touch_views"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    analysis_record_id = Column(
        Integer,
        ForeignKey("analysis_records.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    viewed_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    user = relationship("User")
    analysis_record = relationship("AnalysisRecord")

    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "analysis_record_id",
            name="uq_final_touch_view_user_record",
        ),
    )


class FinalTouchPracticeResult(Base):
    __tablename__ = "final_touch_practice_results"

    id = Column(Integer, primary_key=True, index=True)
    student_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    final_touch_id = Column(
        Integer,
        ForeignKey("analysis_records.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    passage_id = Column(
        Integer,
        ForeignKey("passages.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    source_label = Column(String(255), nullable=True)
    total_questions = Column(Integer, nullable=False, default=0)
    correct_count = Column(Integer, nullable=False, default=0)
    accuracy_rate = Column(Float, nullable=False, default=0)
    practiced_types = Column(Text, nullable=True)
    wrong_types = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    student = relationship("User")
    final_touch = relationship("AnalysisRecord")
    passage = relationship("Passage")


class AssignedRecommendation(Base):
    __tablename__ = "assigned_recommendations"

    id = Column(Integer, primary_key=True, index=True)
    teacher_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    student_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    recommendation_type = Column(String(50), nullable=False, index=True)
    message = Column(Text, nullable=False)
    priority = Column(String(20), default="medium")
    target_route = Column(String(120), nullable=True)
    book_folder_id = Column(Integer, nullable=True)
    unit_folder_id = Column(Integer, nullable=True)
    problem_set_id = Column(Integer, nullable=True)
    analysis_record_id = Column(Integer, nullable=True)
    status = Column(String(20), default="assigned", index=True)
    assigned_at = Column(DateTime, default=datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)

    teacher = relationship("User", foreign_keys=[teacher_id])
    student = relationship("User", foreign_keys=[student_id])


class LearningAssignment(Base):
    __tablename__ = "learning_assignments"

    id = Column(Integer, primary_key=True, index=True)
    teacher_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    student_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    content_type = Column(String(50), nullable=False, index=True)
    content_id = Column(Integer, nullable=False, index=True)
    title = Column(String(255), nullable=False)
    teacher_message = Column(Text, nullable=True)
    due_at = Column(DateTime, nullable=True, index=True)
    status = Column(String(20), default="assigned", nullable=False, index=True)
    assigned_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, nullable=True)

    teacher = relationship("User", foreign_keys=[teacher_id])
    student = relationship("User", foreign_keys=[student_id])

    __table_args__ = (
        UniqueConstraint(
            "teacher_id",
            "student_id",
            "content_type",
            "content_id",
            name="uq_learning_assignment_teacher_student_content",
        ),
    )


class Workbook(Base):
    __tablename__ = "workbooks"

    id = Column(Integer, primary_key=True, index=True)
    teacher_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    source_label = Column(String(255), nullable=True)
    folder_name = Column(String(255), nullable=True)
    unit_label = Column(String(255), nullable=True)
    final_touch_id = Column(
        Integer,
        ForeignKey("analysis_records.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    status = Column(String(20), default="draft", nullable=False, index=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, nullable=True)

    teacher = relationship("User", foreign_keys=[teacher_id])
    final_touch = relationship("AnalysisRecord")
    questions = relationship(
        "WorkbookQuestion",
        back_populates="workbook",
        cascade="all, delete-orphan",
        order_by="WorkbookQuestion.order_index",
    )
    sections = relationship(
        "WorkbookSection",
        back_populates="workbook",
        cascade="all, delete-orphan",
        order_by="WorkbookSection.sort_order",
    )


class WorkbookSection(Base):
    __tablename__ = "workbook_sections"

    id = Column(Integer, primary_key=True, index=True)
    workbook_id = Column(
        Integer,
        ForeignKey("workbooks.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    title = Column(String(255), nullable=False)
    source_label = Column(String(255), nullable=True)
    unit_label = Column(String(255), nullable=True)
    section_key = Column(String(100), nullable=True, index=True)
    sort_order = Column(Integer, default=0, nullable=False, index=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, nullable=True)

    workbook = relationship("Workbook", back_populates="sections")
    questions = relationship("WorkbookQuestion", back_populates="section")


class WorkbookQuestion(Base):
    __tablename__ = "workbook_questions"

    id = Column(Integer, primary_key=True, index=True)
    workbook_id = Column(
        Integer,
        ForeignKey("workbooks.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    section_id = Column(
        Integer,
        ForeignKey("workbook_sections.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    question_type = Column(String(50), nullable=False, index=True)
    order_index = Column(Integer, nullable=False, default=1, index=True)
    prompt = Column(Text, nullable=False)
    passage_text = Column(Text, nullable=True)
    choices_json = Column(JSON, nullable=True)
    answer_json = Column(JSON, nullable=False)
    explanation = Column(Text, nullable=True)
    points = Column(Integer, default=1, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, nullable=True)

    workbook = relationship("Workbook", back_populates="questions")
    section = relationship("WorkbookSection", back_populates="questions")


class WorkbookAttempt(Base):
    __tablename__ = "workbook_attempts"

    id = Column(Integer, primary_key=True, index=True)
    assignment_id = Column(
        Integer,
        ForeignKey("learning_assignments.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    workbook_id = Column(
        Integer,
        ForeignKey("workbooks.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    student_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    teacher_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    attempt_no = Column(Integer, nullable=False, default=1)
    status = Column(String(20), default="submitted", nullable=False, index=True)
    total_questions = Column(Integer, default=0, nullable=False)
    correct_count = Column(Integer, default=0, nullable=False)
    wrong_count = Column(Integer, default=0, nullable=False)
    score_percent = Column(Float, default=0, nullable=False)
    started_at = Column(DateTime, nullable=True)
    submitted_at = Column(DateTime, nullable=True, index=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    assignment = relationship("LearningAssignment")
    workbook = relationship("Workbook")
    student = relationship("User", foreign_keys=[student_id])
    teacher = relationship("User", foreign_keys=[teacher_id])
    answers = relationship(
        "WorkbookAttemptAnswer",
        cascade="all, delete-orphan",
        back_populates="attempt",
    )


class WorkbookAttemptAnswer(Base):
    __tablename__ = "workbook_attempt_answers"

    id = Column(Integer, primary_key=True, index=True)
    attempt_id = Column(
        Integer,
        ForeignKey("workbook_attempts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    question_id = Column(
        Integer,
        ForeignKey("workbook_questions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    question_type = Column(String(50), nullable=False)
    item_number = Column(Integer, nullable=True)
    student_answer = Column(Text, nullable=True)
    correct_answer = Column(Text, nullable=True)
    is_correct = Column(Boolean, nullable=True)
    explanation = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    attempt = relationship("WorkbookAttempt", back_populates="answers")
    question = relationship("WorkbookQuestion")


class MockExam(Base):
    __tablename__ = "mock_exams"

    id = Column(Integer, primary_key=True, index=True)
    grade = Column(String(20), nullable=False, index=True)
    year = Column(Integer, nullable=False, index=True)
    month = Column(Integer, nullable=False, index=True)
    title = Column(String(255), nullable=False)
    total_questions = Column(Integer, nullable=False, default=20)
    total_score = Column(Integer, nullable=False, default=100)
    has_listening = Column(Boolean, nullable=False, default=False)
    created_by = Column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    created_at = Column(DateTime, default=datetime.utcnow)

    creator = relationship("User")
    questions = relationship(
        "MockQuestion",
        back_populates="mock_exam",
        cascade="all, delete-orphan",
        order_by="MockQuestion.number",
    )
    attempts = relationship(
        "MockAttempt",
        back_populates="mock_exam",
        cascade="all, delete-orphan",
    )


class MockQuestion(Base):
    __tablename__ = "mock_questions"

    id = Column(Integer, primary_key=True, index=True)
    mock_exam_id = Column(
        Integer,
        ForeignKey("mock_exams.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    number = Column(Integer, nullable=False)
    question_type = Column(String(50), nullable=False, index=True)
    source = Column(String(255), nullable=True)
    passage = Column(Text, nullable=True)
    question_text = Column(Text, nullable=False)
    options = Column(JSON, nullable=False)
    answer_index = Column(Integer, nullable=False)
    explanation = Column(Text, nullable=True)
    passage_group_id = Column(String(80), nullable=True, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    mock_exam = relationship("MockExam", back_populates="questions")
    answers = relationship(
        "MockAnswer",
        back_populates="mock_question",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        UniqueConstraint(
            "mock_exam_id",
            "number",
            name="uq_mock_question_exam_number",
        ),
    )


class MockAttempt(Base):
    __tablename__ = "mock_attempts"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    mock_exam_id = Column(
        Integer,
        ForeignKey("mock_exams.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    correct_count = Column(Integer, nullable=False, default=0)
    total_questions = Column(Integer, nullable=False, default=20)
    score = Column(Float, nullable=False, default=0)
    started_at = Column(DateTime, default=datetime.utcnow)
    submitted_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User")
    mock_exam = relationship("MockExam", back_populates="attempts")
    answers = relationship(
        "MockAnswer",
        back_populates="attempt",
        cascade="all, delete-orphan",
    )


class MockAnswer(Base):
    __tablename__ = "mock_answers"

    id = Column(Integer, primary_key=True, index=True)
    attempt_id = Column(
        Integer,
        ForeignKey("mock_attempts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    mock_question_id = Column(
        Integer,
        ForeignKey("mock_questions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    selected_index = Column(Integer, nullable=False)
    is_correct = Column(Boolean, nullable=False)
    question_type = Column(String(50), nullable=False, index=True)

    attempt = relationship("MockAttempt", back_populates="answers")
    mock_question = relationship("MockQuestion", back_populates="answers")

class Source(Base):
    __tablename__ = "sources"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, index=True)
    

from sqlalchemy import Column, Integer, String, DateTime, Boolean
from datetime import datetime

class Folder(Base):
    __tablename__ = "folders"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    parent_id = Column(Integer, ForeignKey("folders.id"), nullable=True, index=True)

    owner_id = Column(Integer, nullable=False)  # teacher1
    is_public = Column(Boolean, default=True)   # 학생도 볼 수 있게

    created_at = Column(DateTime, default=datetime.utcnow)
    parent = relationship("Folder", remote_side=[id], backref="children")
