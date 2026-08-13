"""World Radar V1 competition catalog: name + country, never provider ids.

Provider league ids are resolved live via `/leagues` at execution time (see
`football_intelligence.jobs.sync_world_radar`); nothing here is trusted to be
a stable provider identifier.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

_ALLOWED_KEYS = frozenset({"code", "name", "country"})
_CODE_PATTERN = re.compile(r"^[A-Z0-9_]{2,20}$")

DEFAULT_CONFIG_PATH = (
    Path(__file__).resolve().parents[4] / "config" / "world_radar_competitions.json"
)


@dataclass(frozen=True, slots=True)
class RadarCompetitionConfig:
    code: str
    name: str
    country: str


def load_radar_competitions(path: Path | None = None) -> tuple[RadarCompetitionConfig, ...]:
    target = path or DEFAULT_CONFIG_PATH
    try:
        raw_text = target.read_text(encoding="utf-8")
    except OSError as exc:
        raise ValueError(f"world radar competition config not readable at {target}: {exc}") from exc

    try:
        payload: Any = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"world radar competition config is not valid JSON: {exc}") from exc

    return parse_radar_competitions(payload)


def parse_radar_competitions(payload: Any) -> tuple[RadarCompetitionConfig, ...]:
    if not isinstance(payload, list) or not payload:
        raise ValueError("world radar competition config must be a non-empty JSON array")

    seen_codes: set[str] = set()
    competitions: list[RadarCompetitionConfig] = []
    for index, item in enumerate(payload):
        if not isinstance(item, dict):
            raise ValueError(f"world radar competition[{index}] must be a JSON object")

        extra_keys = set(item.keys()) - _ALLOWED_KEYS
        if extra_keys:
            raise ValueError(
                f"world radar competition[{index}] has unsupported keys: {sorted(extra_keys)}"
            )
        missing_keys = _ALLOWED_KEYS - set(item.keys())
        if missing_keys:
            raise ValueError(
                f"world radar competition[{index}] is missing keys: {sorted(missing_keys)}"
            )

        code = item["code"]
        name = item["name"]
        country = item["country"]
        if not isinstance(code, str) or not _CODE_PATTERN.match(code):
            raise ValueError(
                f"world radar competition[{index}].code must match {_CODE_PATTERN.pattern!r}"
            )
        if not isinstance(name, str) or not name.strip():
            raise ValueError(f"world radar competition[{index}].name must not be blank")
        if not isinstance(country, str) or not country.strip():
            raise ValueError(f"world radar competition[{index}].country must not be blank")
        if code in seen_codes:
            raise ValueError(f"world radar competition code '{code}' is duplicated")
        seen_codes.add(code)

        competitions.append(
            RadarCompetitionConfig(code=code, name=name.strip(), country=country.strip())
        )

    return tuple(competitions)
