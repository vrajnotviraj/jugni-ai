from typing import Protocol

from domain.analysis import FoodAnalysis
from domain.photo import Photo, StoredPhoto


class PhotoRepository(Protocol):
    async def reserve(self, photo: Photo) -> bool:
        """Reserve storage for an incoming photo. Return False if already stored."""

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

    async def daily_user_total(self, photo: Photo) -> int:
        """Return the running calorie total for this photo's sender today."""

    async def close(self) -> None:
        """Close any network connections owned by the repository."""
