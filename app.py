import telebot
import sqlite3
import os
import logging
from datetime import datetime
import time
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton

# Настройка логирования
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Токен из переменных окружения
TOKEN = os.environ.get('BOT_TOKEN')
if not TOKEN:
    logger.error("❌ BOT_TOKEN не установлен!")
    exit(1)

bot = telebot.TeleBot(TOKEN)
logger.info("🎨 Бот для учета краски запускается...")

# Инициализация базы данных
def init_db():
    try:
        conn = sqlite3.connect('paint_db.sqlite')
        cursor = conn.cursor()
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS paints (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                color_code TEXT NOT NULL,
                effect TEXT NOT NULL,
                quantity REAL NOT NULL,
                unit TEXT DEFAULT 'kg',
                last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS transactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                paint_id INTEGER,
                type TEXT NOT NULL,
                amount REAL NOT NULL,
                date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (paint_id) REFERENCES paints (id)
            )
        ''')
        
        conn.commit()
        conn.close()
        logger.info("✅ База данных инициализирована")
    except Exception as e:
        logger.error(f"❌ Ошибка инициализации БД: {e}")

# Доступные эффекты
EFFECTS = {
    'matt': '🟢 Матовый',
    'gloss': '🔵 Глянец', 
    'moire': '🟣 Муар',
    'texture': '🟠 Шагрень',
    'varnish': '⚪ Лак'
}

# Хранилище временных данных
user_states = {}

# Создание главного меню
def create_main_keyboard():
    keyboard = ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    buttons = [
        KeyboardButton('🎨 Добавить краску'),
        KeyboardButton('📋 Список красок'),
        KeyboardButton('📤 Списать краску'),
        KeyboardButton('🔍 Поиск по коду'),
        KeyboardButton('📊 Статистика'),
        KeyboardButton('ℹ️ Помощь')
    ]
    keyboard.add(*buttons)
    return keyboard

# Создание клавиатуры для выбора эффекта
def create_effect_keyboard():
    keyboard = InlineKeyboardMarkup(row_width=2)
    buttons = []
    for effect_key, effect_name in EFFECTS.items():
        buttons.append(InlineKeyboardButton(effect_name, callback_data=f"effect_{effect_key}"))
    keyboard.add(*buttons)
    return keyboard

# Команда /start
@bot.message_handler(commands=['start'])
def send_welcome(message):
    welcome_text = """
🎨 <b>Добро пожаловать в PaintStock Bot!</b>

Простой и удобный учет порошковой краски и лаков.

<b>Возможности:</b>
• Учет по кодам (RAL, цифровые, буквенные)
• 5 видов эффектов
• Учет веса в кг
• Поиск и статистика

Выберите действие:
    """
    bot.send_message(
        message.chat.id, 
        welcome_text,
        parse_mode='HTML',
        reply_markup=create_main_keyboard()
    )
    logger.info(f"👤 Пользователь {message.chat.id} запустил бота")

# Обработка главного меню
@bot.message_handler(func=lambda message: True)
def handle_main_menu(message):
    user_id = message.chat.id
    text = message.text
    
    if text == '🎨 Добавить краску':
        add_paint_step1(message)
    elif text == '📋 Список красок':
        list_paints(message)
    elif text == '📤 Списать краску':
        use_paint(message)
    elif text == '🔍 Поиск по коду':
        search_paint(message)
    elif text == '📊 Статистика':
        show_stats(message)
    elif text == 'ℹ️ Помощь':
        show_help(message)
    else:
        bot.send_message(user_id, "Используйте кнопки меню для навигации 📱", 
                        reply_markup=create_main_keyboard())

# Добавление краски - Шаг 1
def add_paint_step1(message):
    user_id = message.chat.id
    user_states[user_id] = {'step': 'waiting_code'}
    
    msg = bot.send_message(
        user_id, 
        "🎨 <b>Введите код или название краски:</b>\n\nПримеры:\n• 3005\n• прозрачный\n• черный матовый",
        parse_mode='HTML'
    )
    bot.register_next_step_handler(msg, add_paint_step2)

# Шаг 2: Получение кода
def add_paint_step2(message):
    try:
        user_id = message.chat.id
        color_code = message.text.strip()
        
        if not color_code:
            bot.send_message(user_id, "❌ Код не может быть пустым!", reply_markup=create_main_keyboard())
            if user_id in user_states:
                del user_states[user_id]
            return
        
        user_states[user_id] = {
            'step': 'waiting_effect',
            'color_code': color_code
        }
        
        keyboard = create_effect_keyboard()
        bot.send_message(user_id, f"🎨 Код: <b>{color_code}</b>\n\nВыберите эффект:", 
                        parse_mode='HTML', reply_markup=keyboard)
        
    except Exception as e:
        logger.error(f"Ошибка в add_paint_step2: {e}")
        bot.send_message(user_id, "❌ Произошла ошибка", reply_markup=create_main_keyboard())
        if user_id in user_states:
            del user_states[user_id]

# Обработчик выбора эффекта
@bot.callback_query_handler(func=lambda call: call.data.startswith('effect_'))
def handle_effect_selection(call):
    try:
        user_id = call.message.chat.id
        
        if user_id not in user_states or user_states[user_id]['step'] != 'waiting_effect':
            bot.answer_callback_query(call.id, "❌ Сессия устарела")
            return
        
        effect_key = call.data.replace('effect_', '')
        effect_name = EFFECTS.get(effect_key)
        
        if not effect_name:
            bot.answer_callback_query(call.id, "❌ Неверный эффект")
            return
        
        user_states[user_id] = {
            'step': 'waiting_weight',
            'color_code': user_states[user_id]['color_code'],
            'effect': effect_name.replace('🟢 ', '').replace('🔵 ', '').replace('🟣 ', '').replace('🟠 ', '').replace('⚪ ', '')
        }
        
        bot.edit_message_text(
            chat_id=user_id,
            message_id=call.message.message_id,
            text=f"🎨 Код: <b>{user_states[user_id]['color_code']}</b>\n✅ Эффект: {effect_name}",
            parse_mode='HTML'
        )
        
        msg = bot.send_message(user_id, "⚖️ <b>Введите вес в кг:</b>\n\nПример: 5.0, 10.5, 25", 
                              parse_mode='HTML')
        bot.register_next_step_handler(msg, add_paint_step3)
        
        bot.answer_callback_query(call.id, f"Выбран: {effect_name}")
        
    except Exception as e:
        logger.error(f"Ошибка в handle_effect_selection: {e}")
        bot.answer_callback_query(call.id, "❌ Ошибка")

# Шаг 3: Получение веса
def add_paint_step3(message):
    user_id = message.chat.id
    try:
        if user_id not in user_states or user_states[user_id]['step'] != 'waiting_weight':
            bot.send_message(user_id, "❌ Сессия устарела", reply_markup=create_main_keyboard())
            return
        
        weight = float(message.text.strip())
        color_code = user_states[user_id]['color_code']
        effect = user_states[user_id]['effect']
        
        if weight <= 0:
            bot.send_message(user_id, "❌ Вес должен быть положительным!", reply_markup=create_main_keyboard())
            del user_states[user_id]
            return
        
        conn = sqlite3.connect('paint_db.sqlite')
        cursor = conn.cursor()
        
        # Проверяем существование
        cursor.execute('SELECT id, quantity FROM paints WHERE color_code = ? AND effect = ?', (color_code, effect))
        existing = cursor.fetchone()
        
        if existing:
            # Обновляем существующую
            cursor.execute('UPDATE paints SET quantity = quantity + ? WHERE id = ?', (weight, existing[0]))
            paint_id = existing[0]
            new_quantity = existing[1] + weight
            action_text = "обновлена"
        else:
            # Добавляем новую
            cursor.execute('INSERT INTO paints (color_code, effect, quantity) VALUES (?, ?, ?)', 
                         (color_code, effect, weight))
            paint_id = cursor.lastrowid
            new_quantity = weight
            action_text = "добавлена"
        
        # Добавляем транзакцию
        cursor.execute('INSERT INTO transactions (paint_id, type, amount) VALUES (?, ?, ?)',
                     (paint_id, 'add', weight))
        
        conn.commit()
        conn.close()
        
        bot.send_message(
            user_id,
            f"✅ Краска <b>{action_text}!</b>\n\n"
            f"🎨 Код: <b>{color_code}</b>\n"
            f"✨ Эффект: <b>{effect}</b>\n"
            f"📦 Вес: <b>{weight} кг</b>\n"
            f"📊 Теперь: <b>{new_quantity} кг</b>",
            parse_mode='HTML',
            reply_markup=create_main_keyboard()
        )
        
        logger.info(f"➕ Добавлена краска: {color_code} ({effect}) - {weight}кг")
        
    except ValueError:
        bot.send_message(user_id, "❌ Неверный формат веса!", reply_markup=create_main_keyboard())
    except Exception as e:
        logger.error(f"Ошибка в add_paint_step3: {e}")
        bot.send_message(user_id, "❌ Ошибка при сохранении", reply_markup=create_main_keyboard())
    finally:
        if user_id in user_states:
            del user_states[user_id]

# Список всех красок
def list_paints(message):
    try:
        conn = sqlite3.connect('paint_db.sqlite')
        cursor = conn.cursor()
        cursor.execute('SELECT color_code, effect, quantity FROM paints ORDER BY color_code, effect')
        paints = cursor.fetchall()
        conn.close()
        
        if not paints:
            bot.send_message(message.chat.id, "📭 <b>Склад пуст</b>\n\nДобавьте первую краску!",
                           parse_mode='HTML', reply_markup=create_main_keyboard())
            return
        
        response = "🎨 <b>Склад порошковой краски:</b>\n\n"
        current_code = None
        
        for color_code, effect, quantity in paints:
            if color_code != current_code:
                current_code = color_code
                response += f"\n🔸 <b>{color_code}:</b>\n"
            response += f"   • {effect}: {quantity} кг\n"
        
        bot.send_message(message.chat.id, response, parse_mode='HTML', reply_markup=create_main_keyboard())
        
    except Exception as e:
        logger.error(f"Ошибка в list_paints: {e}")
        bot.send_message(message.chat.id, "❌ Ошибка при загрузке списка", reply_markup=create_main_keyboard())

# Поиск краски
def search_paint(message):
    msg = bot.send_message(message.chat.id, "🔍 <b>Введите код для поиска:</b>", parse_mode='HTML')
    bot.register_next_step_handler(msg, process_search)

def process_search(message):
    try:
        color_code = message.text.strip()
        conn = sqlite3.connect('paint_db.sqlite')
        cursor = conn.cursor()
        cursor.execute('SELECT effect, quantity FROM paints WHERE color_code = ? ORDER BY effect', (color_code,))
        paints = cursor.fetchall()
        conn.close()
        
        if not paints:
            bot.send_message(message.chat.id, f"❌ Код '<b>{color_code}</b>' не найден", 
                           parse_mode='HTML', reply_markup=create_main_keyboard())
            return
        
        response = f"🔍 <b>Найдено по коду '{color_code}':</b>\n\n"
        total = 0
        for effect, quantity in paints:
            response += f"• {effect}: {quantity} кг\n"
            total += quantity
        
        response += f"\n📦 <b>Итого: {total} кг</b>"
        bot.send_message(message.chat.id, response, parse_mode='HTML', reply_markup=create_main_keyboard())
        
    except Exception as e:
        logger.error(f"Ошибка в process_search: {e}")
        bot.send_message(message.chat.id, "❌ Ошибка при поиске", reply_markup=create_main_keyboard())

# Списание краски
def use_paint(message):
    msg = bot.send_message(
        message.chat.id, 
        "📤 <b>Введите данные для списания:</b>\n\nФормат: <code>КОД эффект количество</code>\n\nПример:\n<code>3005 глянец 1.5</code>\n<code>прозрачный лак 2.0</code>",
        parse_mode='HTML'
    )
    bot.register_next_step_handler(msg, process_use_paint)

def process_use_paint(message):
    try:
        data = message.text.split()
        if len(data) < 3:
            bot.send_message(message.chat.id, "❌ Неверный формат", reply_markup=create_main_keyboard())
            return
            
        possible_effects = ['матовый', 'глянец', 'муар', 'шагрень', 'лак']
        effect_index = None
        
        for i, word in enumerate(data):
            if word in possible_effects:
                effect_index = i
                break
        
        if effect_index is None:
            bot.send_message(message.chat.id, f"❌ Не найден эффект", reply_markup=create_main_keyboard())
            return
        
        color_code = ' '.join(data[:effect_index])
        effect = data[effect_index]
        amount = float(data[-1])
        
        conn = sqlite3.connect('paint_db.sqlite')
        cursor = conn.cursor()
        cursor.execute('SELECT id, quantity FROM paints WHERE color_code = ? AND effect = ?', (color_code, effect))
        paint = cursor.fetchone()
        
        if not paint:
            bot.send_message(message.chat.id, f"❌ Краска не найдена", reply_markup=create_main_keyboard())
            return
        
        paint_id, current_quantity = paint
        
        if current_quantity < amount:
            bot.send_message(message.chat.id, 
                           f"❌ Недостаточно краски!\n\nДоступно: <b>{current_quantity} кг</b>",
                           parse_mode='HTML', reply_markup=create_main_keyboard())
            return
        
        new_quantity = current_quantity - amount
        cursor.execute('UPDATE paints SET quantity = ? WHERE id = ?', (new_quantity, paint_id))
        cursor.execute('INSERT INTO transactions (paint_id, type, amount) VALUES (?, ?, ?)', 
                     (paint_id, 'use', amount))
        conn.commit()
        conn.close()
        
        bot.send_message(
            message.chat.id,
            f"✅ <b>Списано {amount} кг</b>\n\n"
            f"🎨 Код: <b>{color_code}</b>\n"
            f"✨ Эффект: <b>{effect}</b>\n"
            f"📊 Остаток: <b>{new_quantity} кг</b>",
            parse_mode='HTML',
            reply_markup=create_main_keyboard()
        )
        
        logger.info(f"➖ Списана краска: {color_code} ({effect}) - {amount}кг")
        
    except Exception as e:
        logger.error(f"Ошибка в process_use_paint: {e}")
        bot.send_message(message.chat.id, "❌ Ошибка при списании", reply_markup=create_main_keyboard())

# Статистика
def show_stats(message):
    try:
        conn = sqlite3.connect('paint_db.sqlite')
        cursor = conn.cursor()
        cursor.execute('SELECT COUNT(*), SUM(quantity) FROM paints')
        total_paints, total_quantity = cursor.fetchone()
        
        cursor.execute('''
            SELECT p.color_code, p.effect, t.amount, t.date 
            FROM transactions t 
            JOIN paints p ON t.paint_id = p.id 
            ORDER BY t.date DESC 
            LIMIT 5
        ''')
        recent_transactions = cursor.fetchall()
        conn.close()
        
        response = "📊 <b>Статистика склада:</b>\n\n"
        response += f"• 🎨 Всего позиций: <b>{total_paints}</b>\n"
        response += f"• ⚖️ Общий вес: <b>{total_quantity or 0} кг</b>\n\n"
        
        if recent_transactions:
            response += "<b>Последние операции:</b>\n"
            for color_code, effect, amount, date in recent_transactions:
                response += f"• {color_code} ({effect}): {amount} кг\n"
        else:
            response += "📝 Операций пока нет"
        
        bot.send_message(message.chat.id, response, parse_mode='HTML', reply_markup=create_main_keyboard())
        
    except Exception as e:
        logger.error(f"Ошибка в show_stats: {e}")
        bot.send_message(message.chat.id, "❌ Ошибка при загрузке статистики", reply_markup=create_main_keyboard())

# Помощь
def show_help(message):
    help_text = """
🎨 <b>PaintStock Bot - помощь</b>

<b>Возможности:</b>
• Учет краски по любым кодам
• 5 видов эффектов
• Учет веса в кг
• Поиск и статистика

<b>Доступные эффекты:</b>
• 🟢 Матовый
• 🔵 Глянец  
• 🟣 Муар
• 🟠 Шагрень
• ⚪ Лак

<b>Использование:</b>
1. 🎨 Добавить краску - ввести код, выбрать эффект, ввести вес
2. 📋 Список - посмотреть весь склад
3. 📤 Списать - указать код, эффект и количество
4. 🔍 Поиск - найти краску по коду
5. 📊 Статистика - общая информация

<b>Примеры кодов:</b>
• 3005 (RAL)
• прозрачный
• черный матовый
• металлик серебро
    """
    bot.send_message(message.chat.id, help_text, parse_mode='HTML', reply_markup=create_main_keyboard())

# Запуск бота
if __name__ == '__main__':
    init_db()
    logger.info("✅ Бот запущен и готов к работе!")
    
    while True:
        try:
            logger.info("🔄 Запуск polling...")
            bot.polling(none_stop=True, interval=1, timeout=30)
        except Exception as e:
            logger.error(f"❌ Ошибка polling: {e}")
            logger.info("🔄 Перезапуск через 15 секунд...")
            time.sleep(15)
# ... весь ваш существующий код бота ...

# === ДОБАВЬТЕ ЭТОТ КОД В КОНЕЦ ФАЙЛА ===

import os
from http.server import HTTPServer, BaseHTTPRequestHandler
import threading

class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-type', 'text/html')
        self.end_headers()
        self.wfile.write("🎨 Paint Stock Bot is running!".encode('utf-8'))
    
    def log_message(self, format, *args):
        return  # Отключаем логи

def start_health_server():
    port = int(os.environ.get("PORT", 10000))
    server = HTTPServer(('0.0.0.0', port), HealthHandler)
    print(f"✅ Health server started on port {port}")
    server.serve_forever()

# Заменяем существующий запуск бота
if __name__ == "__main__":
    # Запускаем health server в отдельном потоке
    health_thread = threading.Thread(target=start_health_server, daemon=True)
    health_thread.start()
    
    print("✅ Bot starting with health server...")
    bot.infinity_polling()
