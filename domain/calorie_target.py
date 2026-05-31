from domain.profile import UserProfile

# Maintenance = BMR x activity factor, then a BOUNDED goal adjustment. The bounds
# are what keep goals realistic: a gain goal earns a fixed moderate surplus, not
# whatever huge number a person might wish for, and a loss goal cannot drop below
# a floor. BMR uses Mifflin-St Jeor when height, age, and sex are known, and a
# weight-only approximation otherwise, so the target degrades gracefully.
_GAIN_SURPLUS_KCAL = 400  # ~0.25-0.5 kg/week, a realistic lean gain
_LOSS_DEFICIT_KCAL = 500  # ~0.5 kg/week, a realistic loss
_MIN_TARGET_KCAL = 1400  # never reward an unhealthily low target
_BMR_KCAL_PER_KG = 22.0  # rough BMR per kg when height/age/sex are missing

# Activity multipliers (standard Mifflin-St Jeor levels). "moderate" is the
# average-lifestyle default applied when the person has not stated an activity.
_ACTIVITY_FACTORS = {
    "sedentary": 1.2,
    "light": 1.375,
    "moderate": 1.55,
    "active": 1.725,
    "very_active": 1.9,
}
_DEFAULT_ACTIVITY = "moderate"
_SEX_CONSTANT = {"male": 5, "female": -161}

_GAIN_WORDS = (
    "gain", "bulk", "muscle", "mass", "increase", "put on", "build", "surplus",
)
_LOSS_WORDS = ("lose", "loss", "cut", "shed", "reduce", "slim", "deficit", "drop")


def calorie_target(profile: UserProfile | None) -> int | None:
    """A realistic daily calorie target from the profile, or None to fall back.

    Returns None when there is no profile or no weight (the one required anchor),
    so callers keep their default (goal-agnostic) behavior.
    """
    if profile is None or profile.weight_kg is None:
        return None

    activity = (profile.activity or _DEFAULT_ACTIVITY).lower()
    factor = _ACTIVITY_FACTORS.get(activity, _ACTIVITY_FACTORS[_DEFAULT_ACTIVITY])
    maintenance = _bmr(profile) * factor

    direction = _goal_direction(profile.goal)
    if direction == "gain":
        target = maintenance + _GAIN_SURPLUS_KCAL
    elif direction == "loss":
        target = maintenance - _LOSS_DEFICIT_KCAL
    else:
        target = maintenance
    return max(_MIN_TARGET_KCAL, round(target))


def _bmr(profile: UserProfile) -> float:
    # Mifflin-St Jeor needs weight, height, age, and sex. With all four we use it;
    # otherwise we approximate from weight alone so a partial profile still works.
    weight = profile.weight_kg or 0.0
    if profile.height_cm is not None and profile.age is not None and profile.sex:
        sex_constant = _SEX_CONSTANT.get(profile.sex.lower(), -78)  # midpoint if odd
        return 10 * weight + 6.25 * profile.height_cm - 5 * profile.age + sex_constant
    return weight * _BMR_KCAL_PER_KG


_UNSET = object()


def goal_summary(profile: UserProfile | None, target: object = _UNSET) -> str | None:
    """The goal text plus its realistic target, formatted for prompts.

    "gain weight (realistic daily calorie target about 2800 kcal)", or just the
    goal text when there is no weight to compute a target, or None when no goal.

    Pass ``target`` when the caller already computed ``calorie_target(profile)``
    (it ranks on it too) so the figure is not derived twice; omit it and the
    summary computes its own. ``None`` is a valid target (no weight on file).
    """
    goal = (profile.goal or "").strip() if profile else ""
    if not goal:
        return None
    if target is _UNSET:
        target = calorie_target(profile)
    if target is None:
        return goal
    return f"{goal} (realistic daily calorie target about {target} kcal)"


def highlight_macro(goal: str | None) -> str | None:
    """The macro worth emphasising for this goal, or None when none stands out.

    Protein anchors both directions: a gain/muscle goal needs enough of it to
    build, and a loss goal needs it to hold lean mass and stay full. Maintenance
    or no stated goal gets no single highlight, since balance is the point.
    The returned label matches the ``macro_shares`` labels so callers can mark
    the matching slice. See domain research: protein is the priority macro for
    both gain and fat-loss goals.
    """
    if _goal_direction(goal) in ("gain", "loss"):
        return "Protein"
    return None


def _goal_direction(goal: str | None) -> str:
    text = (goal or "").casefold()
    # Loss is checked first: "lose fat" wins over an incidental "gain" keyword.
    if any(word in text for word in _LOSS_WORDS):
        return "loss"
    if any(word in text for word in _GAIN_WORDS):
        return "gain"
    return "maintain"
