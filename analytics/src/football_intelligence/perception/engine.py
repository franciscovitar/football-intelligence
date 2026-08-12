"""Deterministic normalization, deduplication keys, and player linking."""

from __future__ import annotations

import hashlib
import re
import unicodedata
from collections import defaultdict
from collections.abc import Sequence
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from football_intelligence.perception.models import (
    EvidenceDraft,
    FeedItem,
    LinkablePlayer,
    PlayerMention,
)

MODEL_VERSION = "perception-v1.0"
_TRACKING_KEYS = {"fbclid", "gclid", "dclid", "msclkid"}
_SPACE_RE = re.compile(r"\s+")


def canonicalize_article_url(url: str) -> str:
    parsed = urlsplit(url.strip())
    scheme = parsed.scheme.lower()
    if scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("evidence URL must be absolute HTTP(S)")
    if parsed.username is not None or parsed.password is not None:
        raise ValueError("evidence URL must not contain user information")

    host = parsed.hostname.lower()
    try:
        port = parsed.port
    except ValueError as exc:
        raise ValueError("evidence URL has invalid port") from exc
    if port and not ((scheme == "http" and port == 80) or (scheme == "https" and port == 443)):
        host = f"{host}:{port}"

    query = [
        (key, value)
        for key, value in parse_qsl(parsed.query, keep_blank_values=True)
        if not key.lower().startswith("utm_") and key.lower() not in _TRACKING_KEYS
    ]
    query.sort()
    return urlunsplit((scheme, host, parsed.path or "/", urlencode(query, doseq=True), ""))


def content_fingerprint(title: str, excerpt: str | None) -> str:
    normalized = "|".join((_normalize_text(title), _normalize_text(excerpt or "")))
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def build_evidence(item: FeedItem) -> EvidenceDraft:
    return EvidenceDraft(
        external_id=item.external_id.strip() if item.external_id else None,
        canonical_url=canonicalize_article_url(item.url),
        title=_collapse(item.title),
        excerpt=_collapse(item.excerpt) if item.excerpt else None,
        published_at=item.published_at,
        content_sha256=content_fingerprint(item.title, item.excerpt),
        raw_metadata=item.raw_metadata,
    )


def link_players(
    evidence: EvidenceDraft,
    players: Sequence[LinkablePlayer],
) -> tuple[PlayerMention, ...]:
    players_by_name: dict[str, list[LinkablePlayer]] = defaultdict(list)
    for player in players:
        normalized_name = _normalize_text(player.display_name)
        if len(normalized_name) >= 4:
            players_by_name[normalized_name].append(player)

    haystack = _normalize_text(f"{evidence.title} {evidence.excerpt or ''}")
    context = _collapse(f"{evidence.title} {evidence.excerpt or ''}")[:400]
    mentions: list[PlayerMention] = []

    for normalized_name, candidates in players_by_name.items():
        if len(candidates) != 1:
            continue
        pattern = rf"(?<!\w){re.escape(normalized_name)}(?!\w)"
        if not re.search(pattern, haystack):
            continue
        player = candidates[0]
        mentions.append(
            PlayerMention(
                player_id=player.player_id,
                matched_text=player.display_name,
                match_method="display_name_exact",
                context_excerpt=context or None,
            )
        )

    return tuple(sorted(mentions, key=lambda item: item.player_id))


def _normalize_text(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value)
    without_marks = "".join(char for char in decomposed if not unicodedata.combining(char))
    return _SPACE_RE.sub(" ", without_marks.casefold()).strip()


def _collapse(value: str) -> str:
    return _SPACE_RE.sub(" ", value).strip()
