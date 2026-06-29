# routers/community.py

from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session, joinedload

import models
from utils.points import add_points
from db import get_db
from utils.auth_jwt import get_current_user

# 🔥 community_schemas만 사용 (schemas.py 사용하지 않음)
from community_schemas import (
    CommunityPostBase,
    CommunityPostCreate,
    CommunityPostOut,
    CommentCreate,
    CommentOut,
    CommentUpdate,
)

router = APIRouter(prefix="/community", tags=["community"])


# ─────────────────────
# 🔹 Post Endpoints
# ─────────────────────

@router.post("/posts", response_model=CommunityPostOut)
def create_post(
    payload: CommunityPostCreate,
    db: Session = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    post = models.CommunityPost(
        title=payload.title.strip(),
        content=payload.content.strip(),
        nickname=user["username"],
        region=(payload.region or "").strip(),
        category=payload.category.strip(),
        author_id=int(user["sub"]),
    )

    db.add(post)
    db.commit()
    db.refresh(post)

    # 🔥 게시글 작성 +10점
    current_user = db.query(models.User).get(int(user["sub"]))
    if current_user:
        add_points(db, current_user, 10)

    return post


@router.get("/posts", response_model=List[CommunityPostOut])
def get_posts(
    db: Session = Depends(get_db),
    category: Optional[str] = Query(None),
    region: Optional[str] = Query(None),
):
    query = db.query(models.CommunityPost)

    if category:
        query = query.filter(models.CommunityPost.category == category)

    if region:
        query = query.filter(models.CommunityPost.region == region)

    posts = (
        query
        .order_by(models.CommunityPost.created_at.desc())
        .all()
    )

    return posts


@router.put("/posts/{post_id}")
def update_post(
    post_id: int,
    payload: CommunityPostBase,
    db: Session = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    post = db.query(models.CommunityPost).filter(
        models.CommunityPost.id == post_id
    ).first()

    if not post:
        raise HTTPException(status_code=404, detail="Post not found")

    if post.author_id != int(user["sub"]) and user["role"] != "admin":
        raise HTTPException(status_code=403, detail="Permission denied")

    post.title = payload.title
    post.content = payload.content
    post.category = payload.category
    post.region = payload.region

    db.commit()
    db.refresh(post)

    return {"message": "Post updated successfully"}


@router.delete("/posts/{post_id}")
def delete_post(
    post_id: int,
    db: Session = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    post = db.query(models.CommunityPost).filter(
        models.CommunityPost.id == post_id
    ).first()

    if not post:
        raise HTTPException(status_code=404, detail="Post not found")

    if post.author_id != int(user["sub"]) and user["role"] != "admin":
        raise HTTPException(status_code=403, detail="Permission denied")

    db.delete(post)
    db.commit()

    return {"message": "Post deleted successfully"}


# ─────────────────────
# 🔹 Comment Endpoints
# ─────────────────────

@router.post("/posts/{post_id}/comments", response_model=CommentOut)
def create_comment(
    post_id: int,
    payload: CommentCreate,
    db: Session = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    post = db.query(models.CommunityPost).get(post_id)
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")

    comment = models.Comment(
        content=payload.content.strip(),
        post_id=post_id,
        author_id=int(user["sub"]),
    )

    db.add(comment)
    db.commit()
    db.refresh(comment)

    # 🔥 댓글 작성 +3점
    current_user = db.query(models.User).get(int(user["sub"]))
    if current_user:
        add_points(db, current_user, 3)

    return comment


@router.get("/posts/{post_id}/comments", response_model=List[CommentOut])
def get_comments(post_id: int, db: Session = Depends(get_db)):
    comments = (
        db.query(models.Comment)
        .options(joinedload(models.Comment.author))  # 🔥 author 포함
        .filter(models.Comment.post_id == post_id)
        .order_by(models.Comment.created_at.asc())
        .all()
    )
    return comments


@router.put("/comments/{comment_id}")
def update_comment(
    comment_id: int,
    payload: CommentUpdate,
    db: Session = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    comment = db.query(models.Comment).filter(
        models.Comment.id == comment_id
    ).first()

    if not comment:
        raise HTTPException(status_code=404, detail="Comment not found")

    if comment.author_id != int(user["sub"]) and user["role"] != "admin":
        raise HTTPException(status_code=403, detail="Permission denied")

    comment.content = payload.content

    db.commit()
    db.refresh(comment)

    return {"message": "Comment updated successfully"}


@router.delete("/comments/{comment_id}")
def delete_comment(
    comment_id: int,
    db: Session = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    comment = db.query(models.Comment).filter(
        models.Comment.id == comment_id
    ).first()

    if not comment:
        raise HTTPException(status_code=404, detail="Comment not found")

    if comment.author_id != int(user["sub"]) and user["role"] != "admin":
        raise HTTPException(status_code=403, detail="Permission denied")

    db.delete(comment)
    db.commit()

    return {"message": "Comment deleted successfully"}


# ─────────────────────
# 🔹 Like Endpoints
# ─────────────────────

@router.post("/posts/{post_id}/like")
def toggle_like(
    post_id: int,
    db: Session = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    post = db.query(models.CommunityPost).get(post_id)
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")

    user_id = int(user["sub"])

    existing_like = db.query(models.PostLike).filter(
        models.PostLike.post_id == post_id,
        models.PostLike.user_id == user_id
    ).first()

    # 좋아요 취소
    if existing_like:
        db.delete(existing_like)
        db.commit()
        return {"liked": False}

    # 좋아요 생성
    new_like = models.PostLike(
        post_id=post_id,
        user_id=user_id
    )

    db.add(new_like)
    db.commit()

    # 좋아요 누른 사람 +1점
    liker = db.query(models.User).get(user_id)
    if liker:
        add_points(db, liker, 1)

    # 좋아요 받은 글 작성자 +2점
    author = db.query(models.User).get(post.author_id)
    if author:
        add_points(db, author, 2)

    return {"liked": True}


@router.get("/posts/{post_id}/like-count")
def get_like_count(post_id: int, db: Session = Depends(get_db)):
    count = db.query(models.PostLike).filter_by(
        post_id=post_id
    ).count()

    return {"count": count}


@router.get("/posts/{post_id}/like-status")
def get_like_status(
    post_id: int,
    db: Session = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    user_id = int(user["sub"])

    like = db.query(models.PostLike).filter_by(
        post_id=post_id,
        user_id=user_id
    ).first()

    return {"liked": like is not None}


# ─────────────────────
# 🔹 My Posts
# ─────────────────────

@router.get("/my-posts", response_model=List[CommunityPostOut])
def get_my_posts(
    db: Session = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    user_id = int(user["sub"])

    posts = (
        db.query(models.CommunityPost)
        .filter(models.CommunityPost.author_id == user_id)
        .order_by(models.CommunityPost.created_at.desc())
        .all()
    )

    return posts