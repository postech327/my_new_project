# main.py

from __future__ import annotations

print("🔥 지금 실행된 main.py 맞음")

import re
import json
import logging
from typing import List

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy.orm import Session

# -----------------------------
# DB & Models (⭐ 중요 순서)
# -----------------------------
from db import engine, Base, get_db
import models   # ⭐ 반드시 engine import 이후, create_all 이전

# -----------------------------
# Auth
# -----------------------------
from utils.auth_jwt import get_current_user

# -----------------------------
# Routers
# -----------------------------
from routers.auth import router as auth_router
from routers.structure import router as structure_router
from routers.paragraph import router as paragraph_router
from routers.word_mcq_api import router as word_mcq_router
from routers.dashboard_api import router as dashboard_router
from routers.export import router as export_router
from routers.analysis import router as analysis_router
from routers.question_maker_api import router as question_maker_router
from routers.teacher import router as teacher_router
from routers.community import router as community_router
from routers.users import router as users_router
from routers.problem_sets_api import router as problem_sets_api_router
from routers.statistics import router as statistics_router
from routers.reports import router as reports_router
from routers.admin_dashboard import router as admin_dashboard_router
from routers.admin_charts import router as admin_charts_router
from routers.admin_students import router as admin_students_router
from routers.admin_difficulty import router as admin_difficulty_router
from routers.admin_exam_generator import router as admin_exam_router
from routers.admin_personal_exam import router as admin_personal_exam_router
from routers.student_learning_flow import router as student_learning_flow_router
from routers.student_gpt_explain import router as student_gpt_explain_router
from routers.analysis_records import router as analysis_records_router
from routers.teacher_exam_assignments import router as teacher_exam_assignments_router
from routers import student_assignments
from routers import student_problem_sets
from routers.student_answers import router as student_answers_router
from routers.student_dashboard import router as student_dashboard_router
from routers.teacher_class import router as teacher_class_router
from routers import student_class
from routers import (
    recommendation,
    admin_student_recommendation,
    student_exams,
    study_reports,
    concepts,
    student_exam_builder,
    student_study_reports,
    teacher_passages,
)
from routers import ranking
from routers import student_recommend
from routers import student_wrong_answers
from routers import student_exam_start
from routers import student_final_touches
from routers import final_touch_practice_results
from routers import teacher_mock_exams
from routers import student_mock_exams
from routers import learning_assignments
from routers import student_workbooks
from routers import workbooks
from routers import workbook_attempts
from routers import vocabulary

import routers.student_wrong_answers
print(routers.student_wrong_answers.__file__)


from routers.folders import router as folders_router

# -----------------------------
# OpenAI
# -----------------------------
from config import OPENAI_API_KEY, OPENAI_MODEL
from openai import OpenAI

# --------------------------------------------------
# Init
# --------------------------------------------------
load_dotenv()
logger = logging.getLogger("uvicorn.error")
client = OpenAI(api_key=OPENAI_API_KEY)

# ⭐ 모델 로딩 완료 후 테이블 생성
Base.metadata.create_all(bind=engine)


def ensure_lightweight_migrations():
    with engine.begin() as conn:
        analysis_columns = {
            row[1]
            for row in conn.exec_driver_sql("PRAGMA table_info(analysis_records)")
        }
        if "outline" not in analysis_columns:
            conn.exec_driver_sql("ALTER TABLE analysis_records ADD COLUMN outline JSON")
        if "sentence_details" not in analysis_columns:
            conn.exec_driver_sql(
                "ALTER TABLE analysis_records ADD COLUMN sentence_details JSON"
            )
        if "folder_id" not in analysis_columns:
            conn.exec_driver_sql("ALTER TABLE analysis_records ADD COLUMN folder_id INTEGER")

        problem_set_columns = {
            row[1]
            for row in conn.exec_driver_sql("PRAGMA table_info(problem_sets)")
        }
        if "folder_id" not in problem_set_columns:
            conn.exec_driver_sql("ALTER TABLE problem_sets ADD COLUMN folder_id INTEGER")

        passage_columns = {
            row[1]
            for row in conn.exec_driver_sql("PRAGMA table_info(passages)")
        }
        if "folder_id" not in passage_columns:
            conn.exec_driver_sql("ALTER TABLE passages ADD COLUMN folder_id INTEGER")

        folder_columns = {
            row[1]
            for row in conn.exec_driver_sql("PRAGMA table_info(folders)")
        }
        if "parent_id" not in folder_columns:
            conn.exec_driver_sql("ALTER TABLE folders ADD COLUMN parent_id INTEGER")

        mock_question_columns = {
            row[1]
            for row in conn.exec_driver_sql("PRAGMA table_info(mock_questions)")
        }
        if mock_question_columns and "source" not in mock_question_columns:
            conn.exec_driver_sql("ALTER TABLE mock_questions ADD COLUMN source VARCHAR(255)")

        workbook_question_columns = {
            row[1]
            for row in conn.exec_driver_sql("PRAGMA table_info(workbook_questions)")
        }
        if workbook_question_columns and "section_id" not in workbook_question_columns:
            conn.exec_driver_sql("ALTER TABLE workbook_questions ADD COLUMN section_id INTEGER")


ensure_lightweight_migrations()

app = FastAPI(title="English Analyzer API", version="1.3.0")

# --------------------------------------------------
# Middleware
# --------------------------------------------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],   # 🔥 일단 이걸로 해결
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --------------------------------------------------
# Schemas
# --------------------------------------------------
class TextInput(BaseModel):
    text: str


class ChatRequest(BaseModel):
    question: str


class WordRequest(BaseModel):
    words: List[str]

# --------------------------------------------------
# Basic
# --------------------------------------------------
@app.get("/")
def root():
    return {"message": "OK"}

@app.get("/healthz")
def healthz():
    return {"status": "healthy"}

@app.get("/me")
def read_me(
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    db_user = db.query(models.User).get(int(current_user["sub"]))

    return {
        "id": db_user.id,
        "nickname": db_user.nickname,
        "role": db_user.role,
        "level": db_user.level,
        "points": db_user.points,
        "coins": db_user.coins
    }

# --------------------------------------------------
# Routers
# --------------------------------------------------
app.include_router(auth_router)
app.include_router(structure_router)
app.include_router(paragraph_router)
app.include_router(word_mcq_router)
app.include_router(dashboard_router)
app.include_router(export_router)
app.include_router(analysis_router)
app.include_router(question_maker_router)
app.include_router(teacher_router)
app.include_router(community_router)
app.include_router(users_router)
app.include_router(problem_sets_api_router)
app.include_router(statistics_router)
app.include_router(reports_router)
app.include_router(admin_dashboard_router)
app.include_router(admin_charts_router)
app.include_router(admin_students_router)
app.include_router(admin_difficulty_router)
app.include_router(admin_exam_router)
app.include_router(admin_personal_exam_router)
app.include_router(student_learning_flow_router)
app.include_router(student_gpt_explain_router)

app.include_router(recommendation.router)
app.include_router(admin_student_recommendation.router)
app.include_router(student_exams.router)
app.include_router(study_reports.router)
app.include_router(concepts.router)
app.include_router(student_exam_builder.router)
app.include_router(student_study_reports.router)
app.include_router(teacher_passages.router)
app.include_router(analysis_records_router)
app.include_router(teacher_exam_assignments_router)
app.include_router(student_assignments.router)
app.include_router(student_problem_sets.router)
app.include_router(student_answers_router)
app.include_router(student_dashboard_router)
app.include_router(ranking.router)
app.include_router(teacher_class_router)
app.include_router(student_class.router)
app.include_router(student_recommend.router)
app.include_router(folders_router)
app.include_router(student_wrong_answers.router)
app.include_router(student_exam_start.router)
app.include_router(student_final_touches.router)
app.include_router(final_touch_practice_results.router)
app.include_router(teacher_mock_exams.router)
app.include_router(student_mock_exams.router)
app.include_router(learning_assignments.router)
app.include_router(student_workbooks.router)
app.include_router(workbooks.router)
app.include_router(workbook_attempts.router)
app.include_router(vocabulary.router)
