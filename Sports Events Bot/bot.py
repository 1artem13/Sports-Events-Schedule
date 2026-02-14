from scheduler import update_all_sports
import telebot
import psycopg2
from datetime import datetime, timedelta
from telebot import types
import threading
import time
import requests
import os
from pathlib import Path
from psycopg2.extras import DictCursor
from databaseOperations import (
    save_user_if_not_exists, save_reminder, get_user_reminders,
    delete_reminder, delete_all_user_reminders, get_matches_for_reminders,
    mark_reminder_as_notified, get_match_by_id, get_matches_by_sport_for_selection,
    get_matches_as_dicts, save_matches_to_db, remove_past_matches, get_db_connection
)

def load_env():
    env_path = Path('.env')
    if env_path.exists():
        with open(env_path, 'r') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#'):
                    key, value = line.split('=', 1)
                    os.environ[key] = value

# Загружаем .env файл (если он есть)
load_env()

# Теперь читаем токен из окружения
BOT_TOKEN = os.environ.get('BOT_TOKEN')
if not BOT_TOKEN:
    raise ValueError("Нет BOT_TOKEN! Создайте .env файл")

bot = telebot.TeleBot(BOT_TOKEN)

def format_minutes(minutes):
    """Форматирует минуты в читаемый текст"""
    minutes = int(round(minutes))
    
    if minutes < 60:
        return f"{minutes} мин."
    elif minutes < 1440:
        hours = minutes // 60
        mins = minutes % 60
        if mins == 0:
            return f"{hours} ч."
        else:
            return f"{hours} ч. {mins} мин."
    else:
        days = minutes // 1440
        hours = (minutes % 1440) // 60
        mins = minutes % 60
        if mins > 0:
            return f"{days} д. {hours} ч. {mins} мин."
        elif hours > 0:
            return f"{days} д. {hours} ч."
        else:
            return f"{days} д."

def save_user(func):
    """Декоратор для сохранения пользователя в БД"""
    def wrapper(message, *args, **kwargs):
        try:
            save_user_if_not_exists(message.from_user.id, message.from_user.username)
        except Exception as e:
            print(f"Ошибка сохранения пользователя: {e}")
        return func(message, *args, **kwargs)
    return wrapper

user_selection = {}

def get_main_menu():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    btn1 = types.KeyboardButton('⚽ Футбол')
    btn2 = types.KeyboardButton('🏀 Баскетбол')
    btn3 = types.KeyboardButton('🔔 Мои напоминания')
    btn4 = types.KeyboardButton('ℹ️ Помощь')
    markup.row(btn1, btn2)
    markup.row(btn3, btn4)
    return markup

def create_match_selection_keyboard(matches):
    markup = types.InlineKeyboardMarkup(row_width=1)
    
    for match in matches[:10]:
        match_time = match['start_time'].strftime('%d.%m %H:%M')
        btn_text = f"{match['team_home']} vs {match['team_away']} ({match_time})"
        markup.add(types.InlineKeyboardButton(
            btn_text, 
            callback_data=f"sel_match_{match['id']}"
        ))
    
    markup.add(types.InlineKeyboardButton("❌ Отмена", callback_data="cancel"))
    return markup

def create_hours_keyboard(match_id):
    markup = types.InlineKeyboardMarkup(row_width=3)
    
    hours = [1, 2, 3, 6, 12, 24, 48, 72]
    buttons = []
    
    for h in hours:
        text = f"{h} ч." if h < 24 else f"{h//24} д."
        buttons.append(types.InlineKeyboardButton(
            text, 
            callback_data=f"hours_{match_id}_{h}"
        ))
    
    for i in range(0, len(buttons), 3):
        markup.row(*buttons[i:i+3])
    
    markup.row(
        types.InlineKeyboardButton("✏️ Своё время (в минутах)", callback_data=f"custom_time_{match_id}"),
        types.InlineKeyboardButton("❌ Отмена", callback_data="cancel")
    )
    
    return markup

def create_reminders_keyboard(reminders):
    markup = types.InlineKeyboardMarkup(row_width=1)
    
    for rem in reminders:
        match_time = rem['start_time'].strftime('%d.%m %H:%M')
        emoji = "⚽" if rem['sport_type'] == 'football' else "🏀"
        
        hours = rem['remind_before_hours']
        total_minutes = hours * 60
        total_minutes_rounded = int(round(total_minutes))
        
        print(f"Отображение: {hours} часов = {total_minutes} минут -> {total_minutes_rounded} мин.") 
        
        if total_minutes_rounded < 60:
            time_text = f"{total_minutes_rounded} мин."
        elif total_minutes_rounded < 1440:
            hours_display = total_minutes_rounded // 60
            mins_display = total_minutes_rounded % 60
            if mins_display == 0:
                time_text = f"{hours_display} ч."
            else:
                time_text = f"{hours_display} ч. {mins_display} мин."
        else:
            days = total_minutes_rounded // 1440
            hours_left = (total_minutes_rounded % 1440) // 60
            mins_left = total_minutes_rounded % 60
            if mins_left > 0:
                time_text = f"{days} д. {hours_left} ч. {mins_left} мин."
            elif hours_left > 0:
                time_text = f"{days} д. {hours_left} ч."
            else:
                time_text = f"{days} д."
        
        btn_text = f"{emoji} {rem['team_home']} vs {rem['team_away']} ({match_time}, за {time_text})"
        markup.add(types.InlineKeyboardButton(
            f"❌ {btn_text}",
            callback_data=f"del_rem_{rem['id']}"
        ))
    
    markup.row(
        types.InlineKeyboardButton("✅ Удалить все", callback_data="del_all_reminders"),
        types.InlineKeyboardButton("❌ Закрыть", callback_data="close")
    )
    
    return markup

def show_reminders_list(chat_id, message_id, reminders):
    """Показывает список напоминаний"""
    markup = types.InlineKeyboardMarkup(row_width=1)
    
    for rem in reminders:
        match_time = rem['start_time'].strftime('%d.%m %H:%M')
        emoji = "⚽" if rem['sport_type'] == 'football' else "🏀"
        
        hours = rem['remind_before_hours']
        total_minutes = hours * 60
        total_minutes_rounded = int(round(total_minutes))
        
        time_text = format_minutes(total_minutes_rounded)
        
        btn_text = f"{emoji} {rem['team_home']} vs {rem['team_away']} ({match_time}, за {time_text})"
        markup.add(types.InlineKeyboardButton(f"❌ {btn_text}", callback_data=f"del_rem_{rem['id']}"))
    
    markup.row(
        types.InlineKeyboardButton("✅ Удалить все", callback_data="del_all_reminders"),
        types.InlineKeyboardButton("❌ Закрыть", callback_data="close")
    )
    
    text = "🔔 *Ваши напоминания:*\n\n"
    for rem in reminders:
        emoji = "⚽" if rem['sport_type'] == 'football' else "🏀"
        match_time = rem['start_time'].strftime('%d.%m.%Y %H:%M')
        
        hours = rem['remind_before_hours']
        total_minutes = hours * 60
        total_minutes_rounded = int(round(total_minutes))
        
        if total_minutes_rounded < 60:
            time_text = f"{total_minutes_rounded} мин."
        elif total_minutes_rounded < 1440:
            hours_display = total_minutes_rounded // 60
            mins_display = total_minutes_rounded % 60
            if mins_display == 0:
                time_text = f"{hours_display} ч."
            else:
                time_text = f"{hours_display} ч. {mins_display} мин."
        else:
            days = total_minutes_rounded // 1440
            hours_left = (total_minutes_rounded % 1440) // 60
            mins_left = total_minutes_rounded % 60
            if mins_left > 0:
                time_text = f"{days} д. {hours_left} ч. {mins_left} мин."
            elif hours_left > 0:
                time_text = f"{days} д. {hours_left} ч."
            else:
                time_text = f"{days} д."
        
        text += f"{emoji} *{rem['team_home']}* vs *{rem['team_away']}*\n"
        text += f"   📅 {match_time}\n"
        text += f"   ⏰ За {time_text}\n\n"
    
    try:
        bot.edit_message_text(text, chat_id, message_id, parse_mode='Markdown', reply_markup=markup)
    except:
        bot.send_message(chat_id, text, parse_mode='Markdown', reply_markup=markup)


@bot.message_handler(commands=['start'])
@save_user
def start_command(msg):
    welcome_text = (
        f"👋 Привет, {msg.from_user.first_name}!\n\n"
        f"🏆 *Sports Events Bot*\n\n"
        f"*Доступные команды:*\n"
        f"⚽ /football - Футбольные матчи\n"
        f"🏀 /basketball - Баскетбольные матчи\n"
        f"⏰ /setreminder - Установить напоминание\n"
        f"🔔 /myreminders - Мои напоминания\n"
        f"ℹ️ /help - Справка"
    )
    bot.send_message(msg.chat.id, welcome_text, parse_mode='Markdown', reply_markup=get_main_menu())

@bot.message_handler(commands=['help'])
@save_user
def help_command(msg):
    help_text = (
        "📖 *Справка*\n\n"
        "• Нажмите кнопки меню для навигации\n"
        "• /setreminder - установить напоминание\n"
        "• /myreminders - просмотр напоминаний\n"
        "• Можно ввести своё время в минутах"
    )
    bot.send_message(msg.chat.id, help_text, parse_mode='Markdown', reply_markup=get_main_menu())

@bot.message_handler(commands=['football'])
@save_user
def football_command(msg):
    show_matches(msg, "football", "⚽")

@bot.message_handler(commands=['basketball'])
@save_user
def basketball_command(msg):
    show_matches(msg, "basketball", "🏀")

@bot.message_handler(commands=['setreminder'])
@save_user
def set_reminder_command(msg):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.row('⚽ Футбол', '🏀 Баскетбол')
    markup.row('❌ Отмена')
    
    bot.send_message(msg.chat.id, "Выберите вид спорта:", reply_markup=markup)

@bot.message_handler(commands=['myreminders'])
@save_user
def my_reminders_command(msg):
    reminders = get_user_reminders(msg.from_user.id)
    
    if not reminders:
        bot.send_message(msg.chat.id, "📭 Нет активных напоминаний", reply_markup=get_main_menu())
        return
    
    bot.send_message(
        msg.chat.id,
        "🔔 *Ваши напоминания:*",
        parse_mode='Markdown',
        reply_markup=create_reminders_keyboard(reminders)
    )

@bot.message_handler(commands=['test'])
@save_user
def test_command(msg):
    """Тестовая команда для проверки напоминаний"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, team_home, team_away, start_time 
            FROM matches 
            WHERE start_time > NOW() 
            ORDER BY start_time ASC 
            LIMIT 1
        """)
        match = cursor.fetchone()
        cursor.close()
        conn.close()
        
        if match:
            match_id = match[0]
            reminder_id = save_reminder(msg.from_user.id, match_id, 0.0167)
            
            if reminder_id:
                bot.send_message(
                    msg.chat.id,
                    f"✅ Тестовое напоминание создано!\n"
                    f"Матч: {match[1]} vs {match[2]}\n"
                    f"Время: {match[3].strftime('%H:%M')}\n"
                    f"Напомню через 1 минуту!",
                    reply_markup=get_main_menu()
                )
            else:
                bot.send_message(msg.chat.id, "❌ Ошибка", reply_markup=get_main_menu())
        else:
            bot.send_message(msg.chat.id, "❌ Нет матчей", reply_markup=get_main_menu())
            
    except Exception as e:
        print(f"Ошибка в test: {e}")
        bot.send_message(msg.chat.id, "❌ Ошибка", reply_markup=get_main_menu())

@bot.message_handler(commands=['check'])
@save_user
def check_command(msg):
    """Проверка всех напоминаний"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=DictCursor)
        
        cursor.execute("""
            SELECT r.id, r.remind_before_hours, r.notified,
                   m.team_home, m.team_away, m.start_time
            FROM reminders r
            JOIN matches m ON r.match_id = m.id
            JOIN users u ON r.user_id = u.id
            WHERE u.telegram_id = %s
            ORDER BY m.start_time ASC
        """, (msg.from_user.id,))
        
        reminders = cursor.fetchall()
        cursor.close()
        conn.close()
        
        if not reminders:
            bot.send_message(msg.chat.id, "📭 Нет напоминаний")
            return
        
        text = "📋 *Твои напоминания:*\n\n"
        current_time = datetime.now()
        
        for r in reminders:
            match_time = r['start_time']
            remind_time = match_time - timedelta(hours=float(r['remind_before_hours']))
            time_diff = (remind_time - current_time).total_seconds() / 60
            
            status = "✅ отправлено" if r['notified'] else f"⏳ через {time_diff:.0f} мин."
            
            text += (
                f"• {r['team_home']} vs {r['team_away']}\n"
                f"  Матч: {match_time.strftime('%d.%m %H:%M')}\n"
                f"  Напомнить за {r['remind_before_hours']} ч.\n"
                f"  Статус: {status}\n\n"
            )
        
        bot.send_message(msg.chat.id, text, parse_mode='Markdown')
        
    except Exception as e:
        print(f"Ошибка в check: {e}")
        bot.send_message(msg.chat.id, "❌ Ошибка")

@bot.message_handler(commands=['test_reminder'])
@save_user
def test_reminder_command(msg):
    """Тестовая команда для проверки точности"""
    try:
        minutes = 2
        hours = minutes / 60 
        
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, team_home, team_away, start_time 
            FROM matches 
            WHERE start_time > NOW() 
            ORDER BY start_time ASC 
            LIMIT 1
        """)
        match = cursor.fetchone()
        cursor.close()
        conn.close()
        
        if match:
            match_id = match[0]
            reminder_id = save_reminder(msg.from_user.id, match_id, hours)
            
            if reminder_id:
                bot.send_message(
                    msg.chat.id,
                    f"✅ *Тест на {minutes} минуты*\n\n"
                    f"Матч: {match[1]} vs {match[2]}\n"
                    f"Время матча: {match[3].strftime('%H:%M:%S')}\n"
                    f"Значение в БД: {hours} часов\n"
                    f"Это = {format_minutes(minutes)}",
                    parse_mode='Markdown',
                    reply_markup=get_main_menu()
                )
        else:
            bot.send_message(msg.chat.id, "❌ Нет матчей", reply_markup=get_main_menu())
            
    except Exception as e:
        print(f"Ошибка в test_reminder: {e}")
        bot.send_message(msg.chat.id, "❌ Ошибка", reply_markup=get_main_menu())

def show_matches(msg, sport_type, emoji):
    try:
        matches = get_matches_as_dicts(sport_type)
        if not matches:
            bot.send_message(msg.chat.id, f"{emoji} Нет предстоящих матчей", reply_markup=get_main_menu())
            return
        
        text = f"{emoji} *Ближайшие матчи:*\n\n"
        for match in matches:
            match_time = match['start_time'].strftime('%d.%m.%Y %H:%M')
            text += f"• *{match['team_home']}* vs *{match['team_away']}*\n  🏆 {match['tournament']}\n  📅 {match_time}\n\n"
        
        if len(text) > 4000:
            parts = [text[i:i+4000] for i in range(0, len(text), 4000)]
            for part in parts:
                bot.send_message(msg.chat.id, part, parse_mode='Markdown')
        else:
            bot.send_message(msg.chat.id, text, parse_mode='Markdown')
            
        bot.send_message(msg.chat.id, "Используйте /setreminder для напоминаний", reply_markup=get_main_menu())
        
    except Exception as e:
        print(f"Ошибка: {e}")
        bot.send_message(msg.chat.id, "❌ Ошибка загрузки", reply_markup=get_main_menu())

@bot.message_handler(func=lambda msg: msg.text in ['⚽ Футбол', '🏀 Баскетбол'])
@save_user
def handle_sport_selection(msg):
    sport = "football" if msg.text == '⚽ Футбол' else "basketball"
    matches = get_matches_by_sport_for_selection(sport)
    
    if not matches:
        bot.send_message(msg.chat.id, "😕 Нет предстоящих матчей", reply_markup=get_main_menu())
        return
    
    bot.send_message(msg.chat.id, "Выберите матч:", reply_markup=create_match_selection_keyboard(matches))

@bot.message_handler(func=lambda msg: msg.chat.id in user_selection and msg.text and msg.text.isdigit())
def handle_custom_time(msg):
    try:
        minutes = int(msg.text)
        
        if minutes < 1 or minutes > 10080:
            bot.send_message(msg.chat.id, "❌ Введите число от 1 до 10080", reply_markup=types.ForceReply())
            return
        
        match_id = user_selection.get(msg.from_user.id)
        if not match_id:
            bot.send_message(msg.chat.id, "❌ Сессия истекла", reply_markup=get_main_menu())
            return
        
        hours = minutes / 60  
        waiting = bot.send_message(msg.chat.id, "⏳ Устанавливаю...")
        
        reminder_id = save_reminder(msg.from_user.id, match_id, hours) 
        
        if reminder_id:
            match = get_match_by_id(match_id)
            if match:
                match_time = match['start_time'].strftime('%d.%m.%Y %H:%M')
                emoji = "⚽" if match['sport_type'] == 'football' else "🏀"
                
                time_text = format_minutes(minutes)
                
                markup = types.InlineKeyboardMarkup()
                markup.row(
                    types.InlineKeyboardButton("📋 Мои напоминания", callback_data="show_reminders"),
                    types.InlineKeyboardButton("✅ Ещё", callback_data="new_reminder")
                )
                
                bot.edit_message_text(
                    f"✅ *Установлено!*\n\n{emoji} *{match['team_home']}* vs *{match['team_away']}*\n📅 {match_time}\n⏰ За {time_text}",
                    msg.chat.id,
                    waiting.message_id,
                    parse_mode='Markdown',
                    reply_markup=markup
                )
                
                del user_selection[msg.from_user.id]
        else:
            bot.edit_message_text("❌ Ошибка", msg.chat.id, waiting.message_id)
            
    except Exception as e:
        print(f"Ошибка: {e}")
        bot.send_message(msg.chat.id, "❌ Ошибка", reply_markup=get_main_menu())


@bot.message_handler(func=lambda msg: True)
@save_user
def handle_text(msg):
    if msg.text == "🔔 Мои напоминания":
        my_reminders_command(msg)
    elif msg.text == "ℹ️ Помощь":
        help_command(msg)
    elif msg.text == "❌ Отмена":
        bot.send_message(msg.chat.id, "❌ Отменено", reply_markup=get_main_menu())
    else:
        bot.send_message(msg.chat.id, "Используйте кнопки меню", reply_markup=get_main_menu())


@bot.callback_query_handler(func=lambda call: True)
def handle_callback(call):
    chat_id = call.message.chat.id
    user_id = call.from_user.id
    data = call.data
    
    try:
        print(f"Callback: {data}")
        bot.answer_callback_query(call.id)
        
        if data == "cancel":
            bot.delete_message(chat_id, call.message.message_id)
            bot.send_message(chat_id, "❌ Отменено", reply_markup=get_main_menu())
            
        elif data == "close":
            bot.delete_message(chat_id, call.message.message_id)
            
        elif data == "new_reminder":
            bot.delete_message(chat_id, call.message.message_id)
            set_reminder_command(call.message)
            
        elif data == "show_reminders":
            reminders = get_user_reminders(user_id)
            if reminders:
                show_reminders_list(chat_id, call.message.message_id, reminders)
            else:
                bot.edit_message_text("📭 Нет напоминаний", chat_id, call.message.message_id)
                
        elif data == "del_all_reminders":
            markup = types.InlineKeyboardMarkup()
            markup.row(
                types.InlineKeyboardButton("⚠️ Да", callback_data="confirm_del_all"),
                types.InlineKeyboardButton("❌ Нет", callback_data="show_reminders")
            )
            bot.edit_message_text("⚠️ Удалить все?", chat_id, call.message.message_id, reply_markup=markup)
            
        elif data == "confirm_del_all":
            count = delete_all_user_reminders(user_id)
            bot.delete_message(chat_id, call.message.message_id)
            bot.send_message(chat_id, f"🗑 Удалено {count}", reply_markup=get_main_menu())
            
        elif data.startswith("custom_time_"):
            match_id = int(data.split("_")[2])
            user_selection[user_id] = match_id
            bot.edit_message_text("⏰ Введите минуты:", chat_id, call.message.message_id)
            bot.send_message(chat_id, "✏️ Напишите число:", reply_markup=types.ForceReply())
            
        elif data.startswith("sel_match_"):
            match_id = int(data.split("_")[2])
            user_selection[user_id] = match_id
            bot.edit_message_text("⏰ Выберите время:", chat_id, call.message.message_id, 
                                reply_markup=create_hours_keyboard(match_id))
            
        elif data.startswith("hours_"):
            parts = data.split("_")
            match_id = int(parts[1])
            hours = int(parts[2])
            
            reminder_id = save_reminder(user_id, match_id, hours)
            
            if reminder_id:
                match = get_match_by_id(match_id)
                if match:
                    match_time = match['start_time'].strftime('%d.%m.%Y %H:%M')
                    emoji = "⚽" if match['sport_type'] == 'football' else "🏀"
                    
                    if hours < 24:
                        time_text = f"{hours} ч."
                    else:
                        days = hours // 24
                        remaining_hours = hours % 24
                        if remaining_hours > 0:
                            time_text = f"{days} д. {remaining_hours} ч."
                        else:
                            time_text = f"{days} д."
                    
                    markup = types.InlineKeyboardMarkup()
                    markup.row(
                        types.InlineKeyboardButton("📋 Мои", callback_data="show_reminders"),
                        types.InlineKeyboardButton("✅ Ещё", callback_data="new_reminder")
                    )
                    
                    bot.edit_message_text(
                        f"✅ *Установлено!*\n\n{emoji} *{match['team_home']}* vs *{match['team_away']}*\n📅 {match_time}\n⏰ За {time_text}",
                        chat_id,
                        call.message.message_id,
                        parse_mode='Markdown',
                        reply_markup=markup
                    )
            else:
                bot.edit_message_text("❌ Ошибка", chat_id, call.message.message_id)
                
        elif data.startswith("del_rem_") and data != "del_all_reminders":
            reminder_id = int(data.split("_")[2])
            markup = types.InlineKeyboardMarkup()
            markup.row(
                types.InlineKeyboardButton("✅ Да", callback_data=f"confirm_del_{reminder_id}"),
                types.InlineKeyboardButton("❌ Нет", callback_data="show_reminders")
            )
            bot.edit_message_text("🗑 Удалить?", chat_id, call.message.message_id, reply_markup=markup)
            
        elif data.startswith("confirm_del_"):
            reminder_id = int(data.split("_")[2])
            if delete_reminder(reminder_id, user_id):
                reminders = get_user_reminders(user_id)
                if reminders:
                    show_reminders_list(chat_id, call.message.message_id, reminders)
                else:
                    bot.edit_message_text("📭 Все удалены", chat_id, call.message.message_id)
            else:
                bot.answer_callback_query(call.id, "❌ Ошибка")
                
    except Exception as e:
        print(f"Callback error: {e}")
        import traceback
        traceback.print_exc()


def check_reminders():
    """Поток для проверки напоминаний"""
    print("✅ Поток проверки напоминаний запущен")
    
    while True:
        try:
            reminders = get_matches_for_reminders()
            
            for rem in reminders:
                match = rem['match']
                match_time = match['start_time'].strftime('%d.%m.%Y %H:%M')
                emoji = "⚽" if match['sport_type'] == 'football' else "🏀"
                
                remind_before = rem['remind_before_hours']
                total_minutes = int(round(remind_before * 60))
                
                if total_minutes < 60:
                    time_text = f"{total_minutes} мин."
                elif total_minutes < 1440:
                    hours_display = total_minutes // 60
                    mins_display = total_minutes % 60
                    if mins_display == 0:
                        time_text = f"{hours_display} ч."
                    else:
                        time_text = f"{hours_display} ч. {mins_display} мин."
                else:
                    days = total_minutes // 1440
                    hours_left = (total_minutes % 1440) // 60
                    mins_left = total_minutes % 60
                    if mins_left > 0:
                        time_text = f"{days} д. {hours_left} ч. {mins_left} мин."
                    elif hours_left > 0:
                        time_text = f"{days} д. {hours_left} ч."
                    else:
                        time_text = f"{days} д."
                
                text = (
                    f"⏰ *НАПОМИНАНИЕ!*\n\n"
                    f"{emoji} *{match['team_home']}* vs *{match['team_away']}*\n"
                    f"🏆 {match['tournament']}\n"
                    f"📅 {match_time}\n\n"
                    f"⚡ Матч через {time_text}!"
                )
                
                try:
                    bot.send_message(rem['telegram_id'], text, parse_mode='Markdown')
                    mark_reminder_as_notified(rem['reminder_id'])
                    print(f"✅ Напоминание отправлено пользователю {rem['telegram_id']} за {time_text}")
                except Exception as e:
                    print(f"❌ Ошибка отправки: {e}")
            
            time.sleep(30)
            
        except Exception as e:
            print(f"❌ Ошибка в потоке: {e}")
            time.sleep(30)



reminder_thread = threading.Thread(target=check_reminders, daemon=True)
reminder_thread.start()

try:
    bot.remove_webhook()
    time.sleep(1)
except:
    pass

print("🤖 Бот запускается...")
if __name__ == "__main__":
    try:
        bot.polling(none_stop=True, interval=0, timeout=20)
    except Exception as e:
        print(f"❌ Ошибка: {e}")
        time.sleep(5)
        bot.polling(none_stop=True, interval=0, timeout=20)