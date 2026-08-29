"""Small JSON-Schema validator for the checked-in match publish contract.

The repository intentionally avoids a new runtime dependency for one private
contract. This module implements only the Draft 2020-12 keywords used by
`database/contracts/match-research-publish.schema.json` and fails closed on
unsupported schema constructs.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any, TypeGuard
from urllib.parse import urlsplit


class SchemaValidationError(ValueError):
    """Raised when a publish package does not conform to its JSON Schema."""

    def __init__(self, issues: Sequence[str]) -> None:
        self.issues = tuple(issues)
        super().__init__("; ".join(self.issues))


def validate_json_schema(instance: Any, schema: Mapping[str, Any]) -> None:
    """Validate ``instance`` against the subset of JSON Schema used by V1."""

    issues: list[str] = []
    _validate(instance, schema, schema, "$", issues)
    if issues:
        raise SchemaValidationError(issues)


def _validate(
    value: Any,
    node: Mapping[str, Any],
    root: Mapping[str, Any],
    path: str,
    issues: list[str],
) -> None:
    if "$ref" in node:
        ref = node["$ref"]
        if not isinstance(ref, str) or not ref.startswith("#/"):
            raise RuntimeError(f"unsupported JSON Schema ref: {ref!r}")
        target: Any = root
        for part in ref[2:].split("/"):
            if not isinstance(target, Mapping) or part not in target:
                raise RuntimeError(f"unresolvable JSON Schema ref: {ref}")
            target = target[part]
        if not isinstance(target, Mapping):
            raise RuntimeError(f"JSON Schema ref does not target an object: {ref}")
        _validate(value, target, root, path, issues)
        return

    all_of = node.get("allOf")
    if all_of is not None:
        if not isinstance(all_of, list):
            raise RuntimeError("JSON Schema allOf must be a list")
        for child in all_of:
            if not isinstance(child, Mapping):
                raise RuntimeError("JSON Schema allOf child must be an object")
            _validate(value, child, root, path, issues)

    if "const" in node and value != node["const"]:
        issues.append(f"{path}: expected constant {node['const']!r}, got {value!r}")
        return

    enum = node.get("enum")
    if enum is not None:
        if not isinstance(enum, list):
            raise RuntimeError("JSON Schema enum must be a list")
        if value not in enum:
            issues.append(f"{path}: value {value!r} is not one of {enum!r}")
            return

    expected_type = node.get("type")
    if expected_type is not None and not _matches_type(value, expected_type):
        issues.append(f"{path}: expected type {expected_type!r}, got {_type_name(value)}")
        return

    if isinstance(value, Mapping):
        _validate_object(value, node, root, path, issues)
    elif isinstance(value, list):
        _validate_array(value, node, root, path, issues)
    elif isinstance(value, str):
        _validate_string(value, node, path, issues)
    elif _is_number(value):
        _validate_number(value, node, path, issues)


def _validate_object(
    value: Mapping[str, Any],
    node: Mapping[str, Any],
    root: Mapping[str, Any],
    path: str,
    issues: list[str],
) -> None:
    required = node.get("required", [])
    if not isinstance(required, list) or not all(isinstance(item, str) for item in required):
        raise RuntimeError("JSON Schema required must be a list of strings")
    for key in required:
        if key not in value:
            issues.append(f"{path}: missing required property {key!r}")

    properties = node.get("properties", {})
    if not isinstance(properties, Mapping):
        raise RuntimeError("JSON Schema properties must be an object")

    additional = node.get("additionalProperties", True)
    for key, child_value in value.items():
        child_path = f"{path}.{key}"
        child_schema = properties.get(key)
        if child_schema is not None:
            if not isinstance(child_schema, Mapping):
                raise RuntimeError(f"JSON Schema property {key!r} must be an object")
            _validate(child_value, child_schema, root, child_path, issues)
            continue
        if additional is False:
            issues.append(f"{path}: unexpected property {key!r}")
        elif isinstance(additional, Mapping):
            _validate(child_value, additional, root, child_path, issues)
        elif additional is not True:
            raise RuntimeError("unsupported JSON Schema additionalProperties value")


def _validate_array(
    value: list[Any],
    node: Mapping[str, Any],
    root: Mapping[str, Any],
    path: str,
    issues: list[str],
) -> None:
    min_items = node.get("minItems")
    max_items = node.get("maxItems")
    if isinstance(min_items, int) and len(value) < min_items:
        issues.append(f"{path}: expected at least {min_items} items, got {len(value)}")
    if isinstance(max_items, int) and len(value) > max_items:
        issues.append(f"{path}: expected at most {max_items} items, got {len(value)}")

    if node.get("uniqueItems") is True:
        normalized = [repr(item) for item in value]
        if len(set(normalized)) != len(normalized):
            issues.append(f"{path}: items must be unique")

    items = node.get("items")
    if items is not None:
        if not isinstance(items, Mapping):
            raise RuntimeError("JSON Schema items must be an object")
        for index, item in enumerate(value):
            _validate(item, items, root, f"{path}[{index}]", issues)


def _validate_string(value: str, node: Mapping[str, Any], path: str, issues: list[str]) -> None:
    min_length = node.get("minLength")
    if isinstance(min_length, int) and len(value) < min_length:
        issues.append(f"{path}: expected length >= {min_length}")

    pattern = node.get("pattern")
    if isinstance(pattern, str) and re.fullmatch(pattern, value) is None:
        issues.append(f"{path}: value does not match pattern {pattern!r}")

    format_name = node.get("format")
    if format_name is None:
        return
    if format_name == "date-time":
        try:
            parsed_datetime = datetime.fromisoformat(value.replace("Z", "+00:00"))
            if parsed_datetime.tzinfo is None:
                raise ValueError("timezone required")
        except ValueError:
            issues.append(f"{path}: invalid RFC3339-style date-time {value!r}")
    elif format_name == "date":
        try:
            date.fromisoformat(value)
        except ValueError:
            issues.append(f"{path}: invalid ISO date {value!r}")
    elif format_name == "uri":
        parsed_uri = urlsplit(value)
        if not parsed_uri.scheme or (
            parsed_uri.scheme in {"http", "https"} and not parsed_uri.netloc
        ):
            issues.append(f"{path}: invalid URI {value!r}")
    else:
        raise RuntimeError(f"unsupported JSON Schema format: {format_name!r}")


def _validate_number(
    value: int | float, node: Mapping[str, Any], path: str, issues: list[str]
) -> None:
    minimum = node.get("minimum")
    maximum = node.get("maximum")
    if _is_number(minimum) and value < minimum:
        issues.append(f"{path}: value {value!r} is below minimum {minimum!r}")
    if _is_number(maximum) and value > maximum:
        issues.append(f"{path}: value {value!r} is above maximum {maximum!r}")

    multiple_of = node.get("multipleOf")
    if _is_number(multiple_of):
        try:
            number = Decimal(str(value))
            unit = Decimal(str(multiple_of))
            if unit == 0 or number % unit != 0:
                issues.append(f"{path}: value {value!r} is not a multiple of {multiple_of!r}")
        except InvalidOperation:
            issues.append(f"{path}: invalid numeric value {value!r}")


def _matches_type(value: Any, expected: Any) -> bool:
    if isinstance(expected, str):
        return _matches_single_type(value, expected)
    if isinstance(expected, list) and all(isinstance(item, str) for item in expected):
        return any(_matches_single_type(value, item) for item in expected)
    raise RuntimeError(f"unsupported JSON Schema type declaration: {expected!r}")


def _matches_single_type(value: Any, expected: str) -> bool:
    if expected == "null":
        return value is None
    if expected == "object":
        return isinstance(value, Mapping)
    if expected == "array":
        return isinstance(value, list)
    if expected == "string":
        return isinstance(value, str)
    if expected == "boolean":
        return isinstance(value, bool)
    if expected == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if expected == "number":
        return _is_number(value)
    raise RuntimeError(f"unsupported JSON Schema primitive type: {expected!r}")


def _is_number(value: Any) -> TypeGuard[int | float]:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _type_name(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, Mapping):
        return "object"
    if isinstance(value, list):
        return "array"
    if isinstance(value, str):
        return "string"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        return "number"
    return type(value).__name__
