"""Register the bot's DM command menu with Telegram (setMyCommands).

The app also does this at startup; this script is for setting commands manually
without a full boot. Respects TELEGRAM_DRY_RUN.

Run: python3 scripts/set_bot_commands.py
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.settings import Settings  # noqa: E402
from telegram.api import TelegramBotApi  # noqa: E402
from telegram.commands import bot_commands  # noqa: E402


async def main() -> None:
    settings = Settings.from_environment()
    telegram = TelegramBotApi(
        settings.telegram_bot_token,
        dry_run=settings.telegram_dry_run,
    )
    commands = bot_commands()
    await telegram.set_my_commands(commands)
    print(f"Registered {len(commands)} bot commands.")


if __name__ == "__main__":
    asyncio.run(main())
