"""Normalize FPL `element-summary` `history_past` entries into `PlayerSeasonStatsRecord`.

`history_past` is a season-aggregate record (Block 16) -- no match-by-match
breakdown, so this never claims a per-match observation. Verified live
against the real FPL API during implementation: a `history_past` entry's
`season_name` field uses the `"2025/26"` forward-slash format (e.g.
`{"season_name": "2025/26", "goals_scored": 0, ...}`), and several numeric
fields (`influence`, `creativity`, `threat`, `ict_index`, `expected_goals`,
`expected_assists`, `expected_goal_involvements`, `expected_goals_conceded`)
arrive as strings, not numbers.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from football_intelligence.normalization.models import PlayerSeasonStatsRecord

JsonObject = dict[str, Any]

SOURCE = "fpl-official-api"
SEMANTIC_VERSION = "fpl-official-api-v1"


def normalize_fpl_element_summary(
    element: JsonObject,
    history_past_entry: JsonObject,
    *,
    season_label: str,
    competition_external_id: str,
    retrieved_at: datetime,
) -> PlayerSeasonStatsRecord | None:
    """Build one `PlayerSeasonStatsRecord` from a bootstrap element + history entry.

    `element` is one entry from `bootstrap-static`'s `elements` list (needs
    only `id`). `history_past_entry` is one entry from that same player's
    `element-summary` `history_past` list. Returns `None` when the entry's
    `season_name` does not match `season_label` -- never guessed, and never
    silently substitutes the wrong season's numbers.
    """

    element_id = element.get("id")
    if not isinstance(element_id, int):
        return None

    season_name = history_past_entry.get("season_name")
    if season_name != season_label:
        return None

    return PlayerSeasonStatsRecord(
        player_external_id=str(element_id),
        competition_external_id=competition_external_id,
        season_label=season_label,
        minutes=_int_or_none(history_past_entry.get("minutes")),
        starts=_int_or_none(history_past_entry.get("starts")),
        # FPL's history_past never publishes a distinct "appearances" count
        # (only "minutes" and "starts") -- left None rather than fabricated
        # from starts or a nonzero-minutes heuristic.
        appearances=None,
        goals=_int_or_none(history_past_entry.get("goals_scored")),
        assists=_int_or_none(history_past_entry.get("assists")),
        clean_sheets=_int_or_none(history_past_entry.get("clean_sheets")),
        goals_conceded=_int_or_none(history_past_entry.get("goals_conceded")),
        own_goals=_int_or_none(history_past_entry.get("own_goals")),
        penalties_saved=_int_or_none(history_past_entry.get("penalties_saved")),
        penalties_missed=_int_or_none(history_past_entry.get("penalties_missed")),
        yellow_cards=_int_or_none(history_past_entry.get("yellow_cards")),
        red_cards=_int_or_none(history_past_entry.get("red_cards")),
        saves=_int_or_none(history_past_entry.get("saves")),
        bonus=_int_or_none(history_past_entry.get("bonus")),
        bps=_int_or_none(history_past_entry.get("bps")),
        influence=_float_or_none(history_past_entry.get("influence")),
        creativity=_float_or_none(history_past_entry.get("creativity")),
        threat=_float_or_none(history_past_entry.get("threat")),
        ict_index=_float_or_none(history_past_entry.get("ict_index")),
        tackles=_int_or_none(history_past_entry.get("tackles")),
        recoveries=_int_or_none(history_past_entry.get("recoveries")),
        clearances_blocks_interceptions=_int_or_none(
            history_past_entry.get("clearances_blocks_interceptions")
        ),
        defensive_contribution=_int_or_none(history_past_entry.get("defensive_contribution")),
        expected_goals=_float_or_none(history_past_entry.get("expected_goals")),
        expected_assists=_float_or_none(history_past_entry.get("expected_assists")),
        expected_goal_involvements=_float_or_none(
            history_past_entry.get("expected_goal_involvements")
        ),
        expected_goals_conceded=_float_or_none(history_past_entry.get("expected_goals_conceded")),
        source=SOURCE,
        source_url=f"https://fantasy.premierleague.com/api/element-summary/{element_id}/",
        retrieved_at=retrieved_at,
        semantic_version=SEMANTIC_VERSION,
    )


def _int_or_none(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        stripped = value.strip()
        if stripped.lstrip("-").isdigit():
            return int(stripped)
    return None


def _float_or_none(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return None
    return None
