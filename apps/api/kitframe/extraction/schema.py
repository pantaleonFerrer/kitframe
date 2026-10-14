from __future__ import annotations

from typing import Any


def enforce_strict_schema(schema: dict[str, Any]) -> dict[str, Any]:
    """Ensure Mistral strict JSON schema rules (§8.1)."""
    out = dict(schema)
    _walk(out)
    return out


def _walk(node: Any) -> None:
    if not isinstance(node, dict):
        return
    t = node.get("type")
    if t == "object" or (isinstance(t, list) and "object" in t) or "properties" in node:
        props = node.setdefault("properties", {})
        node["additionalProperties"] = False
        node["required"] = list(props.keys())
        for child in props.values():
            _walk(child)
    if t == "array" or (isinstance(t, list) and "array" in t):
        items = node.get("items")
        if isinstance(items, dict):
            _walk(items)
    for key in ("anyOf", "oneOf", "allOf"):
        if key in node and isinstance(node[key], list):
            for child in node[key]:
                _walk(child)


def taxonomy_extraction_schema(taxonomy: dict[str, Any]) -> dict[str, Any]:
    field_props: dict[str, Any] = {}
    for field in taxonomy.get("fields") or []:
        key = field["key"]
        field_props[key] = {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "value": {"type": ["string", "number", "boolean", "null"]},
                "confidence": {"type": "number"},
                "source_quote": {"type": ["string", "null"]},
            },
            "required": ["value", "confidence", "source_quote"],
        }
    schema = {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "products": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "internal_reference": {"type": "string"},
                        "fields": {
                            "type": "object",
                            "additionalProperties": False,
                            "properties": field_props,
                            "required": list(field_props.keys()),
                        },
                        "variants": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "additionalProperties": False,
                                "properties": {
                                    "color": {"type": ["string", "null"]},
                                    "size": {"type": ["string", "null"]},
                                    "sku": {"type": "string"},
                                    "price_eur": {"type": ["string", "null"]},
                                },
                                "required": ["color", "size", "sku", "price_eur"],
                            },
                        },
                    },
                    "required": ["internal_reference", "fields", "variants"],
                },
            }
        },
        "required": ["products"],
    }
    return enforce_strict_schema(schema)


def copy_schema() -> dict[str, Any]:
    from kitframe.content.locales import CONTENT_LOCALES

    locale = {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "name": {"type": "string"},
            "description": {"type": "string"},
            "seo_title": {"type": "string"},
            "seo_meta": {"type": "string"},
            "seo_keywords": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["name", "description", "seo_title", "seo_meta", "seo_keywords"],
    }
    return enforce_strict_schema(
        {
            "type": "object",
            "additionalProperties": False,
            "properties": {loc: locale for loc in CONTENT_LOCALES},
            "required": list(CONTENT_LOCALES),
        }
    )


def alt_text_schema() -> dict[str, Any]:
    return enforce_strict_schema(
        {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "es": {"type": "string"},
                "ca": {"type": "string"},
                "en": {"type": "string"},
            },
            "required": ["es", "ca", "en"],
        }
    )


def assert_strict_schema(schema: dict[str, Any]) -> None:
    def check(node: Any, path: str) -> None:
        if not isinstance(node, dict):
            return
        if "properties" in node:
            assert node.get("additionalProperties") is False, f"{path}: additionalProperties"
            assert set(node.get("required") or []) == set(node["properties"].keys()), f"{path}: required"
            for k, v in node["properties"].items():
                check(v, f"{path}.{k}")
        if "items" in node and isinstance(node["items"], dict):
            check(node["items"], f"{path}[]")

    check(schema, "$")
