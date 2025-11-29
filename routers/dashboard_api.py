# routers/dashboard_api.py
from fastapi import APIRouter

router = APIRouter(prefix="", tags=["dashboard"])

@router.get("/dashboard")
async def get_dashboard(period: str = "7d"):
    # TODO: period에 따라 실제 통계 산출
    return {
        "streakDays": 23,
        "totalAnalyses": 157,
        "learnedWords": 132,
        "level": "B2",
        "wrongTypes": [
            {"label": "시제", "count": 4},
            {"label": "수일치", "count": 6},
            {"label": "전치사", "count": 2},
            {"label": "관사", "count": 3},
            {"label": "어휘", "count": 7},
            {"label": "도치", "count": 6},
            {"label": "가정법", "count": 3},
        ],
        "ratios": [
            {"label": "어법 정확성", "value": 40},
            {"label": "문맥 어휘", "value": 26},
            {"label": "요지 추론", "value": 23},
            {"label": "기타", "value": 11},
        ],
    }