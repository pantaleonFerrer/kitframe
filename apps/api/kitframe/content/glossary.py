from __future__ import annotations

from typing import Any


def apply_glossary_check(
    source: str,
    locales: dict[str, dict[str, Any]],
    do_not_translate: list[str],
) -> list[dict[str, str]]:
    warnings: list[dict[str, str]] = []
    for term in do_not_translate:
        if term not in source:
            continue
        for locale, payload in locales.items():
            blob = " ".join(str(payload.get(k, "")) for k in ("name", "description", "seo_title", "seo_meta"))
            if term not in blob:
                warnings.append({"locale": locale, "term": term, "code": "glossary_violation"})
    return warnings
