"""Step 54: Social listener for Reddit/Facebook/X keywords."""
from __future__ import annotations

SIGNAL_KEYWORDS = [
    "looking for dispatcher", "need dispatch help", "owner operator dispatch",
    "new mc number", "just got my authority", "dispatch percentage",
    "factoring company recommendation", "load board suggestions",
]


def match_signals(post_text: str) -> list[str]:
    t = (post_text or "").lower()
    return [kw for kw in SIGNAL_KEYWORDS if kw in t]
