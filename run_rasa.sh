#!/bin/bash

# Script to run Rasa server and action server

# Set environment variables
export PYTHONPATH=$PYTHONPATH:$(pwd)

# Load environment variables from .env file if it exists
if [ -f .env ]; then
    echo "Loading environment variables from .env file"
    export $(grep -v '^#' .env | xargs)
fi

# Function to check if a command exists
command_exists() {
    command -v "$1" >/dev/null 2>&1
}

# Check if Python is installed
if ! command_exists python; then
    echo "Python is not installed. Please install Python 3.9 or later."
    exit 1
fi

# Check if pip is installed
if ! command_exists pip; then
    echo "pip is not installed. Please install pip."
    exit 1
fi

# Check if Rasa is installed
if ! python -c "import rasa" &>/dev/null; then
    echo "Rasa is not installed. Installing Rasa..."
    pip install rasa==3.6.15 rasa-sdk==3.6.2
fi

# Check if required packages are installed
if ! python -c "import openai" &>/dev/null; then
    echo "OpenAI client is not installed. Installing..."
    pip install openai
fi

# Function to run Rasa server
run_rasa_server() {
    echo "Starting Rasa server..."
    
    python -m rasa run --enable-api --cors "*" --debug
}

# Function to run Rasa action server
run_action_server() {
    echo "Starting Rasa action server..."
    
    python -m rasa run actions
}

# Function to train Rasa model
train_rasa_model() {
    echo "Training Rasa model..."
    
    python -m rasa train
}

# Function to run Rasa shell
run_rasa_shell() {
    echo "Starting Rasa shell..."
    
    python -m rasa shell
}

# Display menu
echo "=== Rasa Dating Profile Assistant ==="
echo "1. Train Rasa model"
echo "2. Run Rasa server"
echo "3. Run Rasa action server"
echo "4. Run Rasa shell (for testing)"
echo "5. Exit"
echo "=================================="

# Get user choice
read -p "Enter your choice (1-5): " choice

case $choice in
    1)
        train_rasa_model
        ;;
    2)
        run_rasa_server
        ;;
    3)
        run_action_server
        ;;
    4)
        run_rasa_shell
        ;;
    5)
        echo "Exiting..."
        exit 0
        ;;
    *)
        echo "Invalid choice. Please enter a number between 1 and 5."
        exit 1
        ;;
esac 