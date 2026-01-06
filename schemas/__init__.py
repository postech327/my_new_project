# schemas/__init__.py
from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel


# ---- AnalysisRecord 관련 스키마 ----
class AnalysisCreate(BaseModel):
    kind: str
    input_text: Optional[str] = None
    result_text: Optional[str] = None
    result_json: Optional[str] = None


class AnalysisOut(AnalysisCreate):
    id: int
    created_at: datetime

    class Config:
        orm_mode = True