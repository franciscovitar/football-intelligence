from __future__ import annotations

from datetime import UTC, datetime

import pytest

from football_intelligence.perception.engine import (
    build_evidence,
    canonicalize_article_url,
    content_fingerprint,
    link_players,
)
from football_intelligence.perception.feed_client import validate_feed_url
from football_intelligence.perception.feed_parser import (
    clean_feed_text,
    parse_feed,
    parse_feed_datetime,
)
from football_intelligence.perception.models import FeedItem, LinkablePlayer


def test_rss_parser_extracts_supported_fields() -> None:
    payload = b"""<?xml version="1.0"?>
    <rss version="2.0"><channel><item>
      <title>Lionel Messi shines</title>
      <link>https://example.com/story?utm_source=test</link>
      <guid>story-1</guid>
      <pubDate>Mon, 10 Aug 2026 12:30:00 GMT</pubDate>
      <description><![CDATA[<p>Strong display &amp; two assists.</p>]]></description>
    </item></channel></rss>"""
    items = parse_feed(payload, base_url="https://example.com/feed")
    assert len(items) == 1
    assert items[0].external_id == "story-1"
    assert items[0].title == "Lionel Messi shines"
    assert items[0].excerpt == "Strong display & two assists."
    assert items[0].published_at == datetime(2026, 8, 10, 12, 30, tzinfo=UTC)


def test_atom_parser_uses_alternate_link_and_updated() -> None:
    payload = b"""<?xml version="1.0"?>
    <feed xmlns="http://www.w3.org/2005/Atom"><entry>
      <id>tag:example,2026:2</id>
      <title>Player profile</title>
      <link rel="alternate" href="/profile"/>
      <updated>2026-08-11T09:15:00Z</updated>
      <summary>Measured praise.</summary>
    </entry></feed>"""
    items = parse_feed(payload, base_url="https://example.com/feed")
    assert len(items) == 1
    assert items[0].url == "https://example.com/profile"
    assert items[0].published_at == datetime(2026, 8, 11, 9, 15, tzinfo=UTC)


def test_text_and_date_parsing_are_defensive() -> None:
    assert clean_feed_text("<b> Great&nbsp; player </b>") == "Great player"
    assert parse_feed_datetime("not a date") is None


def test_canonical_url_removes_tracking_and_fragment() -> None:
    value = canonicalize_article_url(
        "HTTPS://Example.com/story?utm_source=x&b=2&a=1&fbclid=abc#section"
    )
    assert value == "https://example.com/story?a=1&b=2"


def test_content_fingerprint_is_stable_under_spacing_and_case() -> None:
    left = content_fingerprint(" Great Player ", "Two   assists")
    right = content_fingerprint("great player", "two assists")
    assert left == right


def test_exact_player_linking_excludes_ambiguous_names() -> None:
    evidence = build_evidence(
        FeedItem(
            external_id="1",
            url="https://example.com/one",
            title="Lionel Messi and Alex Smith impressed",
            excerpt="Lionel Messi created two chances.",
            published_at=None,
            raw_metadata={},
        )
    )
    players = (
        LinkablePlayer(1, "Lionel Messi"),
        LinkablePlayer(2, "Alex Smith"),
        LinkablePlayer(3, "Alex Smith"),
    )
    mentions = link_players(evidence, players)
    assert [(item.player_id, item.matched_text) for item in mentions] == [(1, "Lionel Messi")]


@pytest.mark.parametrize(
    "url",
    (
        "http://example.com/feed",
        "https://user:pass@example.com/feed",
        "https://example.com:8443/feed",
    ),
)
def test_feed_url_structure_rejects_unsafe_shapes(url: str) -> None:
    with pytest.raises(ValueError):
        validate_feed_url(url, resolve_dns=False)


def test_feed_url_structure_accepts_https_default_port() -> None:
    validate_feed_url("https://example.com/feed.xml", resolve_dns=False)
