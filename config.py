# config.py
import os
import logging
from dotenv import load_dotenv

# .env 파일 로드
load_dotenv()

logger = logging.getLogger(__name__)

# 🔑 OpenAI 키 & 모델 이름
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o")  # 기본값 gpt-4o

if not OPENAI_API_KEY:
    logger.warning("⚠️ OPENAI_API_KEY is not set. GPT endpoints will fail.")
    
SECRET_KEY = "CHANGE_THIS_TO_RANDOM_STRING"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30
REFRESH_TOKEN_EXPIRE_DAYS = 7
