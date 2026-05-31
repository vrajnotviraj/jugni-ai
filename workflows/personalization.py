import re

from domain.profile import UserProfile
from storage.profile_repository import ProfileRepository

# The diet field packs several comma-separated facts ("vegetarian, no eggs") and
# the rewriter keeps each note atomic, so splitting on these joiners gives us the
# individual facts to dedup across both sources.
_FACT_SPLIT = re.compile(r"[;,]")


async def dietary_facts(
    profile: UserProfile | None,
    profile_repo: ProfileRepository | None,
    sender_id: int | None,
) -> str | None:
    """Combine the profile's diet field with the user's standing context notes
    into one deduped "dietary facts" string for the analyzers, or None.

    Both sources are durable facts about what the person eats and will not eat
    (e.g. "vegetarian", "no eggs"): the structured `diet` field set during
    profile setup, and the free-text notes managed via /context. The analyzers
    treat the combined string as hard constraints on any food they SUGGEST,
    never as instructions that change the calorie estimate or output format.

    Each source is exploded into atomic facts and deduped case-insensitively
    (first spelling wins), so a fact stated in both channels collapses cleanly:
    diet "vegetarian, no eggs" plus a note "no eggs" yields "vegetarian; no eggs"
    rather than repeating "no eggs".
    """
    sources: list[str] = []
    if profile is not None and profile.diet and profile.diet.strip():
        sources.append(profile.diet)
    if profile_repo is not None and sender_id is not None:
        sources.extend(await profile_repo.list_context(sender_id))

    seen: set[str] = set()
    facts: list[str] = []
    for source in sources:
        for fact in _FACT_SPLIT.split(source):
            fact = fact.strip()
            key = fact.casefold()
            if not fact or key in seen:
                continue
            seen.add(key)
            facts.append(fact)
    return "; ".join(facts) if facts else None
