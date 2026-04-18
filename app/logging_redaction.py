"""Redact secrets from third-party HTTP client log lines."""

import logging
import re

# Telegram REST URLs embed the bot token: .../bot<token>/method
_TELEGRAM_BOT_URL = re.compile(
    r"(https://api\.telegram\.org/bot)[^/\s]+(/)",
    re.IGNORECASE,
)


class RedactTelegramBotUrlFilter(logging.Filter):
    """Strip bot token from httpx/httpcore INFO lines."""

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            text = record.getMessage()
        except Exception:
            return True
        if "api.telegram.org/bot" not in text:
            return True
        redacted = _TELEGRAM_BOT_URL.sub(r"\1<redacted>\2", text)
        record.msg = redacted
        record.args = ()
        return True


def install_http_client_log_redaction() -> None:
    """Attach to httpx/httpcore (used by python-telegram-bot). Idempotent."""
    f = RedactTelegramBotUrlFilter()
    for name in ("httpx", "httpcore"):
        log = logging.getLogger(name)
        if not any(type(x) is RedactTelegramBotUrlFilter for x in log.filters):
            log.addFilter(f)
