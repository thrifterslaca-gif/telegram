# -*- coding: utf-8 -*-
import logging
import sqlite3
import os
import json
from datetime import datetime

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, BotCommand
from telegram.ext import (
    Application, CommandHandler, MessageHandler, filters,
    CallbackQueryHandler, ContextTypes, ConversationHandler
)

# --- CONFIGURATION ---

BOT_TOKEN = os.getenv("BOT_TOKEN", "7624289688:AAFlgNQTH9zKw0w9PQTjQXVVFHTbI_ZF63A")
ADMIN_USER_ID = int(os.getenv("ADMIN_USER_ID", "1325661780"))
QR_CODE_FILE = os.getenv("QR_CODE_FILE", "payment_qr.png")
DB_FILE = "script_orders_chatter.db"
SCRIPT_PRICE = "150"
LIBRARY_PRICE = "1000"
CURRENCY = "Php"

# --- DATABASE SETUP ---
def setup_database():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute(''' CREATE TABLE IF NOT EXISTS orders ( order_id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL, username TEXT, order_details TEXT, status TEXT NOT NULL, timestamp REAL ) ''')
    conn.commit()
    conn.close()

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# --- CONVERSATION STATES ---
(SELECT_LOOKING_FOR, SELECT_GENDER, SELECT_SCRIPT_TYPE, SELECT_TONE,
 CONFIRM_ORDER, AWAIT_RECEIPT, CONFIRM_LIBRARY_ORDER, AWAITING_ADMIN_MESSAGE) = range(8)

# --- SCRIPT DATA STRUCTURE ---
LOOKING_FOR_OPTIONS = {
    "ppv_sexting": "📲 Sexting Scripts / PPV Captions",
    "library_inquiry": "📚 Inquire about the Entire Library",
    "something_else": "💡 Something Else (Custom Request)"
}
GENDERS = ["♀️ Female", "♂️ Male", "🏳️‍🌈 Gay"]
TONES = ["🥰 Sweet & Flirty", "🔥 Dominant & Bold", "🥺 Submissive & Eager", "😂 Playful & Witty"]
GENDER_SCRIPT_OPTIONS = {
    "♀️ Female": ["GFE / Romantic Scripts", "Sexting & Dirty Talk Flows", "PPV & Teaser Captions", "Domme / Findom Scenarios", "Custom Request Templates"],
    "♂️ Male": ["Boyfriend Experience Scripts", "Dominant / Alpha Talk", "JOI & Edging Sequences", "PPV & Flex Captions", "Custom Request Templates"],
    "🏳️‍🌈 Gay": ["Top / Dom Scenarios", "Bottom / Sub Scenarios", "Roleplay (Daddy/Boy, etc.)", "Twink / Jock Talk", "Custom Request Templates"]
}

# --- CONVERSATION HANDLERS ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Starts the main order conversation."""
    context.user_data.clear()
    keyboard = [[InlineKeyboardButton(desc, callback_data=f"looking_{key}")] for key, desc in LOOKING_FOR_OPTIONS.items()]
    reply_markup = InlineKeyboardMarkup(keyboard)

    message_text = (
        "🤖 **Welcome, Chatter!**\n\n"
        "This bot is your dedicated tool for ordering high-converting scripts.\n\n"
        "First, what are you looking for today?"
    )

    if update.callback_query:
        await update.callback_query.edit_message_text(message_text, reply_markup=reply_markup, parse_mode='Markdown')
    else:
        await update.message.reply_text(message_text, reply_markup=reply_markup, parse_mode='Markdown')

    return SELECT_LOOKING_FOR

async def handle_looking_for(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    choice = query.data.split('_', 1)[1]

    if choice == "library_inquiry":
        context.user_data['order'] = {'looking_for': LOOKING_FOR_OPTIONS[choice], 'price': LIBRARY_PRICE}
        keyboard = [[InlineKeyboardButton(f"✅ Yes, Pay {CURRENCY}{LIBRARY_PRICE}", callback_data="library_proceed")], [InlineKeyboardButton("❌ No, go back", callback_data="library_cancel")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(f"📚 **Entire Script Library Access**\n\nGet instant access to over 300 assorted but organized script files for only **{CURRENCY}{LIBRARY_PRICE}**.\n\nWould you like to purchase now?", reply_markup=reply_markup, parse_mode='Markdown')
        return CONFIRM_LIBRARY_ORDER

    elif choice == "something_else":
        # The /help command will now handle this flow
        await query.edit_message_text("💡 For custom requests, please use the /help command to contact the admin directly with your needs.")
        return ConversationHandler.END

    context.user_data['order'] = {'looking_for': LOOKING_FOR_OPTIONS[choice], 'price': SCRIPT_PRICE}
    keyboard = [[InlineKeyboardButton(g, callback_data=f"gender_{g}")] for g in GENDERS]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text("Whose content are you handling?", reply_markup=reply_markup)
    return SELECT_GENDER

async def handle_library_confirmation(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    if query.data == 'library_cancel':
        return await start(update, context)
    await query.edit_message_text("💰 Preparing your payment for the Full Library...")
    return await proceed_to_payment(query.from_user.id, context)

async def handle_gender_selection(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    gender = query.data.split('gender_', 1)[1]
    context.user_data['order']['gender'] = gender
    script_options = GENDER_SCRIPT_OPTIONS.get(gender, [])
    keyboard = [[InlineKeyboardButton(opt, callback_data=f"script_{opt}")] for opt in script_options]
    reply_markup = InlineKeyboardMarkup(keyboard)
    gender_name = gender.split(" ")[1] if " " in gender else gender
    await query.edit_message_text(f"Choose the script type for your {gender_name.lower()} model:", reply_markup=reply_markup)
    return SELECT_SCRIPT_TYPE

async def handle_script_type_selection(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    script_type = query.data.split('script_', 1)[1]
    context.user_data['order']['script_type'] = script_type
    keyboard = [[InlineKeyboardButton(t, callback_data=f"tone_{t}")] for t in TONES]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text("Pick the tone of the script you want:", reply_markup=reply_markup)
    return SELECT_TONE

async def handle_tone_selection(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    tone = query.data.split('tone_', 1)[1]
    context.user_data['order']['tone'] = tone
    order = context.user_data['order']
    summary_text = (
        "🧾 **Please confirm your final order:**\n\n"
        f"**Looking For:** {order['looking_for']}\n"
        f"**Model Gender:** {order['gender']}\n"
        f"**Script Type:** {order['script_type']}\n"
        f"**Script Tone:** {order['tone']}\n\n"
        f"--------------------\n"
        f"**Total Price: {CURRENCY} {order['price']}**\n\n"
        "🎁 **Bonus:** With this purchase, the admin will give you a free file of your choice upon delivery."
    )
    keyboard = [[InlineKeyboardButton("✅ Looks Good, Proceed to Payment", callback_data="payment_proceed")], [InlineKeyboardButton("✏️ Start Over", callback_data="payment_modify")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(summary_text, reply_markup=reply_markup, parse_mode='Markdown')
    return CONFIRM_ORDER

async def handle_confirmation(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    if query.data == 'payment_modify':
        return await start(update, context)
    await query.edit_message_text("💰 Preparing your payment details...")
    return await proceed_to_payment(query.from_user.id, context)

async def proceed_to_payment(user_id: int, context: ContextTypes.DEFAULT_TYPE) -> int:
    price = context.user_data['order']['price']
    try:
        caption_text = (f"Please send exactly **{CURRENCY}{price}**.\n\n"
                        "You can either scan the QR code above, or send to:\n\n"
                        "**Bank:** ShopeePay\n"
                        "**Account Name:** jaspi jaspi\n"
                        "**Account Number:** 621733412\n\n"
                        "After sending, upload a screenshot of your successful transaction *in this chat* for validation.")
        await context.bot.send_photo(chat_id=user_id, photo=open(QR_CODE_FILE, 'rb'), caption=caption_text, parse_mode='Markdown')
        return AWAIT_RECEIPT
    except FileNotFoundError:
        logger.error(f"CRITICAL: The script QR code file '{QR_CODE_FILE}' was not found.")
        await context.bot.send_message(chat_id=user_id, text="❌ Sorry, there's a technical issue with the payment system. Please use the /help command to contact an admin.")
        return ConversationHandler.END
    except Exception as e:
        logger.error(f"ERROR sending QR code: {e}")
        return ConversationHandler.END

async def handle_receipt(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user = update.message.from_user
    order_details = context.user_data.get('order', {})
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("INSERT INTO orders (user_id, username, order_details, status, timestamp) VALUES (?, ?, ?, ?, ?)", (user.id, user.username or user.full_name, json.dumps(order_details), 'awaiting_approval', datetime.now().timestamp()))
    order_id = cursor.lastrowid
    conn.commit()
    conn.close()
    await update.message.reply_text("👍 Thank you! Your receipt is now pending review.")
    keyboard = [[InlineKeyboardButton("✅ Approve", callback_data=f"admin:approve:{order_id}"), InlineKeyboardButton("❌ Reject", callback_data=f"admin:reject:{order_id}")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    summary_text = f"**New Script Order for Approval**\n**Order ID:** {order_id}\n\n"
    if order_details:
        summary_text += f"**Looking For:** {order_details.get('looking_for')}\n"
        if "gender" in order_details:
             summary_text += (f"**Gender:** {order_details.get('gender')}\n"
                             f"**Script Type:** {order_details.get('script_type')}\n"
                             f"**Tone:** {order_details.get('tone')}\n")
        summary_text += f"**Price:** {CURRENCY}{order_details.get('price')}"
    await context.bot.send_message(chat_id=ADMIN_USER_ID, text=f"New Script Order from {user.mention_html()}:", parse_mode='HTML')
    await context.bot.forward_message(chat_id=ADMIN_USER_ID, from_chat_id=user.id, message_id=update.message.message_id)
    await context.bot.send_message(chat_id=ADMIN_USER_ID, text=summary_text, reply_markup=reply_markup, parse_mode='Markdown')
    return ConversationHandler.END

async def delete_message_job(context: ContextTypes.DEFAULT_TYPE):
    job = context.job
    try:
        await context.bot.delete_message(chat_id=job.chat_id, message_id=job.data)
    except Exception as e:
        logger.error(f"Failed to delete message {job.data} in chat {job.chat_id}: {e}")

async def handle_admin_approval(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.from_user.id != ADMIN_USER_ID: return
    try:
        _, decision, order_id_str = query.data.split(':')
        order_id = int(order_id_str)
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute("SELECT user_id, username FROM orders WHERE order_id = ?", (order_id,))
        result = cursor.fetchone()
        if not result:
            await query.edit_message_text("Error: Order not found.")
            conn.close()
            return
        user_id_to_notify, username = result
        if decision == "approve":
            cursor.execute("UPDATE orders SET status = ? WHERE order_id = ?", ('completed', order_id))
            conn.commit()
            sent_message = await context.bot.send_message(chat_id=user_id_to_notify, text="🎉 Your order is confirmed! Your scripts will be delivered within 24 hours.\n\nIf you have any questions, please use the /help command.")
            three_days_in_seconds = 3 * 24 * 60 * 60
            context.job_queue.run_once(delete_message_job, three_days_in_seconds, data=sent_message.message_id, chat_id=user_id_to_notify, name=f"delete_{user_id_to_notify}_{sent_message.message_id}")
            await query.edit_message_text(text=f"✅ Order #{order_id} for {username} has been approved.")
        elif decision == "reject":
            cursor.execute("UPDATE orders SET status = ? WHERE order_id = ?", ('rejected', order_id))
            conn.commit()
            await context.bot.send_message(chat_id=user_id_to_notify, text="❌ Sorry, your payment could not be validated. Please use the /help command to contact an admin for assistance.")
            await query.edit_message_text(text=f"❌ Order #{order_id} for {username} has been rejected.")
        conn.close()
    except Exception as e:
        logger.error(f"Error in admin approval: {e}")

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.callback_query:
        await update.callback_query.edit_message_text("👍 Action cancelled. You can start over by sending /start anytime.")
    else:
        await update.message.reply_text("👍 Action cancelled. You can start over by sending /start anytime.")
    context.user_data.clear()
    return ConversationHandler.END

# --- NEW HELP SYSTEM ---
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    keyboard = [[InlineKeyboardButton("📨 Message Admin", callback_data="contact_admin")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        "💡 **Script Hub Bot Help**\n\n- Use `/start` to begin a new script order.\n- Use `/cancel` to stop an order in progress.\n- To speak to a person, use the button below.",
        parse_mode='Markdown',
        reply_markup=reply_markup
    )
    return AWAITING_ADMIN_MESSAGE

async def prompt_for_admin_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(text="Please type your message below. I will forward it directly to the admin.")
    return AWAITING_ADMIN_MESSAGE

async def forward_to_admin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user = update.message.from_user
    try:
        await context.bot.send_message(chat_id=ADMIN_USER_ID, text=f"New help message from {user.mention_html()} ({user.id}):", parse_mode='HTML')
        await context.bot.forward_message(chat_id=ADMIN_USER_ID, from_chat_id=user.id, message_id=update.message.message_id)
        await update.message.reply_text("Thank you. Your message has been sent to the admin.")
    except Exception as e:
        logger.error(f"Failed to forward message to admin: {e}")
        await update.message.reply_text("Sorry, there was an error sending your message. Please try again later.")
    return ConversationHandler.END

async def my_orders(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Displays the user's order history."""
    user = update.message.from_user
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT order_id, order_details, status, timestamp FROM orders WHERE user_id = ? ORDER BY timestamp DESC LIMIT 5", (user.id,))
    orders = cursor.fetchall()
    conn.close()

    if not orders:
        await update.message.reply_text("📭 You haven't placed any orders yet.")
        return

    message_text = "📜 **Your Recent Orders:**\n\n"
    for order_id, details_json, status, timestamp in orders:
        details = json.loads(details_json)
        date_str = datetime.fromtimestamp(timestamp).strftime('%Y-%m-%d %H:%M')

        status_icon = "⏳"
        if status == 'completed': status_icon = "✅"
        elif status == 'rejected': status_icon = "❌"

        message_text += f"**Order #{order_id}** ({date_str})\n"
        message_text += f"Status: {status_icon} `{status.upper()}`\n"
        message_text += f"Item: {details.get('looking_for', 'Unknown')}\n"
        message_text += f"Price: {CURRENCY}{details.get('price', '?')}\n\n"

    await update.message.reply_text(message_text, parse_mode='Markdown')

async def set_bot_commands(application: Application):
    commands = [
        BotCommand("start", "🛍️ Order a New Script"),
        BotCommand("myorders", "📜 View Order History"),
        BotCommand("cancel", "❌ Cancel Current Order"),
        BotCommand("help", "ℹ️ Get Help")
    ]
    await application.bot.set_my_commands(commands)
    logger.info("Bot command menu has been set.")

def main():
    setup_database()
    application = Application.builder().token(BOT_TOKEN).build()
    application.post_init = set_bot_commands

    order_conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            SELECT_LOOKING_FOR: [CallbackQueryHandler(handle_looking_for, pattern="^looking_")],
            CONFIRM_LIBRARY_ORDER: [CallbackQueryHandler(handle_library_confirmation, pattern="^library_")],
            SELECT_GENDER: [CallbackQueryHandler(handle_gender_selection, pattern="^gender_")],
            SELECT_SCRIPT_TYPE: [CallbackQueryHandler(handle_script_type_selection, pattern="^script_")],
            SELECT_TONE: [CallbackQueryHandler(handle_tone_selection, pattern="^tone_")],
            CONFIRM_ORDER: [CallbackQueryHandler(handle_confirmation, pattern="^payment_")],
            AWAIT_RECEIPT: [MessageHandler(filters.PHOTO, handle_receipt)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        allow_reentry=True
    )

    help_conv_handler = ConversationHandler(
        entry_points=[CommandHandler("help", help_command)],
        states={
            AWAITING_ADMIN_MESSAGE: [
                CallbackQueryHandler(prompt_for_admin_message, pattern="^contact_admin$"),
                MessageHandler(filters.TEXT & (~filters.COMMAND), forward_to_admin)
            ]
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        allow_reentry=True
    )

    application.add_handler(order_conv_handler)
    application.add_handler(help_conv_handler)
    application.add_handler(CommandHandler("myorders", my_orders))
    application.add_handler(CallbackQueryHandler(handle_admin_approval, pattern="^admin:"))

    print("Script Seller Bot is running...")
    application.run_polling()

if __name__ == '__main__':
    main()
