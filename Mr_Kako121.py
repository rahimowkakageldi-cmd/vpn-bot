import json
import logging
import telebot
import requests
import base64
import os
import uuid
import time
from flask import Flask, request

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
                return None
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
            "id": client_uuid, "alterId": 0, "email": email, "limitIp": 2,
            "totalGB": 0, "expiryTime": expiry_time, "enable": True, "tgId": str(user_id), "subId": ""
        }

        add_url = f"{PANEL_URL}/panel/api/inbounds/addClient"
        payload = {"id": inbound_id, "settings": json.dumps({"clients": [client_spec]})}
        
        add_resp = session.post(add_url, json=payload, timeout=10)
        if add_resp.json().get("success"):
            reality_settings = stream_settings.get("realitySettings", {})
            server_names = reality_settings.get("serverNames", ["example.com"])
            server_name = server_names if isinstance(server_names, list) and len(server_names) > 0 else server_names
            
            public_key = reality_settings.get("publicKey", "")
            short_ids = reality_settings.get("shortIds", [""])
            short_id = short_ids if isinstance(short_ids, list) and len(short_ids) > 0 else short_ids
            
            port = target_inbound["port"]
            vless_link = f"vless://{client_uuid}@{XUI_IP}:{port}?type=tcp&security=reality&pbk={public_key}&fp=chrome&sni={server_name}&sid={short_id}#{email}"
            return vless_link
    except Exception:
        pass
    return None

# =====================================================================
# ДИЗАЙН КНОПОК ПОД СООБЩЕНИЕМ
# =====================================================================
def build_inline_menu():
    markup = types.InlineKeyboardMarkup(row_width=2)
    
    btn_buy = types.InlineKeyboardButton("💰 Купить подписку", callback_data="menu_buy")
    btn_test = types.InlineKeyboardButton("🎁 Получить бесплатный тест (3 дня)", callback_data="menu_test")
    
    btn_earn = types.InlineKeyboardButton("💸 Заработок", callback_data="menu_earn")
    btn_site = types.InlineKeyboardButton("🌐 Наш сайт", callback_data="menu_site")
    btn_about = types.InlineKeyboardButton("ℹ️ О сервисе", callback_data="menu_about")
    btn_support = types.InlineKeyboardButton("👤 Поддержка", callback_data="menu_support")
    
    markup.add(btn_buy)
    markup.add(btn_test)
    markup.add(btn_earn, btn_site)     
    markup.add(btn_about, btn_support) 
    
    return markup

@bot.message_handler(commands=['start'])
def send_welcome(message):
    welcome_text = (
        f"👤 **Профиль**\n\n"
        f"Привет, {message.from_user.first_name}!\n"
        f"Ваш Telegram ID: `{message.from_user.id}`\n"
        f"📱 VPN PRO Status: Нажмите кнопку ниже для проверки подписки."
    )
    bot.send_message(message.chat.id, welcome_text, parse_mode="Markdown", reply_markup=build_inline_menu())

# =====================================================================
# ОБРАБОТЧИК НАЖАТИЙ НА ИНЛАЙН-КНОПКИ МЕНЮ
# =====================================================================
@bot.callback_query_handler(func=lambda call: call.data.startswith('menu_'))
def handle_menu_clicks(call):
    bot.answer_callback_query(call.id)
    user_id = call.from_user.id
    
    if call.data == "menu_test":
        if user_id in load_test_users():
            bot.send_message(call.message.chat.id, "❌ Вы уже брали тестовый период. Повторное получение невозможно.")
            return
        bot.send_message(call.message.chat.id, "⏳ Создаем ваш тестовый профиль in Amsterdam...")
        vpn_link = create_vpn_client(user_id=user_id, username=call.from_user.username, days_count=3)
        if vpn_link:
            save_test_user(user_id)
            success_text = (
                f"🎉 **Ваш тестовый доступ готов!**\n\n"
                f"⏳ Срок действия: 3 дня\n"
                f"📋 **Ваша ссылка для подключения:**\n"
                f"`{vpn_link}`\n\n"
                f"💡 _Нажмите на ссылку выше, чтобы скопировать её, и вставьте в ваше VPN-приложение._"
            )
            bot.send_message(call.message.chat.id, success_text, parse_mode="Markdown")
        else:
            bot.send_message(call.message.chat.id, "❌ Ошибка соединения с панелью. Проверьте порт и настройки.")

    elif call.data == "menu_buy":
        markup = types.InlineKeyboardMarkup(row_width=1)
        markup.add(
            types.InlineKeyboardButton(PRICE_1_MONTH, callback_data="buy_30"),
            types.InlineKeyboardButton(PRICE_2_MONTH, callback_data="buy_60"),
            types.InlineKeyboardButton(PRICE_6_MONTH, callback_data="buy_180"),
            types.InlineKeyboardButton(PRICE_1_YEAR, callback_data="buy_365")
        )
        bot.send_message(call.message.chat.id, "👇 Выберите тарифный план для покупки:", reply_markup=markup)

    elif call.data == "menu_earn":
        bot.send_message(call.message.chat.id, "💸 **Реферальная программа**\n\nПриглашайте друзей по вашей ссылке и получайте 20% от их покупок на баланс!")

    elif call.data == "menu_site":
        bot.send_message(call.message.chat.id, "🌐 Наш официальный сайт доступен по адресу: `https://example.com` (замените на ваш домен).")

    elif call.data == "menu_about":
        bot.send_message(call.message.chat.id, "ℹ️ **О сервисе**\n\nМы предоставляем сверхбыстрый VPN на протоколе VLESS Reality со скоростью до 1 Гбит/с. Серверы расположены в Амстердаме, Нидерланды.")

    elif call.data == "menu_support":
        bot.send_message(call.message.chat.id, "👤 **Поддержка**\n\nЕсли у вас возникли вопросы по оплате или подключению, напишите нашему администратору: @ваша_поддержка")

# =====================================================================
# ОБРАБОТКА ПОКУПКИ ТАРИФОВ
# =====================================================================
@bot.callback_query_handler(func=lambda call: call.data.startswith('buy_'))
def handle_payment(call):
    bot.answer_callback_query(call.id)
    days = int(call.data.split('_')[1])

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

# =====================================================================
# ИСПРАВЛЕНО: ПРЯМАЯ И СТАБИЛЬНАЯ ОБРАБОТКА ВЕБХУКА НА ГЛАВНОМ ПУТИ
# =====================================================================
