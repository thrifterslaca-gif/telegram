import logging
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
from src.config import TELEGRAM_BOT_TOKEN
from src.drip_logic import initiate_drip_campaign, job_runner_tick
from src.db import init_db

# Enable logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Sends a welcome message."""
    user = update.effective_user
    await update.message.reply_html(
        rf"Hi {user.mention_html()}! Welcome to the Jules Command Center.",
    )

async def jules_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Triggers the 100-step drip sequence for the user.
    Usage: /jules_initiate
    """
    user_id = update.effective_chat.id
    await update.message.reply_text("Initiating Protocol: 100-Step Drip Sequence Injection...")

    # Trigger the injection
    # In a real scenario, this might take arguments for template ID
    await initiate_drip_campaign(user_id, "SEQ_100_STEP_ALPHA", context)

    await update.message.reply_text("Injection Complete. Monitoring initiated.")

def create_app():
    """Configures and returns the Application."""
    # Initialize DB
    init_db()

    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    # Handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("jules_initiate", jules_command))

    # Scheduler: Add the Job Runner Tick
    # Runs every 60 seconds to check for due messages
    if application.job_queue:
        application.job_queue.run_repeating(job_runner_tick, interval=60, first=10)

    return application
