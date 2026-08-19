"""Source-compliance guardrails (Block 18 / AGENTS.md section 5).

Unknown permission is never certification, and a provider whose terms
prohibit automated collection (Fantasy Premier League) or whose provenance
cannot be verified (scraping, unofficial/private endpoints) must never be
registered as a selectable product provider or leave a committed artifact
under `data/real/`.
"""

from __future__ import annotations

import json
from pathlib import Path

from football_intelligence.coverage_lab.provider_capabilities import PROVIDER_CAPABILITIES
from football_intelligence.data_mesh.entity_resolution import COMPETITION_MAPPINGS

_REPO_ROOT = Path(__file__).resolve().parents[2]

# Every provider ever reviewed and approved (see docs/REAL_DATA_SOURCE_AUDIT_V2.md
# and docs/SOURCES.md) for automated, zero-cost, documented/official
# acquisition. This is a closed allowlist, not a pattern -- a new provider
# must be added here deliberately, after review, never implicitly.
_APPROVED_PROVIDER_CODES = frozenset(
    {
        "thesportsdb",
        "openligadb",
        "football-data-org",
        "football-data-uk",
        "statsbomb-open",
        "openfootball",
        # Wyscout Open Data (Block 20B): certified Data Mesh adapter since
        # Block 20B.2b (411,844 real NormalizedObservation rows, same
        # evidentiary bar as statsbomb-open, CC BY 4.0 -- less restrictive
        # than StatsBomb's internal_only terms). Never added to this
        # allowlist at the time; added in Block 20D.2 when
        # entity_resolution.COMPETITION_MAPPINGS first referenced it.
        "wyscout-open",
    }
)

# Explicitly rejected during source review (AGENTS.md section 5 / Block 18
# task section 5): scraping, unofficial/private endpoints, or terms that
# prohibit automated collection.
_PROHIBITED_PROVIDER_CODES = frozenset(
    {
        "fpl",
        "fantasy-premier-league",
        "fbref",
        "sports-reference",
        "sofascore",
        "fotmob",
        "espn-hidden",
        "understat",
        "transfermarkt",
        "bundesliga-scrape",
        "api-football",
    }
)


def test_only_approved_providers_are_registered_in_provider_capabilities() -> None:
    codes = {capability.provider_code for capability in PROVIDER_CAPABILITIES}
    assert codes <= _APPROVED_PROVIDER_CODES
    assert codes.isdisjoint(_PROHIBITED_PROVIDER_CODES)


def test_only_approved_providers_are_registered_in_competition_mappings() -> None:
    codes = {mapping.source_code for mapping in COMPETITION_MAPPINGS}
    assert codes <= _APPROVED_PROVIDER_CODES
    assert codes.isdisjoint(_PROHIBITED_PROVIDER_CODES)


def test_no_prohibited_source_is_declared_in_any_committed_real_data_file() -> None:
    real_dir = _REPO_ROOT / "data" / "real"
    checked = 0
    for path in real_dir.rglob("*.json"):
        payload = json.loads(path.read_text(encoding="utf-8"))
        provenance = payload.get("provenance")
        if provenance is None or "source" not in provenance:
            continue
        checked += 1
        assert provenance["source"] in _APPROVED_PROVIDER_CODES, (
            f"{path} declares an unapproved/unreviewed source: {provenance['source']!r}"
        )
        assert provenance["source"] not in _PROHIBITED_PROVIDER_CODES
    assert checked >= 2  # football-data-uk + openfootball, at minimum


def test_no_fantasy_premier_league_artifacts_are_committed() -> None:
    real_dir = _REPO_ROOT / "data" / "real"
    for path in real_dir.rglob("*"):
        if path.is_file():
            assert "fpl" not in path.name.lower()
            assert "fantasy" not in path.name.lower()
