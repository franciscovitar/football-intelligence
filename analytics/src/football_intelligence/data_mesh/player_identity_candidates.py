"""Deterministic cross-source player identity candidate analysis.

This module is intentionally *not* an entity resolver. It produces auditable
candidate evidence for later review/promotion into ``PlayerCrosswalk`` without
weakening the existing rule that player identities are never joined by name
similarity alone.

The comparison rules are conservative and provider-independent:

- names are compared only with the existing exact deterministic normalizer;
- fuzzy/edit-distance/LLM matching is never used;
- contradictory dates of birth are a hard conflict;
- exact name alone is always insufficient;
- a candidate is ``crosswalk_ready`` only when exact normalized name, at least
  one shared canonical team context, and at least one shared canonical match
  are all present, with no hard contradiction;
- richer profile evidence without shared-match evidence is review material,
  never an automatic crosswalk.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date
from typing import Literal

from football_intelligence.data_mesh.player_name_normalization import normalize_player_name

PlayerIdentityCandidateState = Literal[
    "crosswalk_ready",
    "review_required",
    "insufficient_evidence",
    "conflict",
]


class PlayerIdentityRecordError(ValueError):
    """One source-local player identity record violates the intake contract."""


@dataclass(frozen=True, slots=True)
class PlayerIdentityRecord:
    """Provider-local identity evidence used to compare the same real player.

    ``team_context_keys`` and ``shared_match_keys`` must already use canonical
    Football Intelligence logical keys when present. Static season-level sources
    that do not expose match identity may leave ``shared_match_keys`` empty; such
    records can produce review candidates but can never become crosswalk-ready by
    themselves.
    """

    source_code: str
    provider_player_id: str
    raw_name: str
    competition_code: str
    season_label: str
    team_context_keys: tuple[str, ...] = ()
    shared_match_keys: tuple[str, ...] = ()
    date_of_birth: date | None = None
    nationality: str | None = None
    position: str | None = None
    height_cm: int | None = None

    def __post_init__(self) -> None:
        for field_name, value in (
            ("source_code", self.source_code),
            ("provider_player_id", self.provider_player_id),
            ("raw_name", self.raw_name),
            ("competition_code", self.competition_code),
            ("season_label", self.season_label),
        ):
            if not isinstance(value, str) or not value.strip():
                raise PlayerIdentityRecordError(f"{field_name} must be a non-blank string")

        if not self.normalized_name:
            raise PlayerIdentityRecordError("raw_name does not produce a usable normalized name")
        _validate_sorted_unique(self.team_context_keys, "team_context_keys")
        _validate_sorted_unique(self.shared_match_keys, "shared_match_keys")
        if self.height_cm is not None and not 100 <= self.height_cm <= 230:
            raise PlayerIdentityRecordError(
                f"height_cm must be between 100 and 230 when present, got {self.height_cm}"
            )

    @property
    def normalized_name(self) -> str:
        return normalize_player_name(self.raw_name)

    @property
    def source_ref(self) -> tuple[str, str]:
        return (self.source_code, self.provider_player_id)


@dataclass(frozen=True, slots=True)
class PlayerIdentityCandidate:
    left: PlayerIdentityRecord
    right: PlayerIdentityRecord
    state: PlayerIdentityCandidateState
    reasons: tuple[str, ...]
    shared_team_context_keys: tuple[str, ...]
    shared_match_keys: tuple[str, ...]

    @property
    def exact_name_match(self) -> bool:
        return self.left.normalized_name == self.right.normalized_name


def compare_player_identity_records(
    left: PlayerIdentityRecord,
    right: PlayerIdentityRecord,
) -> PlayerIdentityCandidate:
    """Compare two source-local records without mutating a crosswalk."""

    if left.source_code == right.source_code:
        raise PlayerIdentityRecordError(
            "player identity candidates must compare two different sources"
        )

    shared_teams = tuple(sorted(set(left.team_context_keys) & set(right.team_context_keys)))
    shared_matches = tuple(sorted(set(left.shared_match_keys) & set(right.shared_match_keys)))
    reasons: list[str] = []

    if left.normalized_name != right.normalized_name:
        return PlayerIdentityCandidate(
            left=left,
            right=right,
            state="insufficient_evidence",
            reasons=("normalized_name_mismatch",),
            shared_team_context_keys=shared_teams,
            shared_match_keys=shared_matches,
        )

    reasons.append("exact_normalized_name")

    if (
        left.date_of_birth is not None
        and right.date_of_birth is not None
        and left.date_of_birth != right.date_of_birth
    ):
        return PlayerIdentityCandidate(
            left=left,
            right=right,
            state="conflict",
            reasons=tuple(reasons + ["date_of_birth_conflict"]),
            shared_team_context_keys=shared_teams,
            shared_match_keys=shared_matches,
        )

    if left.date_of_birth is not None and left.date_of_birth == right.date_of_birth:
        reasons.append("date_of_birth_match")
    if _same_optional_text(left.nationality, right.nationality):
        reasons.append("nationality_match")
    elif left.nationality and right.nationality:
        reasons.append("nationality_differs_non_blocking")
    if _same_optional_text(left.position, right.position):
        reasons.append("position_match")
    elif left.position and right.position:
        reasons.append("position_differs_non_blocking")
    if left.height_cm is not None and right.height_cm is not None:
        difference = abs(left.height_cm - right.height_cm)
        if difference == 0:
            reasons.append("height_match")
        elif difference <= 2:
            reasons.append("height_near_match")
        else:
            reasons.append("height_differs_non_blocking")

    same_scope = (
        left.competition_code == right.competition_code
        and left.season_label == right.season_label
    )
    if same_scope:
        reasons.append("same_competition_season")
    if shared_teams:
        reasons.append("shared_team_context")
    if shared_matches:
        reasons.append("shared_canonical_match")

    # The existing PlayerCrosswalk contract needs team-context-specific shared
    # match evidence. With exactly one shared team context, the global shared
    # match intersection is unambiguous enough to mark the pair ready for a
    # caller to build that explicit evidence object. Multiple shared teams (a
    # real transfer scenario) stay review-required until the caller attributes
    # each shared match to its team context explicitly.
    if len(shared_teams) == 1 and shared_matches:
        return PlayerIdentityCandidate(
            left=left,
            right=right,
            state="crosswalk_ready",
            reasons=tuple(reasons),
            shared_team_context_keys=shared_teams,
            shared_match_keys=shared_matches,
        )

    corroborating_profile = any(
        reason in reasons
        for reason in (
            "date_of_birth_match",
            "nationality_match",
            "position_match",
            "height_match",
            "height_near_match",
        )
    )
    if shared_teams or (same_scope and corroborating_profile):
        return PlayerIdentityCandidate(
            left=left,
            right=right,
            state="review_required",
            reasons=tuple(reasons),
            shared_team_context_keys=shared_teams,
            shared_match_keys=shared_matches,
        )

    return PlayerIdentityCandidate(
        left=left,
        right=right,
        state="insufficient_evidence",
        reasons=tuple(reasons + ["name_only_or_weak_profile_evidence"]),
        shared_team_context_keys=shared_teams,
        shared_match_keys=shared_matches,
    )


def generate_exact_name_candidates(
    left_records: Iterable[PlayerIdentityRecord],
    right_records: Iterable[PlayerIdentityRecord],
) -> tuple[PlayerIdentityCandidate, ...]:
    """Generate deterministic candidates only for exact normalized-name buckets.

    This is deliberately a recall-limited helper. A player whose two sources use
    materially different names remains unresolved until explicit aliases/crosswalk
    evidence is reviewed; the function never widens into fuzzy matching.
    """

    left = tuple(left_records)
    right = tuple(right_records)
    _validate_single_source_batch(left, "left_records")
    _validate_single_source_batch(right, "right_records")
    if left and right and left[0].source_code == right[0].source_code:
        raise PlayerIdentityRecordError("candidate batches must come from different sources")

    right_by_name: dict[str, list[PlayerIdentityRecord]] = defaultdict(list)
    for record in right:
        right_by_name[record.normalized_name].append(record)

    candidates: list[PlayerIdentityCandidate] = []
    for left_record in left:
        for right_record in right_by_name.get(left_record.normalized_name, []):
            candidates.append(compare_player_identity_records(left_record, right_record))
    return tuple(
        sorted(
            candidates,
            key=lambda candidate: (
                candidate.left.source_code,
                candidate.left.provider_player_id,
                candidate.right.source_code,
                candidate.right.provider_player_id,
            ),
        )
    )


def _validate_single_source_batch(
    records: tuple[PlayerIdentityRecord, ...], field_name: str
) -> None:
    if not records:
        return
    source_codes = {record.source_code for record in records}
    if len(source_codes) != 1:
        raise PlayerIdentityRecordError(
            f"{field_name} must contain records from exactly one source, got {sorted(source_codes)!r}"
        )
    seen: dict[str, PlayerIdentityRecord] = {}
    for record in records:
        existing = seen.get(record.provider_player_id)
        if existing is not None and existing != record:
            raise PlayerIdentityRecordError(
                f"{field_name} contains conflicting rows for provider_player_id "
                f"{record.provider_player_id!r}"
            )
        seen[record.provider_player_id] = record


def _validate_sorted_unique(values: tuple[str, ...], field_name: str) -> None:
    if tuple(sorted(values)) != values:
        raise PlayerIdentityRecordError(f"{field_name} must be in canonical ascending order")
    if len(set(values)) != len(values):
        raise PlayerIdentityRecordError(f"{field_name} must not contain duplicates")
    if any(not isinstance(value, str) or not value.strip() for value in values):
        raise PlayerIdentityRecordError(f"{field_name} must contain only non-blank strings")


def _same_optional_text(left: str | None, right: str | None) -> bool:
    if left is None or right is None:
        return False
    normalized_left = " ".join(left.casefold().split())
    normalized_right = " ".join(right.casefold().split())
    return bool(normalized_left) and normalized_left == normalized_right
