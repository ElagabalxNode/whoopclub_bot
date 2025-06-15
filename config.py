import os

from dotenv import load_dotenv

load_dotenv(override=True)

REQUIRED_CHAT_ID = os.getenv("REQUIRED_CHAT_ID")
BOT_TOKEN = os.getenv("BOT_TOKEN")
print(f"Loaded BOT_TOKEN: {BOT_TOKEN}")
if not BOT_TOKEN:
    print("❌ BOT_TOKEN не найден! Проверь .env файл.")
    exit(1)

ADMINS = list(map(int, os.getenv("ADMINS", "").split()))
PAYMENT_LINK = os.getenv("PAYMENT_LINK")