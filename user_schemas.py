# user_schemas.py
from datetime import datetime
from pydantic import BaseModel


# ─────────────────────────────
# 1. 프로필 조회용 스키마
# ─────────────────────────────
class UserProfile(BaseModel):
    id: int
    email: str
    nickname: str
    region: str | None = None
    role: str          # "normal" / "student" / "teacher"
    level: int         # 1, 2, 3 ...
    coins: int         # 보유 코인
    created_at: datetime
    level_label: str   # "Lv3 선생님회원" 같은 문구

    class Config:
        orm_mode = True


# ─────────────────────────────
# 2. 코인 증감 요청 바디
# ─────────────────────────────
class CoinChangeRequest(BaseModel):
    amount: int                # +10, -5 등
    reason: str | None = None  # "퀴즈 정답 보상" 같은 메모


# ─────────────────────────────
# 3. 코인 로그 응답용
# ─────────────────────────────
class CoinLogOut(BaseModel):
    id: int
    action: str          # "earn" / "spend"
    amount: int
    reason: str | None = None
    created_at: datetime

    class Config:
        orm_mode = True