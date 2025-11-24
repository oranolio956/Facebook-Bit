#!/bin/bash
set -e

# Define virtual environment directory
VENV_DIR=".venv"

echo "Creating virtual environment in $VENV_DIR..."
python3 -m venv $VENV_DIR

# Activate the virtual environment
source $VENV_DIR/bin/activate

echo "Upgrading pip..."
pip install --upgrade pip

echo "Installing dependencies from requirements.txt..."
pip install -r requirements.txt

echo "Installing Playwright browsers (chromium)..."
playwright install chromium

echo "Setup complete! Activate the environment with: source $VENV_DIR/bin/activate"
