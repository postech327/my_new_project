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
)
from sqlalchemy.orm import relationship

from db import Base


# ───────── 공통: 분석 기록 (기존 기능) ─────────
class AnalysisRecord(Base):
    __tablename__ = "analysis_records"

    id = Column(Integer, primary_key=True, index=True)
    kind = Column(String(50), nullable=False)  # "paragraph" / "topic" / "words" / "chat"
    input_text = Column(Text, nullable=True)
    result_text = Column(Text, nullable=True)
    result_json = Column(Text, nullable=True)  # JSON 문자열 저장
    created_at = Column(DateTime, default=datetime.utcnow)


# ───────── 영어 지문 / 문제 세트 ─────────
# --- Passage -------------------------------------------------
class Passage(Base):
    __tablename__ = "passages"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, nullable=False)
    content = Column(Text, nullable=False)
    source = Column(String, nullable=True)
    level = Column(String, nullable=True)
    created_by = Column(String, nullable=True)

    # Question 과의 1:N 관계
    questions = relationship(
        "Question",
        back_populates="passage",
        cascade="all, delete-orphan",
    )

    # ProblemSet 과의 1:N 관계
    problem_sets = relationship(
        "ProblemSet",
        back_populates="passage",
        cascade="all, delete-orphan",
    )


# --- ProblemSet ----------------------------------------------
class ProblemSet(Base):
    __tablename__ = "problem_sets"

    id = Column(Integer, primary_key=True, index=True)
    passage_id = Column(Integer, ForeignKey("passages.id"), nullable=False)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    created_by = Column(String(100), nullable=True)

    passage = relationship("Passage", back_populates="problem_sets")

    questions = relationship(
        "Question",
        back_populates="problem_set",
        cascade="all, delete-orphan",
    )


# --- Question -----------------------------------------------
class Question(Base):
    __tablename__ = "questions"

    id = Column(Integer, primary_key=True, index=True)

    # 예: "topic", "title", "gist", "summary", "cloze", "insertion", "order", ...
    question_type = Column(String, nullable=False)

    # 실제 문항 문장(지금까지 text 컬럼으로 사용하던 것)
    text = Column(String, nullable=False)

    passage_id = Column(Integer, ForeignKey("passages.id"), nullable=False)
    problem_set_id = Column(Integer, ForeignKey("problem_sets.id"), nullable=True)

    passage = relationship("Passage", back_populates="questions")
    problem_set = relationship("ProblemSet", back_populates="questions")

    # 보기들
    options = relationship(
        "Option",
        back_populates="question",
        cascade="all, delete-orphan",
    )


# --- Option --------------------------------------------------
class Option(Base):
    __tablename__ = "options"

    id = Column(Integer, primary_key=True, index=True)
    label = Column(String, nullable=False)        # "A", "B", ...
    text = Column(String, nullable=False)         # 보기 텍스트
    is_correct = Column(Boolean, default=False)

    question_id = Column(Integer, ForeignKey("questions.id"), nullable=False)

    question = relationship(
        "Question",
        back_populates="options",
    )


# ───────── 커뮤니티 게시글 ─────────
class CommunityPost(Base):
    __tablename__ = "community_posts"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(200), nullable=False)
    content = Column(Text, nullable=False)
    nickname = Column(String(50), nullable=False)
    region = Column(String(100), nullable=True)
    category = Column(String(50), nullable=False)  # '질문·답변', '스터디 모집' 등
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    
    # 새로 추가
    author_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    author = relationship("User", back_populates="posts")
    
# 🔹 새로 추가: 댓글 1:N 관계
    comments = relationship(
        "CommunityComment",
        back_populates="post",
        cascade="all, delete-orphan",
    )
    
class CommunityComment(Base):
    __tablename__ = "community_comments"

    id = Column(Integer, primary_key=True, index=True)
    post_id = Column(Integer, ForeignKey("community_posts.id"), nullable=False)
    content = Column(Text, nullable=False)
    nickname = Column(String(100), nullable=False, default="익명")
    created_at = Column(DateTime, default=datetime.utcnow)
    
    author_id = Column(Integer, ForeignKey("users.id"), nullable=True)


    # 🔹 역방향 관계
    post = relationship("CommunityPost", back_populates="comments")
    author = relationship("User", back_populates="comments")
    
class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(255), unique=True, index=True, nullable=False)
    password_hash = Column(String(255), nullable=False)

    nickname = Column(String(50), nullable=False)      # 기본 닉네임
    region = Column(String(100), nullable=True)        # 기본 지역 (서울 · 강남구 등)

    # 'normal' / 'student' / 'teacher'
    role = Column(String(20), default="normal", nullable=False)

    # Lv1/Lv2/Lv3 같은 숫자 레벨
    level = Column(Integer, default=1)

    # 내부 화폐(코인) 잔액
    coins = Column(Integer, default=0)

    created_at = Column(DateTime, default=datetime.utcnow)

    # 커뮤니티 글/댓글 연결 (나중 용도)
    posts = relationship("CommunityPost", back_populates="author")
    comments = relationship("CommunityComment", back_populates="author")