from datetime import datetime
from typing import Protocol

from domain.profile import UserProfile


class ProfileRepository(Protocol):
    async def get_profile(self, user_id: int) -> UserProfile | None:
        """Return the stored profile for a user, or None if they have none."""

    async def update_profile_fields(
        self,
        user_id: int,
        fields: dict[str, object],
        *,
        mark_weight_updated: bool = False,
    ) -> UserProfile:
        """Write only the provided (non-None) profile fields and return the
        merged profile. When mark_weight_updated is set and a weight is present,
        also stamp weight_updated_at and append the reading to weight history."""

    async def weight_history(self, user_id: int) -> list[tuple[datetime, float]]:
        """Return every recorded weight as (recorded_at, weight_kg), oldest first."""

    async def replace_context(self, user_id: int, notes: list[str]) -> int:
        """Overwrite the user's context notes with the given set and return the
        new note count. Used after an AI rewrite consolidates the notes."""

    async def list_context(self, user_id: int) -> list[str]:
        """Return the user's saved context notes, oldest first."""

    async def delete_profile(self, user_id: int) -> None:
        """Remove the profile hash, context list, weight history, and membership."""

    async def bump_daily_llm_count(self, user_id: int, day_key: str) -> int:
        """Increment and return today's LLM-command count for a user (24h TTL)."""

    async def close(self) -> None:
        """Close any network connections owned by the repository."""
