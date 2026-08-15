"""Structural invariants for the committed Block 18 snapshot manifest and the
second (OpenFootball) real evidence file it reconciles against
Football-Data.co.uk. Regenerate both with
`uv run football-intelligence-build-real-snapshot-v2`.
"""

from __future__ import annotations

import json
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_MANIFEST_PATH = _REPO_ROOT / "data" / "manifests" / "real" / "ENG_PL" / "2025-26.json"
_FOOTBALL_DATA_UK_PATH = _REPO_ROOT / "data" / "real" / "2025-26" / "eng_pl_matches.json"
_OPENFOOTBALL_PATH = _REPO_ROOT / "data" / "real" / "2025-26" / "eng_pl_matches_openfootball.json"


def _load_manifest() -> dict:
    return json.loads(_MANIFEST_PATH.read_text(encoding="utf-8"))


def _fingerprint_for(manifest: dict, provider: str) -> dict:
    return next(entry for entry in manifest["source_files"] if entry["provider"] == provider)


def test_manifest_identifies_snapshot_as_real_eng_pl_2025_26() -> None:
    manifest = _load_manifest()
    assert manifest["competition_code"] == "ENG_PL"
    assert manifest["season_label"] == "2025/26"
    assert manifest["data_context"] == "real"
    assert manifest["snapshot_id"]


def test_manifest_reports_full_real_team_and_match_population() -> None:
    manifest = _load_manifest()
    assert manifest["teams_resolved"] == 20
    assert manifest["matches_resolved"] == 380
    assert manifest["players_resolved"] == 0
    assert manifest["unresolved_entities"]["count"] == 0


def test_manifest_declares_latest_completed_period_role_not_current() -> None:
    # Blocker 1: ENG_PL 2025/26 is the latest COMPLETED season, never
    # reported as true current-period coverage.
    manifest = _load_manifest()
    assert manifest["period_role"] == "latest_completed"
    for provider_entry in manifest["providers_used"].values():
        assert provider_entry["period_acquired_this_run"] == "latest_completed"


def test_manifest_metric_coverage_denominator_matches_live_catalog() -> None:
    from football_intelligence.metric_catalog.catalog import METRIC_CATALOG_V2

    manifest = _load_manifest()
    coverage = manifest["metric_coverage"]
    assert coverage["catalog_identity_count"] == len(METRIC_CATALOG_V2)
    assert coverage["available_current_period_identity_count"] == 0
    assert coverage["available_recent_completed_identity_count"] > 0
    assert (
        coverage["available_current_period_identity_count"]
        + coverage["available_recent_completed_identity_count"]
        + coverage["unavailable_identity_count"]
        + coverage["historical_deep_only_identity_count"]
        == coverage["catalog_identity_count"]
    )


def test_manifest_never_claims_rich_player_data() -> None:
    manifest = _load_manifest()
    assert manifest["player_data"]["rich_player_source_found"] is False


def test_manifest_reconciliation_shows_real_cross_source_agreement() -> None:
    # Two independent real recent-completed-season sources agreeing on every
    # real match result (home_score/away_score/status for all 380 matches)
    # is the concrete evidence Block 18 set out to produce.
    manifest = _load_manifest()
    reconciliation = manifest["reconciliation"]
    assert reconciliation["agreed_count"] >= 1140  # 380 matches * 3 match-level facts
    assert reconciliation["overlap_count"] >= reconciliation["agreed_count"]


# ---------------------------------------------------------------------------
# Blocker 2: no database writes claimed in the committed manifest by default
# ---------------------------------------------------------------------------


def test_committed_manifest_shows_no_implicit_database_persistence() -> None:
    manifest = _load_manifest()
    assert manifest["audit_persistence"]["mode"] == "not_requested"
    assert manifest["canonical_database_state"]["mode"] == "not_requested"


# ---------------------------------------------------------------------------
# Blocker 3: source storage + provenance fingerprints
# ---------------------------------------------------------------------------


def test_football_data_uk_tracked_file_matches_accepted_block16_17_content() -> None:
    # The committed Football-Data.co.uk snapshot must be exactly the
    # already-accepted Block 16/17 evidence -- Block 18's corrective pass
    # must never silently create a new redistribution claim by rewriting it.
    payload = json.loads(_FOOTBALL_DATA_UK_PATH.read_text(encoding="utf-8"))
    assert payload["provenance"]["source"] == "football-data-uk"
    assert payload["provenance"]["redistribution_permission"] == "unknown"
    assert payload["provenance"]["certification_state"] == "not_certified"
    assert payload["provenance"]["record_count"] == 6460


def test_manifest_source_files_carry_full_fingerprints_for_both_providers() -> None:
    manifest = _load_manifest()
    fduk = _fingerprint_for(manifest, "football-data-uk")
    openfootball = _fingerprint_for(manifest, "openfootball")

    for fingerprint in (fduk, openfootball):
        assert len(fingerprint["sha256"]) == 64
        assert fingerprint["retrieved_at"]
        assert fingerprint["source_locator"].startswith("https://")
        assert fingerprint["collection_method"]
        assert fingerprint["competition_code"] == "ENG_PL"
        assert fingerprint["season_label"] == "2025/26"

    assert fduk["redistribution_permission"] == "unknown"
    assert fduk["certification_state"] == "not_certified"
    assert "not written by this job" in fduk["persisted_to"]

    assert openfootball["redistribution_permission"] == "public_domain_cc0"
    assert openfootball["certification_state"] == "certified"
    assert openfootball["persisted_to"] == "data/real/2025-26/eng_pl_matches_openfootball.json"


def test_openfootball_evidence_file_is_public_domain_and_match_scoped() -> None:
    payload = json.loads(_OPENFOOTBALL_PATH.read_text(encoding="utf-8"))
    assert payload["provenance"]["source"] == "openfootball"
    assert payload["provenance"]["redistribution_permission"] == "public_domain_cc0"
    assert payload["scope"]["player_coverage"] == "unavailable"
    assert payload["scope"]["entity_grains"] == ["match"]


def test_openfootball_evidence_covers_the_full_real_season() -> None:
    payload = json.loads(_OPENFOOTBALL_PATH.read_text(encoding="utf-8"))
    match_names = {
        record["value"]
        for record in payload["records"]
        if record["entity_type"] == "team" and record["metric_name"] == "name"
    }
    assert len(match_names) == 20
