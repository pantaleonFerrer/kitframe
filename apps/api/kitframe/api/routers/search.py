from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query
from sqlalchemy import select

from kitframe.api.deps import BrandAuthDep, SessionDep
from kitframe.db.models import Product, Project, Variant

router = APIRouter(tags=["search"])


@router.get("/search")
async def search(ctx: BrandAuthDep, session: SessionDep, q: str = Query(min_length=1)) -> dict[str, Any]:
    like = f"%{q}%"
    products = (
        await session.execute(
            select(Product).where(Product.brand_id == ctx.brand_id, Product.internal_reference.ilike(like)).limit(20)
        )
    ).scalars().all()
    projects = (
        await session.execute(
            select(Project).where(Project.brand_id == ctx.brand_id, Project.name.ilike(like)).limit(10)
        )
    ).scalars().all()
    variants = (
        await session.execute(
            select(Variant).where(Variant.brand_id == ctx.brand_id, Variant.sku.ilike(like)).limit(20)
        )
    ).scalars().all()
    return {
        "products": [
            {"id": str(p.id), "internal_reference": p.internal_reference, "name": ((p.content or {}).get("es") or {}).get("name")}
            for p in products
        ],
        "projects": [{"id": str(p.id), "name": p.name} for p in projects],
        "skus": [{"sku": v.sku, "product_id": str(v.product_id)} for v in variants],
    }
