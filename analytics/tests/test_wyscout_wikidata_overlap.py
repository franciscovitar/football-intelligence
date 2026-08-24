from __future__ import annotations

from datetime import date

from football_intelligence.jobs.audit_wyscout_wikidata_overlap import (
    WikidataDiscoveryRow,
    WyscoutRosterProfile,
    build_wyscout_roster_profiles,
    discover_exact_name_candidates,
    evaluate_player_overlap,
    resolve_wikidata_team_candidate,
)
from football_intelligence.providers.wikidata_profiles import (
    PROLEPTIC_GREGORIAN_QID,
    WikidataPlayerProfile,
    WikidataTeamMembership,
    WikidataTimeValue,
)


def _time(raw: str) -> WikidataTimeValue:
    return WikidataTimeValue(
        raw_time=raw,
        precision=11,
        calendar_model_qid=PROLEPTIC_GREGORIAN_QID,
    )


def _roster_player(
    *,
    player_id: str = "907",
    name: str = "Mohamed Salah",
    variants: tuple[str, ...] = ("Mohamed Salah",),
    dob: date | None = date(1992, 6, 15),
    team_contexts: tuple[str, ...] = ("team:ENG_PL:liverpool",),
) -> WyscoutRosterProfile:
    return WyscoutRosterProfile(
        provider_player_id=player_id,
        display_name=name,
        name_variants=variants,
        date_of_birth=dob,
        nationality="Egypt",
        position="Forward",
        team_context_keys=team_contexts,
        team_names=("Liverpool",),
    )


def _wikidata_profile(
    *,
    qid: str = "Q1",
    name: str = "Mohamed Salah",
    dob: str = "+1992-06-15T00:00:00Z",
    team_qid: str = "Q200",
    team_start: str = "+2017-07-01T00:00:00Z",
    team_end: str = "+2026-06-30T00:00:00Z",
) -> WikidataPlayerProfile:
    return WikidataPlayerProfile(
        qid=qid,
        display_name=name,
        dates_of_birth=(_time(dob),),
        citizenship_qids=("Q79",),
        position_qids=("Q280658",),
        team_memberships=(
            WikidataTeamMembership(
                team_qid=team_qid,
                start_times=(_time(team_start),),
                end_times=(_time(team_end),),
            ),
        ),
        last_revision_id=1,
        modified_at="2026-08-24T00:00:00Z",
    )


def test_build_wyscout_roster_profiles_preserves_source_fields_and_team_context() -> None:
    matches = [
        {
            "teamsData": {
                "100": {
                    "formation": {
                        "lineup": [{"playerId": 907}],
                        "bench": [],
                    }
                }
            }
        }
    ]
    players = [
        {
            "wyId": 907,
            "shortName": "Mohamed Salah",
            "firstName": "Mohamed",
            "middleName": "",
            "lastName": "Salah",
            "birthDate": "1992-06-15",
            "passportArea": {"name": "Egypt"},
            "role": {"name": "Forward", "code2": "FW"},
        }
    ]
    teams = [{"wyId": 100, "name": "Liverpool"}]

    profiles = build_wyscout_roster_profiles(
        matches_payload=matches,
        players_payload=players,
        teams_payload=teams,
    )

    assert len(profiles) == 1
    profile = profiles[0]
    assert profile.provider_player_id == "907"
    assert profile.display_name == "Mohamed Salah"
    assert profile.name_variants == ("Mohamed Salah",)
    assert profile.date_of_birth == date(1992, 6, 15)
    assert profile.nationality == "Egypt"
    assert profile.position == "Forward"
    assert profile.team_context_keys == ("team:ENG_PL:liverpool",)


def test_team_mapping_requires_one_exact_normalized_football_candidate() -> None:
    mapping = resolve_wikidata_team_candidate(
        wyscout_team_id=100,
        wyscout_name="Liverpool",
        search_results=[
            {"id": "Q1", "label": "Liverpool", "description": "city in England"},
            {
                "id": "Q2",
                "label": "Liverpool F.C.",
                "description": "English association football club",
            },
        ],
    )

    assert mapping.status == "resolved"
    assert mapping.canonical_team_context == "team:ENG_PL:liverpool"
    assert mapping.wikidata_qid == "Q2"


def test_team_mapping_fails_closed_on_ambiguous_exact_football_candidates() -> None:
    mapping = resolve_wikidata_team_candidate(
        wyscout_team_id=100,
        wyscout_name="Liverpool",
        search_results=[
            {
                "id": "Q2",
                "label": "Liverpool F.C.",
                "description": "English association football club",
            },
            {
                "id": "Q3",
                "label": "Liverpool F.C.",
                "description": "football club",
            },
        ],
    )

    assert mapping.status == "ambiguous_exact_football_club_candidates"
    assert mapping.wikidata_qid is None


def test_team_mapping_fails_closed_on_same_name_football_homonym() -> None:
    mapping = resolve_wikidata_team_candidate(
        wyscout_team_id=1623,
        wyscout_name="Everton",
        search_results=[
            {
                "id": "Q140596527",
                "label": "Everton",
                "description": "French footballer",
            },
            {
                "id": "Q5794",
                "label": "Everton F.C.",
                "description": "association football club in Liverpool, England",
            },
        ],
    )

    assert mapping.status == "ambiguous_exact_football_club_candidates"
    assert mapping.wikidata_qid is None


def test_candidate_discovery_uses_exact_name_and_filters_known_dob_conflict() -> None:
    roster = (
        _roster_player(),
        _roster_player(
            player_id="908",
            name="Kevin De Bruyne",
            variants=("Kevin De Bruyne",),
            dob=date(1991, 6, 28),
            team_contexts=("team:ENG_PL:manchester city",),
        ),
    )
    rows = (
        WikidataDiscoveryRow(
            qid="Q1",
            label="Mohamed Salah",
            date_of_birth=date(1992, 6, 15),
            team_qid="Q200",
        ),
        WikidataDiscoveryRow(
            qid="Q9",
            label="Mohamed Salah",
            date_of_birth=date(1980, 1, 1),
            team_qid="Q200",
        ),
        WikidataDiscoveryRow(
            qid="Q2",
            label="Kevin De Bruyne",
            date_of_birth=None,
            team_qid="Q201",
        ),
    )

    candidates = discover_exact_name_candidates(roster, rows)

    assert candidates["907"] == ("Q1",)
    assert candidates["908"] == ("Q2",)


def test_wikidata_profile_with_exact_dob_and_bounded_team_is_review_required_only() -> None:
    player = _roster_player()
    profile = _wikidata_profile()

    result = evaluate_player_overlap(
        player=player,
        candidate_qids=("Q1",),
        profiles_by_qid={"Q1": profile},
        team_qid_to_context={"Q200": "team:ENG_PL:liverpool"},
    )

    assert result.state == "review_required"
    assert result.date_of_birth_matches is True
    assert result.shared_team_context_keys == ("team:ENG_PL:liverpool",)
    assert result.wikidata_has_exact_dob
    assert result.wikidata_has_citizenship
    assert result.wikidata_has_position
    assert result.wikidata_has_bounded_team_context
    assert "shared_team_specific_canonical_match" not in result.reasons


def test_dob_disagreement_remains_hard_conflict() -> None:
    player = _roster_player()
    profile = _wikidata_profile(dob="+1993-06-15T00:00:00Z")

    result = evaluate_player_overlap(
        player=player,
        candidate_qids=("Q1",),
        profiles_by_qid={"Q1": profile},
        team_qid_to_context={"Q200": "team:ENG_PL:liverpool"},
    )

    assert result.state == "conflict"
    assert result.date_of_birth_matches is False
    assert "date_of_birth_conflict" in result.reasons


def test_unbounded_or_unmapped_team_context_does_not_fake_shared_team_evidence() -> None:
    player = _roster_player()
    profile = WikidataPlayerProfile(
        qid="Q1",
        display_name="Mohamed Salah",
        dates_of_birth=(_time("+1992-06-15T00:00:00Z"),),
        citizenship_qids=(),
        position_qids=(),
        team_memberships=(WikidataTeamMembership(team_qid="Q200", start_times=(), end_times=()),),
        last_revision_id=1,
        modified_at=None,
    )

    result = evaluate_player_overlap(
        player=player,
        candidate_qids=("Q1",),
        profiles_by_qid={"Q1": profile},
        team_qid_to_context={"Q200": "team:ENG_PL:liverpool"},
    )

    assert result.state == "review_required"
    assert result.shared_team_context_keys == ()
    assert not result.wikidata_has_bounded_team_context


def test_multiple_exact_candidates_are_not_auto_selected() -> None:
    result = evaluate_player_overlap(
        player=_roster_player(),
        candidate_qids=("Q1", "Q2"),
        profiles_by_qid={"Q1": _wikidata_profile(qid="Q1")},
        team_qid_to_context={"Q200": "team:ENG_PL:liverpool"},
    )

    assert result.state == "ambiguous_exact_name_candidates"
    assert result.wikidata_qid is None
