import os
from pathlib import Path
from dotenv import load_dotenv

# Путь к директории проекта
BASE_DIR = Path(__file__).resolve().parent

# Загрузка переменных окружения из .env (если есть локально)
load_dotenv(BASE_DIR / ".env")

VK_TOKEN = os.getenv("VK_TOKEN", "").strip()
DEFAULT_PREFIX = os.getenv("DEFAULT_PREFIX", "нб").strip().lower()
OWNER_ID_STR = os.getenv("OWNER_ID", "").strip()
OWNER_ID = int(OWNER_ID_STR) if OWNER_ID_STR.isdigit() else 0

# Поддержка Railway Volume / переменной DATA_DIR для сохранения базы данных между перезапусками
DATA_DIR = os.getenv("DATA_DIR", "").strip()
if DATA_DIR:
    os.makedirs(DATA_DIR, exist_ok=True)
    DB_PATH = str(Path(DATA_DIR) / os.getenv("DB_PATH", "bot.db"))
else:
    DB_PATH = str(BASE_DIR / os.getenv("DB_PATH", "bot.db"))

# VK API версия
VK_API_VERSION = "5.199"

# Время старта бота
BOT_START_TIME = 0.0
