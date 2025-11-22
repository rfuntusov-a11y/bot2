from fastapi import FastAPI, Request
import asyncio
import httpx
import os

TOKEN = os.getenv("BOT_TOKEN")
API_URL = f"https://api.telegram.org/bot{TOKEN}/"

app = FastAPI()

# Отправка сообщений
async def send_message(chat_id, text):
    async with httpx.AsyncClient() as client:
        await client.post(API_URL + "sendMessage", json={
            "chat_id": chat_id,
            "text": text
        })

# Webhook endpoint
@app.post("/webhook")
async def telegram_webhook(request: Request):
    data = await request.json()

    if "message" in data:
        chat_id = data["message"]["chat"]["id"]
        text = data["message"].get("text", "")

        if text == "/start":
            await send_message(chat_id, "🔥 Бот запущен!\nПиши текст, и я сгенерирую для тебя контент.")
        else:
            await send_message(chat_id, f"Текст получен: {text}")

    return {"ok": True}

@app.get("/")
def home():
    return {"status": "bot running"}
