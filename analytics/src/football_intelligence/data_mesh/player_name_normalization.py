"""Deterministic player-name normalization for the Block 20D.3 player
crosswalk evidence.

Mirrors `entity_resolution.normalize_team_name()`'s discipline -- every
transformation below is a fixed, reviewable, explicit rule applied
identically regardless of which two names are being compared. It is
deliberately narrower than the team-name normalizer: it never strips
stopword tokens, never applies an alias table, and never reorders tokens.
A club's short/official name genuinely varies by convention in ways a real
person's name does not; token order and every name component are real
identity-bearing information for a player, so preserving them exactly
(after only accent/punctuation/whitespace/case normalization) is the
correct amount of normalization for an EXACT-match crosswalk, not a
similarity heuristic.

Allowed operations: Unicode NFKD decomposition + combining-mark stripping
(accent folding), casefold, punctuation normalization (periods, hyphens,
apostrophes, and similar separators become a single space), and whitespace
collapsing. Never: nickname dictionaries, first-name-only comparison, edit
distance, fuzzy/similarity scoring, LLM matching, or any global
name-only player resolution -- see `data_mesh/entity_resolution_v2.py`'s
`PlayerCrosswalkEntry`/`resolve_player_v2()` for why an exact normalized
name is only ever ONE of several required pieces of evidence, never
sufficient by itself.

Wyscout's real double-escaped-Unicode defect
(`providers/wyscout_open_text.repair_wyscout_double_escaped_unicode`) must
be repaired at that provider's own text boundary BEFORE a name reaches this
generic normalizer -- this module never repairs provider-specific encoding
defects itself.
"""

from __future__ import annotations

import re
import unicodedata

# Characters treated as harmless separators within a real name and folded
# to a single space: hyphens (double-barrelled names), apostrophes
# (O'Brien-style names, including the Unicode right single quote), periods
# (initials), and commas (a "Last, First" ordering some sources use).
_SEPARATOR_RE = re.compile(r"[.\-'’,]")

# Anything else non-alphanumeric (after separators are already folded to
# spaces) becomes a space too -- e.g. stray punctuation, slashes.
_NON_ALNUM_RE = re.compile(r"[^0-9a-z ]+")

_SPACE_RE = re.compile(r"\s+")


def normalize_player_name(raw: str) -> str:
    """Deterministically normalizes one player name for exact-match
    crosswalk comparison. Returns `""` for blank/unusable input -- callers
    must treat that as "no usable name evidence", never as a valid
    identity."""

    if not isinstance(raw, str):
        return ""
    decomposed = unicodedata.normalize("NFKD", raw)
    without_marks = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    lowered = without_marks.casefold().strip()
    separators_folded = _SEPARATOR_RE.sub(" ", lowered)
    cleaned = _NON_ALNUM_RE.sub(" ", separators_folded)
    tokens = [token for token in _SPACE_RE.split(cleaned) if token]
    return " ".join(tokens)
