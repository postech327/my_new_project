# routers/auth.py

from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field
from typing import Optional

from db import get_db
import models

from utils.security import hash_password, verify_password
from utils.auth_jwt import create_access_token, create_refresh_token
from jose import JWTError, jwt
from config import SECRET_KEY, ALGORITHM, ACCESS_TOKEN_EXPIRE_MINUTES


router = APIRouter(
    prefix="/auth",
    tags=["auth"],
)

# =====================================================
# Register
# =====================================================
class RegisterAgreements(BaseModel):
    marketing_opt_in: bool = False
    tos: bool = False
    privacy: bool = False


class RegisterRequest(BaseModel):
    name: Optional[str] = None
    school: Optional[str] = None
    email: str
    phone: Optional[str] = None
    username: str = Field(min_length=4, max_length=20)
    password: str = Field(min_length=8)
    role: str = "student"
    interest: Optional[str] = None
    ref_code: Optional[str] = None
    agreements: RegisterAgreements = Field(default_factory=RegisterAgreements)
    grade_band: Optional[str] = None


_ALLOWED_ROLES = {"student", "teacher"}


@router.get("/check-username")
def check_username(
    username: str = Query(..., min_length=4, max_length=20),
    db: Session = Depends(get_db),
):
    normalized = username.strip()
    existing = (
        db.query(models.User)
        .filter(models.User.nickname == normalized)
        .first()
    )
    if existing:
        return {"available": False, "message": "이미 사용 중인 아이디입니다."}
    return {"available": True, "message": "사용 가능한 아이디입니다."}


@router.post("/register")
def register(
    payload: RegisterRequest,
    db: Session = Depends(get_db),
):
    username = payload.username.strip()
    email = payload.email.strip().lower()
    role = payload.role.strip().lower()

    print("REGISTER REQUEST KEYS:", list(payload.dict(exclude={"password"}).keys()))

    if role not in _ALLOWED_ROLES:
        raise HTTPException(status_code=400, detail="가입 유형을 다시 선택해 주세요.")

    if not payload.agreements.tos or not payload.agreements.privacy:
        raise HTTPException(status_code=400, detail="필수 약관에 동의해 주세요.")

    existing_username = (
        db.query(models.User)
        .filter(models.User.nickname == username)
        .first()
    )
    if existing_username:
        raise HTTPException(status_code=409, detail="이미 사용 중인 아이디입니다.")

    existing_email = (
        db.query(models.User)
        .filter(models.User.email == email)
        .first()
    )
    if existing_email:
        raise HTTPException(status_code=409, detail="이미 사용 중인 이메일입니다.")

    # TODO: users 테이블에 phone 컬럼이 추가되면 휴대폰 번호 중복 검사를 연결합니다.
    password_hash = hash_password(payload.password)

    user = models.User(
        email=email,
        nickname=username,
        password_hash=password_hash,
        role=role,
    )

    db.add(user)
    db.commit()
    db.refresh(user)

    return {
        "ok": True,
        "user_id": user.id,
        "role": user.role,
        "user": {
            "id": user.id,
            "username": user.nickname,
            "role": user.role,
        },
    }

# =====================================================
# OAuth2 Login (Swagger 전용)
# =====================================================
@router.post("/login")
def oauth_login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
):
    """
    Swagger OAuth2 전용 로그인
    - application/x-www-form-urlencoded
    - username / password 사용
    """

    # 1️⃣ 사용자 조회
    user = (
        db.query(models.User)
        .filter(models.User.nickname == form_data.username)
        .first()
    )
    if not user:
        raise HTTPException(status_code=401, detail="Invalid credentials")

    # 2️⃣ 비밀번호 검증
    if not verify_password(form_data.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    # 3️⃣ JWT 생성
    access_token = create_access_token(
        data={
            "sub": str(user.id),        # ⭐ 반드시 문자열
            "username": user.nickname,
            "role": user.role,
        },
        expires_delta=timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES),
    )
    
    refresh_token = create_refresh_token(
    data={
        "sub": str(user.id),
        "username": user.nickname,
        "role": user.role,
    }
)

    # 4️⃣ OAuth2 규격 응답
    return {
    "access_token": access_token,
    "refresh_token": refresh_token,
    "token_type": "bearer",
    "user": {
        "id": user.id,
        "nickname": user.nickname,
        "role": user.role,
        "level": user.level,
    }
}
    
@router.post("/refresh")
def refresh_access_token(
    payload: dict
):
    refresh_token = payload.get("refresh_token")

    if not refresh_token:
        raise HTTPException(status_code=400, detail="Refresh token required")

    try:
        decoded = jwt.decode(
            refresh_token,
            SECRET_KEY,
            algorithms=[ALGORITHM]
        )
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid refresh token")

    user_id = decoded.get("sub")
    username = decoded.get("username")
    role = decoded.get("role")

    new_access_token = create_access_token(
        data={
            "sub": user_id,
            "username": username,
            "role": role,
        },
        expires_delta=timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES),
    )

    return {
        "access_token": new_access_token,
        "token_type": "bearer"
    }



