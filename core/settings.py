import os
from dataclasses import dataclass
from zoneinfo import ZoneInfo

from dotenv import load_dotenv


@dataclass(frozen=True, slots=True)
class Settings:
    telegram_bot_token: str
    telegram_webhook_secret: str | None
    telegram_group_chat_id: int | None
    telegram_polling_enabled: bool
    telegram_dry_run: bool
    redis_url: str
    openai_api_key: str
    openai_model: str
    timezone: ZoneInfo
    admin_api_secret: str | None
    cron_secret: str | None

    @classmethod
    def from_environment(cls) -> "Settings":
        load_dotenv()
        return cls(
            telegram_bot_token=_required_env("TELEGRAM_BOT_TOKEN"),
            telegram_webhook_secret=os.getenv("TELEGRAM_WEBHOOK_SECRET"),
            telegram_group_chat_id=_optional_int_env("TELEGRAM_GROUP_CHAT_ID"),
            telegram_polling_enabled=_bool_env("TELEGRAM_POLLING_ENABLED"),
            telegram_dry_run=_bool_env("TELEGRAM_DRY_RUN"),
            redis_url=os.getenv("REDIS_URL", "redis://localhost:6379/0"),
            openai_api_key=_required_env("OPENAI_API_KEY"),
            openai_model=os.getenv("OPENAI_MODEL", "gpt-4.1-mini"),
            timezone=ZoneInfo(os.getenv("APP_TIMEZONE", "Asia/Kolkata")),
            admin_api_secret=os.getenv("ADMIN_API_SECRET") or None,
            cron_secret=os.getenv("CRON_SECRET") or None,
        )


def _required_env(name: str) -> str:
    value = os.getenv(name)
    if value:
        return value
    raise RuntimeError(f"Missing required environment variable: {name}")


def _optional_int_env(name: str) -> int | None:
    value = os.getenv(name)
    if not value:
        return None
    return int(value) or None


def _bool_env(name: str) -> bool:
    return os.getenv(name, "").strip().lower() in {"1", "true", "yes", "on"}
