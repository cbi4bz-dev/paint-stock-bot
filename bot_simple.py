import os
import telebot
import sqlite3
import logging
from http.server import HTTPServer, BaseHTTPRequestHandler
import threading
from telebot import types

# Настройка логирования
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
logger = logging.getLogger(__name__)

# Токен бота из переменных окружения
BOT_TOKEN = os.environ.get('BOT_TOKEN')

if not BOT_TOKEN:
    logger.error("❌ BOT_TOKEN not set in environment variables!")
    exit(1)

bot = telebot.TeleBot(BOT_TOKEN)

# Health Server для Render
class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"OK - Paint Bot is Running")
    
    def log_message(self, format, *args):
        pass

def start_health_server():
    port = int(os.environ.get("PORT", 10000))
    server = HTTPServer(('0.0.0.0', port), HealthHandler)
    logger.info(f"✅ Health server started on port {port}")
    server.serve_forever()

# Инициализация базы данных
def init_db():
    conn = sqlite3.connect('paints.db')
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS paints (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            quantity REAL NOT NULL,
            color TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    conn.commit()
    conn.close()
    logger.info("✅ Database initialized")

# Создание клавиатуры с кнопками
def create_main_keyboard():
    keyboard = types.ReplyKeyboardMarkup(row_width=2, resize_keyboard=True)
    btn_add = types.KeyboardButton('🎨 Добавить краску')
    btn_list = types.KeyboardButton('📊 Список красок')
    btn_help = types.KeyboardButton('❓ Помощь')
    btn_stats = types.KeyboardButton('📈 Статистика')
    keyboard.add(btn_add, btn_list, btn_help, btn_stats)
    return keyboard

# Команды бота
@bot.message_handler(commands=['start'])
def send_welcome(message):
    keyboard = create_main_keyboard()
    bot.send_message(
        message.chat.id,
        "🎨 **Бот для учета краски**\n\n"
        "Выберите действие или используйте команды:\n"
        "• /add - добавить краску\n"
        "• /list - список красок\n"
        "• /help - помощь\n\n"
        "Или просто нажмите на кнопку ниже 👇",
        reply_markup=keyboard,
        parse_mode='Markdown'
    )

@bot.message_handler(commands=['help'])
@bot.message_handler(func=lambda message: message.text == '❓ Помощь')
def send_help(message):
    help_text = """
🎨 **Бот для учета краски - Помощь**

**Команды:**
• /start - Главное меню
• /add название количество [цвет] - Добавить краску
• /list - Показать все краски
• /help - Эта справка

**Примеры:**
/add Белая_эмаль 5.0 Белый
/add Красная_акриловая 3.5 Красный

**Или используйте кнопки ниже 👇**
"""
    bot.send_message(message.chat.id, help_text, reply_markup=create_main_keyboard())

@bot.message_handler(commands=['add'])
@bot.message_handler(func=lambda message: message.text == '🎨 Добавить краску')
def add_paint_command(message):
    msg = bot.send_message(
        message.chat.id,
        "📝 **Добавление краски**\n\n"
        "Введите данные в формате:\n"
        "`Название Количество [Цвет]`\n\n"
        "**Пример:**\n"
        "`Белая_эмаль 5.0 Белый`\n"
        "`Красная_акриловая 3.5`",
        parse_mode='Markdown',
        reply_markup=types.ReplyKeyboardRemove()
    )
    bot.register_next_step_handler(msg, process_add_paint)

def process_add_paint(message):
    try:
        parts = message.text.split()
        if len(parts) >= 2:
            name = parts[0]
            quantity = float(parts[1])
            color = parts[2] if len(parts) > 2 else "Не указан"
            
            conn = sqlite3.connect('paints.db')
            cursor = conn.cursor()
            
            # Проверяем, существует ли уже такая краска
            cursor.execute('SELECT name FROM paints WHERE name = ?', (name,))
            existing = cursor.fetchone()
            
            if existing:
                # Обновляем количество
                cursor.execute('UPDATE paints SET quantity = quantity + ? WHERE name = ?', (quantity, name))
                action = "обновлена"
            else:
                # Добавляем новую запись
                cursor.execute('INSERT INTO paints (name, quantity, color) VALUES (?, ?, ?)', (name, quantity, color))
                action = "добавлена"
            
            conn.commit()
            conn.close()
            
            response = f"✅ Краска **{action}**!\n\n" \
                      f"**Название:** {name}\n" \
                      f"**Количество:** {quantity}кг\n" \
                      f"**Цвет:** {color}"
            
            bot.send_message(message.chat.id, response, parse_mode='Markdown', reply_markup=create_main_keyboard())
            logger.info(f"➕ Paint {action}: {name} - {quantity}kg")
            
        else:
            bot.send_message(
                message.chat.id,
                "❌ **Неверный формат!**\n\n"
                "Используйте: `Название Количество [Цвет]`\n"
                "**Пример:** `Белая_эмаль 5.0 Белый`",
                parse_mode='Markdown',
                reply_markup=create_main_keyboard()
            )
    except ValueError:
        bot.send_message(
            message.chat.id,
            "❌ **Ошибка!** Количество должно быть числом.\n\n"
            "**Пример:** `Белая_эмаль 5.0`",
            parse_mode='Markdown',
            reply_markup=create_main_keyboard()
        )
    except Exception as e:
        bot.send_message(
            message.chat.id,
            f"❌ **Ошибка:** {str(e)}",
            reply_markup=create_main_keyboard()
        )

@bot.message_handler(commands=['list'])
@bot.message_handler(func=lambda message: message.text == '📊 Список красок')
def list_paints(message):
    try:
        conn = sqlite3.connect('paints.db')
        cursor = conn.cursor()
        cursor.execute('SELECT name, quantity, color FROM paints ORDER BY name')
        paints = cursor.fetchall()
        conn.close()
        
        if paints:
            total_quantity = sum(paint[1] for paint in paints)
            response = f"📊 **Список красок**\n\n"
            
            for name, quantity, color in paints:
                response += f"• **{name}**: {quantity}кг ({color})\n"
            
            response += f"\n**Всего:** {len(paints)} позиций, {total_quantity}кг"
        else:
            response = "📭 **Список красок пуст**\n\nИспользуйте кнопку '🎨 Добавить краску'"
        
        bot.send_message(message.chat.id, response, parse_mode='Markdown', reply_markup=create_main_keyboard())
    except Exception as e:
        bot.send_message(message.chat.id, f"❌ **Ошибка:** {str(e)}", reply_markup=create_main_keyboard())

@bot.message_handler(commands=['stats'])
@bot.message_handler(func=lambda message: message.text == '📈 Статистика')
def show_stats(message):
    try:
        conn = sqlite3.connect('paints.db')
        cursor = conn.cursor()
        cursor.execute('SELECT COUNT(*), SUM(quantity) FROM paints')
        result = cursor.fetchone()
        conn.close()
        
        count = result[0] or 0
        total = result[1] or 0
        
        stats_text = f"📈 **Статистика склада**\n\n" \
                    f"• **Всего позиций:** {count}\n" \
                    f"• **Общее количество:** {total}кг\n" \
                    f"• **Среднее на позицию:** {total/count:.1f}кг" if count > 0 else "0кг"
        
        bot.send_message(message.chat.id, stats_text, parse_mode='Markdown', reply_markup=create_main_keyboard())
    except Exception as e:
        bot.send_message(message.chat.id, f"❌ **Ошибка:** {str(e)}", reply_markup=create_main_keyboard())

# Обработка обычных сообщений
@bot.message_handler(func=lambda message: True)
def handle_all_messages(message):
    if message.text not in ['🎨 Добавить краску', '📊 Список красок', '❓ Помощь', '📈 Статистика']:
        bot.send_message(
            message.chat.id,
            "🤔 Не понимаю команду. Используйте кнопки или /help для справки.",
            reply_markup=create_main_keyboard()
        )

# Запуск приложения
if __name__ == "__main__":
    logger.info("🚀 Starting Paint Stock Bot with buttons...")
    
    # Инициализация БД
    init_db()
    
    # Очистка webhook
    try:
        bot.remove_webhook()
        logger.info("✅ Webhook cleared")
    except Exception as e:
        logger.info(f"ℹ️ Webhook clear: {e}")
    
    # Запуск health server в отдельном потоке
    health_thread = threading.Thread(target=start_health_server, daemon=True)
    health_thread.start()
    logger.info("✅ Health server thread started")
    
    # Запуск бота
    logger.info("🤖 Starting Telegram bot polling...")
    bot.infinity_polling()
