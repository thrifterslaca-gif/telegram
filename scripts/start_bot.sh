#!/bin/bash

# Navigate to the project root directory
# (Assumes this script is inside a 'scripts' folder one level deep)
cd "$(dirname "$0")/.."

# Activate virtual environment if it exists (common convention)
if [ -d "venv" ]; then
    source venv/bin/activate
fi

# Ensure requirements are installed (optional, can be commented out to speed up restart)
pip install -r requirements.txt

# Set default environment variables if not already set (fallback)
# You should set these in your .bashrc or systemd environment file for production
export BOT_TOKEN=${BOT_TOKEN:-"7624289688:AAFlgNQTH9zKw0w9PQTjQXVVFHTbI_ZF63A"}
export ADMIN_USER_ID=${ADMIN_USER_ID:-"1325661780"}

# Run the bot
echo "Starting Seller Bot..."
exec python3 src/seller_bot.py
