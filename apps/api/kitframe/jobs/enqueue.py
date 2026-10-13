from __future__ import annotations

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from kitframe.db.models import Job


async def enqueue_job(
    session: AsyncSession,
    *,
    brand_id: UUID | None,
    type: str,
    entity_type: str | None,
    entity_id: UUID | None,
    requested_by: UUID | None,
) -> Job:
    job = Job(
        brand_id=brand_id,
        type=type,
        entity_type=entity_type,
        entity_id=entity_id,
        requested_by=requested_by,
        status="queued",
    )
    session.add(job)
    await session.flush()
    return job
