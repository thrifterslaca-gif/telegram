import asyncio
import logging
from aiohttp import web
from src.bot_core import create_app
from src.tracking_server import start_tracking_server
from src.config import TRACKING_SERVER_PORT

# Enable logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

async def main():
    """
    Main entry point. Runs both the Telegram Bot and the Tracking Web Server.
    """
    # 1. Setup Telegram Bot
    application = create_app()

    # 2. Setup Tracking Server
    runner = start_tracking_server()
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', TRACKING_SERVER_PORT)
    await site.start()
    logger.info(f"Tracking server started on port {TRACKING_SERVER_PORT}")

    # 3. Start Bot
    # We use initialize/start/updater flow to control the loop manually
    await application.initialize()
    await application.start()
    await application.updater.start_polling()
    logger.info("Bot started polling.")

    # 4. Keep alive
    stop_signal = asyncio.Event()
    try:
        await stop_signal.wait()
    except (KeyboardInterrupt, SystemExit):
        pass
    finally:
        # Graceful shutdown
        logger.info("Shutting down...")
        await application.updater.stop()
        await application.stop()
        await application.shutdown()
        await runner.cleanup()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
