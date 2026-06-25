import os
from dataclasses import dataclass
from zoneinfo import ZoneInfo

from dotenv import load_dotenv


@dataclass(frozen=True, slots=True)
class Settings:
    telegram_bot_token: str
    telegram_webhook_secret: str | None
    telegram_group_chat_ids: tuple[int, ...]
    telegram_polling_enabled: bool
    telegram_dry_run: bool
    redis_url: str
    openai_api_key: str
    openai_model: str
    openai_flex_enabled: bool
    openai_flex_timeout: float
    youtube_api_key: str | None
    tavily_api_key: str | None
    timezone: ZoneInfo
    admin_api_secret: str | None
    cron_secret: str | None

    @classmethod
    def from_environment(cls) -> "Settings":
        load_dotenv()
        return cls(
            telegram_bot_token=_required_env("TELEGRAM_BOT_TOKEN"),
            telegram_webhook_secret=os.getenv("TELEGRAM_WEBHOOK_SECRET"),
            telegram_group_chat_ids=_int_tuple_env("TELEGRAM_GROUP_CHAT_ID"),
            telegram_polling_enabled=_bool_env("TELEGRAM_POLLING_ENABLED"),
            telegram_dry_run=_bool_env("TELEGRAM_DRY_RUN"),
            redis_url=os.getenv("REDIS_URL", "redis://localhost:6379/0"),
            openai_api_key=_required_env("OPENAI_API_KEY"),
            openai_model=os.getenv("OPENAI_MODEL", "gpt-4.1-mini"),
            openai_flex_enabled=_bool_env("OPENAI_FLEX_ENABLED", default=True),
            openai_flex_timeout=float(os.getenv("OPENAI_FLEX_TIMEOUT", "45")),
            youtube_api_key=(os.getenv("YOUTUBE_API_KEY") or "").strip() or None,
            tavily_api_key=(os.getenv("TAVILY_API_KEY") or "").strip() or None,
            timezone=ZoneInfo(os.getenv("APP_TIMEZONE", "Asia/Kolkata")),
            admin_api_secret=os.getenv("ADMIN_API_SECRET") or None,
            cron_secret=os.getenv("CRON_SECRET") or None,
        )


def _required_env(name: str) -> str:
    value = os.getenv(name)
    if value:
        return value
    raise RuntimeError(f"Missing required environment variable: {name}")


def _int_tuple_env(name: str) -> tuple[int, ...]:
    raw = os.getenv(name) or ""
    return tuple(int(t) for t in raw.split(",") if t.strip())


def _bool_env(name: str, *, default: bool = False) -> bool:
    raw = os.getenv(name, "").strip().lower()
    if not raw:
        return default
    return raw in {"1", "true", "yes", "on"}
