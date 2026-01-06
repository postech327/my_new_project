# routers/users.py
from __future__ import annotations

# ───────── import ─────────
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from db import get_db
import models
from user_schemas import UserProfile, CoinChangeRequest, CoinLogOut


router = APIRouter(prefix="/users", tags=["users"])


# ─────────────────────
# 공통: 레벨 라벨 만들기
# ─────────────────────
def _make_level_label(user: models.User) -> str:
    # role 값: "normal" / "student" / "teacher"
    role_label = {
        "normal": "일반회원",
        "student": "학생회원",
        "teacher": "선생님회원",
    }.get(user.role, "회원")

    return f"Lv{user.level} {role_label}"


# ─────────────────────
# 1) 유저 프로필 조회
#    GET /users/{user_id}
# ─────────────────────
@router.get("/{user_id}", response_model=UserProfile)
def get_user_profile(user_id: int, db: Session = Depends(get_db)):
    user = db.query(models.User).get(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    return UserProfile(
        id=user.id,
        email=user.email,
        nickname=user.nickname,
        region=user.region,
        role=user.role,
        level=user.level,
        coins=user.coins,
        created_at=user.created_at,
        level_label=_make_level_label(user),
    )


# ─────────────────────
# 2) 코인 얻기(적립)
#    POST /users/{user_id}/coins/earn
#    body: { "amount": 10, "reason": "보상" }
# ─────────────────────
@router.post("/{user_id}/coins/earn", response_model=UserProfile)
def earn_coins(
    user_id: int,
    payload: CoinChangeRequest,
    db: Session = Depends(get_db),
):
    if payload.amount <= 0:
        raise HTTPException(status_code=400, detail="amount must be positive")

    user = db.query(models.User).get(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # 코인 증가
    user.coins += payload.amount

    # 로그 기록
    log = models.UserCoinLog(
        user_id=user.id,
        action="earn",
        amount=payload.amount,
        reason=payload.reason,
    )
    db.add(log)
    db.commit()
    db.refresh(user)

    return UserProfile(
        id=user.id,
        email=user.email,
        nickname=user.nickname,
        region=user.region,
        role=user.role,
        level=user.level,
        coins=user.coins,
        created_at=user.created_at,
        level_label=_make_level_label(user),
    )


# ─────────────────────
# 3) 코인 로그 조회
#    GET /users/{user_id}/coins/logs
# ─────────────────────
@router.get("/{user_id}/coins/logs", response_model=list[CoinLogOut])
def list_coin_logs(user_id: int, db: Session = Depends(get_db)):
    logs = (
        db.query(models.UserCoinLog)
        .filter(models.UserCoinLog.user_id == user_id)
        .order_by(models.UserCoinLog.created_at.desc())
        .all()
    )
    return logs