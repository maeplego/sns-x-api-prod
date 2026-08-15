"""Very small NSFW keyword screen for indie labeling."""

from __future__ import annotations

# Keep this conservative and keyword-only (no ML). Extend as needed.
_NSFW_KEYWORDS = (
    "porn",
    "nsfw",
    "xxx",
    "アダルト",
    "エロ",
    "裸",
    "セックス",
)


def detect_nsfw_text(body: str) -> str | None:
    normalized = body.casefold()
    for keyword in _NSFW_KEYWORDS:
        if keyword.casefold() in normalized:
            return f"keyword:{keyword}"
    return None
