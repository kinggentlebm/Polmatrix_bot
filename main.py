import telebot
from telebot import types
import sqlite3
import os
import shutil
from datetime import datetime
import pytz

BOT_TOKEN = os.environ.get("BOT_TOKEN")
bot = telebot.TeleBot(BOT_TOKEN)

LAGOS_TZ = pytz.timezone("Africa/Lagos")
DB_NAME = "polmatrix.db"
BACKUP_FOLDER = "backups"

if not os.path.exists(BACKUP_FOLDER):
    os.makedirs(BACKUP_FOLDER)

def get_time():
    return datetime.now(LAGOS_TZ).strftime("%Y-%m-%d %H:%M:%S")

# ========== DATABASE ==========
def init_db():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()

    c.execute('''CREATE TABLE IF NOT EXISTS users
                 (user_id INTEGER PRIMARY KEY, username TEXT, points INTEGER DEFAULT 50, joined TEXT)''')

    c.execute('''CREATE TABLE IF NOT EXISTS tasks
                 (task_id INTEGER PRIMARY KEY AUTOINCREMENT, task_name TEXT, reward INTEGER, link TEXT, added_by INTEGER, added_time TEXT)''')

    c.execute('''CREATE TABLE IF NOT EXISTS submissions
                 (sub_id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, task_id INTEGER, proof TEXT, status TEXT DEFAULT 'pending', sub_time TEXT)''')

    conn.commit()
    conn.close()

def backup_db():
    time = datetime.now(LAGOS_TZ).strftime("%Y%m%d_%H%M%S")
    backup_path = os.path.join(BACKUP_FOLDER, f"backup_{time}.db")
    shutil.copy(DB_NAME, backup_path)

def add_user(user_id, username):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("SELECT * FROM users WHERE user_id=?", (user_id,))
    if not c.fetchone():
        c.execute("INSERT INTO users VALUES (?,?,?)", (user_id, username, 50, get_time()))
        conn.commit()
    conn.close()

def get_balance(user_id):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("SELECT points FROM users WHERE user_id=?", (user_id,))
    res = c.fetchone()
    conn.close()
    return res[0] if res else 0

def add_task(name, reward, link, admin_id):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("INSERT INTO tasks (task_name, reward, link, added_by, added_time) VALUES (?,?,?)",
              (name, reward, link, admin_id, get_time()))
    conn.commit()
    conn.close()
    backup_db()

def get_tasks():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("SELECT * FROM tasks ORDER BY task_id DESC")
    res = c.fetchall()
    conn.close()
    return res

def submit_proof(user_id, task_id, proof):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("INSERT INTO submissions (user_id, task_id, proof, sub_time) VALUES (?,?,?)",
              (user_id, task_id, proof, get_time()))
    conn.commit()
    conn.close()

def get_pending():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("SELECT * FROM submissions WHERE status='pending'")
    res = c.fetchall()
    conn.close()
    return res

def approve_submission(sub_id, reward):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("SELECT user_id FROM submissions WHERE sub_id=?", (sub_id,))
    user_id = c.fetchone()[0]
    c.execute("UPDATE users SET points = points +? WHERE user_id=?", (reward, user_id))
    c.execute("UPDATE submissions SET status='approved' WHERE sub_id=?", (sub_id,))
    conn.commit()
    conn.close()
    backup_db()

# ========== BOT COMMANDS ==========
@bot.message_handler(commands=['start'])
def start(message):
    add_user(message.from_user.id, message.from_user.username)
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add("💰 Balance", "📋 Available Tasks")
    markup.add("📤 Submit Proof", "📊 My Stats")
    bot.send_message(message.chat.id, f"Welcome to POL MATRIX 🔥\nYou got 50 points to start!", reply_markup=markup)

@bot.message_handler(func=lambda m: m.text == "💰 Balance")
def balance(message):
    points = get_balance(message.from_user.id)
    bot.send_message(message.chat.id, f"Your Balance: {points} points")

@bot.message_handler(func=lambda m: m.text == "📋 Available Tasks")
def tasks(message):
    task_list = get_tasks()
    if not task_list:
        bot.send_message(message.chat.id, "No tasks available yet.")
        return
    text = "📋 AVAILABLE TASKS:\n\n"
    for t in task_list:
        text += f"ID: {t[0]}\nTask: {t[1]}\nReward: {t[2]} points\nLink: {t[3]}\n\n"
    bot.send_message(message.chat.id, text)

@bot.message_handler(func=lambda m: m.text == "📤 Submit Proof")
def ask_proof(message):
    msg = bot.send_message(message.chat.id, "Send: TaskID | Screenshot/Photo")
    bot.register_next_step_handler(msg, process_proof)

def process_proof(message):
    try:
        if message.photo:
            file_id = message.photo[-1].file_id
            task_id = int(message.caption.split("|")[0].strip())
        else:
            parts = message.text.split("|")
            task_id = int(parts[0].strip())
            file_id = parts[1].strip()
        submit_proof(message.from_user.id, task_id, file_id)
        bot.send_message(message.chat.id, "Proof submitted! Waiting for admin approval.")
    except:
        bot.send_message(message.chat.id, "Format: TaskID | Proof")

# ========== RUN BOT ==========
init_db()
print("POL MATRIX BOT IS LIVE 24/7")
bot.infinity_polling()
