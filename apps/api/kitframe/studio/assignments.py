from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from kitframe.db.models import (
    Asset,
    AssetAssignment,
    BrandMembership,
    Notification,
    Product,
    ProjectMember,
    User,
)
from kitframe.errors import AppError, ErrorCode


async def create_assignments(
    session: AsyncSession,
    *,
    brand_id: UUID,
    product: Product,
    review_id: UUID | None,
    assigned_by: UUID,
    items: list[dict[str, Any]],
    phase: str,
) -> list[AssetAssignment]:
    created: list[AssetAssignment] = []
    for item in items:
        asset_id = item["asset_id"] if isinstance(item["asset_id"], UUID) else UUID(str(item["asset_id"]))
        assigned_to = (
            item["assigned_to"]
            if isinstance(item["assigned_to"], UUID)
            else UUID(str(item["assigned_to"]))
        )
        note = str(item.get("note") or "")
        asset = await session.get(Asset, asset_id)
        if asset is None or asset.product_id != product.id or asset.brand_id != brand_id:
            raise AppError(ErrorCode.VALIDATION_ERROR, "Invalid asset for assignment", status_code=422)
        # cancel previous open assignments on this asset
        existing = (
            await session.execute(
                select(AssetAssignment).where(
                    AssetAssignment.asset_id == asset_id,
                    AssetAssignment.status.in_(("open", "in_progress")),
                )
            )
        ).scalars().all()
        for row in existing:
            row.status = "cancelled"
        row = AssetAssignment(
            brand_id=brand_id,
            product_id=product.id,
            asset_id=asset_id,
            review_id=review_id,
            assigned_to=assigned_to,
            assigned_by=assigned_by,
            phase=phase,
            status="open",
            note=note,
        )
        session.add(row)
        session.add(
            Notification(
                brand_id=brand_id,
                user_id=assigned_to,
                event_type="asset_assigned",
                payload={
                    "product_id": str(product.id),
                    "asset_id": str(asset_id),
                    "internal_reference": product.internal_reference,
                    "note": note,
                    "phase": phase,
                },
            )
        )
        created.append(row)
    await session.flush()
    return created


async def complete_open_assignments(
    session: AsyncSession,
    *,
    asset_id: UUID,
    user_id: UUID,
    version_id: UUID,
) -> None:
    rows = (
        await session.execute(
            select(AssetAssignment).where(
                AssetAssignment.asset_id == asset_id,
                AssetAssignment.assigned_to == user_id,
                AssetAssignment.status.in_(("open", "in_progress")),
            )
        )
    ).scalars().all()
    now = datetime.now(UTC)
    for row in rows:
        row.status = "done"
        row.completed_at = now
        row.completed_version_id = version_id


async def user_has_open_assignment(
    session: AsyncSession, *, asset_id: UUID, user_id: UUID
) -> bool:
    row = (
        await session.execute(
            select(AssetAssignment).where(
                AssetAssignment.asset_id == asset_id,
                AssetAssignment.assigned_to == user_id,
                AssetAssignment.status.in_(("open", "in_progress")),
            ).limit(1)
        )
    ).scalar_one_or_none()
    return row is not None


async def list_editors_for_project(
    session: AsyncSession, *, brand_id: UUID, project_id: UUID, phase: str | None = None
) -> list[dict[str, Any]]:
    q = select(ProjectMember, User).join(User, User.id == ProjectMember.user_id).where(
        ProjectMember.project_id == project_id,
        ProjectMember.role == "editor",
    )
    if phase:
        q = q.where(ProjectMember.phase == phase)
    project_editors = (await session.execute(q)).all()
    brand_editors = (
        await session.execute(
            select(BrandMembership, User)
            .join(User, User.id == BrandMembership.user_id)
            .where(BrandMembership.brand_id == brand_id, BrandMembership.role == "editor")
        )
    ).all()
    by_id: dict[str, dict[str, Any]] = {}
    for _m, u in list(project_editors) + list(brand_editors):
        by_id[str(u.id)] = {
            "user_id": str(u.id),
            "name": u.name,
            "email": u.email,
        }
    return list(by_id.values())


def ser_assignment(a: AssetAssignment, *, asset: Asset | None = None, user: User | None = None) -> dict[str, Any]:
    return {
        "id": str(a.id),
        "product_id": str(a.product_id),
        "asset_id": str(a.asset_id),
        "review_id": str(a.review_id) if a.review_id else None,
        "assigned_to": str(a.assigned_to),
        "assigned_by": str(a.assigned_by),
        "phase": a.phase,
        "status": a.status,
        "note": a.note,
        "completed_version_id": str(a.completed_version_id) if a.completed_version_id else None,
        "created_at": a.created_at.isoformat(),
        "completed_at": a.completed_at.isoformat() if a.completed_at else None,
        "shot_type": asset.shot_type if asset else None,
        "assignee_name": user.name if user else None,
        "assignee_email": user.email if user else None,
    }
