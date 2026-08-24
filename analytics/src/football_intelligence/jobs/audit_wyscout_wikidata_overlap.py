"""Real-source Wyscout x Wikidata player-profile overlap laboratory.

Local/read-only. The job acquires official Wyscout Open England 2017/18
roster/profile evidence from Figshare, discovers Wikidata candidates through
competition clubs, and measures identity/profile overlap.

It never writes PostgreSQL, creates PlayerCrosswalk entries, changes scores, or
promotes evidence. Player discovery remains exact-name only; no fuzzy/LLM
matching is used. Wikidata cannot make a player crosswalk-ready by itself
because this profile source exposes no shared canonical match ids.
"""

from __future__ import annotations

import argparse
import json
import time
from collections import Counter, defaultdict
from collections.abc import Iterable
from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path
from typing import Any, cast
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from football_intelligence.data_mesh.entity_resolution import normalize_team_name, resolve_team
from football_intelligence.data_mesh.player_identity_candidates import (
    PlayerIdentityRecord,
    compare_player_identity_records,
)
from football_intelligence.data_mesh.player_name_normalization import normalize_player_name
from football_intelligence.providers.wikidata_profiles import (
    WikidataPlayerProfile,
    WikidataProfileError,
    parse_wikidata_entity_document,
)
from football_intelligence.providers.wyscout_open import (
    WyscoutOpenAsset,
    WyscoutOpenDataClient,
    WyscoutOpenDataError,
    safe_extract_zip,
)
from football_intelligence.providers.wyscout_open_scopes import roster_player_ids
from football_intelligence.providers.wyscout_open_text import (
    repair_wyscout_double_escaped_unicode,
)

FIGSHARE_COLLECTION_ID = 4415000
COMPETITION_CODE = "ENG_PL"
SEASON_LABEL = "2017/18"
SEASON_START = date(2017, 8, 1)
SEASON_END = date(2018, 5, 31)
EXPECTED_ROSTER_PLAYERS = 603
EXPECTED_TEAMS = 20

WIKIDATA_API = "https://www.wikidata.org/w/api.php"
WIKIDATA_SPARQL = "https://query.wikidata.org/sparql"
USER_AGENT = (
    "FootballIntelligence/0.1 "
    "(+https://github.com/franciscovitar/football-intelligence)"
)
HTTP_TIMEOUT_SECONDS = 45
MAX_ATTEMPTS = 4
TEAM_SEARCH_LIMIT = 10
SPARQL_TEAM_CHUNK_SIZE = 4
WIKIDATA_ENTITY_BATCH_SIZE = 40
_MAX_EXAMPLES = 30


class WyscoutWikidataOverlapError(RuntimeError):
    """The real-source overlap audit cannot safely complete."""


@dataclass(frozen=True, slots=True)
class WyscoutRosterProfile:
    provider_player_id: str
    display_name: str
    name_variants: tuple[str, ...]
    date_of_birth: date | None
    nationality: str | None
    position: str | None
    team_context_keys: tuple[str, ...]
    team_names: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class WikidataTeamMapping:
    wyscout_team_id: int
    wyscout_name: str
    canonical_team_context: str | None
    wikidata_qid: str | None
    wikidata_label: str | None
    status: str
    candidate_qids: tuple[str, ...]
    plausible_candidates: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class WikidataDiscoveryRow:
    qid: str
    label: str
    date_of_birth: date | None
    team_qid: str


@dataclass(frozen=True, slots=True)
class PlayerOverlapResult:
    wyscout_player_id: str
    wyscout_name: str
    wikidata_qid: str | None
    wikidata_name: str | None
    state: str
    reasons: tuple[str, ...]
    shared_team_context_keys: tuple[str, ...]
    date_of_birth_matches: bool | None
    wikidata_has_exact_dob: bool
    wikidata_has_citizenship: bool
    wikidata_has_position: bool
    wikidata_has_bounded_team_context: bool


@dataclass(frozen=True, slots=True)
class WyscoutWikidataOverlapReport:
    competition_code: str
    season_label: str
    wyscout_roster_total: int
    wyscout_profiles_available: int
    wyscout_profiles_missing: int
    team_total: int
    team_mappings_resolved: int
    team_mappings_unresolved: int
    wikidata_discovery_rows: int
    wikidata_discovery_entities: int
    players_with_exact_name_candidate: int
    players_with_unique_candidate: int
    wikidata_entities_loaded: int
    wikidata_exact_dob_coverage: int
    wikidata_citizenship_coverage: int
    wikidata_position_coverage: int
    wikidata_bounded_team_context_coverage: int
    candidate_state_counts: dict[str, int]
    results: tuple[PlayerOverlapResult, ...]
    team_mappings: tuple[WikidataTeamMapping, ...]
    failures: tuple[str, ...]

    @property
    def passed(self) -> bool:
        return not self.failures


def build_wyscout_roster_profiles(
    *,
    matches_payload: list[Any],
    players_payload: list[Any],
    teams_payload: list[Any],
) -> tuple[WyscoutRosterProfile, ...]:
    roster_ids = roster_player_ids(matches_payload)
    player_teams = _roster_team_ids_by_player(matches_payload)
    player_rows = {
        item["wyId"]: item
        for item in players_payload
        if isinstance(item, dict) and isinstance(item.get("wyId"), int)
    }
    team_names = _team_names_by_id(teams_payload)

    profiles: list[WyscoutRosterProfile] = []
    for player_id in sorted(roster_ids):
        row = player_rows.get(player_id)
        if not isinstance(row, dict):
            continue
        variants = _source_name_variants(row)
        if not variants:
            continue

        contexts: set[str] = set()
        names: set[str] = set()
        for team_id in player_teams.get(player_id, set()):
            name = team_names.get(team_id)
            if name is None:
                continue
            names.add(name)
            resolution = resolve_team(name=name, competition_code=COMPETITION_CODE)
            if resolution.status == "resolved" and resolution.logical_key is not None:
                contexts.add(resolution.logical_key)

        profiles.append(
            WyscoutRosterProfile(
                provider_player_id=str(player_id),
                display_name=variants[0],
                name_variants=variants,
                date_of_birth=_parse_iso_date(row.get("birthDate")),
                nationality=_nested_name(row.get("passportArea")),
                position=_role_name(row.get("role")),
                team_context_keys=tuple(sorted(contexts)),
                team_names=tuple(sorted(names)),
            )
        )
    return tuple(profiles)


def resolve_wikidata_team_candidate(
    *,
    wyscout_team_id: int,
    wyscout_name: str,
    search_results: list[Any],
) -> WikidataTeamMapping:
    """Resolve one club conservatively from Wikidata search results.

    Wikidata commonly renders corporate abbreviations as ``F.C.`` / ``A.F.C.``,
    while Football Intelligence's generic resolver strips ``FC`` / ``AFC``.
    For this external-search boundary only, periods are removed before the
    existing deterministic normalizer runs. This does not widen matching into
    edit distance or fuzzy similarity.

    More than one exact football-club candidate is an ambiguity and remains
    unresolved; a same-name club is never silently selected.
    """

    resolution = resolve_team(name=wyscout_name, competition_code=COMPETITION_CODE)
    canonical_context = (
        resolution.logical_key if resolution.status == "resolved" else None
    )
    target = _normalize_wikidata_search_label(wyscout_name)

    plausible: list[tuple[str, str, str]] = []
    all_qids: list[str] = []
    for raw in search_results:
        if not isinstance(raw, dict):
            continue
        qid = raw.get("id")
        label = raw.get("label")
        description = raw.get("description")
        if not isinstance(qid, str) or not qid.startswith("Q"):
            continue
        all_qids.append(qid)
        if not isinstance(label, str) or not label.strip():
            continue

        description_text = description.casefold() if isinstance(description, str) else ""
        if "football" not in description_text:
            continue
        if _normalize_wikidata_search_label(label) != target:
            continue

        plausible.append(
            (
                qid,
                label.strip(),
                description.strip() if isinstance(description, str) else "",
            )
        )

    if canonical_context is None:
        status = "canonical_team_unresolved"
        selected: tuple[str, str] | None = None
    elif len(plausible) == 1:
        status = "resolved"
        selected = (plausible[0][0], plausible[0][1])
    elif not plausible:
        status = "no_exact_football_club_candidate"
        selected = None
    else:
        status = "ambiguous_exact_football_club_candidates"
        selected = None

    return WikidataTeamMapping(
        wyscout_team_id=wyscout_team_id,
        wyscout_name=wyscout_name,
        canonical_team_context=canonical_context,
        wikidata_qid=selected[0] if selected is not None else None,
        wikidata_label=selected[1] if selected is not None else None,
        status=status,
        candidate_qids=tuple(sorted(set(all_qids))),
        plausible_candidates=tuple(
            sorted(f"{qid}|{label}|{description}" for qid, label, description in plausible)
        ),
    )


def discover_exact_name_candidates(
    roster: Iterable[WyscoutRosterProfile],
    discovery_rows: Iterable[WikidataDiscoveryRow],
) -> dict[str, tuple[str, ...]]:
    by_name: dict[str, set[str]] = defaultdict(set)
    rows_by_qid: dict[str, list[WikidataDiscoveryRow]] = defaultdict(list)
    for row in discovery_rows:
        by_name[normalize_player_name(row.label)].add(row.qid)
        rows_by_qid[row.qid].append(row)

    result: dict[str, tuple[str, ...]] = {}
    for player in roster:
        qids: set[str] = set()
        for variant in player.name_variants:
            qids.update(by_name.get(normalize_player_name(variant), set()))

        if player.date_of_birth is not None:
            compatible: set[str] = set()
            for qid in qids:
                candidate_dates = {
                    row.date_of_birth
                    for row in rows_by_qid[qid]
                    if row.date_of_birth is not None
                }
                if not candidate_dates or player.date_of_birth in candidate_dates:
                    compatible.add(qid)
            qids = compatible

        if qids:
            result[player.provider_player_id] = tuple(sorted(qids))
    return result


def evaluate_player_overlap(
    *,
    player: WyscoutRosterProfile,
    candidate_qids: tuple[str, ...],
    profiles_by_qid: dict[str, WikidataPlayerProfile],
    team_qid_to_context: dict[str, str],
) -> PlayerOverlapResult:
    if not candidate_qids:
        return _empty_player_result(player, state="no_exact_name_candidate")
    if len(candidate_qids) != 1:
        return _empty_player_result(
            player,
            state="ambiguous_exact_name_candidates",
            reasons=(f"candidate_count={len(candidate_qids)}",),
        )

    qid = candidate_qids[0]
    profile = profiles_by_qid.get(qid)
    if profile is None or profile.display_name is None:
        return _empty_player_result(
            player,
            state="candidate_profile_unavailable",
            wikidata_qid=qid,
        )

    matching_variant = _matching_source_variant(player.name_variants, profile.display_name)
    if matching_variant is None:
        return _empty_player_result(
            player,
            state="normalized_name_mismatch_after_profile_load",
            wikidata_qid=qid,
            wikidata_name=profile.display_name,
        )

    wikidata_record = profile.to_player_identity_record(
        competition_code=COMPETITION_CODE,
        season_label=SEASON_LABEL,
        season_start=SEASON_START,
        season_end=SEASON_END,
        team_qid_to_context=team_qid_to_context,
    )
    wyscout_record = PlayerIdentityRecord(
        source_code="wyscout-open",
        provider_player_id=player.provider_player_id,
        raw_name=matching_variant,
        competition_code=COMPETITION_CODE,
        season_label=SEASON_LABEL,
        team_context_keys=player.team_context_keys,
        date_of_birth=player.date_of_birth,
        nationality=player.nationality,
        position=player.position,
    )
    candidate = compare_player_identity_records(wyscout_record, wikidata_record)

    exact_dob = profile.exact_date_of_birth
    dob_matches = (
        None
        if player.date_of_birth is None or exact_dob is None
        else player.date_of_birth == exact_dob
    )
    return PlayerOverlapResult(
        wyscout_player_id=player.provider_player_id,
        wyscout_name=player.display_name,
        wikidata_qid=qid,
        wikidata_name=profile.display_name,
        state=candidate.state,
        reasons=candidate.reasons,
        shared_team_context_keys=candidate.shared_team_context_keys,
        date_of_birth_matches=dob_matches,
        wikidata_has_exact_dob=exact_dob is not None,
        wikidata_has_citizenship=bool(profile.citizenship_qids),
        wikidata_has_position=bool(profile.position_qids),
        wikidata_has_bounded_team_context=bool(wikidata_record.team_context_keys),
    )


def _empty_player_result(
    player: WyscoutRosterProfile,
    *,
    state: str,
    reasons: tuple[str, ...] = (),
    wikidata_qid: str | None = None,
    wikidata_name: str | None = None,
) -> PlayerOverlapResult:
    return PlayerOverlapResult(
        wyscout_player_id=player.provider_player_id,
        wyscout_name=player.display_name,
        wikidata_qid=wikidata_qid,
        wikidata_name=wikidata_name,
        state=state,
        reasons=reasons,
        shared_team_context_keys=(),
        date_of_birth_matches=None,
        wikidata_has_exact_dob=False,
        wikidata_has_citizenship=False,
        wikidata_has_position=False,
        wikidata_has_bounded_team_context=False,
    )


def _normalize_wikidata_search_label(raw: str) -> str:
    return normalize_team_name(raw.replace(".", ""))


def _source_name_variants(row: dict[str, Any]) -> tuple[str, ...]:
    variants: list[str] = []
    short_name = row.get("shortName")
    if isinstance(short_name, str) and short_name.strip():
        variants.append(repair_wyscout_double_escaped_unicode(short_name).strip())

    first = _clean_wyscout_text(row.get("firstName"))
    middle = _clean_wyscout_text(row.get("middleName"))
    last = _clean_wyscout_text(row.get("lastName"))
    for parts in ((first, last), (first, middle, last)):
        full = " ".join(part for part in parts if part)
        if full:
            variants.append(full)

    deduped: list[str] = []
    seen: set[str] = set()
    for variant in variants:
        normalized = normalize_player_name(variant)
        if normalized and normalized not in seen:
            seen.add(normalized)
            deduped.append(variant)
    return tuple(deduped)


def _matching_source_variant(
    variants: tuple[str, ...], candidate_name: str
) -> str | None:
    candidate_normalized = normalize_player_name(candidate_name)
    return next(
        (
            variant
            for variant in variants
            if normalize_player_name(variant) == candidate_normalized
        ),
        None,
    )


def _clean_wyscout_text(raw: Any) -> str | None:
    if not isinstance(raw, str) or not raw.strip():
        return None
    return repair_wyscout_double_escaped_unicode(raw).strip()


def _nested_name(raw: Any) -> str | None:
    return _clean_wyscout_text(raw.get("name")) if isinstance(raw, dict) else None


def _role_name(raw: Any) -> str | None:
    if not isinstance(raw, dict):
        return None
    value = raw.get("name") or raw.get("code2")
    return value.strip() if isinstance(value, str) and value.strip() else None


def _parse_iso_date(raw: Any) -> date | None:
    if not isinstance(raw, str) or not raw.strip():
        return None
    try:
        return date.fromisoformat(raw.strip())
    except ValueError:
        return None


def _roster_team_ids_by_player(matches_payload: list[Any]) -> dict[int, set[int]]:
    result: dict[int, set[int]] = defaultdict(set)
    for match in matches_payload:
        if not isinstance(match, dict):
            continue
        teams_data = match.get("teamsData")
        if not isinstance(teams_data, dict):
            continue

        for raw_team_id, team_entry in teams_data.items():
            try:
                team_id = int(raw_team_id)
            except (TypeError, ValueError):
                continue
            if not isinstance(team_entry, dict):
                continue
            formation = team_entry.get("formation")
            if not isinstance(formation, dict):
                continue

            for key in ("lineup", "bench"):
                entries = formation.get(key)
                if not isinstance(entries, list):
                    continue
                for entry in entries:
                    if not isinstance(entry, dict):
                        continue
                    player_id = entry.get("playerId")
                    if isinstance(player_id, int) and player_id != 0:
                        result[player_id].add(team_id)
    return result


def _team_names_by_id(payload: list[Any]) -> dict[int, str]:
    result: dict[int, str] = {}
    for item in payload:
        if not isinstance(item, dict):
            continue
        team_id = item.get("wyId")
        raw_name = item.get("name") or item.get("officialName")
        if isinstance(team_id, int) and isinstance(raw_name, str) and raw_name.strip():
            result[team_id] = repair_wyscout_double_escaped_unicode(raw_name).strip()
    return result


def _competition_team_ids(matches_payload: list[Any]) -> tuple[int, ...]:
    team_ids: set[int] = set()
    for match in matches_payload:
        if not isinstance(match, dict):
            continue
        teams_data = match.get("teamsData")
        if not isinstance(teams_data, dict):
            continue
        for raw_team_id in teams_data:
            try:
                team_ids.add(int(raw_team_id))
            except (TypeError, ValueError):
                continue
    return tuple(sorted(team_ids))


def _load_wyscout_asset_json(
    asset: WyscoutOpenAsset,
    *,
    cache_dir: Path,
    expected_filename: str | None = None,
) -> list[Any]:
    path = asset.local_path
    if path.suffix.casefold() == ".zip":
        extract_dir = cache_dir / "extracted" / path.stem
        extracted = safe_extract_zip(path, extract_dir)
        candidates = [
            candidate
            for candidate in extracted
            if candidate.is_file()
            and (expected_filename is None or candidate.name == expected_filename)
        ]
        if len(candidates) != 1:
            expected = expected_filename or "JSON"
            raise WyscoutWikidataOverlapError(
                f"{path.name} expected one {expected} file, got {len(candidates)}"
            )
        path = candidates[0]

    with path.open("rb") as handle:
        payload = json.load(handle)
    if not isinstance(payload, list):
        raise WyscoutWikidataOverlapError(f"{path.name} is not a JSON array")
    return payload


class WikidataLabClient:
    def __init__(self, *, cache_dir: Path) -> None:
        self._cache_dir = cache_dir
        self._cache_dir.mkdir(parents=True, exist_ok=True)

    def search_team(self, name: str) -> list[Any]:
        payload = self._request_json(
            WIKIDATA_API,
            params={
                "action": "wbsearchentities",
                "search": name,
                "language": "en",
                "uselang": "en",
                "type": "item",
                "limit": str(TEAM_SEARCH_LIMIT),
                "format": "json",
                "formatversion": "2",
            },
        )
        if not isinstance(payload, dict) or not isinstance(payload.get("search"), list):
            raise WyscoutWikidataOverlapError(
                f"Wikidata team search failed for {name!r}"
            )
        return cast(list[Any], payload["search"])

    def discover_players_for_teams(
        self, mappings: tuple[WikidataTeamMapping, ...]
    ) -> tuple[WikidataDiscoveryRow, ...]:
        qids = [
            mapping.wikidata_qid
            for mapping in mappings
            if mapping.wikidata_qid is not None
        ]
        rows: list[WikidataDiscoveryRow] = []
        for start in range(0, len(qids), SPARQL_TEAM_CHUNK_SIZE):
            chunk = qids[start : start + SPARQL_TEAM_CHUNK_SIZE]
            payload = self._request_json(
                WIKIDATA_SPARQL,
                data={"query": _player_discovery_query(chunk), "format": "json"},
                accept="application/sparql-results+json",
            )
            rows.extend(_parse_sparql_discovery(payload))
            time.sleep(0.25)

        unique = {
            (row.qid, row.label, row.date_of_birth, row.team_qid): row for row in rows
        }
        return tuple(
            sorted(
                unique.values(),
                key=lambda row: (
                    row.qid,
                    row.team_qid,
                    row.label,
                    row.date_of_birth or date.min,
                ),
            )
        )

    def fetch_player_profiles(
        self, qids: Iterable[str]
    ) -> dict[str, WikidataPlayerProfile]:
        canonical_qids = sorted(set(qids))
        profiles: dict[str, WikidataPlayerProfile] = {}

        for batch_index, start in enumerate(
            range(0, len(canonical_qids), WIKIDATA_ENTITY_BATCH_SIZE),
            start=1,
        ):
            batch = canonical_qids[start : start + WIKIDATA_ENTITY_BATCH_SIZE]
            payload = self._request_json(
                WIKIDATA_API,
                data={
                    "action": "wbgetentities",
                    "ids": "|".join(batch),
                    "props": "info|labels|claims",
                    "languages": "en|es",
                    "languagefallback": "1",
                    "format": "json",
                    "formatversion": "2",
                },
            )
            path = self._cache_dir / f"wikidata-entities-{batch_index:03d}.json"
            encoded = (
                json.dumps(payload, sort_keys=True, ensure_ascii=False) + "\n"
            ).encode("utf-8")
            path.write_bytes(encoded)

            entities = payload.get("entities") if isinstance(payload, dict) else None
            if not isinstance(entities, dict):
                raise WyscoutWikidataOverlapError(
                    "Wikidata wbgetentities returned no entities map"
                )
            for qid in batch:
                raw_entity = entities.get(qid)
                if not isinstance(raw_entity, dict):
                    continue
                try:
                    profile = parse_wikidata_entity_document(
                        {"entities": {qid: raw_entity}},
                        expected_qid=qid,
                    )
                except WikidataProfileError:
                    continue
                profiles[qid] = profile
            time.sleep(0.15)

        return profiles

    def _request_json(
        self,
        url: str,
        *,
        params: dict[str, str] | None = None,
        data: dict[str, str] | None = None,
        accept: str = "application/json",
    ) -> Any:
        if params:
            url = f"{url}?{urlencode(params)}"
        body = urlencode(data).encode("utf-8") if data is not None else None

        last_error: Exception | None = None
        for attempt in range(1, MAX_ATTEMPTS + 1):
            request = Request(
                url,
                data=body,
                headers={
                    "Accept": accept,
                    "Content-Type": "application/x-www-form-urlencoded",
                    "User-Agent": USER_AGENT,
                },
                method="POST" if body is not None else "GET",
            )
            try:
                with urlopen(request, timeout=HTTP_TIMEOUT_SECONDS) as response:
                    raw = cast(bytes, response.read())
                return json.loads(raw)
            except HTTPError as exc:
                last_error = exc
                if (
                    exc.code not in {429, 500, 502, 503, 504}
                    or attempt == MAX_ATTEMPTS
                ):
                    break
                retry_after = exc.headers.get("Retry-After")
                delay = (
                    float(retry_after)
                    if retry_after and retry_after.isdigit()
                    else float(attempt)
                )
                time.sleep(min(delay, 10.0))
            except (URLError, TimeoutError, json.JSONDecodeError) as exc:
                last_error = exc
                if attempt == MAX_ATTEMPTS:
                    break
                time.sleep(float(attempt))

        raise WyscoutWikidataOverlapError(
            f"request failed for {url}: {last_error}"
        )


def _player_discovery_query(team_qids: list[str]) -> str:
    values = " ".join(f"wd:{qid}" for qid in team_qids)
    return f"""
SELECT DISTINCT ?player ?playerLabel ?dob ?team WHERE {{
  VALUES ?team {{ {values} }}
  ?player wdt:P31 wd:Q5 ;
          wdt:P54 ?team .
  OPTIONAL {{ ?player wdt:P569 ?dob . }}
  SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en,es". }}
}}
""".strip()


def _parse_sparql_discovery(payload: Any) -> list[WikidataDiscoveryRow]:
    if not isinstance(payload, dict):
        raise WyscoutWikidataOverlapError("Wikidata SPARQL response is not an object")
    results = payload.get("results")
    bindings = results.get("bindings") if isinstance(results, dict) else None
    if not isinstance(bindings, list):
        raise WyscoutWikidataOverlapError("Wikidata SPARQL response has no bindings")

    rows: list[WikidataDiscoveryRow] = []
    for binding in bindings:
        if not isinstance(binding, dict):
            continue
        qid = _qid_from_binding(binding.get("player"))
        team_qid = _qid_from_binding(binding.get("team"))
        label = _value_from_binding(binding.get("playerLabel"))
        if qid is None or team_qid is None or label is None:
            continue
        rows.append(
            WikidataDiscoveryRow(
                qid=qid,
                label=label,
                date_of_birth=_parse_wikidata_datetime(
                    _value_from_binding(binding.get("dob"))
                ),
                team_qid=team_qid,
            )
        )
    return rows


def _value_from_binding(raw: Any) -> str | None:
    if not isinstance(raw, dict):
        return None
    value = raw.get("value")
    return value if isinstance(value, str) and value else None


def _qid_from_binding(raw: Any) -> str | None:
    value = _value_from_binding(raw)
    if value is None:
        return None
    qid = value.rsplit("/", 1)[-1]
    return qid if qid.startswith("Q") and qid[1:].isdigit() else None


def _parse_wikidata_datetime(raw: str | None) -> date | None:
    if raw is None or len(raw) < 10:
        return None
    try:
        return date.fromisoformat(raw[:10])
    except ValueError:
        return None


def _acquire_wyscout_inputs(
    cache_dir: Path,
) -> tuple[list[Any], list[Any], list[Any]]:
    client = WyscoutOpenDataClient(user_agent=USER_AGENT)
    matches_asset = client.fetch_asset(
        collection_id=FIGSHARE_COLLECTION_ID,
        article_title="Matches",
        cache_dir=cache_dir,
        keyword="England",
    )
    players_asset = client.fetch_asset(
        collection_id=FIGSHARE_COLLECTION_ID,
        article_title="Players",
        cache_dir=cache_dir,
    )
    teams_asset = client.fetch_asset(
        collection_id=FIGSHARE_COLLECTION_ID,
        article_title="Teams",
        cache_dir=cache_dir,
    )
    return (
        _load_wyscout_asset_json(
            matches_asset,
            cache_dir=cache_dir,
            expected_filename="matches_England.json",
        ),
        _load_wyscout_asset_json(players_asset, cache_dir=cache_dir),
        _load_wyscout_asset_json(teams_asset, cache_dir=cache_dir),
    )


def run_audit(*, cache_dir: Path) -> WyscoutWikidataOverlapReport:
    try:
        matches, players_payload, teams_payload = _acquire_wyscout_inputs(cache_dir)
    except (OSError, json.JSONDecodeError, WyscoutOpenDataError) as exc:
        raise WyscoutWikidataOverlapError(
            f"Wyscout acquisition failed: {exc}"
        ) from exc

    failures: list[str] = []
    roster_ids = roster_player_ids(matches)
    if len(roster_ids) != EXPECTED_ROSTER_PLAYERS:
        failures.append(
            f"Wyscout roster expected={EXPECTED_ROSTER_PLAYERS} "
            f"actual={len(roster_ids)}"
        )

    team_ids = _competition_team_ids(matches)
    if len(team_ids) != EXPECTED_TEAMS:
        failures.append(
            f"Wyscout teams expected={EXPECTED_TEAMS} actual={len(team_ids)}"
        )

    roster = build_wyscout_roster_profiles(
        matches_payload=matches,
        players_payload=players_payload,
        teams_payload=teams_payload,
    )
    team_names = _team_names_by_id(teams_payload)
    wikidata = WikidataLabClient(cache_dir=cache_dir / "wikidata")

    mappings: list[WikidataTeamMapping] = []
    for team_id in team_ids:
        name = team_names.get(team_id)
        if name is None:
            mappings.append(
                WikidataTeamMapping(
                    wyscout_team_id=team_id,
                    wyscout_name="",
                    canonical_team_context=None,
                    wikidata_qid=None,
                    wikidata_label=None,
                    status="wyscout_team_name_missing",
                    candidate_qids=(),
                    plausible_candidates=(),
                )
            )
            continue
        mappings.append(
            resolve_wikidata_team_candidate(
                wyscout_team_id=team_id,
                wyscout_name=name,
                search_results=wikidata.search_team(name),
            )
        )
        time.sleep(0.1)

    team_mappings = tuple(sorted(mappings, key=lambda item: item.wyscout_team_id))
    discovery_rows = wikidata.discover_players_for_teams(team_mappings)
    candidates_by_player = discover_exact_name_candidates(roster, discovery_rows)
    unique_candidate_qids = {
        qids[0] for qids in candidates_by_player.values() if len(qids) == 1
    }
    profiles_by_qid = wikidata.fetch_player_profiles(unique_candidate_qids)

    team_qid_to_context: dict[str, str] = {}
    for mapping in team_mappings:
        if (
            mapping.wikidata_qid is not None
            and mapping.canonical_team_context is not None
        ):
            team_qid_to_context[mapping.wikidata_qid] = mapping.canonical_team_context

    results = tuple(
        evaluate_player_overlap(
            player=player,
            candidate_qids=candidates_by_player.get(player.provider_player_id, ()),
            profiles_by_qid=profiles_by_qid,
            team_qid_to_context=team_qid_to_context,
        )
        for player in roster
    )

    state_counts = Counter(result.state for result in results)
    resolved_team_mappings = sum(
        mapping.status == "resolved" for mapping in team_mappings
    )
    if resolved_team_mappings < EXPECTED_TEAMS:
        failures.append(
            f"Wikidata team mappings resolved={resolved_team_mappings}/"
            f"{EXPECTED_TEAMS}; player coverage is therefore a lower bound"
        )

    return WyscoutWikidataOverlapReport(
        competition_code=COMPETITION_CODE,
        season_label=SEASON_LABEL,
        wyscout_roster_total=len(roster_ids),
        wyscout_profiles_available=len(roster),
        wyscout_profiles_missing=len(roster_ids) - len(roster),
        team_total=len(team_ids),
        team_mappings_resolved=resolved_team_mappings,
        team_mappings_unresolved=len(team_mappings) - resolved_team_mappings,
        wikidata_discovery_rows=len(discovery_rows),
        wikidata_discovery_entities=len({row.qid for row in discovery_rows}),
        players_with_exact_name_candidate=len(candidates_by_player),
        players_with_unique_candidate=sum(
            len(qids) == 1 for qids in candidates_by_player.values()
        ),
        wikidata_entities_loaded=len(profiles_by_qid),
        wikidata_exact_dob_coverage=sum(
            result.wikidata_has_exact_dob for result in results
        ),
        wikidata_citizenship_coverage=sum(
            result.wikidata_has_citizenship for result in results
        ),
        wikidata_position_coverage=sum(
            result.wikidata_has_position for result in results
        ),
        wikidata_bounded_team_context_coverage=sum(
            result.wikidata_has_bounded_team_context for result in results
        ),
        candidate_state_counts=dict(sorted(state_counts.items())),
        results=results,
        team_mappings=team_mappings,
        failures=tuple(failures),
    )


def _report_payload(report: WyscoutWikidataOverlapReport) -> dict[str, Any]:
    payload = asdict(report)
    payload["status"] = "PASS" if report.passed else "PARTIAL"
    payload["methodology"] = {
        "wyscout_source": "official Figshare collection 4415000, CC BY 4.0",
        "wikidata_source": "official MediaWiki API + WDQS, CC0",
        "player_discovery": (
            "P54 membership in deterministically resolved 2017/18 ENG_PL clubs"
        ),
        "name_matching": (
            "exact deterministic normalized names over source-exposed "
            "Wyscout variants"
        ),
        "identity_promotion": "none; no PlayerCrosswalk writes",
        "shared_match_requirement": (
            "not satisfiable by Wikidata profile evidence"
        ),
    }
    payload["examples"] = {
        "review_required": [
            asdict(result)
            for result in report.results
            if result.state == "review_required"
        ][:_MAX_EXAMPLES],
        "conflict": [
            asdict(result) for result in report.results if result.state == "conflict"
        ][:_MAX_EXAMPLES],
        "unmatched": [
            asdict(result)
            for result in report.results
            if result.state
            in {"no_exact_name_candidate", "ambiguous_exact_name_candidates"}
        ][:_MAX_EXAMPLES],
    }
    return payload


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Audit real Wyscout ENG_PL 2017/18 player profiles against Wikidata."
        )
    )
    parser.add_argument("--cache-dir", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    try:
        report = run_audit(cache_dir=args.cache_dir)
    except WyscoutWikidataOverlapError as exc:
        raise SystemExit(f"WYSCOUT x WIKIDATA: FAIL - {exc}") from exc

    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(
        json.dumps(
            _report_payload(report),
            indent=2,
            sort_keys=True,
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    print(
        "WYSCOUT x WIKIDATA: "
        f"{'PASS' if report.passed else 'PARTIAL'} "
        f"roster={report.wyscout_roster_total} "
        f"teams={report.team_mappings_resolved}/{report.team_total} "
        f"exact_name={report.players_with_exact_name_candidate} "
        f"unique={report.players_with_unique_candidate} "
        f"states={report.candidate_state_counts}"
    )
    print(f"REPORT: {args.report}")


if __name__ == "__main__":
    main()
