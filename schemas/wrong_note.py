from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime


class WrongNoteItem(BaseModel):
    question_id: int
    question_text: str
    selected_index: int
    correct_index: int
    error_type: Optional[str]
    gpt_explanation: Optional[str]
    created_at: datetime


class WrongNoteResponse(BaseModel):
    problem_set_id: int
    user_id: int
    total_wrong: int
    items: List[WrongNoteItem]