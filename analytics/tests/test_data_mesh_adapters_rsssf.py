from __future__ import annotations

from datetime import UTC, date, datetime

from football_intelligence.data_mesh.adapters.rsssf import adapt_argentina_2016_snapshot
from football_intelligence.providers.rsssf import RSSSFArgentina2016Snapshot, RSSSFMatch


def _snapshot(match: RSSSFMatch) -> RSSSFArgentina2016Snapshot:
    return RSSSFArgentina2016Snapshot(
        source_url="https://www.rsssf.org/tablesa/arg2016.html",
        fetched_at=datetime(2026, 8, 27, 15, 0, tzinfo=UTC),
        content_type="text/html; charset=windows-1252",
        decoded_charset="windows-1252",
        raw_bytes=b"fixture",
        matches=(match,),
    )


def test_adapter_emits_only_team_identity_and_five_match_metrics() -> None:
    match = RSSSFMatch(
        external_id="rsssf-arg2016-test",
        match_date=date(2016, 2, 5),
        round_number=1,
        phase="regular_group_1",
        subgroup="Group 1",
        home_team="Club Atlético Banfield Soc. Civ.",
        away_team="C. de Gimnasia y Esgrima La Plata",
        home_score=2,
        away_score=0,
        venue="Florencio Sola, Banfield, B",
        source_line="fixture",
    )

    observations = adapt_argentina_2016_snapshot(_snapshot(match), ingestion_run_id=None)

    assert len(observations) == 7
    assert sum(observation.entity_type == "team" for observation in observations) == 2
    match_observations = [observation for observation in observations if observation.entity_type == "match"]
    assert {observation.metric_name for observation in match_observations} == {
        "status",
        "round_name",
        "venue_name",
        "home_score",
        "away_score",
    }
    assert all(observation.metric_granularity == "match" for observation in match_observations)
    assert all(observation.metric_name != "kickoff_at" for observation in observations)
    assert all(observation.entity_type != "player" for observation in observations)


def test_match_identity_hints_preserve_date_without_fabricating_kickoff_time() -> None:
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

    observations = adapt_argentina_2016_snapshot(_snapshot(match), ingestion_run_id=42)
    status = next(observation for observation in observations if observation.metric_name == "status")
    round_name = next(
        observation for observation in observations if observation.metric_name == "round_name"
    )

    assert status.entity_identity_hints["competition_external_id"] == "arg2016.html"
    assert status.entity_identity_hints["season_label"] == "2016"
    assert status.entity_identity_hints["kickoff_date"] == "2016-05-29"
    assert "kickoff_at" not in status.entity_identity_hints
    assert round_name.value == "Round 17 — Final"
    assert status.ingestion_run_id == 42


def test_adapter_preserves_source_scope_and_provenance_on_every_observation() -> None:
    match = RSSSFMatch(
        external_id="rsssf-arg2016-third",
        match_date=date(2016, 5, 28),
        round_number=17,
        phase="third_place_playoff",
        subgroup=None,
        home_team="C. Dep. Godoy Cruz Antonio Tomba",
        away_team="Club Estudiantes de La Plata",
        home_score=0,
        away_score=1,
        venue="Mario Alberto Kempes, Córdoba, X",
        source_line="fixture",
    )

    observations = adapt_argentina_2016_snapshot(_snapshot(match), ingestion_run_id=None)

    for observation in observations:
        assert observation.source_code == "rsssf"
        assert observation.source_type == "objective_web"
        assert observation.semantic_version == "rsssf-arg-2016-v1"
        assert observation.source_reference == "https://www.rsssf.org/tablesa/arg2016.html"
        assert observation.observed_at == datetime(2026, 8, 27, 15, 0, tzinfo=UTC)

    round_name = next(
        observation for observation in observations if observation.metric_name == "round_name"
    )
    assert round_name.value == "Round 17 — Third Position"
