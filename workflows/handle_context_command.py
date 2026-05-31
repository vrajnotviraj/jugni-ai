import logging

from analyzers.context.rewriter import ContextRewriter
from presenters.profile_reply import format_context_list, format_context_saved
from storage.profile_repository import ProfileRepository
from telegram.api import TelegramBotApi
from telegram.updates import EditContextCommand, ViewContextCommand
from workflows.dm_reply import send_dm
from workflows.onboarding import next_onboarding_nudge

logger = logging.getLogger(__name__)

# The free-text message is a short edit ("whole milk 6%", "forget the milk note"),
# not an essay. Capping the raw input keeps one message from blowing out the rewrite
# prompt; the rewriter trims each kept note further.
CONTEXT_NOTE_MAX_LEN = 200


async def handle_edit_context(
    command: EditContextCommand,
    *,
    repo: ProfileRepository,
    rewriter: ContextRewriter,
    telegram: TelegramBotApi,
) -> None:
    # The parser only builds this command when /context has text, so it is non-empty.
    message = command.text.strip()[:CONTEXT_NOTE_MAX_LEN].strip()

    # Hand the existing notes plus the person's message to the AI, which decides
    # whether to add a fact, change one, or remove notes, and returns the full
    # rewritten set. We then replace the stored list with the result.
    existing = await repo.list_context(command.user_id)
    notes = await rewriter(existing=existing, message=message)
    count = await repo.replace_context(command.user_id, notes)
    logger.info(
        "context edit user=%s existing=%s stored=%s",
        command.user_id,
        len(existing),
        count,
    )

    profile = await repo.get_profile(command.user_id)
    nudge = next_onboarding_nudge(profile, count) if profile else None
    await send_dm(telegram, command.chat_id, format_context_saved(notes, nudge))


async def handle_view_context(
    command: ViewContextCommand,
    *,
    repo: ProfileRepository,
    telegram: TelegramBotApi,
) -> None:
    notes = await repo.list_context(command.user_id)
    logger.info("context view user=%s count=%s", command.user_id, len(notes))
    await send_dm(telegram, command.chat_id, format_context_list(notes))
