# schemas/student_answer.py
from typing import List
from pydantic import BaseModel

# 개별 문제 답안
class StudentAnswerItem(BaseModel):
    question_id: int
    selected_index: int

# 답안 제출 payload
class StudentAnswerSubmit(BaseModel):
    problem_set_id: int
    answers: List[StudentAnswerItem]

# 제출 결과 응답 (선택)
class StudentAnswerOut(BaseModel):
    question_id: int
    selected_index: int
    is_correct: bool