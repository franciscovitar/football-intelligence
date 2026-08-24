from __future__ import annotations

from datetime import date

import pytest

from football_intelligence.data_mesh.player_identity_candidates import (
    PlayerIdentityRecord,
    PlayerIdentityRecordError,
    compare_player_identity_records,
    generate_exact_name_candidates,
)


def _record(
    *,
    source: str,
    player_id: str,
    name: str = "Julián Álvarez",
    teams: tuple[str, ...] = (),
    matches: tuple[str, ...] = (),
    dob: date | None = None,
    nationality: str | None = None,
) -> PlayerIdentityRecord:
    return PlayerIdentityRecord(
        source_code=source,
        provider_player_id=player_id,
        raw_name=name,
        competition_code="ESP_LL",
        season_label="2025/26",
        team_context_keys=teams,
        shared_match_keys=matches,
        date_of_birth=dob,
        nationality=nationality,
        position="forward",
        height_cm=170,
    )


def test_exact_name_alone_is_never_enough() -> None:
    candidate = compare_player_identity_records(
        _record(source="source-a", player_id="1"),
        _record(source="source-b", player_id="9", name="Julian Alvarez"),
    )

    assert candidate.exact_name_match
    assert candidate.state == "insufficient_evidence"
    assert "name_only_or_weak_profile_evidence" in candidate.reasons


def test_exact_name_shared_team_and_match_is_crosswalk_ready() -> None:
    team = "team:ESP_LL:atletico-madrid"
    match = "match:ESP_LL:2025/26:example"
    candidate = compare_player_identity_records(
        _record(
            source="source-a",
            player_id="1",
            teams=(team,),
            matches=(match,),
            dob=date(2000, 1, 31),
        ),
        _record(
            source="source-b",
            player_id="9",
            name="Julian Alvarez",
            teams=(team,),
            matches=(match,),
            dob=date(2000, 1, 31),
        ),
    )

    assert candidate.state == "crosswalk_ready"
    assert candidate.shared_team_context_keys == (team,)
    assert candidate.shared_match_keys == (match,)
    assert "date_of_birth_match" in candidate.reasons


def test_date_of_birth_disagreement_is_a_hard_conflict() -> None:
    team = "team:ESP_LL:atletico-madrid"
    match = "match:ESP_LL:2025/26:example"
    candidate = compare_player_identity_records(
        _record(
            source="source-a",
            player_id="1",
            teams=(team,),
            matches=(match,),
            dob=date(2000, 1, 31),
        ),
        _record(
            source="source-b",
            player_id="9",
            teams=(team,),
            matches=(match,),
            dob=date(2000, 2, 1),
        ),
    )

    assert candidate.state == "conflict"
    assert candidate.reasons[-1] == "date_of_birth_conflict"


def test_profile_and_team_evidence_without_shared_match_requires_review() -> None:
    team = "team:ESP_LL:atletico-madrid"
    candidate = compare_player_identity_records(
        _record(
            source="source-a",
            player_id="1",
            teams=(team,),
            dob=date(2000, 1, 31),
            nationality="Argentina",
        ),
        _record(
            source="source-b",
            player_id="9",
            name="Julian Alvarez",
            teams=(team,),
            dob=date(2000, 1, 31),
            nationality="argentina",
        ),
    )

    assert candidate.state == "review_required"
    assert "shared_team_context" in candidate.reasons
    assert "date_of_birth_match" in candidate.reasons


def test_multiple_shared_teams_need_match_to_team_attribution_before_crosswalk() -> None:
    teams = (
        "team:ESP_LL:atletico-madrid",
        "team:ESP_LL:river-plate",
    )
    match = "match:ESP_LL:2025/26:example"
    candidate = compare_player_identity_records(
        _record(source="source-a", player_id="1", teams=teams, matches=(match,)),
        _record(source="source-b", player_id="9", teams=teams, matches=(match,)),
    )

    assert candidate.state == "review_required"


def test_candidate_generation_is_exact_normalized_name_only() -> None:
    left = (
        _record(source="source-a", player_id="1", name="Julián Álvarez"),
        _record(source="source-a", player_id="2", name="Lionel Messi"),
    )
    right = (
        _record(source="source-b", player_id="8", name="Julian Alvarez"),
        _record(source="source-b", player_id="9", name="Lionel Andres Messi"),
    )

    candidates = generate_exact_name_candidates(left, right)

    assert len(candidates) == 1
    assert candidates[0].left.provider_player_id == "1"
    assert candidates[0].right.provider_player_id == "8"


def test_candidate_batch_rejects_conflicting_duplicate_provider_ids() -> None:
    left = (
        _record(source="source-a", player_id="1", name="Player One"),
        _record(source="source-a", player_id="1", name="Different Player"),
    )

    with pytest.raises(PlayerIdentityRecordError, match="conflicting rows"):
        generate_exact_name_candidates(left, ())
