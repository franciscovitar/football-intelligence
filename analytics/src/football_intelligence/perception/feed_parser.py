"""Small RSS 2.0 / Atom parser for repository-controlled perception feeds."""

from __future__ import annotations

import html
import re
import xml.etree.ElementTree as ET
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from html.parser import HTMLParser
from urllib.parse import urljoin

from football_intelligence.perception.models import FeedItem

_WHITESPACE_RE = re.compile(r"\s+")


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        self.parts.append(data)


def clean_feed_text(value: str | None) -> str | None:
    if value is None:
        return None
    parser = _TextExtractor()
    try:
        parser.feed(html.unescape(value))
        parser.close()
        cleaned = _WHITESPACE_RE.sub(" ", " ".join(parser.parts)).strip()
    except Exception:
        cleaned = _WHITESPACE_RE.sub(" ", html.unescape(value)).strip()
    return cleaned or None


def parse_feed(payload: bytes, *, base_url: str) -> tuple[FeedItem, ...]:
    try:
        root = ET.fromstring(payload)
    except ET.ParseError as exc:
        raise ValueError("feed XML is malformed") from exc

    root_name = _local_name(root.tag)
    if root_name in {"rss", "rdf"}:
        return _parse_rss(root, base_url=base_url)
    if root_name == "feed":
        return _parse_atom(root, base_url=base_url)
    raise ValueError(f"unsupported feed root: {root_name}")


def _parse_rss(root: ET.Element, *, base_url: str) -> tuple[FeedItem, ...]:
    items: list[FeedItem] = []
    for node in root.iter():
        if _local_name(node.tag) != "item":
            continue
        title = clean_feed_text(_child_text(node, "title"))
        link = clean_feed_text(_child_text(node, "link"))
        if not title or not link:
            continue
        guid = clean_feed_text(_child_text(node, "guid"))
        excerpt = clean_feed_text(
            _child_text(node, "description")
            or _child_text(node, "summary")
            or _child_text(node, "content")
        )
        date_raw = (
            _child_text(node, "pubDate")
            or _child_text(node, "published")
            or _child_text(node, "date")
        )
        items.append(
            FeedItem(
                external_id=guid or link,
                url=urljoin(base_url, link),
                title=title,
                excerpt=excerpt,
                published_at=parse_feed_datetime(date_raw),
                raw_metadata={"feed_format": "rss"},
            )
        )
    return tuple(items)


def _parse_atom(root: ET.Element, *, base_url: str) -> tuple[FeedItem, ...]:
    items: list[FeedItem] = []
    for entry in root:
        if _local_name(entry.tag) != "entry":
            continue
        title = clean_feed_text(_child_text(entry, "title"))
        link = _atom_link(entry)
        if not title or not link:
            continue
        external_id = clean_feed_text(_child_text(entry, "id")) or link
        excerpt = clean_feed_text(_child_text(entry, "summary") or _child_text(entry, "content"))
        date_raw = _child_text(entry, "published") or _child_text(entry, "updated")
        items.append(
            FeedItem(
                external_id=external_id,
                url=urljoin(base_url, link),
                title=title,
                excerpt=excerpt,
                published_at=parse_feed_datetime(date_raw),
                raw_metadata={"feed_format": "atom"},
            )
        )
    return tuple(items)


def parse_feed_datetime(value: str | None) -> datetime | None:
    if not value or not value.strip():
        return None
    candidate = value.strip()
    try:
        parsed = parsedate_to_datetime(candidate)
    except (TypeError, ValueError):
        try:
            parsed = datetime.fromisoformat(candidate.replace("Z", "+00:00"))
        except ValueError:
            return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _atom_link(entry: ET.Element) -> str | None:
    fallback: str | None = None
    for child in entry:
        if _local_name(child.tag) != "link":
            continue
        href = child.attrib.get("href")
        if not href:
            continue
        if fallback is None:
            fallback = href
        if child.attrib.get("rel", "alternate") == "alternate":
            return href
    return fallback


def _child_text(node: ET.Element, name: str) -> str | None:
    for child in node:
        if _local_name(child.tag) != name:
            continue
        if list(child):
            return "".join(child.itertext())
        return child.text
    return None


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1].split(":", 1)[-1]
