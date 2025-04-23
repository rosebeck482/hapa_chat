# Rasa Dating Profile Assistant

## Prerequisites

- Python 3.9 (required)
- macOS, Linux, or Windows

## Quick Start Guide

1. **Clone this repository**:
   ```bash
   git clone https://github.com/rosebeck482/hapa_chat.git
   cd hapa_chat
   ```

2. **Set up a virtual environment**:
   ```bash
   # Create a new virtual environment
   python3.9 -m venv venv

   # Activate the virtual environment
   # On macOS/Linux:
   source venv/bin/activate
   # On Windows:
   venv\Scripts\activate
   ```

3. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

4. **Start the application using the provided script**:
   ```bash
   # Make the script executable (macOS/Linux only)
   chmod +x run_rasa.sh
   
   # Run the script
   ./run_rasa.sh
   ```
   
   This will present a menu to:
   - Train the Rasa model
   - Run the Rasa server
   - Run the Rasa action server
   - Run the Rasa shell for testing

## Manual Setup (Alternative to run_rasa.sh)

If you prefer to start services manually:

1. **Train the model** (if needed):
   ```bash
   python -m rasa train
   ```

2. **Start the Rasa server** (in one terminal window):
   ```bash
   python -m rasa run --enable-api --cors "*"
   ```

3. **Start the Rasa Action server** (in another terminal window):
   ```bash
   python -m rasa run actions
   ```

## Using the Web Interface

After starting both the Rasa server and Action server:

1. Open the web interface in your browser:
   ```bash
   # macOS
   open frontend/test_chat_simple.html
   
   # Windows
   start frontend/test_chat_simple.html
   
   # Linux
   xdg-open frontend/test_chat_simple.html
   ```

2. The chatbot will guide you through creating a dating profile by asking about:
   - Your basic information (name, age, gender)
   - Your interests and personality
   - Your preferences for potential partners

## Troubleshooting

- **Ports already in use**: If you see errors about ports being in use, you may have other Rasa instances running. Find and terminate them:
  ```bash
  # Find Rasa processes
  ps aux | grep -i rasa
  
  # Kill specific processes by their process ID (PID)
  kill <PID>
  ```

- **Models not found**: If Rasa complains about missing models, train a new model:
  ```bash
  python -m rasa train
  ```

## Conversation Logging and Export Feature

The chatbot includes a comprehensive conversation logging system that records all interactions between users and the bot. This feature enables users to review their conversation history and export it in various formats.

### Conversation Structure

Each message in the conversation log includes:
- **Timestamp**: When the message was sent
- **Section**: Which part of the conversation flow (e.g., "greeting", "personal_data_collection")
- **Sender**: Who sent the message (user, bot, or system)
- **Content**: The actual message text
- **Metadata**: Additional information like intents, actions, and confidence scores
