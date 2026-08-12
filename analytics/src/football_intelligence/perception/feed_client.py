"""Bounded HTTPS client for repository-controlled RSS/Atom feeds."""

from __future__ import annotations

import http.client
import ipaddress
import socket
from dataclasses import dataclass
from urllib.parse import urljoin, urlsplit

_REDIRECTS = {301, 302, 303, 307, 308}
_MAX_BYTES = 2_000_000
_MAX_REDIRECTS = 3
_TIMEOUT_SECONDS = 10.0
_USER_AGENT = "FootballIntelligence/1.0 perception-feed-reader"


@dataclass(frozen=True, slots=True)
class FetchResult:
    payload: bytes
    final_url: str
    http_status: int
    content_type: str | None


def validate_feed_url(url: str, *, resolve_dns: bool = True) -> None:
    parsed = urlsplit(url)
    if parsed.scheme.lower() != "https":
        raise ValueError("feed URL must use HTTPS")
    if not parsed.hostname:
        raise ValueError("feed URL must include a hostname")
    if parsed.username is not None or parsed.password is not None:
        raise ValueError("feed URL must not contain user information")
    try:
        port = parsed.port
    except ValueError as exc:
        raise ValueError("feed URL has an invalid port") from exc
    if port not in (None, 443):
        raise ValueError("feed URL must use the default HTTPS port")
    if resolve_dns:
        _validate_public_hostname(parsed.hostname)


def fetch_feed(
    url: str,
    *,
    timeout_seconds: float = _TIMEOUT_SECONDS,
    max_bytes: int = _MAX_BYTES,
    max_redirects: int = _MAX_REDIRECTS,
) -> FetchResult:
    current = url
    for redirect_count in range(max_redirects + 1):
        validate_feed_url(current)
        parsed = urlsplit(current)
        host = parsed.hostname
        assert host is not None
        path = parsed.path or "/"
        if parsed.query:
            path = f"{path}?{parsed.query}"

        connection = http.client.HTTPSConnection(host, port=443, timeout=timeout_seconds)
        try:
            connection.request(
                "GET",
                path,
                headers={
                    "Accept": (
                        "application/rss+xml, application/atom+xml, application/xml, text/xml;q=0.9"
                    ),
                    "User-Agent": _USER_AGENT,
                },
            )
            response = connection.getresponse()
            status = int(response.status)

            if status in _REDIRECTS:
                location = response.getheader("Location")
                response.read()
                if not location:
                    raise ValueError("feed redirect did not include Location")
                if redirect_count >= max_redirects:
                    raise ValueError("feed exceeded redirect limit")
                current = urljoin(current, location)
                continue

            if status != 200:
                response.read()
                raise ValueError(f"feed returned HTTP {status}")

            content_type = response.getheader("Content-Type")
            _validate_content_type(content_type)
            payload = response.read(max_bytes + 1)
            if len(payload) > max_bytes:
                raise ValueError("feed response exceeded size limit")
            return FetchResult(
                payload=payload,
                final_url=current,
                http_status=status,
                content_type=content_type,
            )
        finally:
            connection.close()

    raise ValueError("feed redirect loop")


def _validate_public_hostname(hostname: str) -> None:
    try:
        addresses = socket.getaddrinfo(hostname, 443, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise ValueError("feed hostname could not be resolved") from exc
    if not addresses:
        raise ValueError("feed hostname resolved to no addresses")
    for address in addresses:
        ip = ipaddress.ip_address(address[4][0])
        if not ip.is_global:
            raise ValueError("feed hostname resolved to a non-public address")


def _validate_content_type(value: str | None) -> None:
    if value is None:
        return
    media_type = value.split(";", 1)[0].strip().lower()
    if media_type == "text/html":
        raise ValueError("feed returned HTML instead of RSS/Atom")
    if not any(token in media_type for token in ("xml", "rss", "atom")):
        raise ValueError(f"unsupported feed content type: {media_type}")
