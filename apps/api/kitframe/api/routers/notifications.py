from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from fastapi import APIRouter
from pydantic import BaseModel
from sqlalchemy import select

from kitframe.api.deps import BrandAuthDep, SessionDep
from kitframe.db.models import Notification, NotificationPreference

router = APIRouter(tags=["notifications"])

DEFAULT_EVENTS = [
    "phase_assigned", "submitted_for_review", "changes_requested", "phase_approved",
    "sent_back", "mentioned", "generation_completed", "generation_failed",
    "qc_needs_review", "publish_succeeded", "publish_failed", "due_soon", "overdue",
    "golden_set_pending", "extraction_completed", "extraction_failed",
]


class ReadBody(BaseModel):
    ids: list[UUID] | None = None
    all: bool = False


class PrefsBody(BaseModel):
    preferences: list[dict[str, Any]]


@router.get("/notifications")
async def list_notifications(ctx: BrandAuthDep, session: SessionDep, unread: bool | None = None) -> dict[str, Any]:
    q = select(Notification).where(Notification.user_id == ctx.user.id, Notification.brand_id == ctx.brand_id).order_by(Notification.created_at.desc()).limit(100)
    if unread:
        q = q.where(Notification.read_at.is_(None))
    rows = (await session.execute(q)).scalars().all()
    return {"data": [_ser(n) for n in rows]}


@router.get("/notifications/unread-count")
async def unread_count(ctx: BrandAuthDep, session: SessionDep) -> dict[str, int]:
    rows = (
        await session.execute(
            select(Notification).where(
                Notification.user_id == ctx.user.id,
                Notification.brand_id == ctx.brand_id,
                Notification.read_at.is_(None),
            )
        )
    ).scalars().all()
    return {"count": len(rows)}


@router.post("/notifications/read")
async def mark_read(body: ReadBody, ctx: BrandAuthDep, session: SessionDep) -> dict[str, str]:
    q = select(Notification).where(Notification.user_id == ctx.user.id, Notification.brand_id == ctx.brand_id)
    if body.all:
        rows = (await session.execute(q.where(Notification.read_at.is_(None)))).scalars().all()
    else:
        rows = (await session.execute(q.where(Notification.id.in_(body.ids or [])))).scalars().all()
    now = datetime.now(UTC)
    for n in rows:
        n.read_at = now
    await session.commit()
    return {"status": "ok"}


@router.get("/notification-preferences")
async def get_prefs(ctx: BrandAuthDep, session: SessionDep) -> dict[str, Any]:
    rows = (
        await session.execute(
            select(NotificationPreference).where(
                NotificationPreference.user_id == ctx.user.id,
                NotificationPreference.brand_id == ctx.brand_id,
            )
        )
    ).scalars().all()
    by_event = {r.event_type: r.email_enabled for r in rows}
    return {
        "data": [
            {"event_type": e, "email_enabled": by_event.get(e, e in {"phase_assigned", "submitted_for_review", "changes_requested", "sent_back", "mentioned", "publish_succeeded", "publish_failed", "due_soon", "overdue"})}
            for e in DEFAULT_EVENTS
        ]
    }


@router.put("/notification-preferences")
async def put_prefs(body: PrefsBody, ctx: BrandAuthDep, session: SessionDep) -> dict[str, Any]:
    for item in body.preferences:
        event = item["event_type"]
        enabled = bool(item.get("email_enabled"))
        existing = await session.get(NotificationPreference, (ctx.user.id, ctx.brand_id, event))
        if existing is None:
            session.add(NotificationPreference(user_id=ctx.user.id, brand_id=ctx.brand_id, event_type=event, email_enabled=enabled))
        else:
            existing.email_enabled = enabled
    await session.commit()
    return await get_prefs(ctx, session)


def _ser(n: Notification) -> dict[str, Any]:
    return {
        "id": str(n.id),
        "event_type": n.event_type,
        "payload": n.payload,
        "read_at": n.read_at.isoformat() if n.read_at else None,
        "created_at": n.created_at.isoformat(),
    }
