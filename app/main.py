"""Run `python -m app.main` to start the Telegram bot.

FastAPI app is exposed for optional `uvicorn app.main:app` (health check only for now).
"""

from fastapi import FastAPI

from app.bot.telegram import run_bot

app = FastAPI(title="Cal Assist", version="0.1.0")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


def main() -> None:
    run_bot()


if __name__ == "__main__":
    main()
