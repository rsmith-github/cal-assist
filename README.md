# Cal Assist

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

3. **Create the Telegram bot (Cal Assist)**

   In Telegram, open **[@BotFather](https://t.me/BotFather)** and run:

   - `/newbot`
   - **Name** (what users see): `Cal Assist` (or `Cal Assist — your name`)
   - **Username** (must be unique, end in `bot`): e.g. `cal_assist_yourname_bot`

   BotFather replies with an **API token**. Put it in `.env` as `TELEGRAM_BOT_TOKEN`.

   Optional in BotFather: `/setdescription` and `/setabouttext` — the app also pushes
   name, description, and the `/` command menu when it starts.

4. **Configure environment**

   ```bash
   cp .env.example .env
   # Set TELEGRAM_BOT_TOKEN; optionally OPENAI_API_KEY and OFF_CONTACT_URL
   ```

5. **Run the bot** (still inside the venv)

   ```bash
   python -m app.main
   ```

   Deactivate the venv when done: `deactivate`

6. **Optional — FastAPI health check only**

   ```bash
   uvicorn app.main:app --reload
   ```

   Then open `http://127.0.0.1:8000/health`. The Telegram bot is started with `python -m app.main`, not via uvicorn.

## Usage

Send messages to your Telegram bot like:

- `2 beers` — logs 2 beers as calories in
- `300 kcal chicken wrap` — logs 300 kcal food entry
- `ran 5km` — logs exercise as calories out
- `Muay Thai 1.5 hr` — logs exercise
- `ND` — closes the current day and starts a new one
- `remove beers` — deletes the most recent beer entry
- `actually 2 beers not 3` — replaces the last matching entry with the corrected amount
- `summary` or `/summary` — today’s totals only
- `week` or `/week` — closed days whose calendar date falls in the last 7 days (including today), with a rough kg trend vs maintenance

## How Parsing Works

1. If `OPENAI_API_KEY` is set, the bot tries an LLM first for messy phrases.
2. Otherwise (or if the model returns nothing useful), it uses **regex +**
   [`data/known_foods.json`](data/known_foods.json) for common patterns and items.
3. If that still does not match, it can call the **Open Food Facts** search API
   (free, no key) for branded / packaged foods. Set `OPEN_FOOD_FACTS_ENABLED=false`
   in `.env` to stay fully offline. Use `OFF_CONTACT_URL` for a proper
   User-Agent contact (see Open Food Facts API etiquette).

Exercise lines are **not** sent to Open Food Facts (they stay on local estimates).

## Stack

- **Bot**: python-telegram-bot
- **Backend**: FastAPI (ready for a future web dashboard)
- **Database**: SQLite via SQLAlchemy
- **Parsing**: OpenAI GPT (primary) / regex (fallback)


## Deployment commands 

cd ~/path/to/cal-assist
source .venv/bin/activate
nohup python -m app.main >> calassist.log 2>&1 &
echo "PID=$!"
sleep 1
tail -n 50 calassist.log

### To kill:
kill PID that was echoed