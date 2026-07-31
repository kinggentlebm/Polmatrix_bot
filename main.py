import os
from threading import Thread
from flask import Flask

app = Flask('')

@app.route('/')
def home():
    return "Bot is alive"

def run():
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 10000)))

def keep_alive():
    t = Thread(target=run)
    t.start()
import telebot, sqlite3, datetime, pytz, os, hashlib, time, threading, shutil
from telebot import types

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = 6921839341 # <-- PUT YOUR TELEGRAM ID HERE
bot = telebot.TeleBot(BOT_TOKEN)
keep_alive()
DB_NAME = 'polmatrix.db'
BACKUP_FOLDER = 'backups'

conn = sqlite3.connect(DB_NAME, check_same_thread=False)
c = conn.cursor()

# ========= AUTO BACKUP EVERY 6 HOURS =========
def auto_backup():
    if not os.path.exists(BACKUP_FOLDER):
        os.makedirs(BACKUP_FOLDER)
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_file = f"{BACKUP_FOLDER}/polmatrix_backup_{timestamp}.db"
    shutil.copy(DB_NAME, backup_file)
    print(f"✅ AUTO BACKUP CREATED: {backup_file}")
    files = sorted(os.listdir(BACKUP_FOLDER))
    for f in files[:-10]:
        os.remove(os.path.join(BACKUP_FOLDER, f))

def backup_loop():
    while True:
        time.sleep(21600)
        auto_backup()
threading.Thread(target=backup_loop, daemon=True).start()

# ========= TASK RESET AT 12AM NIGERIA =========
def reset_tasks_loop():
    while True:
        tz = pytz.timezone('Africa/Lagos')
        now = datetime.datetime.now(tz)
        if now.hour == 0 and now.minute == 0:
            c.execute("DELETE FROM submissions WHERE date!=?", (today_nigeria(),))
            conn.commit()
            print("✅ TASKS RESET FOR NEW DAY")
            time.sleep(60) # wait 1 min so it doesn't run twice
        time.sleep(30)
threading.Thread(target=reset_tasks_loop, daemon=True).start()
# ========= END LOOPS =========

# ========= CREATE TABLES =========
c.execute('''CREATE TABLE IF NOT EXISTS users
            (user_id INTEGER PRIMARY KEY, hold_points REAL DEFAULT 0, release_points REAL DEFAULT 0, referrer_id INTEGER, join_date TEXT, wallet TEXT, last_claim TEXT)''')
c.execute('''CREATE TABLE IF NOT EXISTS tasks
            (task_id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, reward REAL)''')
c.execute('''CREATE TABLE IF NOT EXISTS submissions
            (user_id INTEGER, task_id INTEGER, status TEXT, date TEXT, proof_hash TEXT, submit_time REAL)''')
c.execute('''CREATE TABLE IF NOT EXISTS withdraw_requests
            (req_id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, amount REAL, wallet TEXT, status TEXT, date TEXT)''')
c.execute('''CREATE TABLE IF NOT EXISTS used_hashes (hash TEXT PRIMARY KEY)''')
c.execute('''CREATE TABLE IF NOT EXISTS hold_history (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, amount REAL, add_date REAL)''')
c.execute('''CREATE TABLE IF NOT EXISTS cooldowns (user_id INTEGER PRIMARY KEY, last_submit REAL)''')
conn.commit()

# ========= +50 COMPENSATION =========
c.execute("UPDATE users SET hold_points = hold_points + 50")
conn.commit()
print("✅ ADDED 50 POINTS TO ALL USERS")

waiting_wallet = {}
user_cooldown = {}

def today_nigeria():
    tz = pytz.timezone('Africa/Lagos')
    return datetime.datetime.now(tz).strftime('%Y-%m-%d')

def get_balances(user_id):
    c.execute("SELECT hold_points, release_points FROM users WHERE user_id=?", (user_id,))
    res = c.fetchone()
    return res if res else (0,0)

def points_to_pol(points):
    return round((points / 1000) * 50, 2)

def user_keyboard():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add("💰 Balance", "👥 Invite")
    markup.add("📊 Staking", "💸 Withdraw")
    markup.add("📋 Tasks", "📜 History")
    markup.add("🏆 Leaderboard")
    return markup

def admin_keyboard():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add("🚨 Approve Tasks", "💸 Approve Withdraw")
    markup.add("➕ Add Task", "📊 Admin Stats")
    markup.add("👥 Users", "💾 Backup Now")
    return markup

# ========= OLD PETER BOARD LEADERBOARD =========
@bot.message_handler(func=lambda m: m.text == "🏆 Leaderboard")
def leaderboard(message):
    c.execute("SELECT user_id, hold_points+release_points FROM users ORDER BY hold_points+release_points DESC LIMIT 10")
    top = c.fetchall()
    text = "🏆 **TOP 10 PETER BOARD** 🏆\n\n"
    medals = ["🥇", "🥈", "🥉"]
    for i, (uid, pts) in enumerate(top, 1):
        medal = medals[i-1] if i <= 3 else f"{i}."
        try: name = bot.get_chat(uid).first_name
        except: name = f"User {uid}"
        text += f"{medal} {name}: **{pts} Points**\n"
    bot.send_message(message.chat.id, text, parse_mode="Markdown")

# ========= OLD HISTORY =========
@bot.message_handler(func=lambda m: m.text == "📜 History")
def history(message):
    user_id = message.from_user.id
    c.execute("SELECT amount, add_date FROM hold_history WHERE user_id=? ORDER BY add_date DESC LIMIT 10", (user_id,))
    hist = c.fetchall()
    if not hist:
        bot.send_message(user_id, "📜 No history yet.")
        return
    text = "📜 **YOUR LAST 10 ACTIVITIES**\n\n"
    for amount, timestamp in hist:
        date = datetime.datetime.fromtimestamp(timestamp).strftime('%d-%m %H:%M')
        text += f"• **+{amount} pts** on {date}\n"
    bot.send_message(user_id, text, parse_mode="Markdown")

# ========= TASKS WITH LINK + SUBMIT PROOF =========
@bot.message_handler(func=lambda m: m.text == "📋 Tasks")
def show_tasks(message):
    user_id = message.from_user.id
    today = today_nigeria()
    c.execute("SELECT task_id, name, reward FROM tasks")
    tasks = c.fetchall()
    if not tasks:
        bot.send_message(user_id, "No tasks available yet.")
        return

    text = f"📋 **TODAY'S TASKS - {today}**\n\n"
    markup = types.InlineKeyboardMarkup()
    for tid, name, reward in tasks:
        if "||" in name:
            task_name, link = name.split("||")
        else:
            task_name, link = name, None

        c.execute("SELECT status FROM submissions WHERE user_id=? AND task_id=? AND date=?", (user_id, tid, today))
        done = c.fetchone()
        status = "✅ Done" if done else "⏳ Pending"

        text += f"**{task_name}**\nReward: {reward} pts | {status}\n"
        if link:
            markup.add(types.InlineKeyboardButton(f"🔗 {task_name}", url=link))
        if not done:
            markup.add(types.InlineKeyboardButton(f"📤 Submit Proof", callback_data=f"submit_{tid}"))
        text += "\n"

    bot.send_message(user_id, text, parse_mode="Markdown", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith("submit_"))
def submit_task(call):
    user_id = call.from_user.id
    tid = int(call.data.split("_")[1])

    # 30 SEC COOLDOWN CHECK
    now = time.time()
    c.execute("SELECT last_submit FROM cooldowns WHERE user_id=?", (user_id,))
    last = c.fetchone()
    if last and now - last[0] < 30:
        wait = int(30 - (now - last[0]))
        bot.answer_callback_query(call.id, f"Wait {wait} seconds before next submit!", show_alert=True)
        return

    bot.send_message(user_id, "📸 Send me a Screenshot or Screen Record as proof now.\nYou have 30s cooldown after this.")
    bot.register_next_step_handler_by_chat_id(user_id, lambda m: handle_proof(m, tid))

def handle_proof(message, tid):
    user_id = message.from_user.id
    today = today_nigeria()

    if not message.photo and not message.video:
        bot.send_message(user_id, "❌ Please send a photo or video only.")
        return

    # ANTI-CHEAT HASH
    file_id = message.photo[-1].file_id if message.photo else message.video.file_id
    file_info = bot.get_file(file_id)
    file = bot.download_file(file_info.file_path)
    file_hash = hashlib.sha256(file).hexdigest()

    c.execute("SELECT * FROM used_hashes WHERE hash=?", (file_hash,))
    if c.fetchone():
        bot.send_message(user_id, "❌ This proof was already used! Anti-cheat blocked.")
        return

    c.execute("INSERT INTO used_hashes (hash) VALUES (?)", (file_hash,))
    c.execute("INSERT INTO submissions (user_id, task_id, status, date, proof_hash, submit_time) VALUES (?,?,?,?,?,?)",
              (user_id, tid, 'pending', today, file_hash, time.time()))
    c.execute("REPLACE INTO cooldowns (user_id, last_submit) VALUES (?,?)", (user_id, time.time()))
    conn.commit()

    bot.send_message(ADMIN_ID, f"🚨 New Proof Submitted!\nUser: {user_id}\nTask: {tid}\nDate: {today}")
    bot.send_message(user_id, "✅ Proof submitted! Waiting for admin approval.")

# ========= ADMIN APPROVE TASKS =========
@bot.message_handler(func=lambda m: m.from_user.id == ADMIN_ID and m.text == "🚨 Approve Tasks")
def approve_tasks(message):
    c.execute("SELECT s.user_id, s.task_id, t.name, t.reward FROM submissions s JOIN tasks t ON s.task_id=t.task_id WHERE s.status='pending'")
    pending = c.fetchall()
    if not pending:
        bot.send_message(ADMIN_ID, "No pending tasks.")
        return
    for uid, tid, name, reward in pending:
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("✅ Approve", callback_data=f"approve_{uid}_{tid}_{reward}"))
        markup.add(types.InlineKeyboardButton("❌ Reject", callback_data=f"reject_{uid}_{tid}"))
        bot.send_message(ADMIN_ID, f"User: {uid}\nTask: {name}\nReward: {reward}", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith("approve_"))
def approve(call):
    _, uid, tid, reward = call.data.split("_")
    uid, tid, reward = int(uid), int(tid), float(reward)
    c.execute("UPDATE submissions SET status='approved' WHERE user_id=? AND task_id=?", (uid, tid))
    c.execute("UPDATE users SET hold_points = hold_points +? WHERE user_id=?", (reward, uid))
    c.execute("INSERT INTO hold_history (user_id, amount, add_date) VALUES (?,?,?)", (uid, reward, time.time()))
    conn.commit()
    bot.send_message(uid, f"✅ Task Approved! +{reward} Points added to Hold")
    bot.answer_callback_query(call.id, "Approved")

# ========= ADD TASK WITH LINK =========
@bot.message_handler(func=lambda m: m.from_user.id == ADMIN_ID and m.text == "➕ Add Task")
def add_task_start(message):
    bot.send_message(ADMIN_ID, "➕ **Send task in format:**\n`Task Name | Reward | Link`\n\n**Example:**\n`Join channel | 500 | https://t.me/polmatrix`", parse_mode="Markdown")

@bot.message_handler(func=lambda m: m.from_user.id == ADMIN_ID and "|" in m.text)
def handle_task_add(message):
    try:
        parts = message.text.split("|")
        if len(parts) < 3: raise Exception
        name = parts[0].strip()
        reward = float(parts[1].strip())
        link = parts[2].strip()
        c.execute("INSERT INTO tasks (name, reward) VALUES (?,?)", (f"{name}||{link}", reward))
        conn.commit()
        bot.send_message(ADMIN_ID, f"✅ Task Added!\n\n**Name:** {name}\n**Reward:** {reward} pts\n**Link:** {link}")
    except:
        bot.send_message(ADMIN_ID, "❌ Invalid format. Use: `Task Name | Reward | Link`", parse_mode="Markdown")

# ========= OTHER COMMANDS =========
@bot.message_handler(commands=['start'])
def start(message):
    user_id = message.from_user.id
    referrer = int(message.text.split()[1]) if len(message.text.split()) > 1 else None
    c.execute("INSERT OR IGNORE INTO users (user_id, referrer_id, join_date) VALUES (?,?,?)", (user_id, referrer, today_nigeria()))
    conn.commit()
    if user_id == ADMIN_ID:
        bot.send_message(user_id, "👑 **ADMIN PANEL**", parse_mode="Markdown", reply_markup=admin_keyboard())
    else:
        bot.send_message(user_id, "👋 **Welcome to POL MATRIX**\n\nWe added **50 Points** as apology 🙏", reply_markup=user_keyboard())

@bot.message_handler(func=lambda m: m.text == "💰 Balance")
def balance(message):
    user_id = message.from_user.id
    hold, release = get_balances(user_id)
    bot.send_message(user_id, f"💰 **Your Balance**\n\n**Hold Points:** {hold}\n**Release Points:** {release}\n**Total:** {hold+release} pts", parse_mode="Markdown")

@bot.message_handler(func=lambda m: m.from_user.id == ADMIN_ID and m.text == "💾 Backup Now")
def manual_backup(message):
    auto_backup()
    bot.send_message(ADMIN_ID, "✅ Manual backup created")

bot.infinity_polling(none_stop=True)
