"""Helpers for per-review conversation threads."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from kitframe.db.models import (
    Asset,
    AssetAssignment,
    AssetVersion,
    Comment,
    Product,
    ProductPhase,
    Review,
    User,
)
from kitframe.media.storage import presign_get
from kitframe.settings import Settings
from kitframe.studio.assignments import ser_assignment


async def reviews_for_product(session: AsyncSession, product_id: UUID) -> list[Review]:
    phases = (
        await session.execute(select(ProductPhase).where(ProductPhase.product_id == product_id))
    ).scalars().all()
    phase_ids = [p.id for p in phases]
    if not phase_ids:
        return []
    return list(
        (
            await session.execute(
                select(Review)
                .where(Review.product_phase_id.in_(phase_ids))
                .order_by(Review.created_at.desc())
            )
        )
        .scalars()
        .all()
    )


async def open_thread_review(
    session: AsyncSession, product: Product
) -> Review | None:
    """Latest changes_requested review on the current phase that is still open."""
    if product.current_phase == "published":
        return None
    phase = (
        await session.execute(
            select(ProductPhase).where(
                ProductPhase.product_id == product.id,
                ProductPhase.phase == product.current_phase,
            )
        )
    ).scalar_one_or_none()
    if phase is None:
        return None
    rows = (
        await session.execute(
            select(Review)
            .where(Review.product_phase_id == phase.id)
            .order_by(Review.created_at.desc())
        )
    ).scalars().all()
    for r in rows:
        if r.decision == "changes_requested":
            return r
        if r.decision in ("approved", "sent_back"):
            return None
    return None


def thread_window(
    review: Review, same_phase_reviews: list[Review]
) -> tuple[datetime, datetime | None]:
    """Activity belongs to this review until the next review on the same phase."""
    later = [r for r in same_phase_reviews if r.created_at > review.created_at]
    later.sort(key=lambda r: r.created_at)
    end = later[0].created_at if later else None
    return review.created_at, end


async def get_review_detail(
    session: AsyncSession,
    *,
    brand_id: UUID,
    product: Product,
    review: Review,
    settings: Settings | None = None,
) -> dict[str, Any]:
    phase = await session.get(ProductPhase, review.product_phase_id)
    same_phase = (
        await session.execute(
            select(Review)
            .where(Review.product_phase_id == review.product_phase_id)
            .order_by(Review.created_at.asc())
        )
    ).scalars().all()
    start, end = thread_window(review, list(same_phase))

    later = [r for r in same_phase if r.created_at > review.created_at]
    closing = later[0] if later else None
    is_open = review.decision == "changes_requested" and closing is None

    comments_q = select(Comment).where(
        Comment.product_id == product.id,
        Comment.created_at >= start,
    )
    if end is not None:
        comments_q = comments_q.where(Comment.created_at < end)
    # Prefer explicitly linked comments, but also include window for legacy rows
    comments = (
        await session.execute(comments_q.order_by(Comment.created_at.asc()))
    ).scalars().all()
    linked = (
        await session.execute(
            select(Comment)
            .where(Comment.review_id == review.id)
            .order_by(Comment.created_at.asc())
        )
    ).scalars().all()
    by_id = {c.id: c for c in comments}
    for c in linked:
        by_id[c.id] = c
    comments = sorted(by_id.values(), key=lambda c: c.created_at)

    assignments = (
        await session.execute(
            select(AssetAssignment, Asset, User)
            .join(Asset, Asset.id == AssetAssignment.asset_id)
            .join(User, User.id == AssetAssignment.assigned_to)
            .where(AssetAssignment.review_id == review.id)
            .order_by(AssetAssignment.created_at.asc())
        )
    ).all()

    assets = (
        await session.execute(select(Asset).where(Asset.product_id == product.id))
    ).scalars().all()
    asset_by_id = {a.id: a for a in assets}
    versions: list[AssetVersion] = []
    if assets:
        vq = select(AssetVersion).where(
            AssetVersion.asset_id.in_([a.id for a in assets]),
            AssetVersion.created_at >= start,
        )
        if end is not None:
            vq = vq.where(AssetVersion.created_at < end)
        versions = list((await session.execute(vq.order_by(AssetVersion.created_at.asc()))).scalars().all())
        linked_v = (
            await session.execute(
                select(AssetVersion)
                .where(AssetVersion.review_id == review.id)
                .order_by(AssetVersion.created_at.asc())
            )
        ).scalars().all()
        v_by_id = {v.id: v for v in versions}
        for v in linked_v:
            v_by_id[v.id] = v
        # versions completed via assignment
        for a, _asset, _u in assignments:
            if a.completed_version_id and a.completed_version_id not in v_by_id:
                ver = await session.get(AssetVersion, a.completed_version_id)
                if ver is not None:
                    v_by_id[ver.id] = ver
        versions = sorted(v_by_id.values(), key=lambda v: v.created_at)

    user_ids = {
        review.reviewer_user_id,
        *[c.author_id for c in comments],
        *[v.created_by for v in versions],
        *[a.assigned_by for a, _, _ in assignments],
        *[a.assigned_to for a, _, _ in assignments],
    }
    if closing:
        user_ids.add(closing.reviewer_user_id)
    users: dict[UUID, User] = {}
    if user_ids:
        for u in (await session.execute(select(User).where(User.id.in_(list(user_ids))))).scalars().all():
            users[u.id] = u

    reviewer = users.get(review.reviewer_user_id)
    version_rows = []
    for v in versions:
        asset = asset_by_id.get(v.asset_id)
        author = users.get(v.created_by)
        url = None
        if settings is not None:
            try:
                url = presign_get(settings, v.storage_key)
            except Exception:
                url = None
        version_rows.append(
            {
                "id": str(v.id),
                "asset_id": str(v.asset_id),
                "shot_type": asset.shot_type if asset else None,
                "version_number": v.version_number,
                "source": v.source,
                "url": url,
                "author_id": str(v.created_by),
                "author_name": author.name if author else None,
                "created_at": v.created_at.isoformat(),
            }
        )

    return {
        "id": str(review.id),
        "decision": review.decision,
        "comment": review.comment,
        "target_phase": review.target_phase,
        "self_review": review.self_review,
        "phase": phase.phase if phase else None,
        "phase_status": phase.status if phase else None,
        "reviewer_id": str(review.reviewer_user_id),
        "reviewer_name": reviewer.name if reviewer else None,
        "created_at": review.created_at.isoformat(),
        "is_open": is_open,
        "closing": (
            {
                "id": str(closing.id),
                "decision": closing.decision,
                "comment": closing.comment,
                "reviewer_name": users.get(closing.reviewer_user_id).name
                if users.get(closing.reviewer_user_id)
                else None,
                "created_at": closing.created_at.isoformat(),
            }
            if closing
            else None
        ),
        "comments": [
            {
                "id": str(c.id),
                "body": c.body,
                "phase": c.phase,
                "author_id": str(c.author_id),
                "author_name": users.get(c.author_id).name if users.get(c.author_id) else None,
                "review_id": str(c.review_id) if c.review_id else None,
                "asset_version_id": str(c.asset_version_id) if c.asset_version_id else None,
                "annotation": c.annotation,
                "resolved_at": c.resolved_at.isoformat() if c.resolved_at else None,
                "created_at": c.created_at.isoformat(),
            }
            for c in comments
        ],
        "assignments": [
            ser_assignment(a, asset=asset, user=user) for a, asset, user in assignments
        ],
        "versions": version_rows,
    }


async def list_review_summaries(
    session: AsyncSession, product: Product
) -> list[dict[str, Any]]:
    reviews = await reviews_for_product(session, product.id)
    if not reviews:
        return []
    phases = {
        p.id: p
        for p in (
            await session.execute(select(ProductPhase).where(ProductPhase.product_id == product.id))
        ).scalars().all()
    }
    user_ids = {r.reviewer_user_id for r in reviews}
    users = {
        u.id: u
        for u in (
            await session.execute(select(User).where(User.id.in_(list(user_ids))))
        ).scalars().all()
    } if user_ids else {}

    open_r = await open_thread_review(session, product)
    open_id = open_r.id if open_r else None

    out: list[dict[str, Any]] = []
    for r in reviews:
        phase = phases.get(r.product_phase_id)
        reviewer = users.get(r.reviewer_user_id)
        comment_count = len(
            (
                await session.execute(select(Comment).where(Comment.review_id == r.id))
            ).scalars().all()
        )
        version_count = len(
            (
                await session.execute(select(AssetVersion).where(AssetVersion.review_id == r.id))
            ).scalars().all()
        )
        out.append(
            {
                "id": str(r.id),
                "decision": r.decision,
                "comment": r.comment,
                "phase": phase.phase if phase else None,
                "reviewer_name": reviewer.name if reviewer else None,
                "created_at": r.created_at.isoformat(),
                "is_open": open_id == r.id,
                "comment_count": comment_count,
                "version_count": version_count,
            }
        )
    return out
