-- SQLite
UPDATE users
SET role = 'teacher'
WHERE username = 'student1';

-- 1. 컬럼 추가
ALTER TABLE users ADD COLUMN username TEXT;
ALTER TABLE users ADD COLUMN role TEXT DEFAULT 'student';

-- 2. 계정 정보 업데이트
UPDATE users
SET username = 'student1',
    role = 'teacher'
WHERE id = 1;

-- 3. 확인
SELECT id, email, username, role FROM users;    