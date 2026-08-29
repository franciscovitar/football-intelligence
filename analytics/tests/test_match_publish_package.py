from __future__ import annotations

from copy import deepcopy

import pytest

from football_intelligence.publishing.package import (
    MatchPublishPackageError,
    PackageNotPublishableError,
    match_publish_package_digest,
    require_publishable_package,
    validate_match_publish_package,
)


def valid_publish_payload() -> dict[str, object]:
    review_base = {
        "review_version": 1,
        "facts_score": 7.0,
        "expert_score": None,
        "fan_score": None,
        "final_score": 7.0,
        "confidence": 72,
        "evidence_status": "DATA_ESTIMATE",
        "summary": "Una actuación positiva respaldada por el proceso observado.",
        "evidence_mix": {"facts": "direct"},
    }
    return {
        "contract_version": "MATCH_RESEARCH_PUBLISH_V1",
        "research": {
            "run_key": "test-run-0001",
            "methodology_sha": "abcdef123456",
            "search_protocol_version": "SEARCH_PROTOCOL_V2",
            "output_contract_version": "OUTPUT_CONTRACT_V2",
            "rating_scale_version": "MATCH_RATING_SCALE_V1",
            "benchmark_version": "MATCH_BENCHMARKS_V1.0",
            "data_cutoff": "2026-08-29T12:00:00+00:00",
            "qa_status": "PASS",
            "notes": "integration fixture",
        },
        "match": {
            "identity_key": "test-league:2026-27:2026-08-29:alpha:beta",
            "competition_slug": "test-league",
            "season_label": "2026/27",
            "stage_name": None,
            "round_label": "Round 1",
            "home_team_slug": "alpha-fc",
            "away_team_slug": "beta-fc",
            "kickoff_at": "2026-08-29T15:00:00+00:00",
            "status": "FINAL",
            "home_goals": 2,
            "away_goals": 1,
            "venue": "Test Ground",
            "attendance": 10000,
            "referee": "Test Referee",
            "identity_verified": True,
            "context": {"venue_state": "home"},
        },
        "teams": [
            {
                "slug": "alpha-fc",
                "name": "Alpha FC",
                "short_name": "Alpha",
                "country_code": "AR",
                "crest_url": None,
            },
            {
                "slug": "beta-fc",
                "name": "Beta FC",
                "short_name": "Beta",
                "country_code": "AR",
                "crest_url": None,
            },
        ],
        "managers": [
            {
                "slug": "alpha-coach",
                "display_name": "Alpha Coach",
                "team_slug": "alpha-fc",
                "nationality": "AR",
            },
            {
                "slug": "beta-coach",
                "display_name": "Beta Coach",
                "team_slug": "beta-fc",
                "nationality": "AR",
            },
        ],
        "players": [
            {
                "slug": "alpha-player",
                "display_name": "Alpha Player",
                "full_name": "Alpha Player",
                "team_slug": "alpha-fc",
                "birth_date": "2000-01-01",
                "nationality": "AR",
                "preferred_foot": "right",
            },
            {
                "slug": "beta-player",
                "display_name": "Beta Player",
                "full_name": "Beta Player",
                "team_slug": "beta-fc",
                "birth_date": "2001-01-01",
                "nationality": "AR",
                "preferred_foot": "left",
            },
        ],
        "appearances": [
            {
                "player_slug": "alpha-player",
                "team_slug": "alpha-fc",
                "starter": True,
                "minute_on": 0,
                "minute_off": 90,
                "minutes": 90,
                "broad_position": "MF",
                "role_label": "central midfielder",
                "role_confidence": 90,
                "captain": False,
            },
            {
                "player_slug": "beta-player",
                "team_slug": "beta-fc",
                "starter": True,
                "minute_on": 0,
                "minute_off": 90,
                "minutes": 90,
                "broad_position": "FW",
                "role_label": "striker",
                "role_confidence": 90,
                "captain": False,
            },
        ],
        "team_stats": [
            {
                "team_slug": "alpha-fc",
                "source_key": "provider",
                "provider_model": "test-xg",
                "definition_version": "v1",
                "evidence_class": "PROVIDER_DERIVED",
                "goals": 2,
                "xg": 1.8,
                "shots": 12,
                "shots_on_target": 5,
                "possession_pct": 55.0,
                "extra_stats": {"xA": 1.1},
                "coverage_notes": None,
            },
            {
                "team_slug": "beta-fc",
                "source_key": "provider",
                "provider_model": "test-xg",
                "definition_version": "v1",
                "evidence_class": "PROVIDER_DERIVED",
                "goals": 1,
                "xg": 0.9,
                "shots": 7,
                "shots_on_target": 2,
                "possession_pct": 45.0,
                "extra_stats": {},
                "coverage_notes": None,
            },
        ],
        "player_stats": [
            {
                "player_slug": "alpha-player",
                "team_slug": "alpha-fc",
                "source_key": "provider",
                "provider_model": "test-player",
                "definition_version": "v1",
                "evidence_class": "PROVIDER_DERIVED",
                "minutes": 90,
                "goals": 0,
                "assists": 1,
                "xg": 0.2,
                "xa": 0.6,
                "shots": 1,
                "shots_on_target": 1,
                "chances_created": 4,
                "touches": 70,
                "dribbles_attempted": 2,
                "dribbles_completed": 1,
                "extra_stats": {"provider_rating": 7.4},
                "coverage_notes": None,
            },
            {
                "player_slug": "beta-player",
                "team_slug": "beta-fc",
                "source_key": "provider",
                "provider_model": "test-player",
                "definition_version": "v1",
                "evidence_class": "PROVIDER_DERIVED",
                "minutes": 90,
                "goals": 1,
                "assists": 0,
                "xg": 0.7,
                "xa": 0.0,
                "shots": 3,
                "shots_on_target": 1,
                "chances_created": 0,
                "touches": 35,
                "dribbles_attempted": 1,
                "dribbles_completed": 0,
                "extra_stats": {},
                "coverage_notes": None,
            },
        ],
        "sources": [
            {
                "key": "provider",
                "name": "Test Provider",
                "source_type": "STRUCTURED_PROVIDER",
                "domain": "example.com",
                "base_url": "https://example.com/",
                "rights_notes": "test fixture",
            }
        ],
        "documents": [
            {
                "key": "match-page",
                "source_key": "provider",
                "url": "https://example.com/matches/alpha-beta#details",
                "title": "Alpha 2-1 Beta",
                "author": None,
                "published_at": "2026-08-29T18:00:00+00:00",
                "retrieved_at": "2026-08-29T18:05:00+00:00",
                "document_type": "MATCH_PAGE",
            }
        ],
        "evidence": [
            {
                "document_key": "match-page",
                "entity_type": "MATCH",
                "entity_key": "test-league:2026-27:2026-08-29:alpha:beta",
                "channel": "FACT",
                "domain": "result",
                "evidence_class": "OBSERVED",
                "claim_type": "FINAL_SCORE",
                "normalized_claim": "Alpha FC won 2-1 against Beta FC.",
                "direction": "POSITIVE",
                "confidence": 100,
            }
        ],
        "fan_themes": [],
        "match_review": {
            "review_version": 1,
            "summary": "Alpha produjo la actuación más completa y ganó un partido que también dominó en ocasiones.",
            "key_takeaways": ["Alpha generó mejores ocasiones."],
            "source_document_keys": ["match-page"],
        },
        "team_reviews": [
            {
                **review_base,
                "team_slug": "alpha-fc",
                "facts_coverage": 80,
                "expert_coverage": 0,
                "fan_coverage": 0,
                "tactical_coverage": 50,
                "attack_score": 7.5,
                "creation_score": 7.5,
                "control_score": 7.0,
                "defence_score": 6.5,
                "pressing_score": None,
                "offensive_transition_score": 7.0,
                "defensive_transition_score": 6.5,
                "set_pieces_score": None,
                "strengths": ["Mejor generación de ocasiones."],
                "concerns": [],
            },
            {
                **review_base,
                "team_slug": "beta-fc",
                "facts_score": 5.8,
                "final_score": 5.8,
                "summary": "Beta compitió, pero concedió más y generó menos volumen útil.",
                "facts_coverage": 80,
                "expert_coverage": 0,
                "fan_coverage": 0,
                "tactical_coverage": 50,
                "attack_score": 5.8,
                "creation_score": 5.5,
                "control_score": 5.5,
                "defence_score": 5.8,
                "pressing_score": None,
                "offensive_transition_score": 6.0,
                "defensive_transition_score": 5.5,
                "set_pieces_score": None,
                "strengths": [],
                "concerns": ["Menor calidad de ocasiones."],
            },
        ],
        "manager_reviews": [
            {
                **review_base,
                "manager_slug": "alpha-coach",
                "team_slug": "alpha-fc",
                "initial_plan_score": 7.0,
                "adaptation_score": 7.0,
                "substitutions_score": 6.5,
                "initial_plan": "Controlar el centro y progresar con paciencia.",
                "adjustments": None,
                "what_worked": ["Control territorial."],
                "what_failed": [],
            },
            {
                **review_base,
                "manager_slug": "beta-coach",
                "team_slug": "beta-fc",
                "facts_score": 5.8,
                "final_score": 5.8,
                "summary": "El plan sostuvo el partido por momentos, pero no redujo suficiente la amenaza rival.",
                "initial_plan_score": 6.0,
                "adaptation_score": 5.8,
                "substitutions_score": 6.0,
                "initial_plan": "Defender compacto y salir rápido.",
                "adjustments": None,
                "what_worked": ["Amenaza puntual en transición."],
                "what_failed": ["Concedió demasiado volumen."],
            },
        ],
        "player_reviews": [
            {
                **review_base,
                "player_slug": "alpha-player",
                "team_slug": "alpha-fc",
                "facts_coverage": 85,
                "expert_coverage": 0,
                "fan_coverage": 0,
                "tactical_coverage": 40,
                "role_label": "central midfielder",
                "positive_notes": ["Creó cuatro ocasiones."],
                "negative_notes": [],
            },
            {
                **review_base,
                "player_slug": "beta-player",
                "team_slug": "beta-fc",
                "facts_score": 6.8,
                "final_score": 6.8,
                "summary": "Marcó y sostuvo amenaza de área, con poco volumen adicional.",
                "facts_coverage": 85,
                "expert_coverage": 0,
                "fan_coverage": 0,
                "tactical_coverage": 40,
                "role_label": "striker",
                "positive_notes": ["Convirtió una ocasión relevante."],
                "negative_notes": ["Participación limitada fuera del área."],
            },
        ],
        "signals": [],
    }


def test_valid_package_passes_schema_and_reference_validation() -> None:
    payload = valid_publish_payload()
    validate_match_publish_package(payload)
    require_publishable_package(payload)


def test_unknown_top_level_property_is_rejected() -> None:
    payload = valid_publish_payload()
    payload["unexpected"] = True
    with pytest.raises(MatchPublishPackageError, match="unexpected property"):
        validate_match_publish_package(payload)


def test_broken_cross_reference_is_rejected() -> None:
    payload = valid_publish_payload()
    payload["appearances"][0]["team_slug"] = "missing-team"  # type: ignore[index]
    with pytest.raises(MatchPublishPackageError, match="unknown reference"):
        validate_match_publish_package(payload)


def test_non_pass_qa_is_valid_but_not_publishable() -> None:
    payload = valid_publish_payload()
    payload["research"]["qa_status"] = "NEEDS_RESEARCH"  # type: ignore[index]
    validate_match_publish_package(payload)
    with pytest.raises(PackageNotPublishableError, match="qa_status"):
        require_publishable_package(payload)


def test_digest_is_stable_across_object_key_order() -> None:
    payload = valid_publish_payload()
    reordered = deepcopy(payload)
    reordered["research"] = dict(reversed(list(reordered["research"].items())))  # type: ignore[union-attr]
    assert match_publish_package_digest(payload) == match_publish_package_digest(reordered)


def test_public_review_versions_must_move_together() -> None:
    payload = valid_publish_payload()
    payload["player_reviews"][0]["review_version"] = 2  # type: ignore[index]
    with pytest.raises(MatchPublishPackageError, match="review_version"):
        validate_match_publish_package(payload)
