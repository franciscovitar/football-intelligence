"""Wyscout-specific text repair for a real, verified source-data defect.

Block 20D.1's real Spain/La Liga 2017/18 overlap investigation found that
some fields in Wyscout Open Data's official Figshare `teams.json` and
`players.json` (e.g. `name`/`officialName`, `firstName`/`lastName`) are
JSON-escaped **twice** for non-ASCII characters. After one normal
`json.loads()` pass, the resulting Python string still contains the literal
six-character sequence `\\uXXXX` (a real backslash followed by the text
"uXXXX") instead of the intended character -- verified at the raw-byte
level, not a parsing artifact of this repository's own tooling. Confirmed
examples from the real source: `"Atl\\u00e9tico Madrid"` (should read
"Atlético Madrid"), `"M\\u00e1laga"` ("Málaga"), and player field
`"Juan Jos\\u00e9"` ("Juan José").

This is a narrow, Wyscout-source-specific repair -- it lives here, not in
`data_mesh.entity_resolution.normalize_team_name()`, because it fixes a
defect in one provider's raw field encoding, not a general name-comparison
heuristic. Callers should apply it to Wyscout `name`/`officialName`/
`firstName`/`lastName`-style identity fields only, never to source ids,
URLs, or `source_reference` values -- those must never be reinterpreted.
"""

from __future__ import annotations

import re

# Matches a literal backslash followed by lowercase "u" and exactly 4 hex
# digits -- the exact real-source pattern verified in Block 20D.1, and
# nothing broader. A genuinely correctly-decoded string (already containing
# real Unicode characters, no literal backslashes) never matches this and
# is returned byte/character-identical.
_DOUBLE_ESCAPED_UNICODE_PATTERN = re.compile(r"\\u([0-9a-fA-F]{4})")


def repair_wyscout_double_escaped_unicode(text: str) -> str:
    """Repairs Wyscout's verified double-JSON-escaping defect in a single
    text field. A no-op for any string that does not contain the literal
    `\\uXXXX` pattern (including plain ASCII, and already-correctly-decoded
    Unicode text)."""

    if "\\u" not in text:
        return text
    return _DOUBLE_ESCAPED_UNICODE_PATTERN.sub(lambda match: chr(int(match.group(1), 16)), text)
