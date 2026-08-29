"""Loading, schema validation and cross-reference validation for publish packages."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from football_intelligence.publishing.schema_validation import (
    SchemaValidationError,
    validate_json_schema,
)

_REPO_ROOT = Path(__file__).resolve().parents[4]
DEFAULT_SCHEMA_PATH = _REPO_ROOT / "database" / "contracts" / "match-research-publish.schema.json"

JsonObject = dict[str, Any]


class MatchPublishPackageError(ValueError):
    """Raised when a package is syntactically valid JSON but semantically invalid."""


class PackageNotPublishableError(MatchPublishPackageError):
    """Raised when research QA has not explicitly passed."""


def load_match_publish_package(
    path: Path, *, schema_path: Path = DEFAULT_SCHEMA_PATH
) -> JsonObject:
    """Load a JSON package and validate both schema and V1 cross references."""

    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise MatchPublishPackageError(f"cannot load publish package {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise MatchPublishPackageError("publish package root must be a JSON object")
    payload: JsonObject = value
    validate_match_publish_package(payload, schema_path=schema_path)
    return payload


def validate_match_publish_package(
    payload: JsonObject, *, schema_path: Path = DEFAULT_SCHEMA_PATH
) -> None:
    """Validate the checked-in JSON Schema plus application-level references."""

    try:
        schema_value = json.loads(schema_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise MatchPublishPackageError(f"cannot load canonical publish schema: {exc}") from exc
    if not isinstance(schema_value, dict):
        raise MatchPublishPackageError("canonical publish schema root must be an object")
    try:
        validate_json_schema(payload, schema_value)
    except SchemaValidationError as exc:
        raise MatchPublishPackageError(f"schema validation failed: {exc}") from exc

    issues = _domain_issues(payload)
    if issues:
        raise MatchPublishPackageError("package reference validation failed: " + "; ".join(issues))


def require_publishable_package(payload: JsonObject) -> None:
    """Require the explicit research QA gate before any database mutation."""

    research = _object(payload, "research")
    qa_status = research.get("qa_status")
    if qa_status != "PASS":
        raise PackageNotPublishableError(
            f"research.qa_status must be 'PASS' to publish; got {qa_status!r}"
        )


def match_publish_package_digest(payload: JsonObject) -> str:
    """Return a stable SHA-256 over the canonical JSON representation."""

    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _domain_issues(payload: JsonObject) -> list[str]:
    issues: list[str] = []
    match = _object(payload, "match")
    teams = _object_list(payload, "teams")
    managers = _object_list(payload, "managers")
    players = _object_list(payload, "players")
    appearances = _object_list(payload, "appearances")
    team_stats = _object_list(payload, "team_stats")
    player_stats = _object_list(payload, "player_stats")
    sources = _object_list(payload, "sources")
    documents = _object_list(payload, "documents")
    evidence = _object_list(payload, "evidence")
    fan_themes = _object_list(payload, "fan_themes")
    team_reviews = _object_list(payload, "team_reviews")
    manager_reviews = _object_list(payload, "manager_reviews")
    player_reviews = _object_list(payload, "player_reviews")
    signals = _object_list(payload, "signals", required=False)
    match_review = _object(payload, "match_review")

    team_slugs = _unique_values(teams, "slug", "teams", issues)
    expected_teams = {match.get("home_team_slug"), match.get("away_team_slug")}
    if team_slugs != expected_teams:
        issues.append("teams must contain exactly match.home_team_slug and match.away_team_slug")

    manager_slugs = _unique_values(managers, "slug", "managers", issues)
    player_slugs = _unique_values(players, "slug", "players", issues)
    source_keys = _unique_values(sources, "key", "sources", issues)
    document_keys = _unique_values(documents, "key", "documents", issues)

    player_team: dict[Any, Any] = {item.get("slug"): item.get("team_slug") for item in players}
    manager_team: dict[Any, Any] = {item.get("slug"): item.get("team_slug") for item in managers}

    for index, manager in enumerate(managers):
        _require_member(manager.get("team_slug"), team_slugs, f"managers[{index}].team_slug", issues)
    for index, player in enumerate(players):
        _require_member(player.get("team_slug"), team_slugs, f"players[{index}].team_slug", issues)

    seen_appearances: set[Any] = set()
    for index, appearance in enumerate(appearances):
        player_slug = appearance.get("player_slug")
        team_slug = appearance.get("team_slug")
        _require_member(player_slug, player_slugs, f"appearances[{index}].player_slug", issues)
        _require_member(team_slug, team_slugs, f"appearances[{index}].team_slug", issues)
        if player_slug in seen_appearances:
            issues.append(f"appearances[{index}]: duplicate player_slug {player_slug!r}")
        seen_appearances.add(player_slug)
        if player_slug in player_team and player_team[player_slug] != team_slug:
            issues.append(f"appearances[{index}]: player/team affiliation disagrees with players[]")

    _validate_stat_references(
        team_stats,
        team_slugs=team_slugs,
        player_slugs=player_slugs,
        player_team=player_team,
        source_keys=source_keys,
        label="team_stats",
        issues=issues,
    )
    _validate_stat_references(
        player_stats,
        team_slugs=team_slugs,
        player_slugs=player_slugs,
        player_team=player_team,
        source_keys=source_keys,
        label="player_stats",
        issues=issues,
    )

    for index, document in enumerate(documents):
        _require_member(
            document.get("source_key"), source_keys, f"documents[{index}].source_key", issues
        )

    for index, item in enumerate(evidence):
        document_key = item.get("document_key")
        if document_key is not None:
            _require_member(document_key, document_keys, f"evidence[{index}].document_key", issues)
        _validate_entity_reference(
            item.get("entity_type"),
            item.get("entity_key"),
            match=match,
            team_slugs=team_slugs,
            manager_slugs=manager_slugs,
            player_slugs=player_slugs,
            path=f"evidence[{index}]",
            issues=issues,
        )

    for index, theme in enumerate(fan_themes):
        _validate_entity_reference(
            theme.get("entity_type"),
            theme.get("entity_key"),
            match=match,
            team_slugs=team_slugs,
            manager_slugs=manager_slugs,
            player_slugs=player_slugs,
            path=f"fan_themes[{index}]",
            issues=issues,
        )
        for document_key in _string_list(theme.get("document_keys")):
            _require_member(
                document_key,
                document_keys,
                f"fan_themes[{index}].document_keys",
                issues,
            )

    match_version = match_review.get("review_version")
    public_reviews = [*team_reviews, *manager_reviews, *player_reviews]
    for label, reviews in (
        ("team_reviews", team_reviews),
        ("manager_reviews", manager_reviews),
        ("player_reviews", player_reviews),
    ):
        seen_keys: set[Any] = set()
        identity_field = {
            "team_reviews": "team_slug",
            "manager_reviews": "manager_slug",
            "player_reviews": "player_slug",
        }[label]
        for index, review in enumerate(reviews):
            key = review.get(identity_field)
            if key in seen_keys:
                issues.append(f"{label}[{index}]: duplicate {identity_field} {key!r}")
            seen_keys.add(key)
            if review.get("review_version") != match_version:
                issues.append(
                    f"{label}[{index}].review_version must equal match_review.review_version"
                )
            if review.get("final_score") is None:
                issues.append(f"{label}[{index}].final_score cannot be null for publication")
            if review.get("confidence") is None:
                issues.append(f"{label}[{index}].confidence cannot be null for publication")

    if {review.get("team_slug") for review in team_reviews} != team_slugs:
        issues.append("team_reviews must contain exactly one review for each match team")

    for index, review in enumerate(manager_reviews):
        manager_slug = review.get("manager_slug")
        team_slug = review.get("team_slug")
        _require_member(manager_slug, manager_slugs, f"manager_reviews[{index}].manager_slug", issues)
        _require_member(team_slug, team_slugs, f"manager_reviews[{index}].team_slug", issues)
        if manager_slug in manager_team and manager_team[manager_slug] != team_slug:
            issues.append(f"manager_reviews[{index}]: manager/team affiliation disagrees")

    for index, review in enumerate(player_reviews):
        player_slug = review.get("player_slug")
        team_slug = review.get("team_slug")
        _require_member(player_slug, player_slugs, f"player_reviews[{index}].player_slug", issues)
        _require_member(team_slug, team_slugs, f"player_reviews[{index}].team_slug", issues)
        if player_slug not in seen_appearances:
            issues.append(f"player_reviews[{index}]: reviewed player has no appearance")
        if player_slug in player_team and player_team[player_slug] != team_slug:
            issues.append(f"player_reviews[{index}]: player/team affiliation disagrees")

    for document_key in _string_list(match_review.get("source_document_keys")):
        _require_member(document_key, document_keys, "match_review.source_document_keys", issues)

    for index, signal in enumerate(signals):
        _validate_entity_reference(
            signal.get("entity_type"),
            signal.get("entity_key"),
            match=match,
            team_slugs=team_slugs,
            manager_slugs=manager_slugs,
            player_slugs=player_slugs,
            path=f"signals[{index}]",
            issues=issues,
        )

    if match_version is None or not isinstance(match_version, int):
        issues.append("match_review.review_version must be an integer")
    if len(public_reviews) == 0:
        issues.append("package must contain public reviews")
    return issues


def _validate_stat_references(
    stats: list[JsonObject],
    *,
    team_slugs: set[Any],
    player_slugs: set[Any],
    player_team: dict[Any, Any],
    source_keys: set[Any],
    label: str,
    issues: list[str],
) -> None:
    for index, item in enumerate(stats):
        team_slug = item.get("team_slug")
        _require_member(team_slug, team_slugs, f"{label}[{index}].team_slug", issues)
        _require_member(item.get("source_key"), source_keys, f"{label}[{index}].source_key", issues)
        if label == "player_stats":
            player_slug = item.get("player_slug")
            _require_member(player_slug, player_slugs, f"{label}[{index}].player_slug", issues)
            if player_slug in player_team and player_team[player_slug] != team_slug:
                issues.append(f"{label}[{index}]: player/team affiliation disagrees")


def _validate_entity_reference(
    entity_type: Any,
    entity_key: Any,
    *,
    match: JsonObject,
    team_slugs: set[Any],
    manager_slugs: set[Any],
    player_slugs: set[Any],
    path: str,
    issues: list[str],
) -> None:
    members: set[Any]
    if entity_type == "TEAM":
        members = team_slugs
    elif entity_type == "MANAGER":
        members = manager_slugs
    elif entity_type == "PLAYER":
        members = player_slugs
    elif entity_type == "MATCH":
        members = {match.get("identity_key")}
    else:
        return
    _require_member(entity_key, members, f"{path}.entity_key", issues)


def _unique_values(
    items: list[JsonObject], field: str, label: str, issues: list[str]
) -> set[Any]:
    values: set[Any] = set()
    for index, item in enumerate(items):
        value = item.get(field)
        if value in values:
            issues.append(f"{label}[{index}]: duplicate {field} {value!r}")
        values.add(value)
    return values


def _require_member(value: Any, members: set[Any], path: str, issues: list[str]) -> None:
    if value not in members:
        issues.append(f"{path}: unknown reference {value!r}")


def _object(payload: JsonObject, key: str) -> JsonObject:
    value = payload.get(key)
    if not isinstance(value, dict):
        raise MatchPublishPackageError(f"{key} must be an object after schema validation")
    return value


def _object_list(payload: JsonObject, key: str, *, required: bool = True) -> list[JsonObject]:
    value = payload.get(key)
    if value is None and not required:
        return []
    if not isinstance(value, list) or not all(isinstance(item, dict) for item in value):
        raise MatchPublishPackageError(f"{key} must be a list of objects after schema validation")
    return value


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str)]
