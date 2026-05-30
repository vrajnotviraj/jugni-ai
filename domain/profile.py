from dataclasses import dataclass, field
from datetime import datetime
from zoneinfo import ZoneInfo


@dataclass(frozen=True, slots=True)
class UserProfile:
    """A person's private profile, keyed by their global Telegram user id.

    Every field except ``user_id`` is optional: a profile is built up one
    command at a time, and only the fields the user actually mentioned are set.
    """

    user_id: int
    display_name: str = ""
    height_cm: int | None = None
    weight_kg: float | None = None
    weight_updated_at: datetime | None = None
    age: int | None = None
    sex: str | None = None
    activity: str | None = None
    goal: str | None = None
    diet: str | None = None
    timezone: str | None = None
    updated_at: datetime | None = None

    def days_since_weight_update(self, now: datetime) -> int | None:
        """Whole days since the latest weight reading, or None if never set."""
        if self.weight_updated_at is None:
            return None
        return max(0, (now - self.weight_updated_at).days)

    def zone(self, default: ZoneInfo) -> ZoneInfo:
        """The user's IANA timezone, falling back to the app default.

        The stored string is already validated on write, but we guard the
        lookup here too so a bad value can never raise at read time.
        """
        if not self.timezone:
            return default
        try:
            return ZoneInfo(self.timezone)
        except Exception:
            return default


@dataclass(frozen=True, slots=True)
class ProfileExtraction:
    """Structured profile fields parsed from a natural-language message.

    Only fields the user actually stated (and that passed validation) are set.
    ``ignored`` names fields the user stated but that were rejected as out of
    range or unresolvable, so the reply can tell them what did not land.
    """

    height_cm: int | None = None
    weight_kg: float | None = None
    age: int | None = None
    sex: str | None = None
    activity: str | None = None
    goal: str | None = None
    diet: str | None = None
    timezone: str | None = None
    ignored: tuple[str, ...] = field(default_factory=tuple)

    @property
    def is_empty(self) -> bool:
        return not any(
            value is not None
            for value in (
                self.height_cm,
                self.weight_kg,
                self.age,
                self.sex,
                self.activity,
                self.goal,
                self.diet,
                self.timezone,
            )
        )

    def to_fields(self) -> dict[str, object]:
        """The non-null fields as a dict ready for ProfileRepository writes."""
        fields: dict[str, object] = {}
        if self.height_cm is not None:
            fields["height_cm"] = self.height_cm
        if self.weight_kg is not None:
            fields["weight_kg"] = self.weight_kg
        if self.age is not None:
            fields["age"] = self.age
        if self.sex is not None:
            fields["sex"] = self.sex
        if self.activity is not None:
            fields["activity"] = self.activity
        if self.goal is not None:
            fields["goal"] = self.goal
        if self.diet is not None:
            fields["diet"] = self.diet
        if self.timezone is not None:
            fields["timezone"] = self.timezone
        return fields
