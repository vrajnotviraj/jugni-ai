from domain.profile import UserProfile

# One nudge at a time, highest-leverage first: a context note improves every photo
# estimate, then goal and diet sharpen the estimates further. Timezone is
# intentionally NOT nudged: it is optional and defaults to the app timezone, so
# pushing it to everyone is noise. Once a context note, goal, and diet all exist
# the profile is "reasonably complete" and we stop nudging.
_NUDGES = (
    (
        lambda p, ctx: ctx < 1,
        "Add a standing note and I will respect it in every photo estimate. "
        "Try <code>/context my chundo has no sugar</code>.",
    ),
    (
        lambda p, ctx: not p.goal,
        "What are you working toward? Tell me and I will tailor everything. "
        "Try <code>/profile my goal is to lose fat</code>.",
    ),
    (
        lambda p, ctx: not p.diet,
        "How do you eat? Knowing this sharpens every estimate. "
        "Try <code>/profile vegetarian, no eggs</code>.",
    ),
)


def next_onboarding_nudge(profile: UserProfile, context_count: int) -> str | None:
    """Return the single most useful next step, or None once the profile is set.

    The priority order is fixed so the user is never asked two things at once and
    the nudges stop entirely when a context note, goal, and diet all exist. Timezone
    is optional and never nudged.
    """
    for applies, message in _NUDGES:
        if applies(profile, context_count):
            return message
    return None
