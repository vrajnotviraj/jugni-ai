from typing import Protocol

from domain.analysis import FoodAnalysis
from domain.photo import DeletedMeal, Photo, StoredPhoto, UpdatedMeal


class PhotoRepository(Protocol):
    async def reserve(self, photo: Photo, *, day_key: str | None = None) -> bool:
        """Reserve storage for an incoming photo. Return False if already stored.

        ``day_key`` lets the caller bucket the meal into a specific local day
        (e.g. computed in the sender's own timezone); when omitted the repository
        falls back to the app-timezone day.
        """

    async def complete(self, photo: Photo, analysis: FoodAnalysis) -> None:
        """Save a successful food analysis for a reserved photo."""

    async def mark_failed(self, photo: Photo, error: str) -> None:
        """Save a failure for a reserved photo."""

    async def estimated_photos_for_day(
        self,
        *,
        chat_id: int,
        day_key: str,
    ) -> list[StoredPhoto]:
        """Return all estimated, food-positive photos for one local day."""

    async def estimated_photos_for_range(
        self,
        *,
        chat_id: int,
        day_keys: list[str],
    ) -> dict[str, list[StoredPhoto]]:
        """Return estimated photos keyed by local day for the requested days."""

    async def estimated_photos_for_user_day(
        self,
        *,
        chat_id: int,
        day_key: str,
        sender_label: str,
    ) -> list[StoredPhoto]:
        """Return one user's estimated meals for a local day, oldest first."""

    async def user_active_days(
        self,
        *,
        chat_id: int,
        sender_label: str,
        day_keys: list[str],
    ) -> set[str]:
        """Return which of the given local days this user logged on.

        A cheap set-existence check (no photo hydration) — the basis for deriving
        streaks across many days for many users.
        """

    async def daily_user_calories(
        self,
        *,
        chat_id: int,
        day_key: str,
        sender_label: str,
    ) -> int:
        """Return the calorie total for one user on one local day."""

    async def delete_meal(
        self,
        *,
        chat_id: int,
        message_id: int,
    ) -> DeletedMeal | None:
        """Delete a stored meal and return its snapshot, or None if missing."""

    async def meal_owner_id(
        self,
        *,
        chat_id: int,
        message_id: int,
    ) -> int | None:
        """Return the stored sender_id for a meal, or None if absent."""

    async def update_meal_calories(
        self,
        *,
        chat_id: int,
        message_id: int,
        calories: int,
    ) -> UpdatedMeal | None:
        """Overwrite a meal's calorie count; return the updated snapshot."""

    async def close(self) -> None:
        """Close any network connections owned by the repository."""
