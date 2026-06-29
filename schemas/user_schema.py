from pydantic import BaseModel

class StudentResponse(BaseModel):
    id: int
    nickname: str
    role: str
    level: int
    points: int
    coins: int

    class Config:
        from_attributes = True   # 🔥 Pydantic v2