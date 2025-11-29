# create_dummy_user.py
from db import SessionLocal   # ⬅️ 네 db.py 안에 있는 세션 팩토리
from models import User

def main():
    db = SessionLocal()
    try:
        user = User(
            email="teacher1@example.com",
            password_hash="dummy-hash",    # 나중에 실제 해시로 교체
            nickname="열카선생님",
            region="서울 · 강남구",
            role="teacher",   # 'normal' / 'student' / 'teacher'
            level=3,
            coins=100,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        print("✅ Created user with id =", user.id)
    finally:
        db.close()

if __name__ == "__main__":
    main()