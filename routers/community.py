# routers/community.py  (또는 app/routers/community.py)

from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from pydantic import BaseModel

from db import get_db          # ✅ 절대 import
import models                  # ✅ models 모듈 전체 import

router = APIRouter(prefix="/community", tags=["community"])

# ───────────────────── Pydantic Schemas ─────────────────────

class AuthorBrief(BaseModel):
    """작성자 요약 정보 (프로필 미니버전)"""
    id: int
    nickname: str
    role: str
    level: int

    class Config:
        orm_mode = True


class CommunityPostBase(BaseModel):
    title: str
    content: str
    nickname: str
    region: Optional[str] = None
    category: str


class CommunityPostCreate(CommunityPostBase):
    # ⭐️ Flutter 에서 보내는 author_id
    author_id: int


class CommunityPostOut(CommunityPostBase):
    id: int
    created_at: datetime

    # ⭐️ 작성자 프로필 요약
    author: Optional[AuthorBrief] = None

    class Config:
        orm_mode = True


# ───────────────────── Endpoints ─────────────────────

@router.post("/posts", response_model=CommunityPostOut)
def create_post(
    payload: CommunityPostCreate,
    db: Session = Depends(get_db),
):
    """
    새 글 작성
    - payload.author_id 를 사용해 User 테이블과 연결
    - nickname/region 은 일단 payload 기준으로 저장
    """

    # 1) author_id 검증
    user = db.query(models.User).get(payload.author_id)
    if not user:
        raise HTTPException(status_code=400, detail="invalid author_id")

    # 2) CommunityPost 생성
    post = models.CommunityPost(
        title=payload.title.strip(),
        content=payload.content.strip(),
        nickname=(payload.nickname or user.nickname).strip(),
        region=(payload.region or user.region or "").strip(),
        category=payload.category.strip(),
        author_id=user.id,
    )

    db.add(post)
    db.commit()
    db.refresh(post)

    # post.author 관계에 user가 연결됨 → AuthorBrief 로 자동 변환
    return post


@router.get("/posts", response_model=List[CommunityPostOut])
def list_posts(
    category: Optional[str] = Query(None, description="카테고리 필터"),
    q: Optional[str] = Query(None, description="제목/내용/닉네임/지역 검색어"),
    db: Session = Depends(get_db),
):
    """
    - category: '질문·답변', '스터디 모집' 등 (없으면 전체)
    - q: 검색어 (없으면 전체)
    """
    query = db.query(models.CommunityPost)

    if category and category != "전체":
        query = query.filter(models.CommunityPost.category == category)

    if q:
        wildcard = f"%{q}%"
        query = query.filter(
            models.CommunityPost.title.ilike(wildcard)
            | models.CommunityPost.content.ilike(wildcard)
            | models.CommunityPost.nickname.ilike(wildcard)
            | models.CommunityPost.region.ilike(wildcard)
        )

    query = query.order_by(models.CommunityPost.created_at.desc())

    posts = query.all()
    # orm_mode + 관계(author) 덕분에 AuthorBrief 로 자동 직렬화
    return posts


@router.get("/posts/{post_id}", response_model=CommunityPostOut)
def get_post(
    post_id: int,
    db: Session = Depends(get_db),
):
    post = db.query(models.CommunityPost).get(post_id)
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")
    return post