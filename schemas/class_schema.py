from pydantic import BaseModel
from datetime import datetime

class ClassCreate(BaseModel):
    name: str

class ClassResponse(BaseModel):
    id: int
    name: str
    join_code: str
    created_at: datetime

    class Config:
        orm_mode = True