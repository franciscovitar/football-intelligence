"""Deterministic position-family classification."""

from __future__ import annotations

from football_intelligence.player_analytics.config import ROLE_ALIASES
from football_intelligence.position_profiles.config import FINE_POSITION_ALIASES


def classify_position_family(listed_position: str | None) -> str | None:
    """Classify a provider `listed_position` token into a position family.

    Tries the fine-grained token table first (e.g. "CB" -> "centre_back").
    Falls back to `player_analytics.config.ROLE_ALIASES`'s coarse broad role
    (e.g. "D" -> "defender") when no fine-grained token matches, so nothing
    V1 could already classify becomes unclassified here. Returns `None` only
    when neither table recognizes the token -- never guessed.
    """

    if listed_position is None:
        return None
    token = listed_position.strip().upper()
    if not token:
        return None

    fine = FINE_POSITION_ALIASES.get(token)
    if fine is not None:
        return fine
    return ROLE_ALIASES.get(token)
