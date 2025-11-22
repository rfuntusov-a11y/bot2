Main 

# main.py
import os
import sqlite3
import time
import hmac
import hashlib
from datetime import datetime, timedelta
from fastapi import FastAPI, Request, BackgroundTasks
from pydantic import BaseModel
import requests
import random

BOT_TOKEN = os.environ.get("BOT_TOKEN", "<ВАШ_BOT_TOKEN>")
ADMIN_ID = int(os.environ.get("ADMIN_ID", "0"))  # поставь свой Telegram ID
BOT_USERNAME = os.environ.get("BOT_USERNAME", "YourBotUsername")  # без @
PAYMENT_LINK = os.environ.get("PAYMENT_LINK", "")  # ссылка на оплату
OPENAI_KEY = os.environ.get("OPENAI_API_KEY", "")

API_URL = f"https://api.telegram.org/bot{BOT_TOKEN}"

DB_PATH = "bot.db"
app = FastAPI()

# --- DB helpers ---
def init_db():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""
    CREATE TABLE IF NOT EXISTS users(
        user_id INTEGER PRIMARY KEY,
        first_seen INTEGER,
        username TEXT,
        requests_count INTEGER DEFAULT 0,
        premium_until INTEGER DEFAULT 0,
        referrer_id INTEGER DEFAULT 0,
        referrals_count INTEGER DEFAULT 0
    )
    """)
    conn.commit()
    conn.close()

def get_user(uid):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT user_id, first_seen, username, requests_count, premium_until, referrer_id, referrals_count FROM users WHERE user_id=?", (uid,))
    row = cur.fetchone()
    conn.close()
    return row

def ensure_user(uid, username=None, ref=0):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    if not get_user(uid):
        cur.execute("INSERT INTO users(user_id, first_seen, username, referrer_id) VALUES(?,?,?,?)", (uid, int(time.time()), username or "", ref))
        # if ref > 0 increment referrals_count
        if ref:
            cur.execute("UPDATE users SET referrals_count = referrals_count + 1 WHERE user_id=?", (ref,))
        conn.commit()
    conn.close()

def inc_request(uid):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("UPDATE users SET requests_count = requests_count + 1 WHERE user_id=?", (uid,))
    conn.commit()
    conn.close()

def set_premium(uid, days):
    until = int((datetime.utcnow() + timedelta(days=days)).timestamp())
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("UPDATE users SET premium_until=? WHERE user_id=?", (until, uid))
    conn.commit()
    conn.close()
    return until

def revoke_premium(uid):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("UPDATE users SET premium_until=0 WHERE user_id=?", (uid,))
    conn.commit()
    conn.close()

def is_premium(uid):
    row = get_user(uid)
    if not row: return False
    premium_until = row[4]
    return premium_until and premium_until > int(time.time())

# --- Telegram helpers ---
def send_message(chat_id, text, reply_markup=None, parse_mode="HTML"):
    payload = {"chat_id": chat_id, "text": text, "parse_mode": parse_mode}
    if reply_markup:
        payload["reply_markup"] = reply_markup
    requests.post(f"{API_URL}/sendMessage", json=payload)

def send_audio(chat_id, audio_bytes, filename="voice.ogg"):
    # simplified: we won't upload real files in this template
    pass

# --- Simple story generator (fallback) ---
STYLES = [
    "жёсткая уличная",
    "романтичная драма",
    "комедийная переписка",
    "мрачный триллер",
    "легкая бытовая история"
]

TEMPLATES = [
    "Это произошло ночью. {hero} и {other} вышли из подъезда — никто не ожидал, что всё закончится так. {detail}",
    "{hero} написал первое сообщение: «{line}». Ответ {other} был неожидан: «{reply}». Так началась цепочка событий.",
    "{hero} проснулся и вспомнил ту ночь, где {detail}. Он решил написать {other}: «{line}» — и его ждало удивление."
]

def gen_story_simple(prompt):
    # prompt is free text like "я, Гоша, драка у подъезда"
    hero = "Ты"
    other = "он/она"
    parts = prompt.split(",")
    if len(parts) >= 2:
        hero = parts[0].strip()
        other = parts[1].strip()
    detail = random.choice(["всё пошло не по плану", "они смеялись до утра", "появилась неожиданная драка", "всё обернулось романом"])
    line = "нужно встретиться"
    reply = "ладно, приди"
    tmpl = random.choice(TEMPLATES)
    return tmpl.format(hero=hero, other=other, detail=detail, line=line, reply=reply)

# --- Webhook endpoint ---
class Update(BaseModel):
    update_id: int

@app.on_event("startup")
def startup_event():
    init_db()

@app.post("/webhook")
async def webhook(update: dict, background_tasks: BackgroundTasks):
    # minimal update handler
    # handle messages
    if "message" not in update:
        return {"ok": True}
    msg = update["message"]
    chat_id = msg["chat"]["id"]
    user = msg["from"]
    uid = user["id"]
    username = user.get("username", "")
    text = msg.get("text", "")

    # handle /start with ref
    if text.startswith("/start"):
        parts = text.split()
        ref = 0
        if len(parts) > 1 and parts[1].startswith("ref"):
            try:
                ref = int(parts[1][3:])
            except:
                ref = 0
        ensure_user(uid, username, ref)
        send_welcome(chat_id, uid)
        return {"ok": True}

    ensure_user(uid, username, 0)

    # admin commands
    if text.startswith("/grant") and int(uid) == ADMIN_ID:
        # format: /grant 123456 30
        try:
            _, target, days = text.split()
            tid = int(target)
            days = int(days)
            until = set_premium(tid, days)
            send_message(chat_id, f"Выдал премиум {days} дней пользователю {tid}. until={datetime.utcfromtimestamp(until)}")
        except Exception as e:
            send_message(chat_id, "Ошибка. Использование: /grant <user_id> <days>")
        return {"ok": True}

    if text.startswith("/revoke") and int(uid) == ADMIN_ID:
        try:
            _, target = text.split()
            tid = int(target)
            revoke_premium(tid)
            send_message(chat_id, f"Отозвал премиум у {tid}")
        except:
            send_message(chat_id, "Ошибка. Использование: /revoke <user_id>")
        return {"ok": True}

    if text.startswith("/status"):
        u = get_user(uid)
        if not u:
            send_message(chat_id, "Нет данных о пользователе.")
            return {"ok": True}
        premium = is_premium(uid)
        rc = u[3]
        until = datetime.utcfromtimestamp(u[4]).isoformat() if u[4] else "—"
        send_message(chat_id, f"requests: {rc}\npremium: {premium}\npremium_until: {until}\nreferrals: {u[6]}")
        return {"ok": True}

    if text.startswith("/premium"):
        # send payment link or instructions
        msg = "Оформить Premium: "
        if PAYMENT_LINK:
            msg += f"<a href=\"{PAYMENT_LINK}\">Оплатить</a>\n\nПосле оплаты пришли админу (он проверит) или подожди автоматической верификации."
        else:
            msg += "ссылка на оплату не задана администратором. Свяжись с админом."
        send_message(chat_id, msg)
        return {"ok": True}

    # Otherwise — treat as generation request
    # Increase request counter then decide whether to insert ad
    user_row = get_user(uid)
    if not user_row:
        ensure_user(uid, username, 0)
        user_row = get_user(uid)
    requests_count = user_row[3]
    premium = is_premium(uid)

    # generate story (if OPENAI_KEY provided we could call OpenAI here)
    story = ""
    if OPENAI_KEY:
        # placeholder for integration: call OpenAI / other API
        # For now fallback to simple generator
        story = gen_story_simple(text)
    else:
        story = gen_story_simple(text)

    # first request -> no ad
    if requests_count == 0 or premium:
        # no ad
        inc_request(uid)
        send_message(chat_id, format_story(story))
        # include share button
        send_share_button(chat_id, uid)
        return {"ok": True}
    else:
        # after first -> include ad block
        inc_request(uid)
        ad_block = get_ad_block()
        send_message(chat_id, format_story(story) + "\n\n" + ad_block)
        send_share_button(chat_id, uid)
        return {"ok": True}

def format_story(s):
    return f"📖 <b>Твоя история</b>:\n\n{s}"

def get_ad_block():
    # gentle CTA
    return ("—\nХотите без рекламы и длиннее истории? Оформите Premium.\n"
            f"Команды: /premium\n"
            "Платная подписка отключает рекламу и даёт расширенные опции.")

def send_share_button(chat_id, uid):
    bot_link = f"https://t.me/{BOT_USERNAME}?start=ref{uid}"
    keyboard = {
        "inline_keyboard": [
            [{"text":"Поделиться ботом", "url": bot_link}],
            [{"text":"В канале (наш контент)", "url": os.environ.get("CHANNEL_LINK","https://t.me/yourchannel")}]
        ]
    }
    send_message(chat_id, "📤 Поделись с другом — ему понравится!", reply_markup=keyboard)

# small health endpoint
@app.get("/")
def root():
    return {"ok": True}