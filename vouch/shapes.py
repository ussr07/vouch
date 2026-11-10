"""Read the model's JSON defensively.

The model is asked for a fixed shape, but replies vary: article numbers come back
as "3" instead of 3, a list is missing, a story is a plain string. None of that
may crash a brief or silently drop a real story, so every read goes through these.
"""


def as_int(value) -> int | None:
    """3, "3", " 3 ", 3.0 -> 3. Anything else (True, "three", 3.5, None) -> None."""
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    if isinstance(value, str) and value.strip().lstrip("-").isdigit():
        return int(value.strip())
    return None


def as_ints(value) -> list[int]:
    """A list of numbers, coerced; a single number becomes a one-item list."""
    items = value if isinstance(value, list) else [value]
    return [n for n in (as_int(v) for v in items) if n is not None]


def as_dicts(value) -> list[dict]:
    """Only the dict items of a list; anything else is skipped."""
    return [v for v in value if isinstance(v, dict)] if isinstance(value, list) else []


def as_dict(value) -> dict:
    return value if isinstance(value, dict) else {}


def as_text(value) -> str:
    return value.strip() if isinstance(value, str) else ""
