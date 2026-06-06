"""The bot's command menus, defined once and registered via setMyCommands.

Telegram requires single lowercase tokens (no slash, no hyphens) and a non-empty
description per command. Each menu is registered against a BotCommandScope so the
client shows the right commands in the right place: the profile/help commands in
private chats, and only /summary and /delete in groups.
"""

# (token, short description) — order is the order shown in the client menu.
# Private (DM) menu: the profile and help commands the bot handles in 1:1 chats.
BOT_COMMANDS: tuple[tuple[str, str], ...] = (
    ("profile", "View your profile, or set it in plain words"),
    ("context", "See your notes, or 'add'/'update' to change them"),
    ("recommend", "Suggest your next meal from your day and goal"),
    ("deleteprofile", "Delete everything I store about you"),
    ("start", "How this private chat works"),
    ("help", "Show the list of commands"),
)

# Group menu: the commands the bot handles in group/supergroup chats.
GROUP_COMMANDS: tuple[tuple[str, str], ...] = (
    ("summary", "Post today's calorie summary for this group"),
    ("recommend", "Suggest your next meal from your day and goal"),
    ("delete", "Reply to a food photo to remove it from today's tally"),
)


def _as_commands(commands: tuple[tuple[str, str], ...]) -> list[dict[str, str]]:
    return [
        {"command": token, "description": description}
        for token, description in commands
    ]


def bot_commands() -> list[dict[str, str]]:
    return _as_commands(BOT_COMMANDS)


def group_commands() -> list[dict[str, str]]:
    return _as_commands(GROUP_COMMANDS)
