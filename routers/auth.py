# routers/auth.py
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, EmailStr, Field

router = APIRouter()

class Agreements(BaseModel):
    marketing_opt_in: bool = False
    tos: bool
    privacy: bool

class RegisterIn(BaseModel):
    name: str = Field(..., min_length=1)
    school: str | None = None
    grade_band: str | None = None
    email: EmailStr | None = None
    phone: str | None = None
    username: str = Field(..., min_length=4, max_length=20)
    password: str = Field(..., min_length=8, max_length=72)
    interest: str | None = None
    ref_code: str | None = None
    agreements: Agreements

@router.post("/register")
def register(payload: RegisterIn):
    return {"ok": True, "user": {"username": payload.username}}