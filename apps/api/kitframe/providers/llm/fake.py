from __future__ import annotations

from typing import Any


class FakeLLMClient:
    key = "fake"
    last_usage: dict[str, int]

    def __init__(self) -> None:
        self.last_usage = {"prompt_tokens": 0, "completion_tokens": 0}

    def complete_json(
        self,
        system: str,
        user: str,
        json_schema: dict[str, Any],
        schema_name: str = "response",
        images: list[bytes] | None = None,
        temperature: float = 0.0,
    ) -> dict[str, Any]:
        schema_str = str(json_schema)
        props = json_schema.get("properties") or {}
        if schema_name == "alt_text" or (
            set(props.keys()) == {"es", "ca", "en"} and "products" not in schema_str and "name" not in schema_str
        ):
            return {
                "es": "Camiseta FC Barcelona, vista frontal",
                "ca": "Samarreta FC Barcelona, vista frontal",
                "en": "FC Barcelona jersey, front view",
            }
        if "products" in schema_str:
            return {
                "products": [
                    {
                        "internal_reference": "FCB-DEMO-001",
                        "fields": {
                            "composition": {
                                "value": "100% polyester",
                                "confidence": 0.92,
                                "source_quote": "100% polyester",
                            },
                            "garment_category": {
                                "value": "jersey",
                                "confidence": 0.95,
                                "source_quote": "jersey",
                            },
                            "gender": {
                                "value": "adult_men",
                                "confidence": 0.9,
                                "source_quote": "hombre",
                            },
                            "care_instructions": {
                                "value": "Wash at 30C",
                                "confidence": 0.88,
                                "source_quote": "Wash at 30C",
                            },
                            "origin": {
                                "value": None,
                                "confidence": 0.0,
                                "source_quote": None,
                            },
                            "season": {
                                "value": "26/27",
                                "confidence": 0.7,
                                "source_quote": "26/27",
                            },
                        },
                        "variants": [
                            {
                                "color": "Blaugrana",
                                "size": "M",
                                "sku": "FCB-DEMO-001-M",
                                "price_eur": "89.95",
                            }
                        ],
                    }
                ]
            }
        base = {
            "es": {
                "name": "Camiseta FC Barcelona",
                "description": "Camiseta oficial del FC Barcelona con escudo nítido y tejido técnico.",
                "seo_title": "Camiseta FC Barcelona oficial",
                "seo_meta": "Compra la camiseta oficial Blaugrana del FC Barcelona.",
                "seo_keywords": ["Barça", "camiseta", "oficial"],
            },
            "ca": {
                "name": "Samarreta FC Barcelona",
                "description": "Samarreta oficial del FC Barcelona amb escut nítid i teixit tècnic.",
                "seo_title": "Samarreta FC Barcelona oficial",
                "seo_meta": "Compra la samarreta oficial Blaugrana del FC Barcelona.",
                "seo_keywords": ["Barça", "samarreta", "oficial"],
            },
            "en": {
                "name": "FC Barcelona Jersey",
                "description": "Official FC Barcelona jersey with crisp crest and technical fabric.",
                "seo_title": "Official FC Barcelona jersey",
                "seo_meta": "Buy the official Blaugrana FC Barcelona jersey.",
                "seo_keywords": ["Barça", "jersey", "official"],
            },
            "fr": {
                "name": "Maillot FC Barcelona",
                "description": "Maillot officiel du FC Barcelona avec écusson net et tissu technique.",
                "seo_title": "Maillot officiel FC Barcelona",
                "seo_meta": "Achetez le maillot officiel Blaugrana du FC Barcelona.",
                "seo_keywords": ["Barça", "maillot", "officiel"],
            },
            "de": {
                "name": "FC Barcelona Trikot",
                "description": "Offizielles FC-Barcelona-Trikot mit klarem Wappen und Funktionsstoff.",
                "seo_title": "Offizielles FC Barcelona Trikot",
                "seo_meta": "Kaufen Sie das offizielle Blaugrana-Trikot von FC Barcelona.",
                "seo_keywords": ["Barça", "Trikot", "offiziell"],
            },
            "it": {
                "name": "Maglia FC Barcelona",
                "description": "Maglia ufficiale del FC Barcelona con stemma nitido e tessuto tecnico.",
                "seo_title": "Maglia ufficiale FC Barcelona",
                "seo_meta": "Acquista la maglia ufficiale Blaugrana del FC Barcelona.",
                "seo_keywords": ["Barça", "maglia", "ufficiale"],
            },
            "pt": {
                "name": "Camisola FC Barcelona",
                "description": "Camisola oficial do FC Barcelona com emblema nítido e tecido técnico.",
                "seo_title": "Camisola oficial FC Barcelona",
                "seo_meta": "Compre a camisola oficial Blaugrana do FC Barcelona.",
                "seo_keywords": ["Barça", "camisola", "oficial"],
            },
            "zh": {
                "name": "巴塞罗那足球俱乐部球衣",
                "description": "官方巴塞罗那足球俱乐部球衣，队徽清晰，面料专业。",
                "seo_title": "官方巴塞罗那足球俱乐部球衣",
                "seo_meta": "购买官方 Blaugrana 巴塞罗那足球俱乐部球衣。",
                "seo_keywords": ["Barça", "球衣", "官方"],
            },
        }
        # If schema asks for a subset, return only those keys.
        props = set((json_schema.get("properties") or {}).keys())
        if props:
            return {k: v for k, v in base.items() if k in props}
        return base
