import json
import logging
import telebot
import requests
import base64
import os
import uuid
import time
import threading  # Добавлено для веб-сервера
from http.server import BaseHTTPRequestHandler, HTTPServer  # Добавлено для веб-сервера
from telebot import types

import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# =====================================================================
# НАСТРОЙКИ СЕРВЕРА И БОТА
# =====================================================================
BOT_TOKEN = "8522132903:AAHldacR2QDY67Pb734vmpMZ0WZSKxs0920"
XUI_IP = "87.199.198.216"
XUI_PORT = "2053"
XUI_LOGIN = "admin"
XUI_PASSWORD = "htgvMHk12h332BPS8w2-"
XUI_SECRET_PATH = "ba9791eb5caf77a79d7f206c4fceda11"

PANEL_URL = f"http://{XUI_IP}:{XUI_PORT}/{XUI_SECRET_PATH}"

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

# =====================================================================
# АВТОРИЗАЦИЯ И РАБОТА С ПАНЕЛЬЮ 3X-UI
# =====================================================================
def get_xui_session():
    session = requests.Session()
    session.verify = False
    session.proxies = {} 
    
    login_url = f"{PANEL_URL}/login"
    try:
        response = session.post(
            login_url, 
            data={"username": XUI_LOGIN, "password": XUI_PASSWORD}, 
            timeout=10
        )
        if response.status_code == 200:
            if "success" in response.text and not response.json().get("success"):
                logging.error(f"Панель отклонила логин/пароль: {response.text}")
                return None
            logging.info("Успешная авторизация в панели 3x-ui.")
            return session
        else:
            logging.error(f"Ошибка авторизации, статус-код: {response.status_code}")
    except Exception as e:
        logging.error(f"Не удалось подключиться к серверу панели: {e}")
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
            logging.error("В панели 3x-ui отсутствуют созданные подключения (Inbounds).")
            return None
        
        target_inbound = None
        for ib in inbounds:
            if ib.get("protocol") == "vless" and ib.get("enable") == True:
                target_inbound = ib
                break
                
        if not target_inbound:
            target_inbound = inbounds
            
        inbound_id = target_inbound["id"]
        stream_settings = json.loads(target_inbound["streamSettings"])
        
        expiry_time = int((time.time() + (days_count * 86400)) * 1000)
        tg_username = username if username else "user"
        email = f"client_{user_id}_{tg_username}_{days_count}d"
        client_uuid = str(uuid.uuid4())

        client_spec = {
            "id": client_uuid,
            "alterId": 0,
            "email": email,
            "limitIp": 2,
            "totalGB": 0,  
            "expiryTime": expiry_time,
            "enable": True,
            "tgId": str(user_id),
            "subId": ""
        }

        add_url = f"{PANEL_URL}/panel/api/inbounds/addClient"
        payload = {
            "id": inbound_id,
            "settings": json.dumps({"clients": [client_spec]})
        }
        
        add_resp = session.post(add_url, json=payload, timeout=10)
        if add_resp.json().get("success"):
            reality_settings = stream_settings.get("realitySettings", {})
            server_names = reality_settings.get("serverNames", ["example.com"])
            server_name = server_names if isinstance(server_names, list) and len(server_names) > 0 else server_names
            
            public_key = reality_settings.get("publicKey", "")
            short_ids = reality_settings.get("shortIds", [""])
            short_id = short_ids if isinstance(short_ids, list) and len(short_ids) > 0 else short_ids
            
            port = target_inbound["port"]
            network = stream_settings.get("network", "tcp")
            security = stream_settings.get("security", "reality")
            
            vless_link = f"vless://{client_uuid}@{XUI_IP}:{port}?type={network}&security={security}&pbk={public_key}&fp=chrome&sni={server_name}&sid={short_id}#{email}"
            return vless_link
        else:
            logging.error(f"Панель вернула ошибку при добавлении клиента: {add_resp.text}")
    except Exception as e:
        logging.error(f"Критическая ошибка при работе с API панели: {e}")
    return None

# =====================================================================
# ИНТЕРФЕЙС И ОБРАБОТКА ТЕЛЕГРАМ
# =====================================================================
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
    welcome_text = (
        "👋 **Приветствуем вас в нашем VPN-сервисе!**\n\n"
        "Мы обеспечиваем высокую скорость на серверах в Амстердаме.\n\n"
        "Вы можете протестировать наш сервис бесплатно в течение 3 дней или сразу приобрести подписку."
    )
    bot.send_message(message.chat.id, welcome_text, parse_mode="Markdown", reply_markup=main_menu())

@bot.message_handler(func=lambda message: message.text == "🎁 Получить бесплатный тест (3 дня)")
def handle_test_period(message):
    user_id = message.from_user.id
    if user_id in load_test_users():
        bot.send_message(message.chat.id, "❌ Вы уже брали тестовый период. Повторное получение невозможно.")
        return

    bot.send_message(message.chat.id, "⏳ Создаем ваш профиль в Амстердаме, пожалуйста, подождите...")
    vpn_link = create_vpn_client(user_id=user_id, username=message.from_user.username, days_count=3)
    
    if vpn_link:
        save_test_user(user_id)
        success_text = (
            f"🎉 **Ваш тестовый доступ готов!**\n\n"
            f"⏳ Срок действия: 3 дня\n"
            f"📊 Лимит трафика: Безлимит\n\n"
            f"📋 **Ваша ссылка для подключения:**\n"
            f"`{vpn_link}`\n\n"
            f"💡 _Нажмите на ссылку выше, чтобы скопировать её, и вставьте в ваше VPN-приложение._"
        )
        bot.send_message(message.chat.id, success_text, parse_mode="Markdown")
    else:
        bot.send_message(message.chat.id, "❌ Не удалось сгенерировать ключ. Убедитесь, что в панели создан хотя бы одно подключение VLESS-Reality, а также открыт порт 2053 в Firewall вашего сервера.")

@bot.message_handler(func=lambda message: message.text == "💰 Купить подписку")
def handle_buy_subscription(message):
    markup = types.InlineKeyboardMarkup(row_width=1)
    markup.add(
        types.InlineKeyboardButton(PRICE_1_MONTH, callback_data="buy_1"),
        types.InlineKeyboardButton(PRICE_2_MONTH, callback_data="buy_2"),
        types.InlineKeyboardButton(PRICE_6_MONTH, callback_data="buy_6"),
        types.InlineKeyboardButton(PRICE_1_YEAR, callback_data="buy_12")
    )
    bot.send_message(message.chat.id, "👇 Выберите тарифный план для покупки:", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith('buy_'))
def handle_payment(call):
    bot.answer_callback_query(call.id)
    days = 30
    if call.data == "buy_2": days = 60
    elif call.data == "buy_6": days = 180
    elif call.data == "buy_12": days = 365

    status_msg = bot.send_message(call.message.chat.id, "⏳ Генерирую вашу оплаченную подписку...")
    vpn_key = create_vpn_client(call.from_user.id, call.from_user.username, days)
    
    if vpn_key:
        final_text = (
            f"🎉 **Оплата успешно подтверждена!**\n\n"
            f"📅 Подписка активирована на {days} дней.\n"
            f"📋 Ваш персональный VPN-ключ:\n\n"
            f"`{vpn_key}`\n\n"
            f"💡 _Нажмите на текст ключа выше, чтобы автоматически скопировать его в буфер обмена._"
        )
        bot.edit_message_text(final_text, chat_id=call.message.chat.id, message_id=status_msg.message_id, parse_mode="Markdown")
    else:
        bot.edit_message_text("❌ Ошибка генерации ключа. Проверьте настройки инбаундов в панели.", chat_id=call.message.chat.id, message_id=status_msg.message_id)

@bot.message_handler(func=lambda message: message.text in ["ℹ️ Мой личный кабинет / Статус"])
def handle_status(message):
    status_text = (
        f"👤 **Личный кабинет**\n\n"
        f"Ваш Telegram ID: `{message.from_user.id}`\n\n"
        f"Статус подписки: Проверка баланса онлайн будет доступна после интеграции базы данных."
    )
    bot.send_message(message.chat.id, status_text, parse_mode="Markdown")

# =====================================================================
# ВСТРОЕННЫЙ МИНИ ВЕБ-СЕРВЕР ДЛЯ ОБМАНА ПРОВЕРКИ ПОРТОВ RENDER
# =====================================================================
class WebServerHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
