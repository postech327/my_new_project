# models.py
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
)
from sqlalchemy.orm import relationship

from db import Base

# =====================================================
# 공통: 분석 기록
# =====================================================
class AnalysisRecord(Base):
    __tablename__ = "analysis_records"

    id = Column(Integer, primary_key=True, index=True)
    kind = Column(String(50), nullable=False)
    input_text = Column(Text, nullable=True)
    result_text = Column(Text, nullable=True)
    result_json = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


# =====================================================
# 영어 지문 / 분석 허브
# =====================================================
class Passage(Base):
    __tablename__ = "passages"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, nullable=False)
    content = Column(Text, nullable=False)
    created_by = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    questions = relationship(
        "Question",
        back_populates="passage",
        cascade="all, delete-orphan",
    )

    problem_sets = relationship(
        "ProblemSet",
        back_populates="passage",
        cascade="all, delete-orphan",
    )


# =====================================================
# 문제 세트 (시험지)
# =====================================================
class ProblemSet(Base):
    __tablename__ = "problem_sets"

    id = Column(Integer, primary_key=True)
    name = Column(String)
    mode = Column(String, index=True)          # teacher / student
    created_by = Column(String, index=True)

    description = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)

    # ✅ Passage FK (핵심)
    passage_id = Column(
        Integer,
        ForeignKey("passages.id"),
        nullable=True,
    )

    passage = relationship("Passage", back_populates="problem_sets")

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
# Question / Option
# =====================================================
class Question(Base):
    __tablename__ = "questions"

    id = Column(Integer, primary_key=True, index=True)

    question_type = Column(String(50), nullable=False)
    text = Column(Text, nullable=False)
    explanation = Column(Text, nullable=True)
    order = Column(Integer, default=1)

    answer_index = Column(Integer, nullable=True)

    difficulty_score = Column(Float, nullable=True)
    difficulty_level = Column(String(20), nullable=True)

    passage_id = Column(
        Integer,
        ForeignKey("passages.id", ondelete="CASCADE"),
        nullable=False,
    )

    problem_set_id = Column(
        Integer,
        ForeignKey("problem_sets.id", ondelete="CASCADE"),
        nullable=False,
    )

    passage = relationship("Passage", back_populates="questions")
    problem_set = relationship("ProblemSet", back_populates="questions")

    options = relationship(
        "Option",
        back_populates="question",
        cascade="all, delete-orphan",
    )


class Option(Base):
    __tablename__ = "options"

    id = Column(Integer, primary_key=True, index=True)
    label = Column(String(5), nullable=False)   # ①②③④⑤
    text = Column(Text, nullable=False)

    question_id = Column(
        Integer,
        ForeignKey("questions.id", ondelete="CASCADE"),
        nullable=False,
    )

    question = relationship("Question", back_populates="options")

    __table_args__ = (
        UniqueConstraint("question_id", "label", name="uq_question_label"),
    )


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

    created_at = Column(DateTime, default=datetime.utcnow)

    exam_assignments = relationship(
        "ExamAssignment",
        back_populates="user",
        cascade="all, delete-orphan",
    )


# =====================================================
# 학생 답안
# =====================================================
class StudentAnswer(Base):
    __tablename__ = "student_answers"

    id = Column(Integer, primary_key=True, index=True)

    user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    question_id = Column(
        Integer,
        ForeignKey("questions.id", ondelete="CASCADE"),
        nullable=False,
    )

    selected_index = Column(Integer, nullable=False)
    is_correct = Column(Boolean, nullable=False)

    # GPT 오답 해설
    gpt_explanation = Column(Text, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("user_id", "question_id", name="uq_user_question"),
    )


# =====================================================
# 시험지 배정
# =====================================================
class ExamAssignment(Base):
    __tablename__ = "exam_assignments"

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

    assigned_at = Column(DateTime, default=datetime.utcnow)
    is_completed = Column(Boolean, default=False)

    user = relationship("User", back_populates="exam_assignments")
    problem_set = relationship("ProblemSet", back_populates="assignments")

    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "problem_set_id",
            name="uq_user_problemset",
        ),
    )


# =====================================================
# 학습 리포트
# =====================================================
class StudyReport(Base):
    __tablename__ = "study_reports"

    id = Column(Integer, primary_key=True)
    student_id = Column(Integer, ForeignKey("users.id"), index=True)

    error_type = Column(String, index=True)

    total_attempts = Column(Integer, default=0)
    total_incorrect = Column(Integer, default=0)
    accuracy = Column(Float, default=0.0)

    last_attempt_at = Column(DateTime)
    updated_at = Column(DateTime, default=datetime.utcnow)

    student = relationship("User")


# =====================================================
# 개념 사전
# =====================================================
class Concept(Base):
    __tablename__ = "concepts"

    id = Column(Integer, primary_key=True)

    # StudyReport.error_type 과 1:1 매핑
    error_type = Column(String, unique=True, index=True)

    title_ko = Column(String)
    title_en = Column(String)

    description_ko = Column(Text)
    description_en = Column(Text)

    example = Column(Text)