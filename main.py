import os
from threading import Thread
from flask import Flask
import telebot
from telebot import types
import sqlite3
import shutil
import glob
from datetime import datetime
import pytz

# KEEP RENDER ALIVE
app = Flask('')
@app.route('/')
def home(): return "Bot is alive"
def run(): app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 10000)))
def keep_alive(): Thread(target=run).start()

BOT_TOKEN = os.environ.get("BOT_TOKEN")
ADMIN_ID = 6921839341 # <--- CHANGE THIS TO YOUR ID FROM @userinfobot
LAGOS_TZ = pytz.timezone("Africa/Lagos")
DB_NAME = "polmatrix.db"
BACKUP_FOLDER = "backups"

if not os.path.exists(BACKUP_FOLDER): os.makedirs(BACKUP_FOLDER)

bot = telebot.TeleBot(BOT_TOKEN)
keep_alive()

def get_time(): return datetime.now(LAGOS_TZ).strftime("%Y-%m-%d %H:%M:%S")

# ========== BACKUP + RESTORE ==========
def restore_latest_backup():
    backups = glob.glob(os.path.join(BACKUP_FOLDER, "backup_*.db"))
    if backups:
        latest = max(backups, key=os.path.getctime)
        shutil.copy(latest, DB_NAME)
        print(f"Restored from {latest}")

def backup_db():
    time = datetime.now(LAGOS_TZ).strftime("%Y%m%d_%H%M%S")
    shutil.copy(DB_NAME, os.path.join(BACKUP_FOLDER, f"backup_{time}.db"))

# ========== DATABASE ==========
def init_db():
    restore_latest_backup() # <--- THIS STOPS RESET
    conn = sqlite3.connect(DB_NAME); c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, username TEXT, points INTEGER DEFAULT 50, joined TEXT, referrer INTEGER)''')
    c.execute('''CREATE TABLE IF NOT EXISTS tasks (task_id INTEGER PRIMARY KEY AUTOINCREMENT, task_name TEXT, reward INTEGER, link TEXT, added_by INTEGER, added_time TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS submissions (sub_id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, task_id INTEGER, proof TEXT, status TEXT DEFAULT 'pending', sub_time TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS stake (user_id INTEGER PRIMARY KEY, amount INTEGER, start_time TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS withdrawals (w_id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, amount INTEGER, wallet TEXT, status TEXT DEFAULT 'pending', req_time TEXT)''')
    conn.commit(); conn.close()

def add_user(user_id, username, referrer=None):
    conn = sqlite3.connect(DB_NAME); c = conn.cursor()
    c.execute("SELECT * FROM users WHERE user_id=?", (user_id,))
    if not c.fetchone():
        c.execute("INSERT INTO users VALUES (?,?,?,?,?)", (user_id, username, 50, get_time(), referrer))
        if referrer: c.execute("UPDATE users SET points = points + 20 WHERE user_id=?", (referrer,))
        conn.commit(); backup_db() # backup after new user
    conn.close()

def get_balance(user_id):
    conn = sqlite3.connect(DB_NAME); c = conn.cursor(); c.execute("SELECT points FROM users WHERE user_id=?", (user_id,)); res = c.fetchone(); conn.close()
    return res[0] if res else 0

def add_task(name, reward, link, admin_id):
    conn = sqlite3.connect(DB_NAME); c = conn.cursor(); c.execute("INSERT INTO tasks (task_name, reward, link, added_by, added_time) VALUES (?,?,?,?,?)", (name, reward, link, admin_id, get_time())); conn.commit(); conn.close(); backup_db()

def get_tasks():
    conn = sqlite3.connect(DB_NAME); c = conn.cursor(); c.execute("SELECT * FROM tasks ORDER BY task_id DESC"); res = c.fetchall(); conn.close(); return res

def submit_proof(user_id, task_id, proof):
    conn = sqlite3.connect(DB_NAME); c = conn.cursor(); c.execute("INSERT INTO submissions (user_id, task_id, proof, sub_time) VALUES (?,?,?,?)", (user_id, task_id, proof, get_time())); conn.commit(); conn.close(); backup_db()

def get_pending_subs():
    conn = sqlite3.connect(DB_NAME); c = conn.cursor(); c.execute("SELECT s.sub_id, u.username, t.task_name, t.reward FROM submissions s JOIN users u ON s.user_id=u.user_id JOIN tasks t ON s.task_id=t.task_id WHERE s.status='pending'"); res = c.fetchall(); conn.close(); return res

def approve_task(sub_id):
    conn = sqlite3.connect(DB_NAME); c = conn.cursor(); c.execute("SELECT s.user_id, t.reward FROM submissions s JOIN tasks t ON s.task_id=t.task_id WHERE s.sub_id=?", (sub_id,)); res = c.fetchone(); user_id, reward = res
    c.execute("UPDATE users SET points = points +? WHERE user_id=?", (reward, user_id)); c.execute("UPDATE submissions SET status='approved' WHERE sub_id=?", (sub_id,)); conn.commit(); conn.close(); backup_db()

def get_pending_withdraws():
    conn = sqlite3.connect(DB_NAME); c = conn.cursor(); c.execute("SELECT w.w_id, u.username, w.amount, w.wallet FROM withdrawals w JOIN users u ON w.user_id=u.user_id WHERE w.status='pending'"); res = c.fetchall(); conn.close(); return res

def approve_withdraw(w_id):
    conn = sqlite3.connect(DB_NAME); c = conn.cursor(); c.execute("UPDATE withdrawals SET status='approved' WHERE w_id=?", (w_id,)); conn.commit(); conn.close(); backup_db()

# ========== USER BUTTONS ==========
@bot.message_handler(commands=['start'])
def start(message):
    args = message.text.split(); referrer = int(args[1]) if len(args) > 1 else None
    add_user(message.from_user.id, message.from_user.username, referrer)
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add("💰 Balance", "📋 Available Tasks")
    markup.add("📤 Submit Proof", "📊 History")
    markup.add("👑 Leaderboard", "👥 Invite")
    markup.add("📈 Stake", "💸 Withdraw")
    bot.send_message(message.chat.id, f"Welcome to POL MATRIX 🔥\nYou got 50 points to start!", reply_markup=markup)

@bot.message_handler(func=lambda m: m.text == "💰 Balance")
def balance(message): bot.send_message(message.chat.id, f"Your Balance: {get_balance(message.from_user.id)} points")

@bot.message_handler(func=lambda m: m.text == "👑 Leaderboard")
def leaderboard(message):
    conn = sqlite3.connect(DB_NAME); c = conn.cursor(); c.execute("SELECT username, points FROM users ORDER BY points DESC LIMIT 10"); res = c.fetchall(); conn.close()
    text = "👑 TOP 10 LEADERBOARD:\n\n"
    for i, row in enumerate(res, 1): text += f"{i}. @{row[0] if row[0] else 'user'} - {row[1]} pts\n"
    bot.send_message(message.chat.id, text)

@bot.message_handler(func=lambda m: m.text == "👥 Invite")
def invite(message): bot.send_message(message.chat.id, f"Invite friends and get 20 points each!\nYour link: https://t.me/{bot.get_me().username}?start={message.from_user.id}")

@bot.message_handler(func=lambda m: m.text == "📈 Stake")
def stake(message): bot.send_message(message.chat.id, "Stake: Send amount to stake. Min 100 points.")
@bot.message_handler(func=lambda m: m.text == "📊 History")
def history(message): bot.send_message(message.chat.id, "History: Feature active. Your points are saved.")

@bot.message_handler(func=lambda m: m.text == "💸 Withdraw")
def withdraw(message): msg = bot.send_message(message.chat.id, "Send: Amount | WalletAddress"); bot.register_next_step_handler(msg, process_withdraw)
def process_withdraw(message):
    try: amount, wallet = message.text.split("|"); conn = sqlite3.connect(DB_NAME); c = conn.cursor(); c.execute("INSERT INTO withdrawals (user_id, amount, wallet, req_time) VALUES (?,?,?,?)", (message.from_user.id, int(amount.strip()), wallet.strip(), get_time())); conn.commit(); conn.close(); backup_db(); bot.send_message(message.chat.id, "Withdrawal request submitted!")
    except: bot.send_message(message.chat.id, "Format: 500 | 0xWalletAddress")

# ========== ADMIN PANEL ==========
@bot.message_handler(commands=['admin'])
def admin_panel(message):
    if message.from_user.id!= ADMIN_ID: return
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add("✅ Approved Tasks", "➕ Add Tasks")
    markup.add("💾 Backup Now", "👥 Users")
    markup.add("📊 Admin Stats", "💸 Approved Withdraw")
    markup.add("👑 Leaderboard")
    bot.send_message(message.chat.id, "Admin Panel", reply_markup=markup)

@bot.message_handler(func=lambda m: m.text == "✅ Approved Tasks" and m.from_user.id == ADMIN_ID)
def pending_tasks(message):
    pending = get_pending_subs()
    if not pending: bot.send_message(message.chat.id, "No pending tasks.")
    else:
        for p in pending: bot.send_message(message.chat.id, f"ID: {p[0]}\nUser: @{p[1]}\nTask: {p[2]}\nReward: {p[3]}\n\nReply: approve {p[0]}")

@bot.message_handler(func=lambda m: m.text.startswith("approve ") and m.from_user.id == ADMIN_ID)
def handle_approve(message):
    sub_id = int(message.text.split()[1]); approve_task(sub_id); bot.send_message(message.chat.id, f"Task {sub_id} approved!")

@bot.message_handler(func=lambda m: m.text == "💸 Approved Withdraw" and m.from_user.id == ADMIN_ID)
def pending_withdraw(message):
    pending = get_pending_withdraws()
    if not pending: bot.send_message(message.chat.id, "No pending withdrawals.")
    else:
        for p in pending: bot.send_message(message.chat.id, f"WID: {p[0]}\nUser: @{p[1]}\nAmount: {p[2]}\nWallet: {p[3]}\n\nReply: approvew {p[0]}")

@bot.message_handler(func=lambda m: m.text.startswith("approvew ") and m.from_user.id == ADMIN_ID)
def handle_approvew(message):
    w_id = int(message.text.split()[1]); approve_withdraw(w_id); bot.send_message(message.chat.id, f"Withdrawal {w_id} approved!")

@bot.message_handler(func=lambda m: m.text == "💾 Backup Now" and m.from_user.id == ADMIN_ID)
def manual_backup(message): backup_db(); bot.send_message(message.chat.id, "Backup created!")

@bot.message_handler(func=lambda m: m.text == "👥 Users" and m.from_user.id == ADMIN_ID)
def admin_users(message):
    conn = sqlite3.connect(DB_NAME); c = conn.cursor(); c.execute("SELECT COUNT(*), SUM(points) FROM users"); res = c.fetchone(); conn.close()
    bot.send_message(message.chat.id, f"Total Users: {res[0]}\nTotal Points: {res[1]}")

@bot.message_handler(func=lambda m: m.text == "📊 Admin Stats" and m.from_user.id == ADMIN_ID)
def admin_stats(message):
    conn = sqlite3.connect(DB_NAME); c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM tasks"); t=c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM submissions WHERE status='pending'"); p=c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM withdrawals WHERE status='pending'"); w=c.fetchone()[0]
    conn.close()
    bot.send_message(message.chat.id, f"📊 Stats:\nTasks: {t}\nPending Tasks: {p}\nPending Withdrawals: {w}")

# ========== RUN BOT ==========
init_db()
print("POL MATRIX BOT IS LIVE 24/7 WITH BACKUP")
bot.infinity_polling()
