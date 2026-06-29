import sqlite3

conn = sqlite3.connect("app.db")
cur = conn.cursor()

# 1. 컬럼 추가 (이미 있으면 무시)
try:
    cur.execute("ALTER TABLE users ADD COLUMN username TEXT")
except sqlite3.OperationalError as e:
    print("username 컬럼 이미 존재")

try:
    cur.execute("ALTER TABLE users ADD COLUMN role TEXT DEFAULT 'student'")
except sqlite3.OperationalError as e:
    print("role 컬럼 이미 존재")

# 2. 계정 업데이트
cur.execute("""
UPDATE users
SET username = 'student1',
    role = 'teacher'
WHERE id = 1
""")

conn.commit()

# 3. 확인 출력
rows = cur.execute("SELECT id, email, username, role FROM users").fetchall()
for r in rows:
    print(r)

conn.close()