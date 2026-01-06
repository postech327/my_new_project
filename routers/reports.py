# routers/reports.py
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Dict, List

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.pagesizes import A4
from reportlab.lib.enums import TA_CENTER
from reportlab.lib import colors

from openai import OpenAI

from db import get_db
import models

router = APIRouter(
    prefix="/reports",
    tags=["reports"],
)

client = OpenAI()

# ======================================================
# 1️⃣ 주간 학습 리포트 PDF 생성 + DB 저장
# ======================================================
@router.get("/weekly/{user_id}")
def generate_weekly_report(
    user_id: int,
    db: Session = Depends(get_db),
):
    user = db.get(models.User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    since = datetime.utcnow() - timedelta(days=7)

    answers = (
        db.query(models.StudentAnswer)
        .filter(
            models.StudentAnswer.user_id == user_id,
            models.StudentAnswer.created_at >= since,
        )
        .all()
    )

    if not answers:
        raise HTTPException(status_code=400, detail="No study data for this week")

    # ───────── 전체 요약
    total = len(answers)
    correct = sum(1 for a in answers if a.is_correct)
    accuracy = round((correct / total) * 100, 2)

    # ───────── 유형별 성취도
    type_stats: Dict[str, Dict] = {}
    for a in answers:
        qt = a.question.question_type
        type_stats.setdefault(qt, {"total": 0, "correct": 0})
        type_stats[qt]["total"] += 1
        if a.is_correct:
            type_stats[qt]["correct"] += 1

    type_rows: List[List[str]] = [["문제 유형", "풀이 수", "정답률 (%)"]]

    weakest_type = None
    weakest_rate = 101

    for qt, s in type_stats.items():
        rate = round((s["correct"] / s["total"]) * 100, 2)
        type_rows.append([qt, str(s["total"]), str(rate)])
        if rate < weakest_rate:
            weakest_rate = rate
            weakest_type = qt

    # ───────── GPT 코치 멘트
    prompt = f"""
너는 학생의 영어 학습을 도와주는 AI 코치야.

이번 주 학습 요약:
- 총 풀이 문제 수: {total}
- 전체 정답률: {accuracy}%
- 가장 약한 유형: {weakest_type} ({weakest_rate}%)

잘한 점과 개선점을 포함해
다음 주 학습 조언을 4~5문장 한국어로 작성해줘.
"""

    try:
        completion = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "You are an English learning coach."},
                {"role": "user", "content": prompt},
            ],
            temperature=0.7,
            max_tokens=300,
        )
        coach_message = completion.choices[0].message.content.strip()
    except Exception:
        coach_message = "이번 주도 꾸준히 학습했어요. 다음 주도 차근차근 이어가 봅시다!"

    # ───────── PDF 생성
    filename = f"weekly_report_user_{user_id}_{datetime.utcnow().date()}.pdf"
    filepath = f"/mnt/data/{filename}"

    styles = getSampleStyleSheet()
    styles["Title"].alignment = TA_CENTER

    doc = SimpleDocTemplate(filepath, pagesize=A4)
    elements = []

    elements.append(Paragraph("주간 영어 학습 리포트", styles["Title"]))
    elements.append(Spacer(1, 20))
    elements.append(Paragraph(f"학생: {user.nickname}", styles["Normal"]))
    elements.append(Paragraph("기간: 최근 7일", styles["Normal"]))
    elements.append(Spacer(1, 15))

    elements.append(Paragraph("1. 학습 요약", styles["Heading2"]))
    elements.append(
        Paragraph(
            f"총 풀이 문제 수: {total}<br/>전체 정답률: {accuracy}%",
            styles["Normal"],
        )
    )
    elements.append(Spacer(1, 15))

    elements.append(Paragraph("2. 유형별 성취도", styles["Heading2"]))
    table = Table(type_rows, hAlign="LEFT")
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey),
                ("GRID", (0, 0), (-1, -1), 1, colors.black),
                ("ALIGN", (1, 1), (-1, -1), "CENTER"),
            ]
        )
    )
    elements.append(table)
    elements.append(Spacer(1, 20))

    elements.append(Paragraph("3. AI 코치의 한마디", styles["Heading2"]))
    elements.append(Paragraph(coach_message.replace("\n", "<br/>"), styles["Normal"]))

    doc.build(elements)

    # ───────── 리포트 DB 저장
    report = models.StudyReport(
        user_id=user_id,
        period_start=since,
        period_end=datetime.utcnow(),
        total_questions=total,
        correct_questions=correct,
        accuracy_rate=int(accuracy),
        weakest_type=weakest_type,
        coach_message=coach_message,
        pdf_path=filepath,
    )
    db.add(report)
    db.commit()

    return FileResponse(filepath, media_type="application/pdf", filename=filename)


# ======================================================
# 2️⃣ 리포트 히스토리 조회
# ======================================================
@router.get("/history/{user_id}")
def report_history(user_id: int, db: Session = Depends(get_db)):
    reports = (
        db.query(models.StudyReport)
        .filter(models.StudyReport.user_id == user_id)
        .order_by(models.StudyReport.created_at.desc())
        .all()
    )

    return [
        {
            "report_id": r.id,
            "period": f"{r.period_start.date()} ~ {r.period_end.date()}",
            "accuracy_rate": r.accuracy_rate,
            "weakest_type": r.weakest_type,
            "created_at": r.created_at,
        }
        for r in reports
    ]


# ======================================================
# 3️⃣ 리포트 재다운로드
# ======================================================
@router.get("/download/{report_id}")
def download_report(report_id: int, db: Session = Depends(get_db)):
    r = db.get(models.StudyReport, report_id)
    if not r:
        raise HTTPException(status_code=404, detail="Report not found")

    return FileResponse(
        r.pdf_path,
        media_type="application/pdf",
        filename=r.pdf_path.split("/")[-1],
    )
@router.post("/reports/generate")
def generate_study_report(
    user_id: int,
    db: Session = Depends(get_db),
):
    answers = (
        db.query(models.StudentAnswer)
        .filter(models.StudentAnswer.user_id == user_id)
        .all()
    )

    total = len(answers)
    correct = sum(1 for a in answers if a.is_correct)

    # 약점 유형 계산
    from collections import Counter
    import json

    counter = Counter()
    for a in answers:
        if not a.is_correct and a.gpt_explanation:
            data = json.loads(a.gpt_explanation)
            counter[data.get("error_type")] += 1

    weakest_type = counter.most_common(1)[0][0] if counter else None

    report = models.StudyReport(
        user_id=user_id,
        period_start=datetime.utcnow(),
        period_end=datetime.utcnow(),
        total_questions=total,
        correct_questions=correct,
        accuracy_rate=round(correct / total * 100, 2) if total else 0,
        weakest_type=weakest_type,
        coach_message=f"{weakest_type} 유형 집중 보완 필요",
        pdf_path="",  # 다음 단계
    )

    db.add(report)
    db.commit()

    return {"status": "ok"}
# routers/reports.py (맨 아래 추가)

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func
from collections import Counter
import json
import datetime

import models
from db import get_db

router = APIRouter(prefix="/reports", tags=["reports"])

@router.post("/recommended/update")
def update_report_from_recommended(
    user_id: int,
    db: Session = Depends(get_db),
):
    """
    추천 문제 풀이 결과를 StudyReport에 누적 반영
    """

    # 추천 문제 답안 중 GPT 해설이 있는 오답만 집계
    answers = (
        db.query(models.StudentAnswer)
        .filter(
            models.StudentAnswer.user_id == user_id,
            models.StudentAnswer.is_correct == False,
            models.StudentAnswer.gpt_explanation.isnot(None),
        )
        .all()
    )

    if not answers:
        return {"status": "skip", "reason": "추천 문제 오답 없음"}

    counter = Counter()

    for a in answers:
        try:
            data = json.loads(a.gpt_explanation)
            error_type = data.get("error_type")
            if error_type:
                counter[error_type] += 1
        except Exception:
            continue

    weakest_type = counter.most_common(1)[0][0] if counter else None

    # 기존 리포트 가져오기 (없으면 새로 생성)
    report = (
        db.query(models.StudyReport)
        .filter(models.StudyReport.user_id == user_id)
        .order_by(models.StudyReport.created_at.desc())
        .first()
    )

    if not report:
        report = models.StudyReport(
            user_id=user_id,
            period_start=datetime.datetime.utcnow(),
            period_end=datetime.datetime.utcnow(),
            total_questions=0,
            correct_questions=0,
            accuracy_rate=0,
        )
        db.add(report)

    # 🔥 약점 유형 업데이트
    report.weakest_type = weakest_type
    report.coach_message = f"{weakest_type} 유형 보완 학습 추천" if weakest_type else report.coach_message

    db.commit()

    return {
        "status": "ok",
        "weakest_type": weakest_type,
    }