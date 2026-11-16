import logging

from core.logging import _RedactBotToken

TOKEN_URL = "https://api.telegram.org/bot123456:AAE_x-Yz9/sendMessage"


def _record(msg, *args, exc_info=None):
    return logging.LogRecord("t", logging.INFO, __file__, 1, msg, args, exc_info)


def test_redacts_token_in_message_and_args():
    record = _record("HTTP Request: POST %s", TOKEN_URL)
    _RedactBotToken().filter(record)
    assert "AAE_x" not in record.getMessage()
    assert "bot<redacted>/sendMessage" in record.getMessage()


def test_redacts_token_in_traceback():
    try:
        raise RuntimeError(f"failed {TOKEN_URL}")
    except RuntimeError:
        import sys

        record = _record("boom", exc_info=sys.exc_info())
    _RedactBotToken().filter(record)
    assert "AAE_x" not in record.exc_text
