# community_schemas.py

from datetime import datetime
from typing import Optional
from pydantic import BaseModel


# ───────── 작성자 요약 ─────────
class AuthorSummary(BaseModel):
    id: int
    nickname: str
    region: Optional[str] = None
    role: str
    level: int

    class Config:
        orm_mode = True


# ───────── 게시글 ─────────
class CommunityPostBase(BaseModel):
    title: str
    content: str
    region: Optional[str] = None
    category: str


class CommunityPostCreate(CommunityPostBase):
    pass   # 🔥 author_id 제거


class CommunityPostOut(CommunityPostBase):
    id: int
    created_at: datetime
    author: Optional[AuthorSummary] = None

    class Config:
        orm_mode = True


# ───────── 댓글 ─────────
class CommentBase(BaseModel):
    content: str


class CommentCreate(CommentBase):
    pass   # 🔥 author_id 제거


class CommentUpdate(BaseModel):   # 🔥 ← 이게 빠져있었음
    content: str



class UserSimple(BaseModel):
    id: int
    nickname: str

    class Config:
        orm_mode = True


class CommentOut(BaseModel):
    id: int
    content: str
    created_at: datetime
    author: UserSimple

    class Config:
        orm_mode = True