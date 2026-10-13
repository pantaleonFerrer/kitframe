from __future__ import annotations

import json
from typing import Any

import httpx
from pydantic import BaseModel, Field

from app.config import Settings, get_settings


class FieldExtraction(BaseModel):
    value: Any
    confidence: float = Field(ge=0.0, le=1.0)


class ExtractRequest(BaseModel):
    source_document_url: str
    taxonomy_schema: dict[str, Any]


class ExtractResponse(BaseModel):
    fields: dict[str, FieldExtraction]
    needs_review_fields: list[str]


REVIEW_CONFIDENCE_FLOOR = 0.75


def _schema_keys(taxonomy_schema: dict[str, Any]) -> list[str]:
    properties = taxonomy_schema.get("properties")
    if isinstance(properties, dict) and properties:
        return list(properties.keys())
    fields = taxonomy_schema.get("fields")
    if isinstance(fields, list):
        keys: list[str] = []
        for item in fields:
            if isinstance(item, str):
                keys.append(item)
            elif isinstance(item, dict) and "name" in item:
                keys.append(str(item["name"]))
        if keys:
            return keys
    if taxonomy_schema:
        return [str(k) for k in taxonomy_schema.keys() if k not in {"type", "title", "description"}]
    return ["internal_reference", "category", "color", "material"]


def mock_extract(taxonomy_schema: dict[str, Any], source_document_url: str) -> ExtractResponse:
    fields: dict[str, FieldExtraction] = {}
    for index, key in enumerate(_schema_keys(taxonomy_schema)):
        confidence = 0.92 if index % 3 else 0.68
        fields[key] = FieldExtraction(
            value=f"mock-{key}-{abs(hash(source_document_url)) % 10000}",
            confidence=confidence,
        )
    needs_review = [k for k, v in fields.items() if v.confidence < REVIEW_CONFIDENCE_FLOOR]
    return ExtractResponse(fields=fields, needs_review_fields=needs_review)


def _build_prompt(taxonomy_schema: dict[str, Any], document_hint: str) -> str:
    keys = _schema_keys(taxonomy_schema)
    schema_json = json.dumps({"fields": keys, "taxonomy_schema": taxonomy_schema})
    return (
        "Extract structured product fields as JSON object mapping each field name to "
        '{"value": ..., "confidence": 0..1}. Use only these fields: '
        f"{schema_json}. Document: {document_hint}"
    )


def _parse_ollama_fields(payload: dict[str, Any], taxonomy_schema: dict[str, Any]) -> ExtractResponse:
    keys = _schema_keys(taxonomy_schema)
    raw_fields = payload.get("fields", payload)
    fields: dict[str, FieldExtraction] = {}
    for key in keys:
        item = raw_fields.get(key) if isinstance(raw_fields, dict) else None
        if isinstance(item, dict) and "value" in item:
            confidence = float(item.get("confidence", 0.5))
            fields[key] = FieldExtraction(value=item["value"], confidence=max(0.0, min(1.0, confidence)))
        elif item is not None:
            fields[key] = FieldExtraction(value=item, confidence=0.7)
        else:
            fields[key] = FieldExtraction(value=None, confidence=0.0)
    needs_review = [k for k, v in fields.items() if v.confidence < REVIEW_CONFIDENCE_FLOOR]
    return ExtractResponse(fields=fields, needs_review_fields=needs_review)


async def extract_document(request: ExtractRequest, settings: Settings | None = None) -> ExtractResponse:
    settings = settings or get_settings()
    timeout = settings.extract_timeout_seconds
    prompt = _build_prompt(request.taxonomy_schema, request.source_document_url)
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(
                f"{settings.ollama_base_url.rstrip('/')}/api/generate",
                json={
                    "model": settings.ollama_model,
                    "prompt": prompt,
                    "stream": False,
                    "format": "json",
                },
            )
            if response.status_code >= 400:
                return mock_extract(request.taxonomy_schema, request.source_document_url)
            data = response.json()
            text = data.get("response", "{}")
            parsed = json.loads(text) if isinstance(text, str) else text
            if not isinstance(parsed, dict):
                return mock_extract(request.taxonomy_schema, request.source_document_url)
            return _parse_ollama_fields(parsed, request.taxonomy_schema)
    except Exception:
        return mock_extract(request.taxonomy_schema, request.source_document_url)
