import json
import logging
import telebot
import requests
import base64
import os
import uuid
import time
from telebot import types

import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

BOT_TOKEN = "8522132903:AAHldacR2QDY67Pb734vmpMZ0WZSKxs0920"
XUI_IP = "87.199.198.168"
XUI_PORT = "2053"
XUI_LOGIN = "admin"
XUI_PASSWORD = "htgvMHk12h332BPS8w2-"
XUI_SECRET_PATH = "ba9791eb5caf77a79d7f206c4fceda11"

PANEL_URL = f"https://{XUI_IP}:{XUI_PORT}/{XUI_SECRET_PATH}"

# Для сторонних хостингов (Render) этот прокси больше не нужен, 
# но мы оставляем его, чтобы библиотека не выдавала ошибок.
telebot.apihelper.proxy = {'https': 'http://proxy.server:3128'}
bot = telebot.TeleBot(BOT_TOKEN)

PRICE_1_MONTH = "💳 На 1 месяц (30 дней) — 199 ₽"
PRICE_2_MONTH = "💳 На 2 месяца (60 дней) — 359 ₽"
PRICE_6_MONTH = "💳 На 6 месяцев (180 дней) — 999 ₽"
PRICE_1_YEAR  = "💳 На 1 год (365 дней) — 1999 ₽"

TEST_USERS_FILE = "client_test_users.json"

def load_test_users():
    if os.path.exists(TEST_USERS_FILE):
        with open(TEST_USERS_FILE, "r") as f:
            return json.load(f)
    return []

def save_test_user(user_id):
    users = load_test_users()
    if user_id not in users:
        users.append(user_id)
        with open(TEST_USERS_FILE, "w") as f:
            json.dump(users, f)

def get_xui_session():
    session = requests.Session()
    session.verify = False
    session.proxies = {} 
    login_url = f"{PANEL_URL}/login"
    try:
        response = session.post(login_url, data={"username": XUI_LOGIN, "password": XUI_PASSWORD}, timeout=10)
        if response.status_code == 200 and response.json().get("success"):
            return session
    except Exception:
        pass
    return None

def create_vpn_client(user_id, username, days_count):
    session = get_xui_session()
    if not session:
        return None
    try:
        list_url = f"{PANEL_URL}/panel/api/inbounds/list"
        list_resp = session.get(list_url, timeout=10)
        inbounds = list_resp.json().get("obj", [])
        if not inbounds:
            return None
        inbound = inbounds if isinstance(inbounds, list) else inbounds
        inbound_id = inbound["id"]
        stream_settings = json.loads(inbound["streamSettings"])
        expiry_time = int((time.time() + (days_count * 86400)) * 1000)
        tg_username = username if username else "user"
        email = f"client_{user_id}_{tg_username}_{days_count}d"
        client_uuid = str(uuid.uuid4())
        client_spec = {
            "id": client_uuid, "alterId": 0, "email": email, "limitIp": 2,
            "totalGB": 0, "expiryTime": expiry_time, "enable": True, "tgId": str(user_id), "subId": ""
        }
        add_url = f"{PANEL_URL}/panel/api/inbounds/addClient"
        payload = {"id": inbound_id, "settings": json.dumps({"clients": [client_spec]})}
        add_resp = session.post(add_url, json=payload, timeout=10)
        if add_resp.json().get("success"):
            server_name = stream_settings.get("realitySettings", {}).get("serverNames", ["example.com"])
            if isinstance(server_name, list) and len(server_name) > 0:
                server_name = server_name[0]
            public_key = stream_settings.get("realitySettings", {}).get("publicKey", "")
            short_id = stream_settings.get("realitySettings", {}).get("shortIds", [""])
            if isinstance(short_id, list) and len(short_id) > 0:
                short_id = short_id[0]
            port = inbound["port"]
            vless_link = f"vless://{client_uuid}@{XUI_IP}:{port}?type=tcp&security=reality&pbk={public_key}&fp=chrome&sni={server_name}&sid={short_id}#{email}"
            return vless_link
    except Exception:
        pass
    return None

def main_menu():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=1)
    markup.add(
        types.KeyboardButton("🎁 Получить бесплатный тест (3 дня)"),
        types.KeyboardButton("💰 Купить подписку"),
        types.KeyboardButton("ℹ️ Мой личный кабинет / Статус")
    )
    return markup

@bot.message_handler(commands=['start'])
def send_welcome(message):
    bot.send_message(message.chat.id, "👋 Приветствуем в VPN! Доступна кнопка теста на 3 дня.", reply_markup=main_menu())

@bot.message_handler(func=lambda message: message.text == "🎁 Получить бесплатный тест (3 дня)")
def handle_test_period(message):
    user_id = message.from_user.id
    if user_id in load_test_users():
        bot.send_message(message.chat.id, "❌ Вы уже брали тест.")
        return
    bot.send_message(message.chat.id, "⏳ Создаем профиль...")
    vpn_link = create_vpn_client(user_id, message.from_user.username, 3)
    if vpn_link:
        save_test_user(user_id)
        bot.send_message(message.chat.id, f"🎉 Доступ готов:\n`{vpn_link}`", parse_mode="Markdown")
    else:
        bot.send_message(message.chat.id, "❌ Ошибка при генерации ключа панели.")

@bot.message_handler(func=lambda message: message.text == "💰 Купить подписку")
def handle_buy_subscription(message):
    markup = types.InlineKeyboardMarkup(row_width=1)
    markup.add(
        types.InlineKeyboardButton(PRICE_1_MONTH, callback_data="buy_1"),
        types.InlineKeyboardButton(PRICE_2_MONTH, callback_data="buy_2"),
        types.InlineKeyboardButton(PRICE_6_MONTH, callback_data="buy_6"),
        types.InlineKeyboardButton(PRICE_1_YEAR, callback_data="buy_12")
    )
    bot.send_message(message.chat.id, "👇 Выберите тарифный план:", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith('buy_'))
def handle_payment(call):
    bot.answer_callback_query(call.id)
    days = 30
    if call.data == "buy_2": days = 60
    elif call.data == "buy_6": days = 180
    elif call.data == "buy_12": days = 365
    status_msg = bot.send_message(call.message.chat.id, "⏳ Генерирую ключ...")
    vpn_key = create_vpn_client(call.from_user.id, call.from_user.username, days)
    if vpn_key:
        bot.edit_message_text(f"🎉 Ключ готов:\n`{vpn_key}`", chat_id=call.message.chat.id, message_id=status_msg.message_id, parse_mode="Markdown")
    else:
        bot.edit_message_text("❌ Ошибка сервера.", chat_id=call.message.chat.id, message_id=status_msg.message_id)

@bot.message_handler(func=lambda message: message.text in ["ℹ️ Мой личный кабинет / Статус"])
def handle_status(message):
    bot.send_message(message.chat.id, f"👤 ID: `{message.from_user.id}`", parse_mode="Markdown")

bot.remove_webhook()
print("START")
bot.polling(none_stop=True, timeout=90, long_polling_timeout=90)
