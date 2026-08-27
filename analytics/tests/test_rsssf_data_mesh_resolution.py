from __future__ import annotations

from datetime import UTC, date, datetime

from football_intelligence.data_mesh.adapters.rsssf import adapt_argentina_2016_snapshot
from football_intelligence.data_mesh.entity_resolution import resolve_competition
from football_intelligence.data_mesh.pipeline import resolve_logical_key
from football_intelligence.providers.rsssf import RSSSFArgentina2016Snapshot, RSSSFMatch


def _final_observations():
    match = RSSSFMatch(
        external_id="rsssf-arg2016-final",
        match_date=date(2016, 5, 29),
        round_number=17,
        phase="final",
        subgroup="Final",
        home_team="Club Atl. San Lorenzo de Almagro",
        away_team="Club Atlético Lanús",
        home_score=0,
        away_score=4,
        venue="Monumental Antonio Vespucio Liberti, Belgrano, C",
        source_line="fixture",
    )
    snapshot = RSSSFArgentina2016Snapshot(
        source_url="https://www.rsssf.org/tablesa/arg2016.html",
        fetched_at=datetime(2026, 8, 27, 15, 0, tzinfo=UTC),
        content_type="text/html; charset=windows-1252",
        decoded_charset="windows-1252",
        raw_bytes=b"fixture",
        matches=(match,),
    )
    return adapt_argentina_2016_snapshot(snapshot, ingestion_run_id=None)


def test_rsssf_competition_mapping_is_explicit_and_bounded() -> None:
    resolution = resolve_competition(source_code="rsssf", external_id="arg2016.html")
    assert resolution.status == "resolved"
    assert resolution.logical_key == "competition:ARG_LPF"
    assert resolve_competition(source_code="rsssf", external_id="ARG_LPF").status == "unresolved"
    assert resolve_competition(source_code="rsssf", external_id="arg2017.html").status == "unresolved"


def test_rsssf_match_observation_resolves_from_date_only_identity_hints() -> None:
    observations = _final_observations()
    status = next(observation for observation in observations if observation.metric_name == "status")

    resolution = resolve_logical_key(
        status,
        match_date_clusters={},
    )

    assert resolution.status == "resolved"
    assert resolution.logical_key is not None
    assert resolution.logical_key.startswith("match:ARG_LPF:2016:")
    assert resolution.logical_key.endswith(":2016-05-29")


def test_rsssf_team_identity_resolves_through_the_shared_pipeline() -> None:
    observations = _final_observations()
    home_team = next(
        observation
        for observation in observations
        if observation.entity_type == "team"
        and observation.value == "Club Atl. San Lorenzo de Almagro"
    )

    resolution = resolve_logical_key(home_team, match_date_clusters={})

    assert resolution.status == "resolved"
    assert resolution.logical_key is not None
    assert resolution.logical_key.startswith("team:ARG_LPF:")
