"""Conservative Wikidata player-profile parsing for static identity evidence.

Wikidata is used here only as a CC0 profile/identity source. This module does
not query Wikidata, create canonical players, or emit performance metrics. It
parses frozen ``Special:EntityData`` entity documents and translates only
sufficiently precise, explicitly scoped evidence into the existing
``PlayerIdentityRecord`` pre-resolution contract.

Important evidence rules:

- provider-native QIDs remain provider IDs, never Football Intelligence IDs;
- only non-deprecated Wikidata statements are considered;
- a year/month precision time value is never coerced into an exact date;
- an exact date of birth is exposed only when all usable DOB claims are
  compatible with one unique day-precision Gregorian value;
- club membership contributes season context only when P54 has one bounded
  P580 start and one bounded P582 end qualifier whose uncertainty interval
  proves overlap with the requested season;
- team QIDs must be mapped explicitly to canonical Football Intelligence team
  context keys by the caller;
- Wikidata provides no canonical match evidence here, so this adapter can
  produce review evidence but never ``crosswalk_ready`` evidence by itself.
"""

from __future__ import annotations

import calendar
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, cast

from football_intelligence.data_mesh.player_identity_candidates import PlayerIdentityRecord

SOURCE_CODE = "wikidata"
ENTITY_DATA_REFERENCE = "https://www.wikidata.org/wiki/Special:EntityData"
LICENCE = "CC0 1.0"
PROLEPTIC_GREGORIAN_QID = "Q1985727"

_QID_RE = re.compile(r"^Q[1-9][0-9]*$")
_WIKIDATA_TIME_RE = re.compile(r"^\+(\d{4,})-(\d{2})-(\d{2})T")


class WikidataProfileError(ValueError):
    """A Wikidata entity document cannot satisfy the profile intake contract."""


@dataclass(frozen=True, slots=True)
class WikidataTimeValue:
    raw_time: str
    precision: int
    calendar_model_qid: str | None

    @property
    def exact_date(self) -> date | None:
        """Return a true day-precision Gregorian date, never a synthetic one."""

        if self.precision != 11 or self.calendar_model_qid != PROLEPTIC_GREGORIAN_QID:
            return None
        parsed = _parse_positive_time_components(self.raw_time)
        if parsed is None:
            return None
        year, month, day = parsed
        try:
            return date(year, month, day)
        except ValueError:
            return None

    @property
    def date_bounds(self) -> tuple[date, date] | None:
        """Return the uncertainty interval represented by year/month/day precision.

        Precision 11 is one exact day, 10 spans a calendar month, and 9 spans a
        calendar year. Lower precisions are intentionally not interpreted for
        season-level player identity evidence.
        """

        if self.calendar_model_qid != PROLEPTIC_GREGORIAN_QID:
            return None
        parsed = _parse_positive_time_components(self.raw_time)
        if parsed is None:
            return None
        year, month, day = parsed
        try:
            if self.precision == 11:
                exact = date(year, month, day)
                return (exact, exact)
            if self.precision == 10:
                first = date(year, month, 1)
                last = date(year, month, calendar.monthrange(year, month)[1])
                return (first, last)
            if self.precision == 9:
                return (date(year, 1, 1), date(year, 12, 31))
        except ValueError:
            return None
        return None


@dataclass(frozen=True, slots=True)
class WikidataTeamMembership:
    team_qid: str
    start_times: tuple[WikidataTimeValue, ...]
    end_times: tuple[WikidataTimeValue, ...]

    def guarantees_overlap(self, *, season_start: date, season_end: date) -> bool:
        """Return true only when qualifiers prove membership intersects a season.

        A membership without exactly one bounded start and end qualifier is not
        used as season identity evidence. For imprecise qualifiers, overlap must
        hold even at the latest possible start and earliest possible end.
        """

        if (
            season_start > season_end
            or len(self.start_times) != 1
            or len(self.end_times) != 1
        ):
            return False
        start_bounds = self.start_times[0].date_bounds
        end_bounds = self.end_times[0].date_bounds
        if start_bounds is None or end_bounds is None:
            return False
        start_low, start_high = start_bounds
        end_low, end_high = end_bounds
        if start_low > end_high:
            return False
        return start_high <= season_end and end_low >= season_start


@dataclass(frozen=True, slots=True)
class WikidataPlayerProfile:
    qid: str
    display_name: str | None
    dates_of_birth: tuple[WikidataTimeValue, ...]
    citizenship_qids: tuple[str, ...]
    position_qids: tuple[str, ...]
    team_memberships: tuple[WikidataTeamMembership, ...]
    last_revision_id: int | None
    modified_at: str | None

    @property
    def exact_date_of_birth(self) -> date | None:
        """Resolve one exact DOB only when every bounded DOB claim is compatible."""

        exact_dates = {
            exact
            for value in self.dates_of_birth
            if (exact := value.exact_date) is not None
        }
        if len(exact_dates) != 1:
            return None
        exact = next(iter(exact_dates))
        for value in self.dates_of_birth:
            bounds = value.date_bounds
            if bounds is None:
                continue
            lower, upper = bounds
            if not lower <= exact <= upper:
                return None
        return exact

    def canonical_team_context_keys(
        self,
        *,
        season_start: date,
        season_end: date,
        team_qid_to_context: Mapping[str, str],
    ) -> tuple[str, ...]:
        contexts = {
            team_qid_to_context[membership.team_qid]
            for membership in self.team_memberships
            if membership.team_qid in team_qid_to_context
            and membership.guarantees_overlap(season_start=season_start, season_end=season_end)
        }
        if any(not context.strip() for context in contexts):
            raise WikidataProfileError("canonical team context mappings must be non-blank strings")
        return tuple(sorted(contexts))

    def to_player_identity_record(
        self,
        *,
        competition_code: str,
        season_label: str,
        season_start: date,
        season_end: date,
        team_qid_to_context: Mapping[str, str],
    ) -> PlayerIdentityRecord:
        if self.display_name is None or not self.display_name.strip():
            raise WikidataProfileError(f"{self.qid} has no usable display label")
        return PlayerIdentityRecord(
            source_code=SOURCE_CODE,
            provider_player_id=self.qid,
            raw_name=self.display_name,
            competition_code=competition_code,
            season_label=season_label,
            team_context_keys=self.canonical_team_context_keys(
                season_start=season_start,
                season_end=season_end,
                team_qid_to_context=team_qid_to_context,
            ),
            team_match_evidence=(),
            date_of_birth=self.exact_date_of_birth,
            # P27 and P413 are preserved provider-native above. They are not
            # silently converted into FI nationality/position taxonomies here.
            nationality=None,
            position=None,
            height_cm=None,
        )


def validate_qid(value: str) -> str:
    qid = value.strip()
    if not _QID_RE.fullmatch(qid):
        raise WikidataProfileError(f"invalid Wikidata item id {value!r}")
    return qid


def load_wikidata_profile(
    path: Path, *, expected_qid: str | None = None
) -> WikidataPlayerProfile:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise WikidataProfileError("Special:EntityData document root must be a JSON object")
    return parse_wikidata_entity_document(
        cast(dict[str, Any], payload), expected_qid=expected_qid
    )


def parse_wikidata_entity_document(
    payload: dict[str, Any], *, expected_qid: str | None = None
) -> WikidataPlayerProfile:
    entities = payload.get("entities")
    if not isinstance(entities, dict):
        raise WikidataProfileError("Special:EntityData document must contain an entities object")
    entity_map = cast(dict[str, Any], entities)

    qid = validate_qid(expected_qid) if expected_qid is not None else _single_entity_qid(entity_map)
    entity_raw = entity_map.get(qid)
    if not isinstance(entity_raw, dict) or entity_raw.get("missing") is not None:
        raise WikidataProfileError(f"Wikidata entity {qid} is missing")
    entity = cast(dict[str, Any], entity_raw)

    labels = entity.get("labels")
    display_name = _preferred_label(
        cast(dict[str, Any], labels) if isinstance(labels, dict) else {}
    )
    claims_raw = entity.get("claims")
    claims = cast(dict[str, Any], claims_raw) if isinstance(claims_raw, dict) else {}

    revision_raw = entity.get("lastrevid")
    last_revision_id = (
        revision_raw
        if isinstance(revision_raw, int) and not isinstance(revision_raw, bool)
        else None
    )
    modified_raw = entity.get("modified")
    modified_at = modified_raw if isinstance(modified_raw, str) else None

    return WikidataPlayerProfile(
        qid=qid,
        display_name=display_name,
        dates_of_birth=_claim_times(claims, "P569"),
        citizenship_qids=_claim_item_qids(claims, "P27"),
        position_qids=_claim_item_qids(claims, "P413"),
        team_memberships=_team_memberships(claims),
        last_revision_id=last_revision_id,
        modified_at=modified_at,
    )


def _single_entity_qid(entities: dict[str, Any]) -> str:
    qids = sorted(validate_qid(key) for key in entities if _QID_RE.fullmatch(key))
    if len(qids) != 1:
        raise WikidataProfileError(
            f"entity document must contain exactly one Wikidata item, got {qids!r}"
        )
    return qids[0]


def _preferred_label(labels: dict[str, Any]) -> str | None:
    for language in ("en", "es"):
        value = _label_value(labels.get(language))
        if value:
            return value
    for language in sorted(labels):
        value = _label_value(labels.get(language))
        if value:
            return value
    return None


def _label_value(raw: Any) -> str | None:
    if not isinstance(raw, dict):
        return None
    value = raw.get("value")
    return value.strip() if isinstance(value, str) and value.strip() else None


def _active_statements(
    claims: dict[str, Any], property_id: str
) -> tuple[dict[str, Any], ...]:
    statements_raw = claims.get(property_id)
    if not isinstance(statements_raw, list):
        return ()
    result: list[dict[str, Any]] = []
    for raw in statements_raw:
        if isinstance(raw, dict) and raw.get("rank") != "deprecated":
            result.append(cast(dict[str, Any], raw))
    return tuple(result)


def _claim_item_qids(claims: dict[str, Any], property_id: str) -> tuple[str, ...]:
    values = {
        qid
        for statement in _active_statements(claims, property_id)
        if (qid := _statement_item_qid(statement)) is not None
    }
    return tuple(sorted(values))


def _claim_times(
    claims: dict[str, Any], property_id: str
) -> tuple[WikidataTimeValue, ...]:
    values = {
        value
        for statement in _active_statements(claims, property_id)
        if (value := _time_from_snak(statement.get("mainsnak"))) is not None
    }
    return tuple(sorted(values, key=_time_sort_key))


def _team_memberships(claims: dict[str, Any]) -> tuple[WikidataTeamMembership, ...]:
    memberships: list[WikidataTeamMembership] = []
    for statement in _active_statements(claims, "P54"):
        team_qid = _statement_item_qid(statement)
        if team_qid is None:
            continue
        qualifiers_raw = statement.get("qualifiers")
        qualifiers = (
            cast(dict[str, Any], qualifiers_raw) if isinstance(qualifiers_raw, dict) else {}
        )
        memberships.append(
            WikidataTeamMembership(
                team_qid=team_qid,
                start_times=_qualifier_times(qualifiers, "P580"),
                end_times=_qualifier_times(qualifiers, "P582"),
            )
        )
    return tuple(
        sorted(
            memberships,
            key=lambda membership: (
                membership.team_qid,
                tuple(_time_sort_key(value) for value in membership.start_times),
                tuple(_time_sort_key(value) for value in membership.end_times),
            ),
        )
    )


def _statement_item_qid(statement: dict[str, Any]) -> str | None:
    return _item_qid_from_snak(statement.get("mainsnak"))


def _item_qid_from_snak(raw: Any) -> str | None:
    if not isinstance(raw, dict) or raw.get("snaktype") != "value":
        return None
    datavalue = raw.get("datavalue")
    if not isinstance(datavalue, dict):
        return None
    value = datavalue.get("value")
    if not isinstance(value, dict):
        return None
    qid = value.get("id")
    if not isinstance(qid, str) or not _QID_RE.fullmatch(qid):
        return None
    return qid


def _qualifier_times(
    qualifiers: dict[str, Any], property_id: str
) -> tuple[WikidataTimeValue, ...]:
    snaks_raw = qualifiers.get(property_id)
    if not isinstance(snaks_raw, list):
        return ()
    values = {
        value for snak in snaks_raw if (value := _time_from_snak(snak)) is not None
    }
    return tuple(sorted(values, key=_time_sort_key))


def _time_from_snak(raw: Any) -> WikidataTimeValue | None:
    if not isinstance(raw, dict) or raw.get("snaktype") != "value":
        return None
    datavalue = raw.get("datavalue")
    if not isinstance(datavalue, dict) or datavalue.get("type") != "time":
        return None
    value = datavalue.get("value")
    if not isinstance(value, dict):
        return None
    raw_time = value.get("time")
    precision = value.get("precision")
    calendar_model = value.get("calendarmodel")
    if (
        not isinstance(raw_time, str)
        or not isinstance(precision, int)
        or isinstance(precision, bool)
    ):
        return None
    calendar_qid = _qid_from_uri(calendar_model) if isinstance(calendar_model, str) else None
    return WikidataTimeValue(
        raw_time=raw_time,
        precision=precision,
        calendar_model_qid=calendar_qid,
    )


def _qid_from_uri(value: str) -> str | None:
    candidate = value.rsplit("/", 1)[-1]
    return candidate if _QID_RE.fullmatch(candidate) else None


def _parse_positive_time_components(raw_time: str) -> tuple[int, int, int] | None:
    match = _WIKIDATA_TIME_RE.match(raw_time)
    if match is None:
        return None
    year, month, day = (int(part) for part in match.groups())
    if not 1 <= year <= 9999:
        return None
    return (year, month, day)


def _time_sort_key(value: WikidataTimeValue) -> tuple[str, int, str]:
    return (value.raw_time, value.precision, value.calendar_model_qid or "")
