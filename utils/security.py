# utils/security.py

from passlib.context import CryptContext
from fastapi import Depends, HTTPException

from utils.auth_jwt import get_current_user

# =====================================================
# Password (✅ 유지)
# =====================================================
pwd_context = CryptContext(
    schemes=["bcrypt"],
    deprecated="auto",
)

def hash_password(password: str) -> str:
    if not password:
        raise ValueError("password required")
    return pwd_context.hash(password)

def verify_password(plain_password: str, hashed_password: str) -> bool:
    if not plain_password or not hashed_password:
        return False
    return pwd_context.verify(plain_password, hashed_password)


# =====================================================
# Role 기반 접근 제어 (JWT 해석 ❌, 역할만 체크)
# =====================================================
def require_role(required_role: str):
    """
    예:
    Depends(require_role("student"))
    Depends(require_role("admin"))
    """
    def role_checker(user: dict = Depends(get_current_user)):
        if user.get("role") != required_role:
            raise HTTPException(
                status_code=403,
                detail="Permission denied",
            )
        return user

    return role_checker