# utils/points.py

from sqlalchemy.orm import Session
from models import User
from utils.level import calculate_level

def add_points(db: Session, user: User, amount: int):
    """
    사용자에게 점수 지급 + 레벨 자동 계산
    """

    user.points += amount

    # 🔥 레벨 자동 계산
    user.level = calculate_level(user.points)

    db.commit()
    db.refresh(user)