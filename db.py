# db.py
from __future__ import annotations

from typing import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base, Session

# SQLite 파일 이름
DATABASE_URL = "sqlite:///./app.db"

# SQLite에서만 필요한 옵션
engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False},
)

# 세션 팩토리
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Base: 모든 모델이 상속하는 베이스 클래스
Base = declarative_base()


# FastAPI 의 Depends 에서 쓸 DB 세션 의존성
def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()