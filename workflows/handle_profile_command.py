import logging
from datetime import UTC, datetime

from analyzers.profile.extractor import ProfileExtractor
from presenters.profile_reply import (
    format_help,
    format_profile,
    format_profile_deleted,
    format_profile_new_user,
    format_profile_not_understood,
    format_profile_saved,
)
from storage.profile_repository import ProfileRepository
from telegram.api import TelegramBotApi
from telegram.updates import DeleteProfileCommand, HelpCommand, ProfileCommand
from workflows.dm_reply import send_dm
from workflows.onboarding import next_onboarding_nudge

logger = logging.getLogger(__name__)


async def handle_profile_command(
    command: ProfileCommand,
    *,
    repo: ProfileRepository,
    extractor: ProfileExtractor,
    telegram: TelegramBotApi,
    now: datetime | None = None,
) -> None:
    now = now or datetime.now(UTC)

    if not command.text:
        await _reply_view(command, repo=repo, telegram=telegram, now=now)
        return

    extraction = await extractor(command.text)
    if extraction.is_empty:
        # Nothing parsed: do not touch storage, just guide the user.
        await send_dm(telegram, command.chat_id, format_profile_not_understood())
        return

    fields = extraction.to_fields()
    # Capture the display name on every write so replies can use it later.
    if command.display_name:
        fields["display_name"] = command.display_name

    profile = await repo.update_profile_fields(
        command.user_id,
        fields,
        mark_weight_updated=extraction.weight_kg is not None,
    )
    context_count = len(await repo.list_context(command.user_id))
    nudge = next_onboarding_nudge(profile, context_count)
    await send_dm(
        telegram, command.chat_id, format_profile_saved(extraction, nudge)
    )


async def handle_delete_profile(
    command: DeleteProfileCommand,
    *,
    repo: ProfileRepository,
    telegram: TelegramBotApi,
) -> None:
    await repo.delete_profile(command.user_id)
    await send_dm(telegram, command.chat_id, format_profile_deleted())


async def handle_help(
    command: HelpCommand,
    *,
    telegram: TelegramBotApi,
) -> None:
    await send_dm(telegram, command.chat_id, format_help(command.display_name))


async def _reply_view(
    command: ProfileCommand,
    *,
    repo: ProfileRepository,
    telegram: TelegramBotApi,
    now: datetime,
) -> None:
    profile = await repo.get_profile(command.user_id)
    logger.info(
        "profile view user=%s found=%s", command.user_id, profile is not None
    )
    if profile is None:
        await send_dm(
            telegram, command.chat_id, format_profile_new_user(command.display_name)
        )
        return
    await send_dm(telegram, command.chat_id, format_profile(profile, now=now))
