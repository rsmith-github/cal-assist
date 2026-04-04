# Cal-Assist

A Telegram-based calorie tracking chatbot that understands natural language input
and keeps a running daily total of calories in, calories out, and net calories.

## Setup

1. **Create and activate a virtual environment** (recommended for local dev)

   ```bash
   cd /path/to/Cal-Assist
   python3 -m venv .venv
   source .venv/bin/activate   # macOS / Linux
   # .venv\Scripts\activate    # Windows (cmd)
   ```

2. **Install dependencies** (with the venv activated)

   ```bash
   pip install -r requirements.txt
   ```

3. **Configure environment**

   ```bash
   cp .env.example .env
   # Fill in your TELEGRAM_BOT_TOKEN and (optionally) OPENAI_API_KEY
   ```

4. **Run the bot** (still inside the venv)

   ```bash
   python -m app.main
   ```

   Deactivate the venv when done: `deactivate`

## Usage

Send messages to your Telegram bot like:

- `2 beers` — logs 2 beers as calories in
- `300 kcal chicken wrap` — logs 300 kcal food entry
- `ran 5km` — logs exercise as calories out
- `Muay Thai 1.5 hr` — logs exercise
- `ND` — closes the current day and starts a new one
- `remove beers` — deletes the most recent beer entry
- `week` — shows a 7-day summary with average net calories

## How Parsing Works

If an `OPENAI_API_KEY` is set, the bot sends your message to an LLM for
accurate structured parsing. Otherwise it falls back to a regex + known-food
lookup table, which handles common patterns like `NUMBER kcal FOOD` and
well-known items (beer, rice, chicken, etc.).

## Stack

- **Bot**: python-telegram-bot
- **Backend**: FastAPI (ready for a future web dashboard)
- **Database**: SQLite via SQLAlchemy
- **Parsing**: OpenAI GPT (primary) / regex (fallback)
