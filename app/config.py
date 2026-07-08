import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
TIMEZONE = os.getenv("TIMEZONE", "Asia/Tashkent")
DB_PATH = BASE_DIR / os.getenv("DB_NAME", "eslatbot.db")
MOHIR_API_KEY = os.getenv("MOHIR_API_KEY", "")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
