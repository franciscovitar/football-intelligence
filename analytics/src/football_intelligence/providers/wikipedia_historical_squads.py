"""Conservative parsing for dated Wikipedia active-squad evidence.

Wikipedia is used here only as a source-scoped, historical membership signal.
The caller must supply the exact raw wikitext stored in one historical article
revision; this module never renders an old page with live template expansion
and never performs network I/O.

Evidence boundaries:

- only explicit active-squad headings are accepted;
- generic ``Players`` / notable-player / reserve / youth sections are rejected;
- one observation means "listed in this active-squad section at this revision",
  not AFA registration, match participation, or performance;
- a linked Wikipedia article is retained only when the link syntactically starts
  the player-name value.  Links appearing later in annotations (for example
  ``on loan from [[Club]]``) are never treated as player identity;
- a Wikipedia article -> Wikidata bridge is usable only when the resolved item
  is explicitly ``instance of (P31) human (Q5)``;
- Wikidata QIDs remain provider-native identifiers and are never canonical
  Football Intelligence player IDs.

Wikipedia text is reusable under Wikimedia's applicable CC BY-SA terms.  Any
retained evidence must preserve attribution/provenance metadata; this module
intentionally does not decide presentation-layer attribution mechanics.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Any

SOURCE_CODE = "wikipedia"
SOURCE_TYPE = "qualitative_structured"
LICENCE = "CC BY-SA 4.0"
ATTRIBUTION_REQUIRED = True
MEDIAWIKI_REVISIONS_REFERENCE = "https://www.mediawiki.org/wiki/API:Revisions"
WIKIMEDIA_TERMS_REFERENCE = "https://foundation.wikimedia.org/wiki/Policy:Terms_of_Use"
HUMAN_QID = "Q5"

_ACCEPTED_HEADINGS: dict[str, int] = {
    "current squad": 0,
    "first-team squad": 1,
    "first team squad": 1,
    "senior squad": 1,
    "first team": 1,
    "squad": 2,
}
_EXCLUDED_CHILD_HEADING_RE = re.compile(
    r"out on loan|loaned|reserve|reserves|youth|academy|other players|"
    r"former players|notable players",
    re.IGNORECASE,
)
_HEADING_RE = re.compile(r"(?m)^(={2,5})\s*(.*?)\s*\1\s*$")
_PLAYER_TEMPLATE_RE = re.compile(
    r"\{\{\s*(?:fs player|football squad player\d*|football squad player)\b(.*?)\}\}",
    re.IGNORECASE | re.DOTALL,
)
_NAME_FIELD_RE = re.compile(
    r"(?:^|\|)\s*name\s*=\s*(.*?)(?=(?:\n?\s*\|\s*[A-Za-z0-9_ -]+\s*=)|$)",
    re.IGNORECASE | re.DOTALL,
)
_LEADING_ARTICLE_LINK_RE = re.compile(
    r"^\s*'{0,5}\s*\[\[([^\]|#]+)(?:#[^\]|]*)?(?:\|[^\]]*)?\]\]",
    re.DOTALL,
)
_QID_RE = re.compile(r"^Q[1-9][0-9]*$")


class WikipediaHistoricalSquadError(ValueError):
    """Historical Wikipedia squad evidence violates the intake contract."""


@dataclass(frozen=True, slots=True)
class WikipediaSquadObservation:
    """One player-name row physically present in a historical article revision."""

    source_article_title: str
    revision_id: int
    revision_timestamp: str
    snapshot_target: str
    heading: str
    raw_name: str
    display_name: str
    player_article_title: str | None


@dataclass(frozen=True, slots=True)
class WikipediaSquadSnapshot:
    """The selected active-squad section from one immutable article revision."""

    source_article_title: str
    revision_id: int
    revision_timestamp: str
    snapshot_target: str
    heading: str
    observations: tuple[WikipediaSquadObservation, ...]


def parse_historical_active_squad_revision(
    wikitext: str,
    *,
    article_title: str,
    revision_id: int,
    revision_timestamp: str,
    snapshot_target: str,
) -> WikipediaSquadSnapshot | None:
    """Parse the best explicit active-squad section from exact revision wikitext.

    ``None`` means the supplied revision contains no accepted section with any
    usable player rows.  Missing evidence is deliberately not converted into an
    empty/zero roster claim.
    """

    _validate_revision_metadata(
        article_title=article_title,
        revision_id=revision_id,
        revision_timestamp=revision_timestamp,
        snapshot_target=snapshot_target,
    )
    if not isinstance(wikitext, str):
        raise WikipediaHistoricalSquadError("wikitext must be a string")

    headings = list(_HEADING_RE.finditer(wikitext))
    candidates: list[tuple[int, str, list[tuple[str, str, str | None]]]] = []

    for index, heading_match in enumerate(headings):
        raw_heading = _clean_wikitext_text(heading_match.group(2))
        heading_key = _normalize_heading(raw_heading)
        priority = _ACCEPTED_HEADINGS.get(heading_key)
        if priority is None:
            continue

        level = len(heading_match.group(1))
        section_end = len(wikitext)
        for later in headings[index + 1 :]:
            later_level = len(later.group(1))
            later_title = _clean_wikitext_text(later.group(2))
            if later_level <= level or (
                later_level > level and _EXCLUDED_CHILD_HEADING_RE.search(later_title)
            ):
                section_end = later.start()
                break

        body = wikitext[heading_match.end() : section_end]
        parsed_rows = _parse_player_rows(body)
        if parsed_rows:
            candidates.append((priority, raw_heading, parsed_rows))

    if not candidates:
        return None

    candidates.sort(key=lambda item: (item[0], -len(item[2]), item[1].casefold()))
    _, selected_heading, rows = candidates[0]
    observations = tuple(
        WikipediaSquadObservation(
            source_article_title=article_title.strip(),
            revision_id=revision_id,
            revision_timestamp=revision_timestamp.strip(),
            snapshot_target=snapshot_target.strip(),
            heading=selected_heading,
            raw_name=raw_name,
            display_name=display_name,
            player_article_title=article_target,
        )
        for raw_name, display_name, article_target in rows
    )
    return WikipediaSquadSnapshot(
        source_article_title=article_title.strip(),
        revision_id=revision_id,
        revision_timestamp=revision_timestamp.strip(),
        snapshot_target=snapshot_target.strip(),
        heading=selected_heading,
        observations=observations,
    )


def leading_player_article_title(raw_name_value: str) -> str | None:
    """Return a player article only when a wiki link starts the name value.

    This intentionally fails closed for plain-text player names followed by an
    annotation link, e.g. ``Lucas Lopez (on loan from [[CA Nueva Chicago]])``.
    """

    if not isinstance(raw_name_value, str):
        raise WikipediaHistoricalSquadError("raw player name must be a string")
    match = _LEADING_ARTICLE_LINK_RE.match(raw_name_value)
    if match is None:
        return None
    target = unicodedata.normalize("NFKC", match.group(1)).strip()
    return target or None


def wikidata_item_is_explicit_human(payload: dict[str, Any], *, expected_qid: str) -> bool:
    """Return true only for a non-missing item with non-deprecated P31=Q5."""

    qid = expected_qid.strip()
    if not _QID_RE.fullmatch(qid):
        raise WikipediaHistoricalSquadError(f"invalid Wikidata item id {expected_qid!r}")
    entities = payload.get("entities")
    if not isinstance(entities, dict):
        raise WikipediaHistoricalSquadError("Wikidata payload must contain an entities object")
    entity = entities.get(qid)
    if not isinstance(entity, dict) or entity.get("missing") is not None:
        return False
    claims = entity.get("claims")
    if not isinstance(claims, dict):
        return False
    statements = claims.get("P31")
    if not isinstance(statements, list):
        return False

    for statement in statements:
        if not isinstance(statement, dict) or statement.get("rank") == "deprecated":
            continue
        mainsnak = statement.get("mainsnak")
        if not isinstance(mainsnak, dict) or mainsnak.get("snaktype") != "value":
            continue
        datavalue = mainsnak.get("datavalue")
        if not isinstance(datavalue, dict):
            continue
        value = datavalue.get("value")
        if isinstance(value, dict) and value.get("id") == HUMAN_QID:
            return True
    return False


def _parse_player_rows(section_body: str) -> list[tuple[str, str, str | None]]:
    rows: dict[str, tuple[str, str, str | None]] = {}
    for block in _PLAYER_TEMPLATE_RE.findall(section_body):
        name_match = _NAME_FIELD_RE.search(block)
        if name_match is None:
            continue
        raw_name = name_match.group(1).strip()
        display_name = _clean_wikitext_text(raw_name)
        if not display_name or len(display_name) > 100:
            continue
        article_target = leading_player_article_title(raw_name)
        dedup_key = _normalize_identity_key(article_target or display_name)
        rows[dedup_key] = (raw_name, display_name, article_target)
    return sorted(rows.values(), key=lambda item: item[1].casefold())


def _validate_revision_metadata(
    *,
    article_title: str,
    revision_id: int,
    revision_timestamp: str,
    snapshot_target: str,
) -> None:
    if not isinstance(article_title, str) or not article_title.strip():
        raise WikipediaHistoricalSquadError("article_title must be a non-blank string")
    if not isinstance(revision_id, int) or isinstance(revision_id, bool) or revision_id <= 0:
        raise WikipediaHistoricalSquadError("revision_id must be a positive integer")
    for field_name, value in (
        ("revision_timestamp", revision_timestamp),
        ("snapshot_target", snapshot_target),
    ):
        if not isinstance(value, str) or not value.strip():
            raise WikipediaHistoricalSquadError(f"{field_name} must be a non-blank string")


def _clean_wikitext_text(value: str) -> str:
    value = re.sub(
        r"<ref\b[^>]*>.*?</ref>|<ref\b[^>]*/>",
        "",
        value,
        flags=re.IGNORECASE | re.DOTALL,
    )
    value = re.sub(r"\[\[([^\]|]+)\|([^\]]+)\]\]", r"\2", value)
    value = re.sub(r"\[\[([^\]]+)\]\]", r"\1", value)
    value = re.sub(r"'{2,5}", "", value)
    value = re.sub(r"\{\{[^{}]*\}\}", "", value)
    value = unicodedata.normalize("NFKC", value)
    return re.sub(r"\s+", " ", value).strip(" *†‡\n\t")


def _normalize_heading(value: str) -> str:
    return value.casefold().replace("–", "-").replace("—", "-").strip()


def _normalize_identity_key(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value)
    return re.sub(r"\s+", " ", normalized).strip().casefold()
