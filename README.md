# Rasa Dating Profile Assistant

Create rich, privacy-aware dating profiles through a conversational experience powered by Rasa 3.6, custom Python actions, and optional Supabase-backed frontends. The assistant walks users through collecting personal details, personality traits, and partner preferences while persisting structured conversation logs for later review.

---

## Highlights

- **Guided profile flow** – intents, stories, and custom actions collaborate to gather name, age, gender, interests, and deal breakers with graceful fallbacks.
- **Hybrid extraction** – blends entity recognition, regex parsing, and optional Ollama `phi4` calls (via HTTP) to cleanly normalize user inputs such as names or age ranges.
- **Persistent logging** – every exchange and slot update is written to disk with export utilities for JSON, text, or CSV review.
- **Multiple clients** – interact through the Rasa CLI shell, a lightweight HTML test page, or a React/Supabase chat widget that syncs messages in real time.
- **Extensible configuration** – modular pipeline, policies, and action servers make it easy to adapt to other domains or UI channels.

---

## Repository Structure

```
actions/                 Custom action implementations (entity collection, AI responses, logging)
conversation_exporter.py Utility for exporting logged conversations
conversation_logger.py   Shared logger used by actions for structured transcripts
data/                    Rasa training data (NLU, rules, stories)
domain.yml               Assistant intents, slots, responses, forms
frontend/                Browser clients (React/Supabase widget & simple HTML tester)
models/                  Trained Rasa model archives (can be regenerated)
tests/                   Rasa conversation and action tests
run_rasa.sh              Convenience script to train/run servers or open the shell
```

---

## Prerequisites

- Python **3.9** (required by Rasa 3.6)
- macOS, Linux, or Windows
- For optional features:
  - [Ollama](https://github.com/ollama/ollama) running locally for advanced language understanding (`OLLAMA_API_HOST`, `OLLAMA_MODEL`)
  - [Supabase](https://supabase.com/) project for the React client (`REACT_APP_SUPABASE_URL`, `REACT_APP_SUPABASE_ANON_KEY`)

Install Python dependencies inside a virtual environment:

```bash
python3.9 -m venv venv
source venv/bin/activate      # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

The assistant relies on `rasa`, `rasa-sdk`, `httpx`, `word2number`, `python-dotenv`, and `openai` (for Ollama fallbacks). Ensure these are present in your environment.

---

## Training & Running

### Using the helper script

```bash
chmod +x run_rasa.sh
./run_rasa.sh
```

Choose from the menu to:

- Train a new model (`rasa train`)
- Start the Rasa server (`rasa run --enable-api --cors "*"`)
- Start the custom action server (`rasa run actions`)
- Launch the interactive Rasa shell (`rasa shell`)

### Manual commands

```bash
# Train the assistant
python -m rasa train

# Terminal 1 – REST server + API
python -m rasa run --enable-api --cors "*"

# Terminal 2 – Action server for custom Python logic
python -m rasa run actions

# (Optional) quick CLI test shell
python -m rasa shell
```

> **Ports**: The default REST server listens on `:5005`; the action server listens on `:5055` (configured in `endpoints.yml`).

---

## Conversational Flow

1. **Personal data collection** – custom actions `ActionCollect*` prompt for name, age (with DOB inference), gender, gender preference, age preference, and height. Slots populate `personal_data_stage` to manage progress.
2. **User info deep dive** – the bot switches to open-ended questions about interests and personality, generating responses with optional Ollama assistance.
3. **Partner preferences** – collects desired qualities, deal breakers, and readiness before concluding the profile.

Training data in `data/stories.yml`, `data/rules.yml`, and `data/nlu.yml` defines this flow, while `domain.yml` centralizes intents, entities, slots, and responses.

---

## Conversation Logging & Exporting

- `ActionLogConversation` writes each exchange and slot change to `conversation_logs/conversation_<sender_id>.json`.
- `ConversationLogger` (used throughout `actions/actions.py`) exposes helpers to append messages, update metadata, and retrieve history during runtime.
- `conversation_exporter.py` can render logs in multiple formats:

```bash
# List available conversations
python conversation_exporter.py --list --log-dir conversation_logs

# Export to JSON
python conversation_exporter.py --id <sender_id> --format json --output export.json

# Export to text or CSV
python conversation_exporter.py --id <sender_id> --format text --output export.txt
python conversation_exporter.py --id <sender_id> --format csv  --output export.csv
```

Logs include timestamps, conversation sections, intents/actions, confidence scores, and slot snapshots for auditing or analytics.

---

## Frontend Options

### Simple HTML tester

`frontend/test_chat_simple.html` is a static page that talks directly to the REST webhook (`http://localhost:5005/webhooks/rest/webhook`). Open it once the Rasa server is running:

```bash
# macOS
open frontend/test_chat_simple.html
# Windows
start frontend/test_chat_simple.html
# Linux
xdg-open frontend/test_chat_simple.html
```

### React + Supabase widget

`frontend/RasaChatComponent.jsx` connects through a Supabase Edge Function called `messageHandler`. Set the following environment variables when bundling the component:

```bash
export REACT_APP_SUPABASE_URL=<your-project-url>
export REACT_APP_SUPABASE_ANON_KEY=<anon-key>
```

Each message is written to the `Messages` table and streamed back through real-time subscriptions, keeping the UI in sync with bot responses.

---

## Configuration & Environment

- `config.yml` – NLU pipeline (Whitespace tokenizer, Regex/Count vectorizers, DIET classifier, ResponseSelector) and policies (Memoization, RulePolicy, TEDPolicy).
- `credentials.yml` – REST and Socket.IO channel settings (by default only REST is enabled).
- `endpoints.yml` – location of the action server (`http://localhost:5055/webhook`). Adjust if you deploy to another host.
- `.env` (optional) – load secrets such as `OLLAMA_API_HOST`, `OLLAMA_MODEL`, and OpenAI credentials; parsed via `python-dotenv` in `actions/actions.py`.

---

## Testing & Quality

- `tests/` includes end-to-end stories (`test_stories.yml`, `e2e_personal_data.yml`) and NLU evaluation data (`nlu_test.yml`). Run with:

  ```bash
  python -m rasa test
  ```

- `test_action.py`, `test_logger.py`, and `test_rasa.py` provide lightweight Python harnesses for verifying custom actions, logging, and REST connectivity.

Add your own pytest or Rasa test suites as you extend the dialogue or action logic.

---

## Maintenance Tips

- Regenerate models whenever you modify `data/` or `domain.yml`.
- Prune `conversation_logs/`, `__pycache__/`, `.rasa/cache/`, and old `models/*.tar.gz` archives to keep the repo tidy.
- Review `requirements.txt` before deployment to ensure all runtime-only packages (e.g., `httpx`, `word2number`, `ollama`) are pinned.
- Monitor `action_server.log` (or console output) for errors, especially when Ollama is unavailable; actions fall back to safe prompts but will log warnings.
