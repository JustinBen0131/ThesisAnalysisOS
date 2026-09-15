"""Small shared helpers: errors, a JSON Schema subset, ids, sanitising.

Standard library only. Python 3.9 compatible.
"""

from __future__ import annotations

import re
import secrets
from typing import Any, Dict, List, Optional


class TaosError(RuntimeError):
    """A user-facing failure. The CLI prints the message and exits 1."""


URL_RE = re.compile(r"https?://\S+")
_SLUG_STRIP = re.compile(r"[^a-z0-9]+")


def short_id(prefix: str) -> str:
    """`prefix` + 10 hex characters, e.g. ``clm_3f9a1c2b4d``."""
    return "{0}{1}".format(prefix, secrets.token_hex(5))


def slugify(text: str, max_len: int = 60) -> str:
    value = _SLUG_STRIP.sub("-", str(text).strip().lower()).strip("-")
    if not value:
        value = "item"
    return value[:max_len].strip("-")


def strip_secrets(text: str, patterns: Optional[List[str]] = None) -> str:
    """Remove URLs and anything matching a secret pattern from free text."""
    cleaned = URL_RE.sub("[url]", str(text))
    for pattern in patterns or []:
        try:
            cleaned = re.sub(pattern, "[redacted]", cleaned, flags=re.IGNORECASE)
        except re.error:
            continue
    return cleaned


def truncate(text: str, limit: int) -> str:
    value = re.sub(r"\s+", " ", str(text)).strip()
    return value[:limit]


# --------------------------------------------------------------------------
# JSON Schema subset
# --------------------------------------------------------------------------

_TYPES = {
    "object": dict,
    "array": list,
    "string": str,
    "boolean": bool,
    "number": (int, float),
    "integer": int,
    "null": type(None),
}


def _type_ok(value: Any, expected: str) -> bool:
    if expected not in _TYPES:
        return True
    if expected == "boolean":
        return isinstance(value, bool)
    if expected in ("number", "integer") and isinstance(value, bool):
        return False
    return isinstance(value, _TYPES[expected])


def validate_json_schema(value: Any, schema: Dict[str, Any], path: str = "$") -> List[str]:
    """Validate `value` against a supported subset of JSON Schema 2020-12.

    Supported: type, required, properties, additionalProperties(False), enum,
    const, pattern, minLength, maxLength, minItems, maxItems, uniqueItems,
    items, minimum, maximum. Returns a list of human-readable problems.
    """
    problems: List[str] = []
    if not isinstance(schema, dict):
        return problems

    expected = schema.get("type")
    if expected is not None:
        options = expected if isinstance(expected, list) else [expected]
        if not any(_type_ok(value, option) for option in options):
            problems.append("{0} must be of type {1}".format(path, " or ".join(options)))
            return problems

    if "const" in schema and value != schema["const"]:
        problems.append("{0} must equal {1!r}".format(path, schema["const"]))
    if "enum" in schema and value not in schema["enum"]:
        problems.append("{0} must be one of {1}".format(path, schema["enum"]))

    if isinstance(value, str):
        pattern = schema.get("pattern")
        if pattern and re.search(pattern, value) is None:
            problems.append("{0} does not match {1}".format(path, pattern))
        if "minLength" in schema and len(value) < schema["minLength"]:
            problems.append("{0} must be at least {1} characters".format(path, schema["minLength"]))
        if "maxLength" in schema and len(value) > schema["maxLength"]:
            problems.append("{0} must be at most {1} characters".format(path, schema["maxLength"]))

    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if "minimum" in schema and value < schema["minimum"]:
            problems.append("{0} must be >= {1}".format(path, schema["minimum"]))
        if "maximum" in schema and value > schema["maximum"]:
            problems.append("{0} must be <= {1}".format(path, schema["maximum"]))

    if isinstance(value, dict):
        for key in schema.get("required", []):
            if key not in value:
                problems.append("{0} is missing required field {1!r}".format(path, key))
        properties = schema.get("properties", {})
        if schema.get("additionalProperties") is False:
            for key in sorted(set(value) - set(properties)):
                problems.append("{0} has unexpected field {1!r}".format(path, key))
        for key, child in properties.items():
            if key in value:
                problems.extend(validate_json_schema(value[key], child, "{0}.{1}".format(path, key)))

    if isinstance(value, list):
        if "minItems" in schema and len(value) < schema["minItems"]:
            problems.append("{0} must contain at least {1} item(s)".format(path, schema["minItems"]))
        if "maxItems" in schema and len(value) > schema["maxItems"]:
            problems.append("{0} must contain at most {1} item(s)".format(path, schema["maxItems"]))
        if schema.get("uniqueItems"):
            seen = []
            for item in value:
                if item in seen:
                    problems.append("{0} items must be unique".format(path))
                    break
                seen.append(item)
        item_schema = schema.get("items")
        if isinstance(item_schema, dict):
            for index, item in enumerate(value):
                problems.extend(
                    validate_json_schema(item, item_schema, "{0}[{1}]".format(path, index))
                )
    return problems
