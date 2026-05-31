"""The bot's DM command menu, defined once and registered via setMyCommands.

Telegram requires single lowercase tokens (no slash, no hyphens) and a non-empty
description per command. Setting them globally makes them appear in the client's
command menu and autocomplete in DMs; groups keep using /summary and /delete.
"""

# (token, short description) — order is the order shown in the client menu.
BOT_COMMANDS: tuple[tuple[str, str], ...] = (
    ("profile", "View your profile, or set it in plain words"),
    ("context", "See your notes, or 'add'/'update' to change them"),
    ("deleteprofile", "Delete everything I store about you"),
    ("start", "How this private chat works"),
    ("help", "Show the list of commands"),
)


def bot_commands() -> list[dict[str, str]]:
    return [
        {"command": token, "description": description}
        for token, description in BOT_COMMANDS
    ]
