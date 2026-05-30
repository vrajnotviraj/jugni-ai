import logging

from analyzers.context.rewriter import ContextRewriter
from presenters.profile_reply import format_context_list, format_context_saved
from storage.profile_repository import ProfileRepository
from telegram.api import TelegramBotApi
from telegram.updates import AddContextCommand, ViewContextCommand
from workflows.dm_reply import send_dm
from workflows.onboarding import next_onboarding_nudge

logger = logging.getLogger(__name__)

# A single standing note is a short fact ("whole milk 6%"), not an essay. Capping
# the raw input keeps one message from blowing out the rewrite prompt; the
# rewriter trims each kept note further.
CONTEXT_NOTE_MAX_LEN = 200

_EMPTY_NOTE_REPLY = (
    "Add a short note after the command, for example: "
    "<code>/addcontext my chundo has no sugar</code>."
)


async def handle_add_context(
    command: AddContextCommand,
    *,
    repo: ProfileRepository,
    rewriter: ContextRewriter,
    telegram: TelegramBotApi,
) -> None:
    note = command.text.strip()[:CONTEXT_NOTE_MAX_LEN].strip()
    if not note:
        await send_dm(telegram, command.chat_id, _EMPTY_NOTE_REPLY)
        return

    # Feed the existing notes plus the new one through the AI rewriter so the
    # stored set stays concise, deduped, and free of contradictions, then replace
    # the whole list with the result.
    existing = await repo.list_context(command.user_id)
    notes = await rewriter(existing=existing, new_note=note)
    count = await repo.replace_context(command.user_id, notes)
    logger.info(
        "context add user=%s existing=%s stored=%s",
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
