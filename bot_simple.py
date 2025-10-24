import os
import telebot
import sqlite3
import logging
from http.server import HTTPServer, BaseHTTPRequestHandler
import threading

# Настройка логирования
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
logger = logging.getLogger(__name__)

# Токен бота из переменных окружения
BOT_TOKEN = os.environ.get('BOT_TOKEN')

if not BOT_TOKEN:
    logger.error("❌ BOT_TOKEN not set in environment variables!")
    exit(1)

bot = telebot.TeleBot(BOT_TOKEN)

# Простой Health Server для Render
class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"OK - Paint Bot is Running")
    
    def log_message(self, format, *args):
        pass  # Отключаем логи

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

# Команды бота
@bot.message_handler(commands=['start'])
def send_welcome(message):
    bot.reply_to(message, "🎨 Бот для учета краски запущен!\n\nКоманды:\n/add название количество [цвет]\n/list - список красок")

@bot.message_handler(commands=['add'])
def add_paint(message):
    try:
        parts = message.text.split()
        if len(parts) >= 3:
            name = parts[1]
            quantity = float(parts[2])
            color = parts[3] if len(parts) > 3 else "Не указан"
            
            conn = sqlite3.connect('paints.db')
            cursor = conn.cursor()
            cursor.execute('''
                INSERT OR REPLACE INTO paints (name, quantity, color) 
                VALUES (?, ?, ?)
            ''', (name, quantity, color))
            conn.commit()
            conn.close()
            
            bot.reply_to(message, f"✅ Добавлено: {name} - {quantity}кг")
            logger.info(f"➕ Added paint: {name} - {quantity}kg")
        else:
            bot.reply_to(message, "❌ Используйте: /add название количество [цвет]")
    except Exception as e:
        bot.reply_to(message, f"❌ Ошибка: {e}")

@bot.message_handler(commands=['list'])
def list_paints(message):
    try:
        conn = sqlite3.connect('paints.db')
        cursor = conn.cursor()
        cursor.execute('SELECT name, quantity, color FROM paints ORDER BY name')
        paints = cursor.fetchall()
        conn.close()
        
        if paints:
            response = "📊 Список красок:\n\n"
            for name, quantity, color in paints:
                response += f"• {name}: {quantity}кг ({color})\n"
        else:
            response = "📭 Список красок пуст"
        
        bot.reply_to(message, response)
    except Exception as e:
        bot.reply_to(message, f"❌ Ошибка: {e}")

# Запуск приложения
if __name__ == "__main__":
    logger.info("🚀 Starting Paint Stock Bot...")
    
    # Инициализация БД
    init_db()
    
    # Очистка webhook (важно для избежания конфликтов)
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
