from datetime import date


MIN_SIGNUP_AGE = 13
ADULT_AGE = 18
NSFW_LABELS = frozenset({"nsfw"})


def age_years(birthdate: date | None, *, today: date | None = None) -> int | None:
    if birthdate is None:
        return None
    ref = today or date.today()
    years = ref.year - birthdate.year
    if (ref.month, ref.day) < (birthdate.month, birthdate.day):
        years -= 1
    return years


def is_adult(birthdate: date | None, *, today: date | None = None) -> bool:
    """Legacy users without birthdate are treated as adults for feed continuity."""
    years = age_years(birthdate, today=today)
    if years is None:
        return True
    return years >= ADULT_AGE
