from fastapi import FastAPI, Request
import requests, os, time
from pydantic import BaseModel

app = FastAPI()

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))
BOT_USERNAME = os.getenv("BOT_USERNAME", "")
CHANNEL_LINK = os.getenv("CHANNEL_LINK", "")
PAYMENT_LINK = os.getenv("PAYMENT_LINK", "https://t.me/" + BOT_USERNAME)

user_db = {}

class TelegramUpdate(BaseModel):
    update_id: int
    message: dict | None = None

def send_message(chat_id, text):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    requests.post(url, json={"chat_id": chat_id, "text": text, "parse_mode": "HTML"})

@app.post("/webhook")
async def webhook(update: TelegramUpdate):
    if update.message:
        chat_id = update.message["chat"]["id"]
        text = update.message.get("text", "")

        if chat_id not in user_db:
            user_db[chat_id] = {"requests": 0, "premium_until": 0}

        is_premium = user_db[chat_id]["premium_until"] > time.time()

        # Команды
        if text == "/start":
            send_message(chat_id, "🔥 Добро пожаловать!\n\nОтправь тему — я сделаю историю. Первый запрос без рекламы.")
            return {"ok": True}

        if text.startswith("/grant") and chat_id == ADMIN_ID:
            try:
                _, uid, days = text.split()
                uid = int(uid)
                days = int(days)
                user_db[uid]["premium_until"] = time.time() + days * 86400
                send_message(chat_id, f"Выдал премиум {uid} на {days} дней.")
            except:
                send_message(chat_id, "Формат: /grant user_id days")
            return {"ok": True}

        if text.startswith("/revoke") and chat_id == ADMIN_ID:
            try:
                _, uid = text.split()
                uid = int(uid)
                user_db[uid]["premium_until"] = 0
                send_message(chat_id, f"Снял премиум с {uid}.")
            except:
                send_message(chat_id, "Формат: /revoke user_id")
            return {"ok": True}

        # Логика генерации
        user_db[chat_id]["requests"] += 1
        req_count = user_db[chat_id]["requests"]

        # Простая генерация истории
        story = f"📘 История по твоей теме:\n\n{text}\n\n🔥 Конец."

        if req_count == 1 or is_premium:
            send_message(chat_id, story)
        else:
            send_message(chat_id, story + "\n\n💰 Хотите без рекламы? Премиум тут:\n" + PAYMENT_LINK)

    return {"ok": True}