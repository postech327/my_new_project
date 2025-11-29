# community_schemas.py
from datetime import datetime
from typing import Optional, List

from pydantic import BaseModel


# ───────── 작성자 프로필 요약 ─────────
class AuthorSummary(BaseModel):
    id: int
    nickname: str
    region: Optional[str] = None
    role: str
    level: int

    class Config:
        orm_mode = True


# ───────── 게시글 스키마 ─────────
class CommunityPostBase(BaseModel):
    title: str
    content: str
    nickname: str
    region: Optional[str] = None
    category: str           # '질문·답변', '스터디 모집' 등


class CommunityPostCreate(CommunityPostBase):
    # 로그인 연동 후: 실제 작성자 User.id 를 넣어줄 수 있도록 옵션으로 둠
    author_id: Optional[int] = None


class CommunityPostOut(CommunityPostBase):
    id: int
    created_at: datetime

    # 🔥 작성자 요약 프로필 (User 테이블과 연결된 경우에만 값이 들어옴)
    author: Optional[AuthorSummary] = None

    class Config:
        orm_mode = True


# ───────── 댓글 스키마 ─────────
class CommentBase(BaseModel):
    content: str
    nickname: str


class CommentCreate(CommentBase):
    author_id: Optional[int] = None  # 로그인 연동용 (없으면 익명)


class CommentOut(CommentBase):
    id: int
    post_id: int
    created_at: datetime

    author: Optional[AuthorSummary] = None

    class Config:
        orm_mode = True