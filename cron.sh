#!/bin/bash

# Get the directory where this script is located
PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"

# Set the path to your virtual environment
VENV_DIR="$PROJECT_DIR/venv"

# Activate the virtual environment
source "$VENV_DIR/bin/activate"

# Change to the project directory
cd "$PROJECT_DIR"

# Run the sync_data.py script
python sync_data.py
