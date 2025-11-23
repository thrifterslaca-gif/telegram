# -*- coding: utf-8 -*-
import logging
import sqlite3
import os
import random
import asyncio
from datetime import datetime, timedelta, time
import pytz

from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup,
    BotCommand, ChatPermissions
)
from telegram.constants import ParseMode
from telegram.ext import (
    Application, CommandHandler, MessageHandler, filters,
    CallbackQueryHandler, ContextTypes, ChatMemberHandler
)

# --- CONFIGURATION ---
# In a real environment, these should be environment variables.
# Using hardcoded values as requested in the sample, but prioritizing Env Vars.
BOT_TOKEN = os.getenv("BOT_TOKEN", "7265883472:AAEEYmG4iuC45LJcJR6obLe1rbpa6KPhxKY")
ADMIN_USER_ID = int(os.getenv("ADMIN_USER_ID", "1325661780"))
TARGET_GROUP_ID = int(os.getenv("TARGET_GROUP_ID", "-1002497338395"))
PAYMENT_FEE = "100"
CURRENCY = "Php"
QR_CODE_FILE = "payment_qr.png"
DB_FILE = "members.db"
TIMEZONE = pytz.timezone("Asia/Manila")

# Attendance Configuration
ATTENDANCE_STRIKE_LIMIT = 2
ATTENDANCE_CHECK_DAYS = [0, 3]  # Monday (0) and Thursday (3)
ATTENDANCE_CHECK_TIME = time(hour=10, minute=0, tzinfo=TIMEZONE)

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# --- DATABASE SETUP & MIGRATION ---
def setup_database():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()

    # Check if table exists
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='members'")
    table_exists = cursor.fetchone()

    if not table_exists:
        cursor.execute('''
            CREATE TABLE members (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                full_name TEXT,
                join_timestamp REAL,
                status TEXT NOT NULL,
                last_attendance_check REAL,
                attendance_strikes INTEGER DEFAULT 0
            )
        ''')
        logger.info("Database initialized.")
    else:
        # Simple migration: Add columns if they don't exist
        cursor.execute("PRAGMA table_info(members)")
        columns = [info[1] for info in cursor.fetchall()]

        if "full_name" not in columns:
            logger.info("Migrating database: Adding full_name column.")
            cursor.execute("ALTER TABLE members ADD COLUMN full_name TEXT")

        if "last_attendance_check" not in columns:
            logger.info("Migrating database: Adding last_attendance_check column.")
            cursor.execute("ALTER TABLE members ADD COLUMN last_attendance_check REAL")

        if "attendance_strikes" not in columns:
            logger.info("Migrating database: Adding attendance_strikes column.")
            cursor.execute("ALTER TABLE members ADD COLUMN attendance_strikes INTEGER DEFAULT 0")

    conn.commit()
    conn.close()

# --- WELCOME MESSAGE GENERATOR (500+ Variations) ---
def get_random_welcome_message(name):
    greetings = ["Hi", "Hello", "Welcome", "Greetings", "Hey there", "Good day", "Salutations", "Hola", "Bonjour", "Yo"]
    adjectives = ["amazing", "fantastic", "exclusive", "wonderful", "great", "awesome", "premium", "top-tier", "vibrant", "dynamic"]
    nouns = ["community", "group", "squad", "team", "family", "hub", "network", "circle", "gathering", "club"]
    closings = [
        "Glad to have you here!", "Make yourself at home.", "Ready to get started?",
        "Let's grow together.", "Enjoy your stay!", "We've been waiting for you.",
        "Excited to see you.", "Thanks for joining us.", "You made a great choice.", "Let's do this!"
    ]

    # 10 * 10 * 10 * 10 = 10,000 combinations
    part1 = random.choice(greetings)
    part2 = random.choice(adjectives)
    part3 = random.choice(nouns)
    part4 = random.choice(closings)

    return f"{part1} {name}! Welcome to our {part2} {part3}. {part4}"

# --- HANDLERS ---

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles the /start command. Registers user and prompts for payment if needed."""
    user = update.message.from_user
    user_id = user.id
    user_name = user.full_name

    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT status FROM members WHERE user_id = ?", (user_id,))
    result = cursor.fetchone()

    if result and result[0] == 'paid':
        await update.message.reply_text("✅ Your account is active. You are all set!", protect_content=True)
        conn.close()
        return

    # If user is not 'paid', add/update them
    if not result:
        logger.info(f"Existing member {user_name} ({user_id}) started bot. Adding to DB.")
        cursor.execute(
            "INSERT OR REPLACE INTO members (user_id, username, full_name, join_timestamp, status, attendance_strikes) VALUES (?, ?, ?, ?, ?, ?)",
            (user_id, user.username, user_name, datetime.now(TIMEZONE).timestamp(), "pending", 0)
        )
        conn.commit()
    conn.close()

    # Send the payment prompt
    keyboard = [
        [InlineKeyboardButton(f"PAY {CURRENCY}{PAYMENT_FEE}", callback_data=f"pay_{user_id}")],
        [InlineKeyboardButton("No, I will leave", callback_data=f"leave_{user_id}")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    welcome_text = get_random_welcome_message(user_name)

    try:
        await context.bot.send_message(
            chat_id=user_id,
            text=(f"{welcome_text}\n\n"
                  f"To gain/maintain access to the group, a one-time fee of *{CURRENCY}{PAYMENT_FEE}* is required within *7 days*.\n\n"
                  "Please choose an option below."),
            reply_markup=reply_markup,
            parse_mode=ParseMode.MARKDOWN,
            protect_content=True
        )
    except Exception as e:
        logger.error(f"Failed to send /start DM to {user_id}. Error: {e}")

async def handle_chat_member_update(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles both new members joining and existing members leaving."""
    if not update.chat_member or update.chat_member.chat.id != TARGET_GROUP_ID:
        return

    old_status = update.chat_member.old_chat_member.status if update.chat_member.old_chat_member else None
    new_status = update.chat_member.new_chat_member.status
    user = update.chat_member.new_chat_member.user

    if user.is_bot: return

    user_id = user.id
    user_name = user.full_name
    user_html_mention = user.mention_html()

    # --- NEW MEMBERS JOINING ---
    if new_status == 'member' and (old_status == 'left' or old_status == 'kicked' or old_status is None):
        logger.info(f"New member joined: {user_name} ({user_id})")

        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute(
            "INSERT OR REPLACE INTO members (user_id, username, full_name, join_timestamp, status, attendance_strikes) VALUES (?, ?, ?, ?, ?, ?)",
            (user_id, user.username, user_name, datetime.now(TIMEZONE).timestamp(), "pending", 0)
        )
        conn.commit()
        conn.close()

        keyboard = [[InlineKeyboardButton(f"PAY {CURRENCY}{PAYMENT_FEE}", callback_data=f"pay_{user_id}")], [InlineKeyboardButton("No, I will leave", callback_data=f"leave_{user_id}")]]
        reply_markup = InlineKeyboardMarkup(keyboard)

        welcome_msg = get_random_welcome_message(user_name)

        try:
            # DM the user
            await context.bot.send_message(
                chat_id=user_id,
                text=(f"{welcome_msg}\n\n"
                      f"To maintain your access, a one-time fee of *{CURRENCY}{PAYMENT_FEE}* is required within *7 days*.\n\n"
                      "Please choose an option below."),
                reply_markup=reply_markup,
                parse_mode=ParseMode.MARKDOWN,
                protect_content=True
            )
            # Notify the group
            await context.bot.send_message(
                chat_id=TARGET_GROUP_ID,
                text=(f"Welcome, {user_html_mention}! I've sent you a private message with instructions."),
                parse_mode=ParseMode.HTML,
                protect_content=True
            )
        except Exception as e:
            logger.error(f"Could not send DM to {user_id}. Error: {e}")
            await context.bot.send_message(
                chat_id=TARGET_GROUP_ID,
                text=(f"Welcome, {user_html_mention}! Please start a chat with me (@{context.bot.username}) to proceed."),
                parse_mode=ParseMode.HTML,
                protect_content=True
            )

    # --- MEMBERS LEAVING ---
    elif (new_status == 'left' or new_status == 'kicked') and (old_status == 'member' or old_status == 'administrator'):
        logger.info(f"Member left or was kicked: {user_name} ({user_id}).")

        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute("DELETE FROM members WHERE user_id = ?", (user_id,))
        conn.commit()
        conn.close()

async def handle_buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    data_parts = query.data.split('_')
    action = data_parts[0]

    # Handle attendance specially (format: attend_confirm_USERID)
    if action == "attend":
        # sub_action = data_parts[1] # confirm
        user_id = int(data_parts[2])
        if query.from_user.id != user_id:
            await query.answer("This is not for you.", show_alert=True)
            return

        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        # Reset last check timestamp to now (indicating they responded)
        cursor.execute("UPDATE members SET last_attendance_check = ?, attendance_strikes = 0 WHERE user_id = ?",
                       (datetime.now(TIMEZONE).timestamp(), user_id))
        conn.commit()
        conn.close()

        await query.edit_message_text("✅ Attendance confirmed! Thank you.", parse_mode=ParseMode.MARKDOWN)
        return

    # Handle payment buttons
    user_id_str = data_parts[1]
    user_id = int(user_id_str)

    if query.from_user.id != user_id:
        await query.answer("This button is not for you.", show_alert=True)
        return

    if action == "pay":
        await query.edit_message_text(text="Great! Please use the QR code below for payment.", parse_mode=ParseMode.MARKDOWN)
        try:
            if os.path.exists(QR_CODE_FILE):
                await context.bot.send_photo(
                    chat_id=user_id,
                    photo=open(QR_CODE_FILE, 'rb'),
                    caption=("Please scan this QR code to pay.\n\n"
                             "After sending, upload a screenshot of your successful transaction *in this chat* for validation."),
                    protect_content=True
                )
            else:
                await context.bot.send_message(
                    chat_id=user_id,
                    text="Payment QR code is currently unavailable. Please contact admin.",
                    protect_content=True
                )
                logger.error(f"QR code file not found: {QR_CODE_FILE}")

            conn = sqlite3.connect(DB_FILE)
            cursor = conn.cursor()
            cursor.execute("UPDATE members SET status = ? WHERE user_id = ?", ("awaiting_receipt", user_id))
            conn.commit()
            conn.close()
        except Exception as e:
            logger.error(f"Error sending QR: {e}")

    elif action == "leave":
        try:
            await context.bot.ban_chat_member(chat_id=TARGET_GROUP_ID, user_id=user_id)
            await query.edit_message_text(text="You have been removed from the group.")
            conn = sqlite3.connect(DB_FILE)
            cursor = conn.cursor()
            cursor.execute("DELETE FROM members WHERE user_id = ?", (user_id,))
            conn.commit()
            conn.close()
        except Exception as e:
            logger.error(f"Failed to ban user {user_id}. Reason: {e}")

# --- MESSAGE RELAY & RECEIPT HANDLING ---

async def handle_private_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles private messages: Receipts, User Feedback (Relay), etc."""
    user = update.message.from_user
    msg = update.message

    if user.id == ADMIN_USER_ID:
        # Admin replying to a forwarded message
        if msg.reply_to_message:
            original_text = msg.reply_to_message.text or msg.reply_to_message.caption
            if original_text and "User ID:" in original_text:
                try:
                    # Extract ID from "User ID: `12345`"
                    import re
                    match = re.search(r"User ID: `(\d+)`", original_text)
                    if match:
                        target_user_id = int(match.group(1))
                        await context.bot.copy_message(
                            chat_id=target_user_id,
                            from_chat_id=msg.chat_id,
                            message_id=msg.message_id,
                            protect_content=True
                        )
                        await msg.reply_text(f"✅ Reply sent to user {target_user_id}.")
                        return
                except Exception as e:
                    logger.error(f"Failed to relay reply: {e}")
                    await msg.reply_text("❌ Failed to send reply. Could not extract User ID.")
            else:
                await msg.reply_text("ℹ️ To reply to a user, please reply to the message forwarded by the bot containing 'User ID'.")
        return

    # Logic for Regular Users
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT status FROM members WHERE user_id = ?", (user.id,))
    result = cursor.fetchone()
    status = result[0] if result else "unknown"
    conn.close()

    # 1. Handle Payment Receipt
    if status == 'awaiting_receipt' and (msg.photo or msg.document):
        await context.bot.send_message(chat_id=user.id, text="Receipt received! Pending admin review.", protect_content=True)

        keyboard = [
            [InlineKeyboardButton("✅ Approve", callback_data=f"admin:approve:{user.id}"),
             InlineKeyboardButton("❌ Reject", callback_data=f"admin:reject:{user.id}")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await context.bot.send_message(
            chat_id=ADMIN_USER_ID,
            text=(f"🧾 **New Payment Receipt**\n"
                  f"User: {user.full_name} (@{user.username})\n"
                  f"User ID: `{user.id}`"),
            parse_mode=ParseMode.MARKDOWN
        )
        await context.bot.forward_message(chat_id=ADMIN_USER_ID, from_chat_id=user.id, message_id=msg.message_id)
        await context.bot.send_message(chat_id=ADMIN_USER_ID, text="Action:", reply_markup=reply_markup)
        return

    # 2. Relay Message to Admin (Support/Feedback)
    header = f"📩 **Message from User**\nName: {user.full_name}\nUser ID: `{user.id}`\n\n"
    try:
        if msg.text:
            await context.bot.send_message(chat_id=ADMIN_USER_ID, text=header + msg.text, parse_mode=ParseMode.MARKDOWN)
        elif msg.photo or msg.document or msg.video:
             await context.bot.send_message(chat_id=ADMIN_USER_ID, text=header + "[Media Attached Below]", parse_mode=ParseMode.MARKDOWN)
             await context.bot.forward_message(chat_id=ADMIN_USER_ID, from_chat_id=user.id, message_id=msg.message_id)
    except Exception as e:
        logger.error(f"Relay failed: {e}")

async def handle_admin_approval(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.from_user.id != ADMIN_USER_ID:
        return

    try:
        parts = query.data.split(':')
        decision = parts[1]
        user_id_str = parts[2]
        target_id = int(user_id_str)

        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()

        if decision == "approve":
            # Initialize last_attendance_check to NOW so they aren't immediately flagged as missing
            now_ts = datetime.now(TIMEZONE).timestamp()
            cursor.execute("UPDATE members SET status = ?, last_attendance_check = ? WHERE user_id = ?", ("paid", now_ts, target_id))
            conn.commit()
            await context.bot.send_message(
                chat_id=target_id,
                text="🎉 Payment Confirmed! You have full access.",
                protect_content=True
            )
            await query.edit_message_text(f"✅ Approved user {target_id}.")

        elif decision == "reject":
            cursor.execute("UPDATE members SET status = ? WHERE user_id = ?", ("pending", target_id))
            conn.commit()
            await context.bot.send_message(
                chat_id=target_id,
                text="⚠️ Your payment receipt was rejected. Please check and try again.",
                protect_content=True
            )
            await query.edit_message_text(f"❌ Rejected user {target_id}.")

        elif decision == "ban":
            await context.bot.ban_chat_member(chat_id=TARGET_GROUP_ID, user_id=target_id)
            cursor.execute("DELETE FROM members WHERE user_id = ?", (target_id,))
            conn.commit()
            await query.edit_message_text(f"⛔ Banned user {target_id}.")

        conn.close()
    except Exception as e:
        logger.error(f"Admin action error: {e}")

# --- JOBS ---

async def daily_ban_check(context: ContextTypes.DEFAULT_TYPE):
    """Bans users who haven't paid within 7 days."""
    logger.info("Running daily payment ban check...")
    seven_days_ago = datetime.now(TIMEZONE) - timedelta(days=7)
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT user_id, username FROM members WHERE join_timestamp < ? AND status = 'pending'", (seven_days_ago.timestamp(),))
    overdue_users = cursor.fetchall()

    for user_id, username in overdue_users:
        try:
            await context.bot.ban_chat_member(chat_id=TARGET_GROUP_ID, user_id=user_id)
            cursor.execute("DELETE FROM members WHERE user_id = ?", (user_id,))
            conn.commit()
            logger.info(f"Banned {user_id} for non-payment.")
        except Exception as e:
            logger.error(f"Failed to ban {user_id}: {e}")
    conn.close()
    return len(overdue_users)

async def force_ban_check(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Manually triggers the ban check."""
    if update.message.from_user.id != ADMIN_USER_ID: return
    await update.message.reply_text("⏳ Forcing ban check now, please wait...", protect_content=True)
    count = await daily_ban_check(context)
    await update.message.reply_text(f"✅ Force ban check complete. Processed {count} overdue users.", protect_content=True)

async def attendance_check_job(context: ContextTypes.DEFAULT_TYPE):
    """
    Runs periodically. If it's Mon or Thu, sends check-in messages.
    Also checks for people who missed previous checks.
    """
    now = datetime.now(TIMEZONE)
    is_check_day = now.weekday() in ATTENDANCE_CHECK_DAYS

    logger.info(f"Running Attendance Check Job. Is Check Day: {is_check_day}")

    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()

    # 1. If it's check day, send messages to all 'paid' users
    if is_check_day:
        cursor.execute("SELECT user_id, full_name, last_attendance_check FROM members WHERE status = 'paid'")
        users = cursor.fetchall()

        for user_id, name, last_check in users:
            keyboard = [[InlineKeyboardButton("✅ I'm Here", callback_data=f"attend_confirm_{user_id}")]]
            try:
                await context.bot.send_message(
                    chat_id=user_id,
                    text=f"👋 **Attendance Check!**\n\nHi {name}, please confirm your active status by clicking the button below.",
                    reply_markup=InlineKeyboardMarkup(keyboard),
                    parse_mode=ParseMode.MARKDOWN,
                    protect_content=True
                )
            except Exception as e:
                logger.error(f"Failed to send attendance check to {user_id}: {e}")

    # 2. Monitor strikes / missed checks
    # If a user hasn't clicked (updated `last_attendance_check`) in > 5 days, strike them.
    # Note: If `last_attendance_check` is NULL, they count as missing.
    threshold_time = now - timedelta(days=5)

    # Handle NULL by using COALESCE(last_attendance_check, 0)
    cursor.execute("""
        SELECT user_id, full_name, attendance_strikes
        FROM members
        WHERE status = 'paid'
        AND (last_attendance_check IS NULL OR last_attendance_check < ?)
    """, (threshold_time.timestamp(),))

    absent_users = cursor.fetchall()

    for user_id, name, strikes in absent_users:
        new_strikes = strikes + 1
        cursor.execute("UPDATE members SET attendance_strikes = ? WHERE user_id = ?", (new_strikes, user_id))
        conn.commit()

        if new_strikes >= ATTENDANCE_STRIKE_LIMIT:
            # Issue warning and prompt admin
            try:
                await context.bot.send_message(
                    chat_id=user_id,
                    text="⚠️ **Warning: Inactivity Detected**\n\nYou have missed multiple attendance checks. The admin has been notified and you may be removed.",
                    protect_content=True
                )
            except:
                pass

            admin_kb = [[InlineKeyboardButton("⛔ Ban User", callback_data=f"admin:ban:{user_id}")]]
            try:
                await context.bot.send_message(
                    chat_id=ADMIN_USER_ID,
                    text=(f"🚨 **Inactive Member Alert**\n\n"
                          f"User: {name}\nID: `{user_id}`\n"
                          f"Strikes: {new_strikes}\n\n"
                          "Action required:"),
                    reply_markup=InlineKeyboardMarkup(admin_kb),
                    parse_mode=ParseMode.MARKDOWN
                )
            except Exception as e:
                logger.error(f"Failed to notify admin about inactive user {user_id}: {e}")
        else:
            # Just a warning to user
            try:
                await context.bot.send_message(
                    chat_id=user_id,
                    text="⚠️ **Attendance Reminder**\n\nYou missed the last check-in. Please ensure you confirm attendance next time to avoid removal.",
                    protect_content=True
                )
            except:
                pass

    conn.close()

# --- MAIN ---

async def set_bot_commands(application: Application):
    commands = [BotCommand("start", "▶️ Start / Status")]
    await application.bot.set_my_commands(commands)

    admin_commands = [
        BotCommand("start", "▶️ Start"),
        BotCommand("force_ban_check", "Run ban check")
    ]
    await application.bot.set_my_commands(admin_commands, scope={"type": "chat", "chat_id": ADMIN_USER_ID})

def main():
    setup_database()
    application = Application.builder().token(BOT_TOKEN).build()
    application.post_init = set_bot_commands

    # Handlers
    application.add_handler(CommandHandler("start", start_command, filters=filters.ChatType.PRIVATE))
    application.add_handler(CommandHandler("force_ban_check", force_ban_check, filters=filters.ChatType.PRIVATE))
    application.add_handler(ChatMemberHandler(handle_chat_member_update, ChatMemberHandler.CHAT_MEMBER))
    application.add_handler(CallbackQueryHandler(handle_buttons, pattern="^(pay|leave|attend)_"))
    application.add_handler(CallbackQueryHandler(handle_admin_approval, pattern="^admin:"))

    # Private Messages (Receipts & Relay)
    # Using filters.Document.ALL to match any document
    application.add_handler(MessageHandler(
        filters.ChatType.PRIVATE & (filters.TEXT | filters.PHOTO | filters.Document.ALL),
        handle_private_message
    ))

    # Jobs
    job_queue = application.job_queue
    job_queue.run_daily(daily_ban_check, time(hour=2, minute=0, tzinfo=TIMEZONE), name="daily_payment_ban_check")
    job_queue.run_daily(attendance_check_job, ATTENDANCE_CHECK_TIME, name="attendance_check")

    print("Unified Security Bot is running...")
    application.run_polling()

if __name__ == '__main__':
    main()
