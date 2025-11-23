# Setup Guide: Auto-Start Seller Bot

This guide will help you set up the Seller Bot to run automatically on your Linux terminal/server, ensuring it restarts even after a reboot.

## Prerequisites

1.  **Python 3.8+** installed.
2.  **Git** (to clone the repo, if applicable).

## Step 1: Prepare the Project

Open your terminal and navigate to the project folder.

1.  Make the start script executable:
    ```bash
    chmod +x scripts/start_bot.sh
    ```

2.  (Optional) Create a virtual environment:
    ```bash
    python3 -m venv venv
    source venv/bin/activate
    pip install -r requirements.txt
    ```
    *Note: The `scripts/start_bot.sh` script attempts to activate `venv` if it exists.*

## Step 2: Configure Systemd (The Auto-Start Mechanism)

We will use `systemd`, the standard Linux init system, to manage the bot as a background service.

1.  **Edit the Service File:**
    Open `scripts/seller_bot.service` in a text editor.

    - Update `User=root` to your actual username (run `whoami` to find it).
    - Update `WorkingDirectory=/path/to/your/project` to the **absolute path** of where this folder is located on your machine (run `pwd` inside the project folder to copy it).
    - Update `ExecStart=/path/to/your/project/scripts/start_bot.sh` with the correct absolute path.

2.  **Copy to System Directory:**
    ```bash
    sudo cp scripts/seller_bot.service /etc/systemd/system/seller_bot.service
    ```

3.  **Reload Systemd:**
    ```bash
    sudo systemctl daemon-reload
    ```

## Step 3: Enable and Start

1.  **Enable on Boot:**
    This tells the system to start this service every time the computer turns on.
    ```bash
    sudo systemctl enable seller_bot.service
    ```

2.  **Start Now:**
    ```bash
    sudo systemctl start seller_bot.service
    ```

3.  **Check Status:**
    To verify it's running correctly:
    ```bash
    sudo systemctl status seller_bot.service
    ```
    You should see "Active: active (running)".

## Managing the Bot

- **Stop:** `sudo systemctl stop seller_bot`
- **Restart:** `sudo systemctl restart seller_bot`
- **View Logs:** To see what the bot is printing (output):
    ```bash
    journalctl -u seller_bot -f
    ```
