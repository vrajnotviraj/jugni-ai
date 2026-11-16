import logging
import re

# Telegram puts the bot token in every request URL (".../bot<id>:<secret>/...").
_BOT_TOKEN = re.compile(r"bot\d+:[A-Za-z0-9_-]+")


class _RedactBotToken(logging.Filter):
    """Masks bot tokens in log messages and tracebacks before any handler
    writes them (httpx errors and HTTPStatusError carry the full URL)."""

    def filter(self, record: logging.LogRecord) -> bool:
        message = record.getMessage()
        if _BOT_TOKEN.search(message):
            record.msg, record.args = _BOT_TOKEN.sub("bot<redacted>", message), None
        if record.exc_info and not record.exc_text:
            record.exc_text = logging.Formatter().formatException(record.exc_info)
        if record.exc_text:
            record.exc_text = _BOT_TOKEN.sub("bot<redacted>", record.exc_text)
        return True


def configure_logging() -> None:
    logging.basicConfig(
        format="%(asctime)s %(levelname)s %(name)s - %(message)s",
        level=logging.INFO,
    )
    # httpx logs every request URL at INFO, token included; keep only warnings.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    for handler in logging.getLogger().handlers:
        handler.addFilter(_RedactBotToken())
