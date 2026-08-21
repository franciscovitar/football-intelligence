"""Block 20D.4: `resolve_and_reconcile_v2()` orchestration -- granularity-
safe V2 grouping, explicit `PlayerCrosswalk` injection, bounded date
clustering, and the provider-pair + semantic-version comparability policy
gate (1 source -> single_source; 2 sources -> policy-gated; >2 sources ->
methodology_pending unconditionally)."""

from __future__ import annotations

from datetime import UTC, datetime

from football_intelligence.data_mesh.adapters.statsbomb_open import (
    SEMANTIC_VERSION as STATSBOMB_SEMANTIC_VERSION,
)
from football_intelligence.data_mesh.adapters.statsbomb_open import SOURCE_CODE as STATSBOMB
from football_intelligence.data_mesh.adapters.wyscout_open import (
    SEMANTIC_VERSION as WYSCOUT_SEMANTIC_VERSION,
)
from football_intelligence.data_mesh.adapters.wyscout_open import SOURCE_CODE as WYSCOUT
from football_intelligence.data_mesh.entity_resolution import resolve_team
from football_intelligence.data_mesh.entity_resolution_v2 import (
    PlayerCrosswalk,
    PlayerCrosswalkEntry,
    PlayerTeamContextEvidence,
)
from football_intelligence.data_mesh.models import NormalizedObservation
from football_intelligence.data_mesh.pipeline import resolve_and_reconcile_v2
from football_intelligence.data_mesh.reconciliation import MODEL_VERSION_V2

_NOW = datetime(2026, 8, 22, 18, 30, tzinfo=UTC)
COMPETITION_CODE = "ESP_LL"
SEASON_LABEL = "2017/18"
# Real, verified COMPETITION_MAPPINGS entries (entity_resolution.py) --
# needed so build_match_date_clusters() (reused unchanged from V0) can
# resolve competition identity for these synthetic observations.
WYSCOUT_COMPETITION_EXTERNAL_ID = "795"
STATSBOMB_COMPETITION_EXTERNAL_ID = "11"

HOME_TEAM_KEY = resolve_team(name="Home FC", competition_code=COMPETITION_CODE).logical_key
AWAY_TEAM_KEY = resolve_team(name="Away FC", competition_code=COMPETITION_CODE).logical_key
assert HOME_TEAM_KEY is not None and AWAY_TEAM_KEY is not None


def _competition_external_id(source_code: str) -> str:
    return (
        WYSCOUT_COMPETITION_EXTERNAL_ID
        if source_code == WYSCOUT
        else STATSBOMB_COMPETITION_EXTERNAL_ID
    )


def _semantic_version(source_code: str) -> str:
    return WYSCOUT_SEMANTIC_VERSION if source_code == WYSCOUT else STATSBOMB_SEMANTIC_VERSION


def _match_obs(
    *,
    source_code: str,
    match_id: str,
    kickoff_date: str,
    metric_name: str,
    value: object,
    semantic_version: str | None = None,
) -> NormalizedObservation:
    return NormalizedObservation(
        source_code=source_code,
        source_type="objective_structured",
        entity_type="match",
        entity_source_id=match_id,
        entity_identity_hints={
            "match_external_id": match_id,
            "home_team_external_id": "home-1",
            "home_team_name": "Home FC",
            "away_team_external_id": "away-1",
            "away_team_name": "Away FC",
            "competition_external_id": _competition_external_id(source_code),
            "season_label": SEASON_LABEL,
            "kickoff_date": kickoff_date,
        },
        metric_name=metric_name,
        value=value,  # type: ignore[arg-type]
        observed_at=_NOW,
        source_timestamp=_NOW,
        source_reference="test",
        ingestion_run_id=None,
        semantic_version=semantic_version or _semantic_version(source_code),
        metric_granularity="match",
    )


def _team_match_obs(
    *,
    source_code: str,
    match_id: str,
    team_id: str,
    team_name: str,
    metric_name: str,
    value: object,
    semantic_version: str | None = None,
) -> NormalizedObservation:
    return NormalizedObservation(
        source_code=source_code,
        source_type="objective_structured",
        entity_type="team",
        entity_source_id=f"{match_id}:{team_id}",
        entity_identity_hints={
            "match_external_id": match_id,
            "team_external_id": team_id,
            "team_name": team_name,
        },
        metric_name=metric_name,
        value=value,  # type: ignore[arg-type]
        observed_at=_NOW,
        source_timestamp=_NOW,
        source_reference="test",
        ingestion_run_id=None,
        semantic_version=semantic_version or _semantic_version(source_code),
        metric_granularity="team_match",
    )


def _player_obs(
    *,
    source_code: str,
    match_id: str,
    team_id: str,
    player_id: str,
    player_name: str,
    metric_name: str,
    value: object,
    metric_granularity: str = "player_match",
    semantic_version: str | None = None,
) -> NormalizedObservation:
    return NormalizedObservation(
        source_code=source_code,
        source_type="objective_structured",
        entity_type="player",
        entity_source_id=f"{match_id}:{player_id}",
        entity_identity_hints={
            "match_external_id": match_id,
            "team_external_id": team_id,
            "player_external_id": player_id,
            "player_name": player_name,
        },
        metric_name=metric_name,
        value=value,  # type: ignore[arg-type]
        observed_at=_NOW,
        source_timestamp=_NOW,
        source_reference="test",
        ingestion_run_id=None,
        semantic_version=semantic_version or _semantic_version(source_code),
        metric_granularity=metric_granularity,  # type: ignore[arg-type]
    )


def _crosswalk_with_one_player(
    *, wyscout_player_id: str, statsbomb_player_id: str, team_key: str, match_key: str
) -> PlayerCrosswalk:
    crosswalk = PlayerCrosswalk()
    canonical_key = f"overlap-player-v2:{COMPETITION_CODE}:{SEASON_LABEL}:test-pair"
    evidence = (
        PlayerTeamContextEvidence(team_context_key=team_key, shared_match_keys=(match_key,)),
    )
    crosswalk.add(
        PlayerCrosswalkEntry(
            source_code=WYSCOUT,
            provider_player_id=wyscout_player_id,
            canonical_player_key=canonical_key,
            normalized_name_used="test player",
            team_context_evidence=evidence,
        )
    )
    crosswalk.add(
        PlayerCrosswalkEntry(
            source_code=STATSBOMB,
            provider_player_id=statsbomb_player_id,
            canonical_player_key=canonical_key,
            normalized_name_used="test player",
            team_context_evidence=evidence,
        )
    )
    return crosswalk


def _match_key(match_id_suffix: str = "2018-01-28") -> str:
    return (
        f"match:{COMPETITION_CODE}:{SEASON_LABEL}:{HOME_TEAM_KEY}:{AWAY_TEAM_KEY}:{match_id_suffix}"
    )


def test_one_source_produces_single_source_regardless_of_policy() -> None:
    """`touches`/player_match has NO reviewed policy for this pair (it is
    empirically SEMANTICALLY_NONCOMPARABLE), but a single-source group must
    still produce real single_source audit evidence -- pairwise
    comparability is never consulted when no cross-source comparison is
    being attempted. Team-level `touches` needs no crosswalk (team identity
    resolves directly); player-level needs a crosswalk entry even for a
    lone source, since player identity itself depends on it."""

    match_key = _match_key("2018-01-28")
    crosswalk = PlayerCrosswalk()
    crosswalk.add(
        PlayerCrosswalkEntry(
            source_code=WYSCOUT,
            provider_player_id="p1",
            canonical_player_key=f"overlap-player-v2:{COMPETITION_CODE}:{SEASON_LABEL}:solo-test",
            normalized_name_used="player one",
            team_context_evidence=(
                PlayerTeamContextEvidence(
                    team_context_key=HOME_TEAM_KEY, shared_match_keys=(match_key,)
                ),
            ),
        )
    )

    observations = [
        _match_obs(
            source_code=WYSCOUT,
            match_id="m1",
            kickoff_date="2018-01-28",
            metric_name="home_score",
            value=2,
        ),
        _team_match_obs(
            source_code=WYSCOUT,
            match_id="m1",
            team_id="home-1",
            team_name="Home FC",
            metric_name="touches",
            value=99,
        ),
        _player_obs(
            source_code=WYSCOUT,
            match_id="m1",
            team_id="home-1",
            player_id="p1",
            player_name="Player One",
            metric_name="touches",
            value=42,
        ),
    ]
    decisions, meta = resolve_and_reconcile_v2(
        observations, competition_code=COMPETITION_CODE, crosswalk=crosswalk
    )

    team_decisions = [
        d for d in decisions if d.metric_name == "touches" and d.entity_type == "team"
    ]
    player_decisions = [
        d for d in decisions if d.metric_name == "touches" and d.entity_type == "player"
    ]
    assert len(team_decisions) == 1
    assert len(player_decisions) == 1
    for decision in (*team_decisions, *player_decisions):
        assert decision.status == "single_source"
        assert decision.source_count == 1
        assert decision.model_version == MODEL_VERSION_V2
    assert player_decisions[0].metric_granularity == "player_match"
    assert meta["missing_metric_granularity_count"] == 0


def test_two_sources_exact_policy_produces_real_agreed_decision() -> None:
    observations = [
        _match_obs(
            source_code=WYSCOUT,
            match_id="mw",
            kickoff_date="2018-01-28",
            metric_name="home_score",
            value=2,
        ),
        _match_obs(
            source_code=STATSBOMB,
            match_id="ms",
            kickoff_date="2018-01-28",
            metric_name="home_score",
            value=2,
        ),
    ]
    decisions, _meta = resolve_and_reconcile_v2(
        observations, competition_code=COMPETITION_CODE, crosswalk=PlayerCrosswalk()
    )
    home_score = [d for d in decisions if d.metric_name == "home_score"]
    assert len(home_score) == 1
    assert home_score[0].status == "agreed"
    assert home_score[0].candidate_value == 2
    assert home_score[0].source_count == 2
    assert home_score[0].metric_granularity == "match"
    assert set(home_score[0].participating_sources) == {WYSCOUT, STATSBOMB}


def test_two_sources_exact_policy_disagreement_produces_real_conflict() -> None:
    observations = [
        _match_obs(
            source_code=WYSCOUT,
            match_id="mw",
            kickoff_date="2018-01-28",
            metric_name="home_score",
            value=2,
        ),
        _match_obs(
            source_code=STATSBOMB,
            match_id="ms",
            kickoff_date="2018-01-28",
            metric_name="home_score",
            value=3,
        ),
    ]
    decisions, _meta = resolve_and_reconcile_v2(
        observations, competition_code=COMPETITION_CODE, crosswalk=PlayerCrosswalk()
    )
    home_score = [d for d in decisions if d.metric_name == "home_score"][0]
    assert home_score.status == "conflict"
    assert home_score.candidate_value is None


def test_two_sources_explicit_not_comparable_policy_never_compares_values() -> None:
    observations = [
        _match_obs(
            source_code=WYSCOUT,
            match_id="mw",
            kickoff_date="2018-01-28",
            metric_name="home_score",
            value=2,
        ),
        _match_obs(
            source_code=STATSBOMB,
            match_id="ms",
            kickoff_date="2018-01-28",
            metric_name="home_score",
            value=2,
        ),
        _team_match_obs(
            source_code=WYSCOUT,
            match_id="mw",
            team_id="home-1",
            team_name="Home FC",
            metric_name="passes_total",
            value=253,
        ),
        _team_match_obs(
            source_code=STATSBOMB,
            match_id="ms",
            team_id="home-1",
            team_name="Home FC",
            metric_name="passes_total",
            value=291,
        ),
    ]
    decisions, _meta = resolve_and_reconcile_v2(
        observations, competition_code=COMPETITION_CODE, crosswalk=PlayerCrosswalk()
    )
    decision = [d for d in decisions if d.metric_name == "passes_total"][0]
    assert decision.status == "not_comparable"
    assert decision.candidate_value is None
    assert decision.evidence["values_by_source"] == {WYSCOUT: 253, STATSBOMB: 291}
    assert decision.evidence["policy_explicitly_matched"] is True
    assert decision.evidence["policy_comparison_mode"] == "not_comparable"


def test_two_sources_with_no_reviewed_policy_is_methodology_pending() -> None:
    """`assists` had high but non-100% empirical agreement in the real
    audit -- explicitly deferred to 20D.5, so it must have NO exact/
    not_comparable entry and therefore fail closed to methodology_pending,
    never silently agree/conflict."""

    match_key = _match_key("2018-01-28")
    crosswalk = _crosswalk_with_one_player(
        wyscout_player_id="p1",
        statsbomb_player_id="p9",
        team_key=HOME_TEAM_KEY,
        match_key=match_key,
    )
    observations = [
        _match_obs(
            source_code=WYSCOUT,
            match_id="mw",
            kickoff_date="2018-01-28",
            metric_name="home_score",
            value=2,
        ),
        _match_obs(
            source_code=STATSBOMB,
            match_id="ms",
            kickoff_date="2018-01-28",
            metric_name="home_score",
            value=2,
        ),
        _player_obs(
            source_code=WYSCOUT,
            match_id="mw",
            team_id="home-1",
            player_id="p1",
            player_name="Player One",
            metric_name="assists",
            value=1,
        ),
        _player_obs(
            source_code=STATSBOMB,
            match_id="ms",
            team_id="home-1",
            player_id="p9",
            player_name="Player One",
            metric_name="assists",
            value=1,
        ),
    ]
    decisions, _meta = resolve_and_reconcile_v2(
        observations, competition_code=COMPETITION_CODE, crosswalk=crosswalk
    )
    decision = [d for d in decisions if d.metric_name == "assists"][0]
    assert decision.status == "methodology_pending"
    assert decision.candidate_value is None
    assert decision.evidence["policy_explicitly_matched"] is False


def test_missing_player_crosswalk_entry_leaves_player_unresolved() -> None:
    observations = [
        _player_obs(
            source_code=WYSCOUT,
            match_id="m1",
            team_id="home-1",
            player_id="p1",
            player_name="Player One",
            metric_name="goals",
            value=1,
        ),
    ]
    decisions, meta = resolve_and_reconcile_v2(
        observations, competition_code=COMPETITION_CODE, crosswalk=PlayerCrosswalk()
    )
    goals_decisions = [d for d in decisions if d.metric_name == "goals"]
    assert goals_decisions == []
    assert meta["unresolved_observation_count"] == 1


def test_more_than_two_sources_is_methodology_pending_unconditionally() -> None:
    observations = [
        _match_obs(
            source_code=WYSCOUT,
            match_id="mw",
            kickoff_date="2018-01-28",
            metric_name="home_score",
            value=2,
        ),
        _match_obs(
            source_code=STATSBOMB,
            match_id="ms",
            kickoff_date="2018-01-28",
            metric_name="home_score",
            value=2,
        ),
        _match_obs(
            source_code="football-data-uk",
            match_id="mf",
            kickoff_date="2018-01-28",
            metric_name="home_score",
            value=2,
            semantic_version="football-data-uk-v1",
        ),
    ]
    decisions, _meta = resolve_and_reconcile_v2(
        observations, competition_code=COMPETITION_CODE, crosswalk=PlayerCrosswalk()
    )
    decision = [d for d in decisions if d.metric_name == "home_score"][0]
    # Even though wyscout-open x statsbomb-open alone would be an exact
    # policy match, a third source present in the SAME group must never be
    # silently dropped to fall back to a 2-source comparison -- >2 sources
    # fails closed unconditionally, per Block 20D.4's explicit scope.
    assert decision.status == "methodology_pending"
    assert decision.candidate_value is None
    assert decision.source_count == 3


def test_inconsistent_semantic_version_within_one_source_fails_closed() -> None:
    observations = [
        _match_obs(
            source_code=WYSCOUT,
            match_id="mw",
            kickoff_date="2018-01-28",
            metric_name="home_score",
            value=2,
            semantic_version="wyscout-open-v0.1",
        ),
        _match_obs(
            source_code=WYSCOUT,
            match_id="mw",
            kickoff_date="2018-01-28",
            metric_name="home_score",
            value=2,
            semantic_version="wyscout-open-v0.2",
        ),
        _match_obs(
            source_code=STATSBOMB,
            match_id="ms",
            kickoff_date="2018-01-28",
            metric_name="home_score",
            value=2,
        ),
    ]
    decisions, _meta = resolve_and_reconcile_v2(
        observations, competition_code=COMPETITION_CODE, crosswalk=PlayerCrosswalk()
    )
    decision = [d for d in decisions if d.metric_name == "home_score"][0]
    assert decision.status == "methodology_pending"
    assert "inconsistent semantic_version" in str(decision.evidence["reason"])


def test_saves_player_match_and_goalkeeper_match_never_share_a_decision() -> None:
    match_key = _match_key("2018-01-28")
    crosswalk = PlayerCrosswalk()
    crosswalk.add(
        PlayerCrosswalkEntry(
            source_code=WYSCOUT,
            provider_player_id="p1",
            canonical_player_key=f"overlap-player-v2:{COMPETITION_CODE}:{SEASON_LABEL}:keeper-test",
            normalized_name_used="keeper",
            team_context_evidence=(
                PlayerTeamContextEvidence(
                    team_context_key=HOME_TEAM_KEY, shared_match_keys=(match_key,)
                ),
            ),
        )
    )
    observations = [
        _match_obs(
            source_code=WYSCOUT,
            match_id="m1",
            kickoff_date="2018-01-28",
            metric_name="home_score",
            value=2,
        ),
        _player_obs(
            source_code=WYSCOUT,
            match_id="m1",
            team_id="home-1",
            player_id="p1",
            player_name="Keeper",
            metric_name="saves",
            value=4,
            metric_granularity="player_match",
        ),
        _player_obs(
            source_code=WYSCOUT,
            match_id="m1",
            team_id="home-1",
            player_id="p1",
            player_name="Keeper",
            metric_name="saves",
            value=4,
            metric_granularity="goalkeeper_match",
        ),
    ]
    decisions, _meta = resolve_and_reconcile_v2(
        observations, competition_code=COMPETITION_CODE, crosswalk=crosswalk
    )
    saves_decisions = [d for d in decisions if d.metric_name == "saves"]
    assert len(saves_decisions) == 2
    granularities = {d.metric_granularity for d in saves_decisions}
    assert granularities == {"player_match", "goalkeeper_match"}
    assert saves_decisions[0].logical_entity_key != saves_decisions[1].logical_entity_key


def test_missing_metric_granularity_is_a_diagnostic_never_silently_legacy() -> None:
    observation = _match_obs(
        source_code=WYSCOUT,
        match_id="mw",
        kickoff_date="2018-01-28",
        metric_name="home_score",
        value=2,
    )
    object.__setattr__(observation, "metric_granularity", None)

    decisions, meta = resolve_and_reconcile_v2(
        [observation], competition_code=COMPETITION_CODE, crosswalk=PlayerCrosswalk()
    )
    assert decisions == []
    assert meta["missing_metric_granularity_count"] == 1


def test_bounded_date_clustering_converges_adjacent_dates_into_one_match() -> None:
    """Two providers report the same real fixture one day apart -- must
    converge on one canonical match (source_count == 2), reusing the
    existing bounded `cluster_match_dates()` primitive, not a new one."""

    observations = [
        _match_obs(
            source_code=WYSCOUT,
            match_id="mw",
            kickoff_date="2018-01-28",
            metric_name="home_score",
            value=2,
        ),
        _match_obs(
            source_code=STATSBOMB,
            match_id="ms",
            kickoff_date="2018-01-29",
            metric_name="home_score",
            value=2,
        ),
    ]
    decisions, _meta = resolve_and_reconcile_v2(
        observations, competition_code=COMPETITION_CODE, crosswalk=PlayerCrosswalk()
    )
    home_score_decisions = [d for d in decisions if d.metric_name == "home_score"]
    assert len(home_score_decisions) == 1
    assert home_score_decisions[0].source_count == 2
    assert home_score_decisions[0].status == "agreed"


def test_dates_outside_tolerance_remain_distinct_matches() -> None:
    observations = [
        _match_obs(
            source_code=WYSCOUT,
            match_id="mw",
            kickoff_date="2018-01-28",
            metric_name="home_score",
            value=2,
        ),
        _match_obs(
            source_code=STATSBOMB,
            match_id="ms",
            kickoff_date="2018-02-05",
            metric_name="home_score",
            value=2,
        ),
    ]
    decisions, _meta = resolve_and_reconcile_v2(
        observations, competition_code=COMPETITION_CODE, crosswalk=PlayerCrosswalk()
    )
    home_score_decisions = [d for d in decisions if d.metric_name == "home_score"]
    assert len(home_score_decisions) == 2
    assert all(d.status == "single_source" for d in home_score_decisions)
