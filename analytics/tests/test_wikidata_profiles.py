from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest

from football_intelligence.data_mesh.player_identity_candidates import (
    PlayerIdentityRecord,
    compare_player_identity_records,
)
from football_intelligence.ingestion.static_snapshot import (
    load_static_snapshot_manifest,
    verify_static_snapshot_files,
)
from football_intelligence.jobs import collect_wikidata_profiles
from football_intelligence.jobs.audit_wikidata_profiles import run_audit
from football_intelligence.jobs.collect_wikidata_profiles import WikidataCollectionError
from football_intelligence.providers.wikidata_profiles import (
    PROLEPTIC_GREGORIAN_QID,
    WikidataProfileError,
    WikidataTimeValue,
    parse_wikidata_entity_document,
)


def _calendar_uri(qid: str = PROLEPTIC_GREGORIAN_QID) -> str:
    return f"http://www.wikidata.org/entity/{qid}"


def _time_snak(raw_time: str, precision: int) -> dict[str, object]:
    return {
        "snaktype": "value",
        "datavalue": {
            "type": "time",
            "value": {
                "time": raw_time,
                "precision": precision,
                "calendarmodel": _calendar_uri(),
            },
        },
    }


def _item_snak(qid: str) -> dict[str, object]:
    return {
        "snaktype": "value",
        "datavalue": {
            "type": "wikibase-entityid",
            "value": {"entity-type": "item", "id": qid},
        },
    }


def _statement(
    mainsnak: dict[str, object],
    *,
    qualifiers: dict[str, list[dict[str, object]]] | None = None,
    rank: str = "normal",
) -> dict[str, object]:
    return {
        "rank": rank,
        "mainsnak": mainsnak,
        "qualifiers": qualifiers or {},
    }


def _document(
    qid: str,
    *,
    label: str = "Example Player",
    claims: dict[str, list[dict[str, object]]] | None = None,
) -> dict[str, object]:
    return {
        "entities": {
            qid: {
                "id": qid,
                "lastrevid": 123456,
                "modified": "2026-08-24T00:00:00Z",
                "labels": {"en": {"language": "en", "value": label}},
                "claims": claims or {},
            }
        }
    }


def test_year_precision_date_is_not_coerced_to_january_first() -> None:
    value = WikidataTimeValue(
        raw_time="+1992-01-01T00:00:00Z",
        precision=9,
        calendar_model_qid=PROLEPTIC_GREGORIAN_QID,
    )

    assert value.exact_date is None
    assert value.date_bounds == (date(1992, 1, 1), date(1992, 12, 31))


def test_day_precision_gregorian_date_is_exact() -> None:
    value = WikidataTimeValue(
        raw_time="+1992-06-15T00:00:00Z",
        precision=11,
        calendar_model_qid=PROLEPTIC_GREGORIAN_QID,
    )

    assert value.exact_date == date(1992, 6, 15)
    assert value.date_bounds == (date(1992, 6, 15), date(1992, 6, 15))


def test_profile_preserves_native_profile_qids_and_exact_date() -> None:
    profile = parse_wikidata_entity_document(
        _document(
            "Q100",
            label="Player One",
            claims={
                "P569": [_statement(_time_snak("+1992-06-15T00:00:00Z", 11))],
                "P27": [_statement(_item_snak("Q414"))],
                "P413": [_statement(_item_snak("Q280658"))],
            },
        ),
        expected_qid="Q100",
    )

    assert profile.display_name == "Player One"
    assert profile.exact_date_of_birth == date(1992, 6, 15)
    assert profile.citizenship_qids == ("Q414",)
    assert profile.position_qids == ("Q280658",)
    assert profile.last_revision_id == 123456


def test_conflicting_dob_claims_do_not_resolve_one_exact_date() -> None:
    profile = parse_wikidata_entity_document(
        _document(
            "Q101",
            claims={
                "P569": [
                    _statement(_time_snak("+1992-06-15T00:00:00Z", 11)),
                    _statement(_time_snak("+1993-01-01T00:00:00Z", 9)),
                ]
            },
        ),
        expected_qid="Q101",
    )

    assert profile.exact_date_of_birth is None


def test_deprecated_profile_claims_are_ignored() -> None:
    profile = parse_wikidata_entity_document(
        _document(
            "Q102",
            claims={
                "P27": [
                    _statement(_item_snak("Q414"), rank="deprecated"),
                    _statement(_item_snak("Q29")),
                ]
            },
        ),
        expected_qid="Q102",
    )

    assert profile.citizenship_qids == ("Q29",)


def test_bounded_team_membership_can_prove_season_context() -> None:
    profile = parse_wikidata_entity_document(
        _document(
            "Q103",
            claims={
                "P54": [
                    _statement(
                        _item_snak("Q200"),
                        qualifiers={
                            "P580": [_time_snak("+2017-07-01T00:00:00Z", 11)],
                            "P582": [_time_snak("+2018-06-30T00:00:00Z", 11)],
                        },
                    )
                ]
            },
        ),
        expected_qid="Q103",
    )

    assert profile.canonical_team_context_keys(
        season_start=date(2017, 8, 1),
        season_end=date(2018, 5, 31),
        team_qid_to_context={"Q200": "team:ENG_PL:liverpool"},
    ) == ("team:ENG_PL:liverpool",)


def test_unbounded_team_membership_is_not_used_as_season_identity_evidence() -> None:
    profile = parse_wikidata_entity_document(
        _document(
            "Q104",
            claims={"P54": [_statement(_item_snak("Q200"))]},
        ),
        expected_qid="Q104",
    )

    assert (
        profile.canonical_team_context_keys(
            season_start=date(2017, 8, 1),
            season_end=date(2018, 5, 31),
            team_qid_to_context={"Q200": "team:ENG_PL:liverpool"},
        )
        == ()
    )


def test_imprecise_membership_must_guarantee_overlap() -> None:
    profile = parse_wikidata_entity_document(
        _document(
            "Q105",
            claims={
                "P54": [
                    _statement(
                        _item_snak("Q200"),
                        qualifiers={
                            "P580": [_time_snak("+2017-01-01T00:00:00Z", 9)],
                            "P582": [_time_snak("+2018-01-01T00:00:00Z", 9)],
                        },
                    )
                ]
            },
        ),
        expected_qid="Q105",
    )

    membership = profile.team_memberships[0]
    assert membership.guarantees_overlap(
        season_start=date(2017, 8, 1), season_end=date(2018, 5, 31)
    )
    assert not membership.guarantees_overlap(
        season_start=date(2019, 8, 1), season_end=date(2020, 5, 31)
    )


def test_wikidata_profile_becomes_review_evidence_not_crosswalk_ready() -> None:
    profile = parse_wikidata_entity_document(
        _document(
            "Q106",
            label="Mohamed Salah",
            claims={
                "P569": [_statement(_time_snak("+1992-06-15T00:00:00Z", 11))],
                "P54": [
                    _statement(
                        _item_snak("Q200"),
                        qualifiers={
                            "P580": [_time_snak("+2017-07-01T00:00:00Z", 11)],
                            "P582": [_time_snak("+2025-06-30T00:00:00Z", 11)],
                        },
                    )
                ],
            },
        ),
        expected_qid="Q106",
    )
    wikidata = profile.to_player_identity_record(
        competition_code="ENG_PL",
        season_label="2017/18",
        season_start=date(2017, 8, 1),
        season_end=date(2018, 5, 31),
        team_qid_to_context={"Q200": "team:ENG_PL:liverpool"},
    )
    wyscout = PlayerIdentityRecord(
        source_code="wyscout-open",
        provider_player_id="120353",
        raw_name="Mohamed Salah",
        competition_code="ENG_PL",
        season_label="2017/18",
        team_context_keys=("team:ENG_PL:liverpool",),
        date_of_birth=date(1992, 6, 15),
    )

    candidate = compare_player_identity_records(wikidata, wyscout)

    assert wikidata.team_match_evidence == ()
    assert candidate.state == "review_required"
    assert "date_of_birth_match" in candidate.reasons
    assert "shared_team_context" in candidate.reasons
    assert "shared_team_specific_canonical_match" not in candidate.reasons


def test_missing_label_cannot_become_identity_record() -> None:
    payload = _document("Q107")
    entity = payload["entities"]["Q107"]  # type: ignore[index]
    entity["labels"] = {}  # type: ignore[index]
    profile = parse_wikidata_entity_document(payload, expected_qid="Q107")

    with pytest.raises(WikidataProfileError, match="no usable display label"):
        profile.to_player_identity_record(
            competition_code="ENG_PL",
            season_label="2017/18",
            season_start=date(2017, 8, 1),
            season_end=date(2018, 5, 31),
            team_qid_to_context={},
        )


def test_collector_is_hard_bounded_before_network_access(tmp_path: Path) -> None:
    qids = tuple(f"Q{index}" for index in range(1, 52))

    with pytest.raises(WikidataCollectionError, match="at most 50"):
        collect_wikidata_profiles.collect_snapshot(
            qids=qids,
            snapshot_id="too-large",
            competition_codes=("ENG_PL",),
            season_labels=("2017/18",),
            output_dir=tmp_path,
        )


def test_collector_writes_verifiable_snapshot_and_audit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    documents = {
        "Q201": _document(
            "Q201",
            label="Player One",
            claims={"P569": [_statement(_time_snak("+1990-05-20T00:00:00Z", 11))]},
        ),
        "Q202": _document(
            "Q202",
            label="Player Two",
            claims={"P569": [_statement(_time_snak("+1991-01-01T00:00:00Z", 9))]},
        ),
    }

    def fake_fetch(qid: str) -> bytes:
        return json.dumps(documents[qid], sort_keys=True).encode("utf-8")

    monkeypatch.setattr(collect_wikidata_profiles, "_fetch_entity", fake_fetch)
    manifest = collect_wikidata_profiles.collect_snapshot(
        qids=("Q202", "Q201", "Q201"),
        snapshot_id="wikidata-eng-pl-2017-18-test",
        competition_codes=("ENG_PL",),
        season_labels=("2017/18",),
        output_dir=tmp_path,
    )

    loaded = load_static_snapshot_manifest(tmp_path / "manifest.json")
    verification = verify_static_snapshot_files(loaded, base_dir=tmp_path)
    report = run_audit(manifest_path=tmp_path / "manifest.json", base_dir=tmp_path)

    assert manifest.files[0].path == "Q201.json"
    assert len(manifest.files) == 2
    assert verification.passed
    assert report.passed
    assert report.profile_count == 2
    assert report.profiles_with_exact_date_of_birth == 1
    assert report.profiles_with_partial_date_of_birth == 1
