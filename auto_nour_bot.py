import telebot
from telebot import types
import sqlite3
import json
import time
import re
from datetime import datetime

# إعدادات البوت
BOT_TOKEN = '8210695509:AAG9mDBnfYL3XKcaIqMbVa4T8c2CH7eZ2Bs'
ADMIN_ID = '1338247690'
SERIATEL_NUMBER = '0932484039'

# تهيئة البوت
bot = telebot.TeleBot(BOT_TOKEN)

# دوال مساعدة للتعامل مع قاعدة البيانات
def get_db_connection():
    return sqlite3.connect('trillo_store.db')

# تهيئة قاعدة البيانات
def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # جدول المستخدمين
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY,
        username TEXT,
        balance INTEGER DEFAULT 0,
        total_spent INTEGER DEFAULT 0,
        purchases_count INTEGER DEFAULT 0,
        is_banned INTEGER DEFAULT 0
    )
    ''')
    
    # جدول الطلبات
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS orders (
        order_id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        game TEXT,
        category TEXT,
        price INTEGER,
        player_id TEXT,
        status TEXT DEFAULT 'pending',
        admin_action TEXT DEFAULT 'none',
        order_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES users (user_id)
    )
    ''')
    
    # جدول طلبات شحن الرصيد
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS deposit_requests (
        request_id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        amount INTEGER,
        transaction_id TEXT,
        status TEXT DEFAULT 'pending',
        admin_action TEXT DEFAULT 'none',
        request_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES users (user_id)
    )
    ''')
    
    # جدول إعدادات البوت
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS settings (
        key TEXT PRIMARY KEY,
        value TEXT
    )
    ''')
    
    # جدول أسعار المنتجات
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS products (
        game TEXT,
        category TEXT,
        price INTEGER,
        is_active INTEGER DEFAULT 1,
        display_order INTEGER DEFAULT 0,
        PRIMARY KEY (game, category)
    )
    ''')

    # جدول المشرفين
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS admins (
        user_id INTEGER PRIMARY KEY,
        is_main_admin INTEGER DEFAULT 0
    )
    ''')
    
    # جدول القناة الإجبارية
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS mandatory_channel (
        channel_id TEXT PRIMARY KEY,
        channel_link TEXT,
        is_active INTEGER DEFAULT 0
    )
    ''')
    
    # إضافة جدول لإعدادات قنوات الطلبات
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS channel_settings (
        key TEXT PRIMARY KEY,
        value TEXT
    )
    ''')
    
    # جدول جديد لتتبع المعاملات المكتملة
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS processed_transactions (
        transaction_id TEXT PRIMARY KEY,
        amount INTEGER,
        user_id INTEGER,
        processed_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    ''')
    
    # جدول جديد للرسائل الواردة من قناة SMS
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS sms_messages (
        message_id INTEGER PRIMARY KEY AUTOINCREMENT,
        transaction_id TEXT,
        amount INTEGER,
        message_text TEXT,
        received_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    ''')
    
    # التحقق إذا كان عمود display_order موجود وإضافته إذا لم يكن موجوداً
    try:
        cursor.execute("SELECT display_order FROM products LIMIT 1")
    except sqlite3.OperationalError:
        cursor.execute('ALTER TABLE products ADD COLUMN display_order INTEGER DEFAULT 0')
    
    # إدخال البيانات الافتراضية للمنتجات مع ترتيب العرض
    default_products = [
        ('FREEFIRE', '110 💎', 1000, 1, 1),
        ('FREEFIRE', '330 💎', 2500, 1, 2),
        ('FREEFIRE', '530 💎', 4000, 1, 3),
        ('FREEFIRE', '1080 💎', 7500, 1, 4),
        ('FREEFIRE', 'عضوية أسبوعية 🎟', 3000, 1, 5),
        ('FREEFIRE', 'عضوية شهرية 🎫', 10000, 1, 6),
        ('PUBGMOBILE', '60 UC', 1500, 1, 1),
        ('PUBGMOBILE', '120 UC', 2800, 1, 2),
        ('PUBGMOBILE', '325 UC', 7000, 1, 3),
        ('PUBGMOBILE', '660 UC', 13000, 1, 4),
        ('PUBGMOBILE', '1800 UC', 35000, 1, 5)
    ]
    
    # حذف البيانات القديمة أولاً ثم إدخال الجديدة
    cursor.execute('DELETE FROM products')
    
    cursor.executemany('''
    INSERT INTO products (game, category, price, is_active, display_order)
    VALUES (?, ?, ?, ?, ?)
    ''', default_products)
    
    # إدخال الإعدادات الافتراضية
    cursor.execute('INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)', 
                  ('seriatel_number', SERIATEL_NUMBER))
    cursor.execute('INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)', 
                  ('bot_active', '1'))
    
    # إدخال الإعدادات الافتراضية لقنوات الطلبات
    cursor.execute('INSERT OR IGNORE INTO channel_settings (key, value) VALUES (?, ?)', 
                  ('orders_channel_id', ''))
    cursor.execute('INSERT OR IGNORE INTO channel_settings (key, value) VALUES (?, ?)', 
                  ('deposit_channel_id', ''))
    cursor.execute('INSERT OR IGNORE INTO channel_settings (key, value) VALUES (?, ?)', 
                  ('sms_channel_id', ''))  # قناة رسائل SMS
    cursor.execute('INSERT OR IGNORE INTO channel_settings (key, value) VALUES (?, ?)', 
                  ('send_to_channels', '0'))
    
    # إضافة الأدمن الأساسي إلى جدول المشرفين
    cursor.execute('INSERT OR IGNORE INTO admins (user_id, is_main_admin) VALUES (?, ?)', 
                  (ADMIN_ID, 1))

    conn.commit()
    conn.close()

# استدعاء تهيئة قاعدة البيانات
init_db()

# دوال جديدة للتعامل مع المعاملات التلقائية
def is_transaction_processed(transaction_id):
    """التحقق إذا كانت المعاملة معالجة مسبقاً"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT 1 FROM processed_transactions WHERE transaction_id = ?', (transaction_id,))
    result = cursor.fetchone()
    conn.close()
    return result is not None

def mark_transaction_processed(transaction_id, amount, user_id):
    """تسجيل المعاملة كمكتملة"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('INSERT INTO processed_transactions (transaction_id, amount, user_id) VALUES (?, ?, ?)', 
                  (transaction_id, amount, user_id))
    conn.commit()
    conn.close()

def save_sms_message(transaction_id, amount, message_text):
    """حفظ رسالة SMS في قاعدة البيانات"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('INSERT INTO sms_messages (transaction_id, amount, message_text) VALUES (?, ?, ?)', 
                  (transaction_id, amount, message_text))
    conn.commit()
    conn.close()

def find_sms_by_transaction(transaction_id):
    """البحث عن رسالة SMS برقم العملية"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM sms_messages WHERE transaction_id = ? ORDER BY received_date DESC LIMIT 1', (transaction_id,))
    sms = cursor.fetchone()
    conn.close()
    return sms

def extract_amount_and_transaction(text):
    """استخراج المبلغ ورقم العملية من نص الرسالة"""
    # أنماط مختلفة لنص الرسالة
    patterns = [
        r'تم استلام مبلغ (\d+) ل\.س.*رقم العملية هو (\d+)',
        r'تم استلام مبلغ (\d+) ل\.س.*رقم العمليه (\d+)',
        r'مبلغ (\d+) ل\.س.*رقم العمليه (\d+)',
        r'(\d+) ل\.س.*رقم العمليه (\d+)',
        r'(\d+) ليرة.*رقم العمليه (\d+)',
        r'Amount:? (\d+).*Transaction:? (\d+)',
    ]
    
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            amount = int(match.group(1))
            transaction_id = match.group(2)
            return amount, transaction_id
    
    return None, None

def process_deposit_request(user_id, amount, transaction_id):
    """معالجة طلب الإيداع"""
    # التحقق إذا كانت المعاملة معالجة مسبقاً
    if is_transaction_processed(transaction_id):
        return False, "❌ رقم العملية هذا تم استخدامه مسبقاً"
    
    # البحث عن رسالة SMS مطابقة
    sms_message = find_sms_by_transaction(transaction_id)
    if not sms_message:
        return False, "❌ لم يتم العثور على العملية، إما أن رقم العملية غير صحيح أو لم تصل بعد"
    
    sms_amount = sms_message[2]  # المبلغ من رسالة SMS
    
    # التحقق من تطابق المبلغ
    if amount != sms_amount:
        return False, f"❌ المبلغ غير مطابق. المبلغ المدخل: {amount}, المبلغ المرسل: {sms_amount}"
    
    # إضافة الرصيد للمستخدم
    update_user_balance(user_id, amount)
    
    # تسجيل المعاملة كمكتملة
    mark_transaction_processed(transaction_id, amount, user_id)
    
    # إرسال إشعار للمستخدم
    new_balance = get_user_balance(user_id)
    user_notification = f"""
✅ تم شحن رصيدك بنجاح!

💳 المبلغ: {amount} ل.س
🔢 رقم العملية: {transaction_id}
💰 رصيدك الحالي: {new_balance} ل.س

شكراً لاستخدامك خدماتنا! 🎮
    """
    
    try:
        bot.send_message(user_id, user_notification)
    except:
        pass  # إذا لم نتمكن من إرسال رسالة للمستخدم
    
    # إرسال إشعار للأدمن
    admin_notification = f"""
✅ تم إيداع رصيد تلقائياً:

👤 المستخدم: {user_id}
💳 المبلغ: {amount} ل.س  
🔢 رقم العملية: {transaction_id}
⏰ الوقت: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
    """
    
    try:
        bot.send_message(ADMIN_ID, admin_notification)
    except:
        pass
    
    return True, "✅ تم إضافة الرصيد بنجاح"

# دوال مساعدة إضافية للتعامل مع قاعدة البيانات
def is_admin(user_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT 1 FROM admins WHERE user_id = ?', (user_id,))
    result = cursor.fetchone()
    conn.close()
    return result is not None

def is_main_admin(user_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT is_main_admin FROM admins WHERE user_id = ?', (user_id,))
    result = cursor.fetchone()
    conn.close()
    return result and result[0] == 1

def add_admin(user_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('INSERT OR IGNORE INTO admins (user_id) VALUES (?)', (user_id,))
    conn.commit()
    conn.close()

def remove_admin(user_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('DELETE FROM admins WHERE user_id = ? AND is_main_admin = 0', (user_id,))
    conn.commit()
    conn.close()

def get_all_admins():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT user_id, is_main_admin FROM admins')
    admins = cursor.fetchall()
    conn.close()
    return admins

def set_mandatory_channel(channel_id, channel_link):
    conn = get_db_connection()
    cursor = conn.cursor()
    # حذف أي قناة سابقة وتعيين الجديدة
    cursor.execute('DELETE FROM mandatory_channel')
    cursor.execute('INSERT INTO mandatory_channel (channel_id, channel_link, is_active) VALUES (?, ?, ?)', 
                  (channel_id, channel_link, 1))
    conn.commit()
    conn.close()

def get_mandatory_channel():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT channel_id, channel_link, is_active FROM mandatory_channel LIMIT 1')
    channel = cursor.fetchone()
    conn.close()
    return channel

def toggle_mandatory_channel(is_active):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('UPDATE mandatory_channel SET is_active = ?', (is_active,))
    conn.commit()
    conn.close()

# دوال جديدة للتعامل مع إعدادات القنوات
def get_channel_setting(key):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT value FROM channel_settings WHERE key = ?', (key,))
    result = cursor.fetchone()
    conn.close()
    return result[0] if result else None

def update_channel_setting(key, value):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('INSERT OR REPLACE INTO channel_settings (key, value) VALUES (?, ?)', 
                  (key, value))
    conn.commit()
    conn.close()

def get_user(user_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM users WHERE user_id = ?', (user_id,))
    user = cursor.fetchone()
    conn.close()
    return user

def create_user(user_id, username):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('INSERT OR IGNORE INTO users (user_id, username) VALUES (?, ?)', 
                  (user_id, username))
    conn.commit()
    conn.close()

def update_user_balance(user_id, amount):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('UPDATE users SET balance = balance + ? WHERE user_id = ?', 
                  (amount, user_id))
    if amount < 0:
        cursor.execute('UPDATE users SET total_spent = total_spent + ? WHERE user_id = ?', 
                      (-amount, user_id))
        cursor.execute('UPDATE users SET purchases_count = purchases_count + 1 WHERE user_id = ?', 
                      (user_id,))
    conn.commit()
    conn.close()

def get_user_balance(user_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT balance FROM users WHERE user_id = ?', (user_id,))
    result = cursor.fetchone()
    conn.close()
    return result[0] if result else 0

def ban_user(user_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('UPDATE users SET is_banned = 1 WHERE user_id = ?', (user_id,))
    conn.commit()
    conn.close()

def unban_user(user_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('UPDATE users SET is_banned = 0 WHERE user_id = ?', (user_id,))
    conn.commit()
    conn.close()

def get_setting(key):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT value FROM settings WHERE key = ?', (key,))
    result = cursor.fetchone()
    conn.close()
    return result[0] if result else None

def update_setting(key, value):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)', 
                  (key, value))
    conn.commit()
    conn.close()

def get_product_price(game, category):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT price FROM products WHERE game = ? AND category = ? AND is_active = 1', 
                  (game, category))
    result = cursor.fetchone()
    conn.close()
    return result[0] if result else None

def get_all_products(game=None):
    conn = get_db_connection()
    cursor = conn.cursor()
    
    if game:
        cursor.execute('SELECT * FROM products WHERE game = ? ORDER BY display_order', (game,))
    else:
        cursor.execute('SELECT * FROM products ORDER BY game, display_order')
        
    products = cursor.fetchall()
    conn.close()
    return products

def update_product_price(game, category, new_price):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('UPDATE products SET price = ? WHERE game = ? AND category = ?', 
                  (new_price, game, category))
    conn.commit()
    conn.close()

def toggle_product_status(game, category, status):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('UPDATE products SET is_active = ? WHERE game = ? AND category = ?', 
                  (status, game, category))
    conn.commit()
    conn.close()

def create_order(user_id, game, category, price, player_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
    INSERT INTO orders (user_id, game, category, price, player_id)
    VALUES (?, ?, ?, ?, ?)
    ''', (user_id, game, category, price, player_id))
    order_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return order_id

def update_order_status(order_id, status, admin_action='none'):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
    UPDATE orders SET status = ?, admin_action = ? WHERE order_id = ?
    ''', (status, admin_action, order_id))
    conn.commit()
    conn.close()

def create_deposit_request(user_id, amount, transaction_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
    INSERT INTO deposit_requests (user_id, amount, transaction_id)
    VALUES (?, ?, ?)
    ''', (user_id, amount, transaction_id))
    request_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return request_id

def update_deposit_request_status(request_id, status, admin_action='none'):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
    UPDATE deposit_requests SET status = ?, admin_action = ? WHERE request_id = ?
    ''', (status, admin_action, request_id))
    conn.commit()
    conn.close()

def get_pending_orders():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM orders WHERE status = "pending"')
    orders = cursor.fetchall()
    conn.close()
    return orders

def get_pending_deposit_requests():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM deposit_requests WHERE status = "pending"')
    requests = cursor.fetchall()
    conn.close()
    return requests

def get_user_stats():
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # إجمالي المستخدمين
    cursor.execute('SELECT COUNT(*) FROM users')
    total_users = cursor.fetchone()[0]
    
    # المستخدمين النشطين (استخدموا البوت خلال آخر 30 يوم)
    thirty_days_ago = time.time() - (30 * 24 * 60 * 60)
    cursor.execute('SELECT COUNT(DISTINCT user_id) FROM orders WHERE order_date > ?', 
                  (thirty_days_ago,))
    active_users = cursor.fetchone()[0]
    
    # المستخدمين المحظورين
    cursor.execute('SELECT COUNT(*) FROM users WHERE is_banned = 1')
    banned_users = cursor.fetchone()[0]
    
    # طلبات الإيداع التي تحتاج مراجعة
    cursor.execute('SELECT COUNT(*) FROM deposit_requests WHERE status = "pending"')
    pending_deposits = cursor.fetchone()[0]
    
    # طلبات الشحن المكتملة
    cursor.execute('SELECT COUNT(*) FROM orders WHERE status = "completed"')
    completed_orders = cursor.fetchone()[0]
    
    # طلبات الإيداع المكتملة
    cursor.execute('SELECT COUNT(*) FROM deposit_requests WHERE status = "completed"')
    completed_deposits = cursor.fetchone()[0]
    
    conn.close()
    
    return {
        'total_users': total_users,
        'active_users': active_users,
        'banned_users': banned_users,
        'pending_deposits': pending_deposits,
        'completed_orders': completed_orders,
        'completed_deposits': completed_deposits
    }

# دوال إنشاء لوحات المفاتيح
def create_main_keyboard():
    keyboard = types.InlineKeyboardMarkup(row_width=1)
    games_btn = types.InlineKeyboardButton("الألعاب 🎮", callback_data="games")
    account_btn = types.InlineKeyboardButton("الحساب والمعلومات 👤", callback_data="account")
    help_btn = types.InlineKeyboardButton("🚨 المساعدة والدعم 🚨", callback_data="help")
    keyboard.add(games_btn, account_btn, help_btn)
    return keyboard

def create_games_keyboard():
    keyboard = types.InlineKeyboardMarkup(row_width=1)
    freefire_btn = types.InlineKeyboardButton("𝗙𝗥𝗘𝗘 𝗙𝗜𝗥𝗘 🎮", callback_data="game_FREEFIRE")
    pubg_btn = types.InlineKeyboardButton("𝗣𝗨𝗕𝗚 𝗠𝗢𝗕𝗜𝗟𝗘🎮", callback_data="game_PUBGMOBILE")
    back_btn = types.InlineKeyboardButton("رجوع", callback_data="main_menu")
    keyboard.add(freefire_btn, pubg_btn, back_btn)
    return keyboard

def create_categories_keyboard(game, is_admin=False):
    keyboard = types.InlineKeyboardMarkup(row_width=2)
    
    products = get_all_products(game)
    for product in products:
        if product[3] or is_admin:  # if is_active or admin view
            btn_text = f"{product[1]} - {product[2]} ل.س"
            if not product[3]:
                btn_text += " (غير مفعل)"
                
            btn = types.InlineKeyboardButton(
                btn_text, 
                callback_data=f"category_{game}_{product[1]}" if not is_admin else f"admin_category_{game}_{product[1]}"
            )
            keyboard.add(btn)
    
    back_target = "games" if not is_admin else f"admin_control_{game}"
    back_btn = types.InlineKeyboardButton("رجوع", callback_data=back_target)
    keyboard.add(back_btn)
    return keyboard

def create_confirmation_keyboard(order_id):
    keyboard = types.InlineKeyboardMarkup(row_width=2)
    confirm_btn = types.InlineKeyboardButton("تأكيد العملية✅", callback_data=f"confirm_{order_id}")
    cancel_btn = types.InlineKeyboardButton("ألغاء العملية❌", callback_data=f"cancel_{order_id}")
    keyboard.add(confirm_btn, cancel_btn)
    return keyboard

def create_admin_order_keyboard(order_id):
    keyboard = types.InlineKeyboardMarkup(row_width=2)
    accept_btn = types.InlineKeyboardButton("قبول ✅", callback_data=f"admin_accept_{order_id}")
    reject_btn = types.InlineKeyboardButton("رفض ❌", callback_data=f"admin_reject_{order_id}")
    keyboard.add(accept_btn, reject_btn)
    return keyboard

def create_admin_deposit_keyboard(request_id):
    keyboard = types.InlineKeyboardMarkup(row_width=2)
    accept_btn = types.InlineKeyboardButton("قبول ✅", callback_data=f"admin_deposit_accept_{request_id}")
    reject_btn = types.InlineKeyboardButton("رفض ❌", callback_data=f"admin_deposit_reject_{request_id}")
    keyboard.add(accept_btn, reject_btn)
    return keyboard

def create_admin_main_keyboard(user_id):
    keyboard = types.InlineKeyboardMarkup(row_width=2)
    stats_btn = types.InlineKeyboardButton("📊 احصائيات", callback_data="admin_stats")
    add_balance_btn = types.InlineKeyboardButton("➕ اضافة رصيد", callback_data="admin_add_balance")
    deduct_balance_btn = types.InlineKeyboardButton("➖ خصم رصيد", callback_data="admin_deduct_balance")
    ban_user_btn = types.InlineKeyboardButton("🚫 حظر عضو", callback_data="admin_ban_user")
    unban_user_btn = types.InlineKeyboardButton("🪄 رفع حظر", callback_data="admin_unban_user")
    control_panel_btn = types.InlineKeyboardButton("⚙️ لوحة التحكم", callback_data="admin_control_panel")
    change_number_btn = types.InlineKeyboardButton("📱 تغيير رقم سيرياتيل", callback_data="admin_change_number")
    user_info_btn = types.InlineKeyboardButton("🪪 معلومات عضو", callback_data="admin_user_info")
    toggle_bot_btn = types.InlineKeyboardButton("⏸️ إيقاف/تشغيل البوت", callback_data="admin_toggle_bot")
    orders_channels_btn = types.InlineKeyboardButton("📤 قنوات الطلبات", callback_data="admin_orders_channels")
    sms_settings_btn = types.InlineKeyboardButton("📨 إعدادات SMS", callback_data="admin_sms_settings")
    
    keyboard.add(stats_btn, add_balance_btn, deduct_balance_btn, ban_user_btn, 
                unban_user_btn, control_panel_btn, change_number_btn, user_info_btn, 
                toggle_bot_btn, orders_channels_btn, sms_settings_btn)
    
    # إضافة أزرار المشرف الأساسي فقط
    if is_main_admin(user_id):
        admins_panel_btn = types.InlineKeyboardButton("👑 قسم المشرفين", callback_data="admin_admins_panel")
        channel_btn = types.InlineKeyboardButton("🔗 قناة الاشتراك الاجباري", callback_data="admin_channel_settings")
        keyboard.add(admins_panel_btn, channel_btn)
        
    return keyboard

def create_admin_control_panel_keyboard():
    keyboard = types.InlineKeyboardMarkup(row_width=1)
    freefire_btn = types.InlineKeyboardButton("FREE FIRE", callback_data="admin_control_FREEFIRE")
    pubg_btn = types.InlineKeyboardButton("PUBG MOBILE", callback_data="admin_control_PUBGMOBILE")
    back_btn = types.InlineKeyboardButton("رجوع", callback_data="admin_main")
    keyboard.add(freefire_btn, pubg_btn, back_btn)
    return keyboard

def create_admin_category_control_keyboard(game, category):
    keyboard = types.InlineKeyboardMarkup(row_width=2)
    change_price_btn = types.InlineKeyboardButton("🔧 تغيير السعر", callback_data=f"admin_change_price_{game}_{category}")
    
    # التحقق من حالة المنتج
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT is_active FROM products WHERE game = ? AND category = ?', (game, category))
    result = cursor.fetchone()
    is_active = result[0] if result else 0
    conn.close()
    
    if is_active:
        deactivate_btn = types.InlineKeyboardButton("تعطيل ❌", callback_data=f"admin_deactivate_{game}_{category}")
        keyboard.add(change_price_btn, deactivate_btn)
    else:
        activate_btn = types.InlineKeyboardButton("تفعيل ✅", callback_data=f"admin_activate_{game}_{category}")
        keyboard.add(change_price_btn, activate_btn)
    
    back_btn = types.InlineKeyboardButton("رجوع", callback_data=f"admin_control_{game}")
    keyboard.add(back_btn)
    return keyboard

def create_back_keyboard(target):
    keyboard = types.InlineKeyboardMarkup()
    back_btn = types.InlineKeyboardButton("رجوع", callback_data=target)
    keyboard.add(back_btn)
    return keyboard

def create_admins_list_keyboard():
    keyboard = types.InlineKeyboardMarkup()
    admins = get_all_admins()
    for admin in admins:
        user_id = admin[0]
        is_main = admin[1]
        
        # لا تعرض زر حذف للأدمن الأساسي
        if not is_main:
            btn = types.InlineKeyboardButton(f"🗑️ حذف المشرف {user_id}", callback_data=f"admin_remove_{user_id}")
            keyboard.add(btn)

    add_btn = types.InlineKeyboardButton("➕ إضافة مشرف جديد", callback_data="admin_add_new_admin")
    back_btn = types.InlineKeyboardButton("رجوع", callback_data="admin_main")
    keyboard.add(add_btn, back_btn)
    return keyboard

def create_channel_settings_keyboard():
    keyboard = types.InlineKeyboardMarkup()
    channel = get_mandatory_channel()
    
    if channel and channel[2] == 1:
        toggle_btn = types.InlineKeyboardButton("🔴 تعطيل الاشتراك الإجباري", callback_data="admin_toggle_channel_0")
        keyboard.add(toggle_btn)
    else:
        toggle_btn = types.InlineKeyboardButton("🟢 تفعيل الاشتراك الإجباري", callback_data="admin_toggle_channel_1")
        keyboard.add(toggle_btn)
        
    set_btn = types.InlineKeyboardButton("🔗 تحديد القناة", callback_data="admin_set_channel")
    back_btn = types.InlineKeyboardButton("رجوع", callback_data="admin_main")
    keyboard.add(set_btn, back_btn)
    return keyboard

def create_orders_channels_keyboard():
    keyboard = types.InlineKeyboardMarkup(row_width=1)
    
    send_to_channels = get_channel_setting('send_to_channels')
    toggle_status = "تعطيل" if send_to_channels == '1' else "تفعيل"
    toggle_data = '0' if send_to_channels == '1' else '1'
    toggle_color = "🔴" if send_to_channels == '1' else "🟢"
    
    toggle_btn = types.InlineKeyboardButton(f"{toggle_color} {toggle_status} إرسال الطلبات للقنوات", callback_data=f"admin_toggle_orders_channels_{toggle_data}")
    set_orders_btn = types.InlineKeyboardButton("🔗 تحديد قناة الشحن", callback_data="admin_set_orders_channel")
    set_deposits_btn = types.InlineKeyboardButton("🔗 تحديد قناة الإيداع", callback_data="admin_set_deposits_channel")
    back_btn = types.InlineKeyboardButton("رجوع", callback_data="admin_main")

    keyboard.add(toggle_btn, set_orders_btn, set_deposits_btn, back_btn)
    return keyboard

def create_sms_settings_keyboard():
    keyboard = types.InlineKeyboardMarkup(row_width=1)
    
    set_sms_channel_btn = types.InlineKeyboardButton("🔗 تحديد قناة SMS", callback_data="admin_set_sms_channel")
    back_btn = types.InlineKeyboardButton("رجوع", callback_data="admin_main")
    
    keyboard.add(set_sms_channel_btn, back_btn)
    return keyboard

def check_mandatory_subscription(user_id):
    channel_info = get_mandatory_channel()
    if not channel_info or not channel_info[2]: # القناة غير محددة أو غير مفعلة
        return True, None, None
    
    channel_id = channel_info[0]
    channel_link = channel_info[1]
    
    try:
        member = bot.get_chat_member(chat_id=channel_id, user_id=user_id)
        if member.status in ['member', 'creator', 'administrator']:
            return True, None, None
        else:
            return False, channel_link, channel_id
    except telebot.apihelper.ApiException as e:
        # إذا كانت القناة غير صحيحة أو البوت ليس فيها
        return False, channel_link, channel_id

# معالجة الأوامر
@bot.message_handler(commands=['start', 'رجوع'])
def send_welcome(message):
    user_id = message.from_user.id
    username = message.from_user.username or f"user_{user_id}"
    
    # التحقق إذا كان المستخدم محظور
    user = get_user(user_id)
    if user and user[5] == 1:  # is_banned
        bot.send_message(message.chat.id, "🚫 تم حظرك من استخدام البوت ، تواصل مع @DEV_NOUR1 لمعرفة سبب الحظر")
        return
    
    # التحقق من الاشتراك الإجباري
    is_subscribed, channel_link, channel_id = check_mandatory_subscription(user_id)
    if not is_subscribed:
        keyboard = types.InlineKeyboardMarkup()
        channel_btn = types.InlineKeyboardButton("اضغط للانضمام للقناة", url=channel_link)
        check_btn = types.InlineKeyboardButton("✅ تحقق من الاشتراك", callback_data="check_subscription")
        keyboard.add(channel_btn, check_btn)
        bot.send_message(message.chat.id, "📢 يجب عليك الانضمام إلى قناتنا لمتابعة استخدام البوت 👇", reply_markup=keyboard)
        return
        
    # إنشاء المستخدم إذا لم يكن موجوداً
    create_user(user_id, username)
    
    # التحقق من حالة البوت
    bot_active = get_setting('bot_active')
    if bot_active == '0':
        bot.send_message(message.chat.id, "البوت متوقف حاليًا عن العمل. يرجى المحاولة لاحقًا.")
        return
    
    welcome_text = """
    اهــلا و سهــلا بــك فـي بـوت Trillo Store®️  
    اخــتـر أحــد الأوامــر الــتـالـيــة :
    """
    
    bot.send_message(message.chat.id, welcome_text, reply_markup=create_main_keyboard())

@bot.message_handler(commands=['admin'])
def admin_panel(message):
    user_id = message.from_user.id
    
    # التحقق من صلاحية الأدمن
    if not is_admin(user_id):
        bot.send_message(message.chat.id, "ليس لديك صلاحية للوصول إلى لوحة الأدمن.")
        return
    
    admin_text = "👋 أهلاً يا أدمن ، اختر أحد الخيارات :"
    bot.send_message(message.chat.id, admin_text, reply_markup=create_admin_main_keyboard(user_id))

# معالجة رسائل القناة
@bot.channel_post_handler(content_types=['text'])
def handle_channel_post(message):
    """معالجة الرسائل في القناة المحددة لرسائل SMS"""
    sms_channel_id = get_channel_setting('sms_channel_id')
    
    if not sms_channel_id or str(message.chat.id) != sms_channel_id:
        return
    
    text = message.text
    amount, transaction_id = extract_amount_and_transaction(text)
    
    if amount and transaction_id:
        # حفظ رسالة SMS في قاعدة البيانات
        save_sms_message(transaction_id, amount, text)
        
        # إرسال تقرير للأدمن
        admin_report = f"""
📨 رسالة SMS جديدة:

📝 النص: {text}
💰 المبلغ: {amount}
🔢 رقم العملية: {transaction_id}
⏰ الوقت: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
        """
        
        try:
            bot.send_message(ADMIN_ID, admin_report)
        except:
            pass

# معالجة Callback Queries
@bot.callback_query_handler(func=lambda call: True)
def handle_callback(call):
    user_id = call.from_user.id
    message_id = call.message.message_id
    chat_id = call.message.chat.id
    
    # تحقق من صلاحية الأدمن قبل معالجة أوامر الأدمن
    if call.data.startswith('admin_') and not is_admin(user_id):
        bot.answer_callback_query(call.id, "ليس لديك صلاحية للوصول إلى هذا القسم.")
        return

    # التحقق من حالة البوت
    bot_active = get_setting('bot_active')
    if bot_active == '0' and not call.data.startswith('admin_'):
        bot.answer_callback_query(call.id, "البوت متوقف حاليًا عن العمل.")
        return
        
    # التحقق من الاشتراك الإجباري
    if not call.data.startswith('admin_'):
        is_subscribed, channel_link, channel_id = check_mandatory_subscription(user_id)
        if not is_subscribed:
            keyboard = types.InlineKeyboardMarkup()
            channel_btn = types.InlineKeyboardButton("اضغط للانضمام للقناة", url=channel_link)
            check_btn = types.InlineKeyboardButton("✅ تحقق من الاشتراك", callback_data="check_subscription")
            keyboard.add(channel_btn, check_btn)
            bot.edit_message_text(
                chat_id=chat_id,
                message_id=message_id,
                text="📢 يجب عليك الانضمام إلى قناتنا لمتابعة استخدام البوت 👇",
                reply_markup=keyboard
            )
            bot.answer_callback_query(call.id)
            return

    # التحقق من الاشتراك بعد ضغط الزر
    if call.data == "check_subscription":
        is_subscribed, channel_link, channel_id = check_mandatory_subscription(user_id)
        if is_subscribed:
            bot.edit_message_text(
                chat_id=chat_id, 
                message_id=message_id, 
                text="✅ شكراً لانضمامك! يمكنك الآن استخدام البوت.", 
                reply_markup=create_main_keyboard()
            )
        else:
            bot.answer_callback_query(call.id, "❌ لم يتم التحقق من اشتراكك بعد.")
        return
    
    # القائمة الرئيسية
    if call.data == "main_menu":
        welcome_text = """
    اهــلا و سهــلا بــك فـي بـوت Trillo Store®️  
    اخــتـر أحــد الأوامــر الــتـالـيــة :
    """
        bot.edit_message_text(
            chat_id=chat_id, 
            message_id=message_id, 
            text=welcome_text, 
            reply_markup=create_main_keyboard()
        )
    
    # قسم الألعاب
    elif call.data == "games":
        bot.edit_message_text(
            chat_id=chat_id, 
            message_id=message_id, 
            text="أختر اللعبة التي تريد شحنها 👇🏻", 
            reply_markup=create_games_keyboard()
        )
    
    # قسم الحساب والمعلومات
    elif call.data == "account":
        user = get_user(user_id)
        if user:
            balance = user[2]
            account_text = f"""
            
👤 حسابي
            
اليوزر : @{user[1]} 
            
الاي دي : {user[0]}
            
رصيدك : {balance} ل.س
            
اضغط الزر أدناه لشحن رصيدك 👇🏻
            """
            keyboard = types.InlineKeyboardMarkup()
            deposit_btn = types.InlineKeyboardButton("شحن رصيدي 💳", callback_data="deposit")
            back_btn = types.InlineKeyboardButton("رجوع", callback_data="main_menu")
            keyboard.add(deposit_btn, back_btn)
            
            bot.edit_message_text(
                chat_id=chat_id, 
                message_id=message_id, 
                text=account_text, 
                reply_markup=keyboard
            )
    
    # قسم المساعدة والدعم
    elif call.data == "help":
        help_text = "اهـلا وسـهـلا تـفـضـل اطـرح الـمـشـكـلـه الـتـي تـواجـهـك 🌔 : @DEV_NOUR1"
        bot.edit_message_text(
            chat_id=chat_id, 
            message_id=message_id, 
            text=help_text, 
            reply_markup=create_back_keyboard("main_menu")
        )
    
    # شحن الرصيد
    elif call.data == "deposit":
        seriatel_number = get_setting('seriatel_number')
        deposit_text =f"""
        
● هنا قسم الشحن عن طريق Syriatel Cash
        
● يرجى ارسال المبلغ المراد تحويله الى المحفظة :  {seriatel_number}
        
        """
        
        bot.edit_message_text(
            chat_id=chat_id, 
            message_id=message_id, 
            text=deposit_text
        )
        
        # طلب المبلغ
        msg = bot.send_message(chat_id, "● يرجى ارسال المبلغ الذي قمت بتحويله :")
        bot.register_next_step_handler(msg, process_deposit_amount)
    
    # اختيار لعبة
    elif call.data.startswith("game_"):
        game = call.data.split("_")[1]
        bot.edit_message_text(
            chat_id=chat_id, 
            message_id=message_id, 
            text=f"اللعبة : {game}\n🛒 اختر فئة الشحن المناسبة :", 
            reply_markup=create_categories_keyboard(game)
        )
    
    # اختيار فئة (للمستخدمين العاديين)
    elif call.data.startswith("category_") and not call.data.startswith("admin_category_"):
        parts = call.data.split("_")
        game = parts[1]
        category = "_".join(parts[2:])
        
        price = get_product_price(game, category)
        if not price:
            bot.answer_callback_query(call.id, "هذه الفئة غير متوفرة حاليا ❌")
            return
        
        category_text = f"""
🧩 اللعبة  {game} :

📊 الفئة : {category}
        

💳 السعر : {price} ل.س
        

🌌 طريقة الشحن : Id
        
        """
        
        bot.edit_message_text(
            chat_id=chat_id, 
            message_id=message_id, 
            text=category_text
        )
        
        # تخزين البيانات مؤقتًا لاستخدامها لاحقًا
        user_data = {"game": game, "category": category, "price": price}
        msg = bot.send_message(chat_id, "🎮 أرسل معرف اللاعب : ")
        bot.register_next_step_handler(msg, process_player_id, user_data)
    
    # تأكيد أو إلغاء الطلب
    elif call.data.startswith("confirm_") or call.data.startswith("cancel_"):
        order_id = call.data.split("_")[1]
        
        # الحصول على معلومات الطلب
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM orders WHERE order_id = ?', (order_id,))
        order = cursor.fetchone()
        conn.close()
        
        if order:
            user_id = order[1]
            price = order[4]
            balance = get_user_balance(user_id)
            
            if call.data.startswith("confirm_"):
                if balance >= price:
                    # خصم المبلغ من رصيد المستخدم
                    update_user_balance(user_id, -price)
                    
                    # تحديث حالة الطلب
                    update_order_status(order_id, "confirmed")
                    
                    # إرسال رسالة التأكيد للمستخدم
                    confirmation_text = f"""
✅ تم تأكيد طلبك بنجاح!
                    
🧩 اللعبة {order[2]}  : 
                    
📊 الفئة : {order[3]} 
                    
💳 السعر : {price} ل.س 
                    
🌌 طريقة الشحن : Id 
                    
🆔معرف اللاعب : {order[5]}
                    
⏳ تم إرسال طلبك إلى الأدمن وسيتم معالجته قريباً.
                    """
                    
                    bot.edit_message_text(
                        chat_id=chat_id, 
                        message_id=message_id, 
                        text=confirmation_text
                    )
                    
                    # إرسال رسالة إلى الأدمن أو القناة المحددة
                    admin_text = f"""
                  
📩 طلب شحن جديد من المستخدم : {user_id}
                    
👤 اليوزر : @{call.from_user.username} 
                    
🎮 اللعبة  {order[2]}  :
                    
📦 الفئة : {order[3]} 
                    
🆔 معرف اللاعب ID: {order[5]} 
                    
💰السعر : {price} ل.س
                    """
                    
                    orders_channel_id = get_channel_setting('orders_channel_id')
                    send_to_channels = get_channel_setting('send_to_channels')
                    target_id = orders_channel_id if send_to_channels == '1' and orders_channel_id else ADMIN_ID
                    
                    bot.send_message(target_id, admin_text, reply_markup=create_admin_order_keyboard(order_id))
                else:
                    bot.answer_callback_query(call.id, "ليس لديك رصيد كافي ❌")
            else:
                # إلغاء الطلب
                update_order_status(order_id, "cancelled")
                bot.edit_message_text(
                    chat_id=chat_id, 
                    message_id=message_id, 
                    text="❌ تم إلغاء العملية",
                    reply_markup=create_back_keyboard("main_menu")
                )
    
    # إجراءات الأدمن على الطلبات
    elif call.data.startswith("admin_accept_") or call.data.startswith("admin_reject_"):
        order_id = call.data.split("_")[2]
        
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM orders WHERE order_id = ?', (order_id,))
        order = cursor.fetchone()
        conn.close()
        
        if order:
            user_id = order[1]
            game = order[2]
            category = order[3]
            price = order[4]
            player_id = order[5]
            
            if call.data.startswith("admin_accept_"):
                # قبول الطلب
                update_order_status(order_id, "completed", "accepted")
                
                # إرسال رسالة للمستخدم
                user_text = f"✅ تم شحن {category} إلى حسابك بنجاح! ال ID: {player_id}"
                bot.send_message(user_id, user_text)
                
                # تحديث رسالة الأدمن
                bot.edit_message_text(
                    chat_id=chat_id, 
                    message_id=message_id, 
                    text=f"✅ تم قبول الطلب #{order_id}",
                    reply_markup=None
                )
            else:
                # رفض الطلب
                update_order_status(order_id, "cancelled", "rejected")
                
                # إعادة الرصيد للمستخدم
                update_user_balance(user_id, price)
                
                # إرسال رسالة للمستخدم
                user_text = f"❌ تم رفض طلب الشحن الخاص بك 💰تم إعادة {price} ل.س إلى رصيدك"
                bot.send_message(user_id, user_text)
                
                # تحديث رسالة الأدمن
                bot.edit_message_text(
                    chat_id=chat_id, 
                    message_id=message_id, 
                    text=f"❌ تم رفض الطلب #{order_id}",
                    reply_markup=None
                )
    
    # إجراءات الأدمن على طلبات الإيداع
    elif call.data.startswith("admin_deposit_accept_") or call.data.startswith("admin_deposit_reject_"):
        request_id = call.data.split("_")[3]
        
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM deposit_requests WHERE request_id = ?', (request_id,))
        request = cursor.fetchone()
        conn.close()
        
        if request:
            user_id = request[1]
            amount = request[2]
            transaction_id = request[3]
            
            if call.data.startswith("admin_deposit_accept_"):
                # قبول طلب الإيداع
                update_deposit_request_status(request_id, "completed", "accepted")
                
                # إضافة الرصيد للمستخدم
                update_user_balance(user_id, amount)
                
                # إرسال رسالة للمستخدم
                new_balance = get_user_balance(user_id)
                user_text = f"✅ تم إضافة {amount} ل.س إلى رصيدك. 💰رصيدك الآن: {new_balance} ل.س"
                bot.send_message(user_id, user_text)
                
                # تحديث رسالة الأدمن
                bot.edit_message_text(
                    chat_id=chat_id, 
                    message_id=message_id, 
                    text=f"✅ تم قبول طلب الإيداع #{request_id}",
                    reply_markup=None
                )
            else:
                # رفض طلب الإيداع
                update_deposit_request_status(request_id, "rejected", "rejected")
                
                # إرسال رسالة للمستخدم
                user_text = "❌ تم رفض طلب شحن الرصيد الخاص بك ، الرجاء التواصل مع قسم المساعدة"
                bot.send_message(user_id, user_text)
                
                # تحديث رسالة الأدمن
                admin_text = f"""
                
❌ تم رفض طلب شحن الرصيد
                
👤 المستخدم: {user_id}
                
💵 المبلغ : {amount} 
                
🔢رقم العملية: {transaction_id}
                """
                
                bot.edit_message_text(
                    chat_id=chat_id, 
                    message_id=message_id, 
                    text=admin_text,
                    reply_markup=None
                )
    
    # لوحة تحكم الأدمن
    elif call.data == "admin_main":
        admin_text = "👋 أهلاً يا أدمن ، اختر أحد الخيارات :"
        bot.edit_message_text(
            chat_id=chat_id, 
            message_id=message_id, 
            text=admin_text, 
            reply_markup=create_admin_main_keyboard(user_id)
        )
    
    # إحصائيات الأدمن
    elif call.data == "admin_stats":
        stats = get_user_stats()
        stats_text = f"""
        📊 إحصائيات البوت:
        👥 إجمالي المستخدمين: {stats['total_users']}
        ✅ المستخدمين النشطين: {stats['active_users']}
        🚫 المستخدمين المحظورين: {stats['banned_users']}
        📋 طلبات ايداع تحتاج مراجعة: {stats['pending_deposits']}
        📦 طلبات الشحن المكتملة: {stats['completed_orders']}
        📮 طلبات ايداع مكتملة: {stats['completed_deposits']}
        """
        
        bot.edit_message_text(
            chat_id=chat_id, 
            message_id=message_id, 
            text=stats_text, 
            reply_markup=create_back_keyboard("admin_main")
        )
    
    # إضافة رصيد
    elif call.data == "admin_add_balance":
        msg = bot.send_message(chat_id, "👤 أرسل ايدي المستخدم الذي تريد إضافة رصيد له:")
        bot.register_next_step_handler(msg, process_admin_add_balance_user)
    
    # خصم رصيد
    elif call.data == "admin_deduct_balance":
        msg = bot.send_message(chat_id, "👤 أرسل ايدي المستخدم الذي تريد خصم رصيد منه:")
        bot.register_next_step_handler(msg, process_admin_deduct_balance_user)
    
    # حظر عضو
    elif call.data == "admin_ban_user":
        msg = bot.send_message(chat_id, "👤 أرسل ايدي المستخدم الذي تريد حظره:")
        bot.register_next_step_handler(msg, process_admin_ban_user)
    
    # رفع حظر
    elif call.data == "admin_unban_user":
        msg = bot.send_message(chat_id, "👤 أرسل ايدي المستخدم الذي تريد رفع حظره:")
        bot.register_next_step_handler(msg, process_admin_unban_user)
    
    # لوحة التحكم
    elif call.data == "admin_control_panel":
        bot.edit_message_text(
            chat_id=chat_id, 
            message_id=message_id, 
            text="⚙️ لوحة التحكم\nأختر اللعبة التي تريد التحكم بفئاتها :)", 
            reply_markup=create_admin_control_panel_keyboard()
        )
    
    # التحكم باللعبة (للأدمن)
    elif call.data.startswith("admin_control_"):
        game = call.data.split("_")[2]
        bot.edit_message_text(
            chat_id=chat_id, 
            message_id=message_id, 
            text=f"🎮 اختر فئة {game} للتحكم :", 
            reply_markup=create_categories_keyboard(game, is_admin=True)
        )
    
    # اختيار فئة للتحكم (للأدمن)
    elif call.data.startswith("admin_category_"):
        parts = call.data.split("_")
        game = parts[2]
        category = "_".join(parts[3:])
        
        # الحصول على سعر الفئة
        price = get_product_price(game, category)
        if not price:
            # إذا كانت غير مفعلة، الحصول على السعر من قاعدة البيانات مباشرة
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute('SELECT price FROM products WHERE game = ? AND category = ?', (game, category))
            result = cursor.fetchone()
            conn.close()
            price = result[0] if result else "غير معروف"
        
        category_text =  f"""
        
🎮 اللعبة {game} :
        
📦 الفئة : {category}
        
💰 السعر : {price} ل.س
        
        
اختر الإجراء الذي تريد تنفيذه :
        """
        
        bot.edit_message_text(
            chat_id=chat_id, 
            message_id=message_id, 
            text=category_text, 
            reply_markup=create_admin_category_control_keyboard(game, category)
        )
    
    # تغيير سعر الفئة
    elif call.data.startswith("admin_change_price_"):
        parts = call.data.split("_")
        game = parts[3]
        category = "_".join(parts[4:])
        
        msg = bot.send_message(chat_id, f"💵 أرسل السعر الجديد لفئة {category}:")
        bot.register_next_step_handler(msg, process_admin_change_price, game, category)
    
    # تفعيل الفئة
    elif call.data.startswith("admin_activate_"):
        parts = call.data.split("_")
        game = parts[2]
        category = "_".join(parts[3:])
        
        toggle_product_status(game, category, 1)
        bot.answer_callback_query(call.id, f"✅ تم تفعيل فئة {category}")
        
        # العودة إلى قائمة الفئات
        bot.edit_message_text(
            chat_id=chat_id, 
            message_id=message_id, 
            text=f"✅ تم تفعيل فئة {category} بنجاح", 
            reply_markup=create_back_keyboard(f"admin_control_{game}")
        )
    
    # تعطيل الفئة
    elif call.data.startswith("admin_deactivate_"):
        parts = call.data.split("_")
        game = parts[2]
        category = "_".join(parts[3:])
        
        toggle_product_status(game, category, 0)
        bot.answer_callback_query(call.id, f"✅ تم تعطيل فئة {category}")
        
        # العودة إلى قائمة الفئات
        bot.edit_message_text(
            chat_id=chat_id, 
            message_id=message_id, 
            text=f"✅ تم تعطيل فئة {category} بنجاح", 
            reply_markup=create_back_keyboard(f"admin_control_{game}")
        )
    
    # تغيير رقم سيرياتيل
    elif call.data == "admin_change_number":
        msg = bot.send_message(chat_id, "📱 أرسل الرقم الجديد لسيرياتيل كاش:")
        bot.register_next_step_handler(msg, process_admin_change_number)
    
    # معلومات عضو
    elif call.data == "admin_user_info":
        msg = bot.send_message(chat_id, "👤 أرسل ايدي المستخدم الذي تريد معلوماته:")
        bot.register_next_step_handler(msg, process_admin_user_info)
    
    # إيقاف/تشغيل البوت
    elif call.data == "admin_toggle_bot":
        current_status = get_setting('bot_active')
        new_status = '0' if current_status == '1' else '1'
        update_setting('bot_active', new_status)
        
        status_text = "متوقف" if new_status == '0' else "يعمل"
        bot.answer_callback_query(call.id, f"✅ تم تغيير حالة البوت إلى: {status_text}")
        bot.edit_message_text(
            chat_id=chat_id, 
            message_id=message_id, 
            text=f"✅ حالة البوت الآن: {status_text}", 
            reply_markup=create_back_keyboard("admin_main")
        )

    # قسم المشرفين
    elif call.data == "admin_admins_panel":
        if not is_main_admin(user_id):
            bot.answer_callback_query(call.id, "ليس لديك صلاحية للوصول إلى هذا القسم.")
            return

        admins = get_all_admins()
        admins_text = "👑 قائمة المشرفين:\n"
        for admin in admins:
            admins_text += f"- ID: {admin[0]} {' (أساسي)' if admin[1] else ''}\n"

        bot.edit_message_text(
            chat_id=chat_id,
            message_id=message_id,
            text=admins_text,
            reply_markup=create_admins_list_keyboard()
        )

    elif call.data == "admin_add_new_admin":
        if not is_main_admin(user_id):
            bot.answer_callback_query(call.id, "ليس لديك صلاحية لإضافة مشرفين.")
            return
        msg = bot.send_message(chat_id, "👤 أرسل ايدي المستخدم الذي تريد إضافته كمشرف:")
        bot.register_next_step_handler(msg, process_add_new_admin)
        
    elif call.data.startswith("admin_remove_"):
        if not is_main_admin(user_id):
            bot.answer_callback_query(call.id, "ليس لديك صلاحية لحذف مشرفين.")
            return
        
        admin_to_remove = int(call.data.split("_")[2])
        remove_admin(admin_to_remove)
        bot.answer_callback_query(call.id, f"✅ تم حذف المشرف {admin_to_remove}.")
        
        # تحديث قائمة المشرفين
        admins_text = "👑 قائمة المشرفين:\n"
        for admin in get_all_admins():
            admins_text += f"- ID: {admin[0]} {' (أساسي)' if admin[1] else ''}\n"
        bot.edit_message_text(
            chat_id=chat_id,
            message_id=message_id,
            text=admins_text,
            reply_markup=create_admins_list_keyboard()
        )

    # قناة الاشتراك الإجباري
    elif call.data == "admin_channel_settings":
        if not is_main_admin(user_id):
            bot.answer_callback_query(call.id, "ليس لديك صلاحية للوصول إلى هذا القسم.")
            return
            
        channel = get_mandatory_channel()
        channel_info = "🔗 لم يتم تحديد قناة اشتراك بعد."
        if channel:
            status = "مفعل" if channel[2] else "معطل"
            channel_info = f"🔗 القناة الحالية: {channel[1]}\nالحالة: {status}"

        bot.edit_message_text(
            chat_id=chat_id,
            message_id=message_id,
            text=channel_info,
            reply_markup=create_channel_settings_keyboard()
        )

    elif call.data == "admin_set_channel":
        if not is_main_admin(user_id):
            bot.answer_callback_query(call.id, "ليس لديك صلاحية لتحديد القناة.")
            return
        msg = bot.send_message(chat_id, "أرسل رابط القناة (مثل: `https://t.me/channel_username`) أو معرفها (@channel_username) مع التأكد أن البوت مشرف فيها:")
        bot.register_next_step_handler(msg, process_set_mandatory_channel)
    
    elif call.data.startswith("admin_toggle_channel_"):
        if not is_main_admin(user_id):
            bot.answer_callback_query(call.id, "ليس لديك صلاحية لتغيير حالة القناة.")
            return

        status = int(call.data.split("_")[3])
        toggle_mandatory_channel(status)
        status_text = "تم تفعيل" if status == 1 else "تم تعطيل"
        bot.answer_callback_query(call.id, f"✅ {status_text} الاشتراك الإجباري.")
        
        # تحديث الرسالة
        channel = get_mandatory_channel()
        channel_info = f"🔗 القناة الحالية: {channel[1]}\nالحالة: {'مفعل' if channel[2] else 'معطل'}"
        bot.edit_message_text(
            chat_id=chat_id,
            message_id=message_id,
            text=channel_info,
            reply_markup=create_channel_settings_keyboard()
        )

    # قنوات الطلبات
    elif call.data == "admin_orders_channels":
        orders_channel_id = get_channel_setting('orders_channel_id')
        deposits_channel_id = get_channel_setting('deposit_channel_id')
        send_to_channels = get_channel_setting('send_to_channels')
        
        status_text = "مفعل" if send_to_channels == '1' else "معطل"
        
        message_text = f"📤 إعدادات قنوات الطلبات:\n\n"
        message_text += f"حالة إرسال الطلبات للقنوات: **{status_text}**\n"
        message_text += f"معرف قناة الشحن: `{orders_channel_id if orders_channel_id else 'لم يتم التحديد'}`\n"
        message_text += f"معرف قناة الإيداع: `{deposits_channel_id if deposits_channel_id else 'لم يتم التحديد'}`\n\n"
        message_text += "استخدم الأزرار أدناه للتحكم."
        
        bot.edit_message_text(
            chat_id=chat_id,
            message_id=message_id,
            text=message_text,
            reply_markup=create_orders_channels_keyboard(),
            parse_mode="Markdown"
        )
    
    elif call.data.startswith("admin_toggle_orders_channels_"):
        status = call.data.split("_")[-1]
        update_channel_setting('send_to_channels', status)
        
        status_text = "تم تفعيل" if status == '1' else "تم تعطيل"
        bot.answer_callback_query(call.id, f"✅ {status_text} إرسال الطلبات للقنوات.")
        
        # تحديث الرسالة
        orders_channel_id = get_channel_setting('orders_channel_id')
        deposits_channel_id = get_channel_setting('deposit_channel_id')
        message_text = f"📤 إعدادات قنوات الطلبات:\n\n"
        message_text += f"حالة إرسال الطلبات للقنوات: **{'مفعل' if status == '1' else 'معطل'}**\n"
        message_text += f"معرف قناة الشحن: `{orders_channel_id if orders_channel_id else 'لم يتم التحديد'}`\n"
        message_text += f"معرف قناة الإيداع: `{deposits_channel_id if deposits_channel_id else 'لم يتم التحديد'}`\n\n"
        message_text += "استخدم الأزرار أدناه للتحكم."
        
        bot.edit_message_text(
            chat_id=chat_id,
            message_id=message_id,
            text=message_text,
            reply_markup=create_orders_channels_keyboard(),
            parse_mode="Markdown"
        )

    elif call.data == "admin_set_orders_channel":
        msg = bot.send_message(chat_id, "🔗 أرسل معرف قناة الشحن (مثال: `-1001234567890`)")
        bot.register_next_step_handler(msg, process_set_orders_channel)
        
    elif call.data == "admin_set_deposits_channel":
        msg = bot.send_message(chat_id, "🔗 أرسل معرف قناة الإيداع (مثال: `-1001234567890`)")
        bot.register_next_step_handler(msg, process_set_deposits_channel)

    # إعدادات SMS
    elif call.data == "admin_sms_settings":
        sms_channel_id = get_channel_setting('sms_channel_id')
        
        message_text = f"""
📨 إعدادات قناة SMS:

🔗 قناة SMS: `{sms_channel_id if sms_channel_id else 'لم يتم التحديد'}`

استخدم الزر أدناه لتحديد قناة SMS:
        """
        
        bot.edit_message_text(
            chat_id=chat_id,
            message_id=message_id,
            text=message_text,
            reply_markup=create_sms_settings_keyboard(),
            parse_mode="Markdown"
        )

    elif call.data == "admin_set_sms_channel":
        msg = bot.send_message(chat_id, "🔗 أرسل معرف قناة SMS (مثال: `-1001234567890`)")
        bot.register_next_step_handler(msg, process_set_sms_channel)
        
    # الرد على callback query لإزالة حالة التحميل
    bot.answer_callback_query(call.id)

# معالجة الخطوات التالية للأدمن
def process_admin_add_balance_user(message):
    if message.text.lower() in ['/start', 'رجوع']:
        send_welcome(message)
        return
        
    try:
        user_id = int(message.text)
        msg = bot.send_message(message.chat.id, "💵 أرسل المبلغ الذي تريد إضافته:")
        bot.register_next_step_handler(msg, process_admin_add_balance_amount, user_id)
    except ValueError:
        msg = bot.send_message(message.chat.id, "❌ يرجى إدخال ايدي صحيح. أرسل ايدي المستخدم مرة أخرى:")
        bot.register_next_step_handler(msg, process_admin_add_balance_user)

def process_admin_add_balance_amount(message, user_id):
    if message.text.lower() in ['/start', 'رجوع']:
        send_welcome(message)
        return
        
    try:
        amount = int(message.text)
        update_user_balance(user_id, amount)
        new_balance = get_user_balance(user_id)
        
        bot.send_message(message.chat.id, f"✅ تم إضافة {amount} ل.س إلى رصيد المستخدم {user_id}. 💰الرصيد الجديد: {new_balance} ل.س")
        bot.send_message(user_id, f"✅ تم إضافة {amount} ل.س إلى رصيدك. 💰رصيدك الآن: {new_balance} ل.س")
    except ValueError:
        msg = bot.send_message(message.chat.id, "❌ يرجى إدخال مبلغ صحيح. أرسل المبلغ مرة أخرى:")
        bot.register_next_step_handler(msg, process_admin_add_balance_amount, user_id)

def process_admin_deduct_balance_user(message):
    if message.text.lower() in ['/start', 'رجوع']:
        send_welcome(message)
        return
        
    try:
        user_id = int(message.text)
        msg = bot.send_message(message.chat.id, "💵 أرسل المبلغ الذي تريد خصمه:")
        bot.register_next_step_handler(msg, process_admin_deduct_balance_amount, user_id)
    except ValueError:
        msg = bot.send_message(message.chat.id, "❌ يرجى إدخال ايدي صحيح. أرسل ايدي المستخدم مرة أخرى:")
        bot.register_next_step_handler(msg, process_admin_deduct_balance_user)

def process_admin_deduct_balance_amount(message, user_id):
    if message.text.lower() in ['/start', 'رجوع']:
        send_welcome(message)
        return
        
    try:
        amount = int(message.text)
        update_user_balance(user_id, -amount)
        new_balance = get_user_balance(user_id)
        
        bot.send_message(message.chat.id, f"✅ تم خصم {amount} ل.س من رصيد المستخدم {user_id}. 💰الرصيد الجديد: {new_balance} ل.س")
        bot.send_message(user_id, f"⚠️ تم خصم {amount} ل.س من رصيدك. 💰رصيدك الآن: {new_balance} ل.س")
    except ValueError:
        msg = bot.send_message(message.chat.id, "❌ يرجى إدخال مبلغ صحيح. أرسل المبلغ مرة أخرى:")
        bot.register_next_step_handler(msg, process_admin_deduct_balance_amount, user_id)

def process_admin_ban_user(message):
    if message.text.lower() in ['/start', 'رجوع']:
        send_welcome(message)
        return
        
    try:
        user_id = int(message.text)
        ban_user(user_id)
        bot.send_message(message.chat.id, f"✅ تم حظر المستخدم {user_id}.")
        bot.send_message(user_id, "🚫 تم حظرك من استخدام البوت ، تواصل مع @DEV_NOUR1 لمعرفة سبب الحظر")
    except ValueError:
        msg = bot.send_message(message.chat.id, "❌ يرجى إدخال ايدي صحيح. أرسل ايدي المستخدم مرة أخرى:")
        bot.register_next_step_handler(msg, process_admin_ban_user)

def process_admin_unban_user(message):
    if message.text.lower() in ['/start', 'رجوع']:
        send_welcome(message)
        return
        
    try:
        user_id = int(message.text)
        unban_user(user_id)
        bot.send_message(message.chat.id, f"✅ تم رفع حظر المستخدم {user_id}.")
        bot.send_message(user_id, "✅ تم رفع حظرك ، اذا لم يتم رفع الحظر تواصل مع @DEV_NOUR1 .")
    except ValueError:
        msg = bot.send_message(message.chat.id, "❌ يرجى إدخال ايدي صحيح. أرسل ايدي المستخدم مرة أخرى:")
        bot.register_next_step_handler(msg, process_admin_unban_user)

def process_admin_change_price(message, game, category):
    if message.text.lower() in ['/start', 'رجوع']:
        send_welcome(message)
        return
        
    try:
        new_price = int(message.text)
        update_product_price(game, category, new_price)
        bot.send_message(message.chat.id, f"✅ تم تغيير سعر فئة {category} إلى {new_price} ل.س")
    except ValueError:
        msg = bot.send_message(message.chat.id, "❌ يرجى إدخال سعر صحيح. أرسل السعر مرة أخرى:")
        bot.register_next_step_handler(msg, process_admin_change_price, game, category)

def process_admin_change_number(message):
    if message.text.lower() in ['/start', 'رجوع']:
        send_welcome(message)
        return
        
    new_number = message.text
    update_setting('seriatel_number', new_number)
    bot.send_message(message.chat.id, f"✅ تم تغيير رقم سيرياتيل كاش إلى: {new_number}")

def process_admin_user_info(message):
    if message.text.lower() in ['/start', 'رجوع']:
        send_welcome(message)
        return
        
    try:
        user_id = int(message.text)
        user = get_user(user_id)
        if user:
            user_info = f"""
            
👤 الـحـسـاب و الـمـعـلـومـات 

🚀 الاسم : @{user[1]} 
            
🚀 ايدي الحساب : {user[0]} 
            
🚀 الرصيد الحالي : {user[2]} ل.س 
            
🚀إجـمـالـي الـمـصـروفـات : {user[3]} ل.س
            
🚀 عدد المشتريات : {user[4]} منتج .
            """
            bot.send_message(message.chat.id, user_info)
        else:
            bot.send_message(message.chat.id, "❌ المستخدم غير موجود")
    except ValueError:
        msg = bot.send_message(message.chat.id, "❌ يرجى إدخال ايدي صحيح. أرسل ايدي المستخدم مرة أخرى:")
        bot.register_next_step_handler(msg, process_admin_user_info)
        
def process_add_new_admin(message):
    if message.text.lower() in ['/start', 'رجوع']:
        send_welcome(message)
        return
    try:
        user_id = int(message.text)
        add_admin(user_id)
        bot.send_message(message.chat.id, f"✅ تم إضافة المستخدم {user_id} كمشرف.")
        bot.send_message(user_id, "👑 تهانينا! لقد تم تعيينك كمشرف في البوت. استخدم أمر /admin للوصول إلى لوحة التحكم.")
    except ValueError:
        msg = bot.send_message(message.chat.id, "❌ يرجى إدخال ايدي صحيح. أرسل ايدي المستخدم مرة أخرى:")
        bot.register_next_step_handler(msg, process_add_new_admin)

def process_set_mandatory_channel(message):
    if message.text.lower() in ['/start', 'رجوع']:
        send_welcome(message)
        return
        
    channel_link = message.text.strip()
    
    try:
        if "t.me/" in channel_link:
            username = channel_link.split("t.me/")[1]
            if not username.startswith("@"):
                username = "@" + username
        elif channel_link.startswith("@"):
            username = channel_link
        else:
            bot.send_message(message.chat.id, "❌ يرجى إدخال رابط أو معرف قناة صحيح.")
            return

        # التحقق من أن البوت مشرف في القناة
        try:
            chat_info = bot.get_chat(username)
            bot.get_chat_member(chat_id=chat_info.id, user_id=bot.get_me().id)
            set_mandatory_channel(chat_info.id, channel_link)
            bot.send_message(message.chat.id, f"✅ تم تعيين قناة الاشتراك الإجباري بنجاح: {channel_link}")
        except telebot.apihelper.ApiException as e:
            bot.send_message(message.chat.id, f"❌ حدث خطأ: يرجى التأكد من أن البوت مشرف في القناة وأن المعرف صحيح.")
            print(f"Error setting channel: {e}")
            
    except Exception as e:
        bot.send_message(message.chat.id, "❌ حدث خطأ غير متوقع. يرجى المحاولة مرة أخرى.")
        print(f"Error processing channel: {e}")

def process_set_orders_channel(message):
    if message.text.lower() in ['/start', 'رجوع']:
        send_welcome(message)
        return
        
    channel_id = message.text.strip()
    update_channel_setting('orders_channel_id', channel_id)
    bot.send_message(message.chat.id, f"✅ تم تعيين قناة الشحن بنجاح: `{channel_id}`", parse_mode="Markdown")

def process_set_deposits_channel(message):
    if message.text.lower() in ['/start', 'رجوع']:
        send_welcome(message)
        return
        
    channel_id = message.text.strip()
    update_channel_setting('deposit_channel_id', channel_id)
    bot.send_message(message.chat.id, f"✅ تم تعيين قناة الإيداع بنجاح: `{channel_id}`", parse_mode="Markdown")

def process_set_sms_channel(message):
    if message.text.lower() in ['/start', 'رجوع']:
        send_welcome(message)
        return
        
    channel_id = message.text.strip()
    update_channel_setting('sms_channel_id', channel_id)
    bot.send_message(message.chat.id, f"✅ تم تعيين قناة SMS بنجاح: `{channel_id}`", parse_mode="Markdown")

# معالجة الخطوات التالية
def process_player_id(message, user_data):
    if message.text.lower() in ['/start', 'رجوع']:
        send_welcome(message)
        return
        
    user_id = message.from_user.id
    player_id = message.text.strip()
    
    game = user_data["game"]
    category = user_data["category"]
    price = user_data["price"]
    
    # إنشاء طلب جديد
    order_id = create_order(user_id, game, category, price, player_id)
    
    # إرسال رسالة التأكيد
    confirmation_text = f"""
    
🧩 اللعبة {game} :
    
📊 الفئة : {category}
    
💳 السعر : {price} ل.س
    
🌌 طريقة الشحن : Id
    
معرف اللاعب : {player_id}
    
لطلب الفئة هذه اضغط تأكيد 👇🏻
    """
    
    bot.send_message(
        message.chat.id, 
        confirmation_text, 
        reply_markup=create_confirmation_keyboard(order_id)
    )

def process_deposit_amount(message):
    if message.text.lower() in ['/start', 'رجوع']:
        send_welcome(message)
        return
        
    user_id = message.from_user.id
    amount_text = message.text.strip()
    
    try:
        amount = int(amount_text)
        if amount <= 0:
            raise ValueError
    except ValueError:
        msg = bot.send_message(message.chat.id, "❌ يرجى إدخال مبلغ صحيح. اكتب المبلغ مرة أخرى:")
        bot.register_next_step_handler(msg, process_deposit_amount)
        return
    
    # طلب رقم العملية
    msg = bot.send_message(message.chat.id," ● ثـم أرسـل الآن رقم العملية : ")
    bot.register_next_step_handler(msg, process_transaction_id, amount, user_id)

def process_transaction_id(message, amount, user_id):
    if message.text.lower() in ['/start', 'رجوع']:
        send_welcome(message)
        return
        
    transaction_id = message.text.strip()
    
    # إرسال رسالة للمستخدم بأنه جاري التحقق
    bot.send_message(message.chat.id, "🔄 جاري التحقق من العملية...")
    
    # معالجة طلب الإيداع
    success, message_text = process_deposit_request(user_id, amount, transaction_id)
    
    # إرسال نتيجة المعالجة للمستخدم
    bot.send_message(message.chat.id, message_text)

def run_bot():
    """الدالة التي تقوم بتشغيل البوت مع معالجة الأخطاء وإعادة التشغيل"""
    print("Bot is running...")
    while True:
        try:
            bot.polling(none_stop=True, interval=0, timeout=20)
        except Exception as e:
            print(f"⚠️ حدث خطأ في حلقة البولينج: {e}")
            print("⏳ تتم محاولة إعادة تشغيل البوت تلقائياً بعد 5 ثوانٍ...")
            time.sleep(5)
        except KeyboardInterrupt:
            print("👋 تم إيقاف البوت يدوياً.")
            break

if __name__ == '__main__':
    run_bot()