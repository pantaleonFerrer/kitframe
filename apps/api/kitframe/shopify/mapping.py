from __future__ import annotations

from typing import Any

from kitframe.db.models import Brand, Product, Variant


def map_product_to_shopify(
    product: Product,
    variants: list[Variant],
    assets: list[dict[str, Any]],
    brand: Brand,
) -> dict[str, Any]:
    es = (product.content or {}).get("es") or {}
    title = es.get("name") or product.internal_reference
    description = es.get("description") or ""
    html = "".join(f"<p>{p.strip()}</p>" for p in description.split("\n") if p.strip())
    options = []
    colors = sorted({v.color for v in variants if v.color})
    sizes = sorted({v.size for v in variants if v.size})
    if colors:
        options.append({"name": "Color", "values": colors})
    if sizes:
        options.append({"name": "Size", "values": sizes})
    shopify_variants = []
    for v in variants:
        shopify_variants.append(
            {
                "sku": v.sku,
                "price": str(v.price_eur or "0.00"),
                "option1": v.color,
                "option2": v.size,
            }
        )
    metafields = []
    for mapping in brand.shopify_metafields or []:
        key = mapping.get("taxonomy_key")
        if key and key in (product.structured_data or {}):
            metafields.append(
                {
                    "namespace": mapping.get("namespace"),
                    "key": mapping.get("key"),
                    "type": mapping.get("type", "single_line_text_field"),
                    "value": str(product.structured_data[key]),
                }
            )
    return {
        "title": title,
        "body_html": html,
        "vendor": brand.name,
        "product_type": product.garment_category or "",
        "tags": ",".join(
            filter(
                None,
                [
                    product.garment_category,
                    (product.structured_data or {}).get("gender"),
                    (product.structured_data or {}).get("season"),
                ],
            )
        ),
        "seo": {"title": es.get("seo_title"), "description": es.get("seo_meta")},
        "options": options,
        "variants": shopify_variants,
        "images": assets,
        "metafields": metafields,
        "translations": {
            "ca": (product.content or {}).get("ca") or {},
            "en": (product.content or {}).get("en") or {},
        },
    }


def render_filename(pattern: str, *, reference: str, sku: str, color: str, shot: str, index: int, channel: str) -> str:
    raw = pattern.format(
        reference=reference,
        sku=sku,
        color=color,
        shot=shot,
        index=index,
        channel=channel,
    )
    return "".join(c.lower() if c.isalnum() else "-" for c in raw).strip("-")
