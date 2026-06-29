## routers/ranking.py

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from typing import List

from db import get_db
import models

router = APIRouter(prefix="/ranking", tags=["ranking"])


@router.get("", response_model=List[dict])
def get_ranking(db: Session = Depends(get_db)):
    users = (
        db.query(models.User)
        .order_by(models.User.points.desc())
        .limit(10)
        .all()
    )

    ranking_list = []

    for index, user in enumerate(users, start=1):
        ranking_list.append({
            "rank": index,
            "nickname": user.nickname,
            "level": user.level,
            "points": user.points,
        })

    return ranking_list