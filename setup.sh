#!/bin/bash

# FB Marketplace Bot - Full Installer
# Usage: bash setup.sh

set -e # Exit on error

echo -e "\033[0;32m[1/6] Updating System Repositories...\033[0m"
sudo apt-get update -qq

echo -e "\033[0;32m[2/6] Installing System Dependencies (Python, Venv, Libraries)...\033[0m"
sudo apt-get install -y \
    python3 \
    python3-pip \
    python3-venv \
    git \
    libjpeg-dev \
    zlib1g-dev \
    libnss3 \
    libnspr4 \
    libatk1.0-0 \
    libatk-bridge2.0-0 \
    libcups2 \
    libdrm2 \
    libxkbcommon0 \
    libxcomposite1 \
    libxdamage1 \
    libxfixes3 \
    librandr2 \
    libgbm1 \
    libasound2

echo -e "\033[0;32m[3/6] Setting up Python Virtual Environment...\033[0m"
# Remove old venv if exists to ensure fresh install
rm -rf venv
python3 -m venv venv
source venv/bin/activate

echo -e "\033[0;32m[4/6] Installing Python Packages...\033[0m"
# Upgrade pip first
pip install --upgrade pip
# Install dependencies directly to avoid missing requirements.txt issues if run standalone
pip install playwright pytest pydantic loguru openai Pillow pyotp requests

echo -e "\033[0;32m[5/6] Installing Playwright Browsers...\033[0m"
playwright install chromium

echo -e "\033[0;32m[6/6] Initializing Configuration...\033[0m"
mkdir -p config user_data logs processed_images

# Create accounts.json template if it doesn't exist
if [ ! -f config/accounts.json ]; then
cat <<EOF > config/accounts.json
[
  {
    "account_id": "default_account",
    "username": "EMAIL_HERE",
    "password": "PASSWORD_HERE",
    "totp_secret": "2FA_SECRET_HERE",
    "proxy_url": null,
    "city": "New York",
    "max_posts_per_day": 5
  }
]
EOF
echo "Created config/accounts.json template."
fi

echo -e "\033[0;32m\nSUCCESS! Installation Complete.\033[0m"
echo "----------------------------------------------------------------"
echo "1. Edit your config:  nano config/accounts.json"
echo "2. Add OpenAI Key:    export OPENAI_API_KEY='sk-...'"
echo "3. Start the bot:     source venv/bin/activate && python3 src/unified_main.py"
echo "----------------------------------------------------------------"
