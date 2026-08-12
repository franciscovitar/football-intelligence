"""Evidence-backed tactical profiles without unsupported spatial claims."""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

from football_intelligence.tactical_intelligence.models import (
    DefensiveSignal,
    FormationSignal,
    StyleSignal,
    TeamTacticalInput,
    TeamTacticalSnapshot,
)

MODEL_VERSION = "tactical-v1.0"
SOURCE_MODEL_VERSION = "team-v1.0"

_HIGH = 65.0
_LOW = 40.0
_MEDIUM_LOW = 50.0
_MIN_SOURCE_CONFIDENCE = 0.35


def calculate_tactical_intelligence(
    inputs: list[TeamTacticalInput],
    *,
    calculated_at: datetime | None = None,
) -> tuple[TeamTacticalSnapshot, ...]:
    effective_at = calculated_at or datetime.now(UTC)
    return tuple(
        _calculate_team(item, calculated_at=effective_at)
        for item in sorted(inputs, key=lambda candidate: candidate.team_id)
    )


def _calculate_team(
    item: TeamTacticalInput,
    *,
    calculated_at: datetime,
) -> TeamTacticalSnapshot:
    control = _dimension(item.dimension_scores, "control")
    volume = _dimension(item.dimension_scores, "chance_generation")
    defense = _dimension(item.dimension_scores, "defense")

    style_signal = _style_signal(
        control=control,
        volume=volume,
        source_confidence=item.source_confidence,
    )
    defensive_signal = _defensive_signal(
        defense=defense,
        source_confidence=item.source_confidence,
    )

    formation = _formation_profile(item)
    formation_matches = int(formation["matches"])
    formation_confidence = float(formation["confidence"])
    tactical_confidence = _clamp01(
        item.source_confidence * (0.85 + 0.15 * formation_confidence if formation_matches else 0.85)
    )

    summary = _summary(
        style_signal=style_signal,
        defensive_signal=defensive_signal,
        primary_formation=_string_or_none(formation["primary"]),
        formation_matches=formation_matches,
        matches=item.matches,
    )

    alternatives = tuple(formation["alternatives"])
    evidence: dict[str, Any] = {
        "source_dimensions": {
            "control": control,
            "chance_generation": volume,
            "defense": defense,
        },
        "source_confidence": round(item.source_confidence, 5),
        "formation": {
            "observed_matches": formation_matches,
            "team_matches": item.matches,
            "primary": formation["primary"],
            "primary_share": formation["share"],
            "counts": list(alternatives),
        },
        "claims_not_supported": [
            "pressing_height",
            "defensive_block_shape",
            "counterattack_frequency",
            "player_movement_paths",
        ],
    }

    return TeamTacticalSnapshot(
        team_id=item.team_id,
        team_name=item.team_name,
        competition_id=item.competition_id,
        competition_code=item.competition_code,
        competition_name=item.competition_name,
        season_id=item.season_id,
        season_label=item.season_label,
        scope_key=item.scope_key,
        matches=item.matches,
        source_confidence=round(item.source_confidence, 5),
        control_score=_rounded(control),
        attacking_volume_score=_rounded(volume),
        defensive_resistance_score=_rounded(defense),
        style_signal=style_signal,
        defensive_signal=defensive_signal,
        primary_formation=_string_or_none(formation["primary"]),
        formation_matches=formation_matches,
        formation_share=_rounded(formation["share"], digits=5),
        formation_confidence=round(formation_confidence, 5),
        formation_signal=formation["signal"],
        alternative_formations=alternatives,
        tactical_confidence=round(tactical_confidence, 5),
        summary=summary,
        evidence=evidence,
        source_model_version=SOURCE_MODEL_VERSION,
        model_version=MODEL_VERSION,
        calculated_at=calculated_at,
    )


def _style_signal(
    *,
    control: float | None,
    volume: float | None,
    source_confidence: float,
) -> StyleSignal:
    if source_confidence < _MIN_SOURCE_CONFIDENCE or control is None or volume is None:
        return "insufficient_evidence"

    if control >= _HIGH and volume >= _HIGH:
        return "control_and_volume"
    if control >= _HIGH and volume < 55.0:
        return "possession_control"
    if volume >= _HIGH and control < _MEDIUM_LOW:
        return "volume_without_control"
    if control <= _LOW and volume <= _LOW:
        return "low_control_low_volume"
    return "balanced"


def _defensive_signal(
    *,
    defense: float | None,
    source_confidence: float,
) -> DefensiveSignal:
    if source_confidence < _MIN_SOURCE_CONFIDENCE or defense is None:
        return "insufficient_evidence"
    if defense >= _HIGH:
        return "restrictive_shot_profile"
    if defense <= 35.0:
        return "permissive_shot_profile"
    return "balanced"


def _formation_profile(item: TeamTacticalInput) -> dict[str, Any]:
    valid = [
        observation
        for observation in sorted(
            item.formations,
            key=lambda candidate: (candidate.kickoff_at, candidate.match_id),
            reverse=True,
        )
        if _valid_formation(observation.formation)
    ]
    if not valid:
        return {
            "primary": None,
            "matches": 0,
            "share": None,
            "confidence": 0.0,
            "signal": "unavailable",
            "alternatives": (),
        }

    counts = Counter(observation.formation for observation in valid)
    first_seen = {
        formation: next(
            index for index, observation in enumerate(valid) if observation.formation == formation
        )
        for formation in counts
    }
    ordered = sorted(
        counts.items(),
        key=lambda pair: (-pair[1], first_seen[pair[0]], pair[0]),
    )

    primary, primary_count = ordered[0]
    formation_matches = len(valid)
    share = primary_count / formation_matches
    coverage = min(1.0, formation_matches / max(1, item.matches))
    confidence = _clamp01(coverage * (0.5 + 0.5 * share))

    signal: FormationSignal
    if formation_matches < 3 or coverage < 0.30:
        signal = "limited_evidence"
    elif share >= 0.65:
        signal = "stable"
    elif share <= 0.50 and len(ordered) >= 2:
        signal = "variable"
    else:
        signal = "mixed"

    alternatives = tuple(
        {
            "formation": formation,
            "matches": count,
            "share": round(count / formation_matches, 5),
        }
        for formation, count in ordered[:4]
    )
    return {
        "primary": primary,
        "matches": formation_matches,
        "share": share,
        "confidence": confidence,
        "signal": signal,
        "alternatives": alternatives,
    }


def _summary(
    *,
    style_signal: StyleSignal,
    defensive_signal: DefensiveSignal,
    primary_formation: str | None,
    formation_matches: int,
    matches: int,
) -> str:
    style_text = {
        "control_and_volume": (
            "Combina control alto de balón con volumen ofensivo alto dentro de su liga."
        ),
        "possession_control": ("Controla mucho el balón, con un volumen ofensivo más moderado."),
        "volume_without_control": (
            "Genera volumen ofensivo alto con menor control de balón; "
            "esto no prueba juego de contra."
        ),
        "low_control_low_volume": (
            "Presenta control y volumen ofensivo bajos en relación con su competición."
        ),
        "balanced": (
            "Muestra un perfil relativamente equilibrado entre control y volumen ofensivo."
        ),
        "insufficient_evidence": (
            "No hay evidencia cuantitativa suficiente para resumir el estilo con confianza."
        ),
    }[style_signal]

    defense_text = {
        "restrictive_shot_profile": (
            " Además, su perfil defensivo limita bien el volumen de tiros del rival."
        ),
        "permissive_shot_profile": (
            " Defensivamente concede un volumen alto de tiros en comparación con su liga."
        ),
        "balanced": " El volumen defensivo concedido está cerca de la zona media.",
        "insufficient_evidence": "",
    }[defensive_signal]

    if primary_formation is None:
        formation_text = " No hay formación nominal observada suficiente todavía."
    else:
        formation_text = (
            f" Formación nominal más repetida: {primary_formation} "
            f"({formation_matches}/{matches} partidos con formación observada)."
        )

    return style_text + defense_text + formation_text


def _dimension(values: Mapping[str, float], name: str) -> float | None:
    value = values.get(name)
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    return None


def _valid_formation(value: str) -> bool:
    parts = value.split("-")
    if not 3 <= len(parts) <= 5:
        return False
    try:
        numbers = [int(part) for part in parts]
    except ValueError:
        return False
    return all(number > 0 for number in numbers) and sum(numbers) == 10


def _rounded(value: Any, *, digits: int = 2) -> float | None:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return round(float(value), digits)
    return None


def _string_or_none(value: object) -> str | None:
    return value if isinstance(value, str) else None


def _clamp01(value: float) -> float:
    return min(1.0, max(0.0, value))
