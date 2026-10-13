from __future__ import annotations

import json
from typing import Any

import httpx
from pydantic import BaseModel, Field

from app.config import Settings, get_settings


class GenerateCopyRequest(BaseModel):
    product: dict[str, Any]
    locales: list[str] = Field(default_factory=lambda: ["es", "ca", "en"])
    glossary: dict[str, Any] = Field(default_factory=dict)


class SeoCopy(BaseModel):
    title: str
    meta_description: str
    keywords: list[str]


class GenerateCopyResponse(BaseModel):
    seo: SeoCopy
    translations: dict[str, dict[str, str]]


def _do_not_translate_terms(glossary: dict[str, Any]) -> list[str]:
    terms: list[str] = []
    if isinstance(glossary.get("do_not_translate"), list):
        terms.extend(str(t) for t in glossary["do_not_translate"])
    for key, value in glossary.items():
        if key == "do_not_translate":
            continue
        if isinstance(value, dict) and value.get("do_not_translate") is True:
            terms.append(str(key))
        elif value is True or value == "do_not_translate":
            terms.append(str(key))
    return terms


def apply_glossary(text: str, glossary: dict[str, Any]) -> str:
    result = text
    for term in _do_not_translate_terms(glossary):
        result = result.replace(term.lower(), term)
        result = result.replace(term.upper(), term)
    return result


def apply_glossary_deep(payload: dict[str, Any], glossary: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in payload.items():
        if isinstance(value, str):
            out[key] = apply_glossary(value, glossary)
        elif isinstance(value, dict):
            out[key] = apply_glossary_deep(value, glossary)
        elif isinstance(value, list):
            out[key] = [
                apply_glossary(v, glossary) if isinstance(v, str) else v for v in value
            ]
        else:
            out[key] = value
    return out


def mock_copy(request: GenerateCopyRequest) -> GenerateCopyResponse:
    ref = str(request.product.get("internal_reference") or request.product.get("name") or "product")
    category = str(request.product.get("category") or "kit")
    title = apply_glossary(f"{ref} {category}", request.glossary)
    seo = SeoCopy(
        title=title,
        meta_description=apply_glossary(f"Official {ref} {category} product page.", request.glossary),
        keywords=[ref, category, "kitframe"],
    )
    translations: dict[str, dict[str, str]] = {}
    for locale in request.locales:
        translations[locale] = apply_glossary_deep(
            {
                "title": title,
                "description": f"{ref} description ({locale})",
            },
            request.glossary,
        )
    return GenerateCopyResponse(seo=seo, translations=translations)


async def generate_copy(request: GenerateCopyRequest, settings: Settings | None = None) -> GenerateCopyResponse:
    settings = settings or get_settings()
    timeout = settings.copy_timeout_seconds
    prompt = (
        "Generate SEO title, meta_description, keywords and locale translations as JSON. "
        f"Product={json.dumps(request.product)} Locales={request.locales} "
        f"Glossary={json.dumps(request.glossary)}"
    )
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
                return mock_copy(request)
            data = response.json()
            text = data.get("response", "{}")
            parsed = json.loads(text) if isinstance(text, str) else text
            if not isinstance(parsed, dict):
                return mock_copy(request)
            seo_raw = parsed.get("seo", {})
            seo = SeoCopy(
                title=str(seo_raw.get("title", "product")),
                meta_description=str(seo_raw.get("meta_description", "")),
                keywords=[str(k) for k in seo_raw.get("keywords", [])],
            )
            translations = parsed.get("translations", {})
            if not isinstance(translations, dict):
                translations = {}
            result = GenerateCopyResponse(seo=seo, translations=translations)
            result.seo.title = apply_glossary(result.seo.title, request.glossary)
            result.seo.meta_description = apply_glossary(result.seo.meta_description, request.glossary)
            result.seo.keywords = [apply_glossary(k, request.glossary) for k in result.seo.keywords]
            result.translations = {
                locale: apply_glossary_deep(values, request.glossary)
                if isinstance(values, dict)
                else values
                for locale, values in result.translations.items()
            }
            return result
    except Exception:
        return mock_copy(request)
