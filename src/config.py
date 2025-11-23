import os

# Configuration settings

# Telegram Bot Token (to be set in environment)
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "mock_token")

# Google Analytics Measurement Protocol
GA_MEASUREMENT_ID = os.environ.get("GA_MEASUREMENT_ID", "G-XXXXXXXXXX")
GA_API_SECRET = os.environ.get("GA_API_SECRET", "secret_value")

# Database Connection String
DATABASE_URL = "sqlite:///jules_outreach.db"

# Throttling Configuration
# Default safety margin for FloodWait
FLOOD_WAIT_SAFETY_MARGIN = 5 # seconds

# Tracking Server Configuration
TRACKING_BASE_URL = os.environ.get("TRACKING_BASE_URL", "http://localhost:8080")
TRACKING_SERVER_PORT = int(os.environ.get("TRACKING_SERVER_PORT", 8080))
