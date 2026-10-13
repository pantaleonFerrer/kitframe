from __future__ import annotations

import re
import unicodedata
from datetime import date
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from kitframe.db.models import ModelReferenceSet, RightsRecord


def _normalize(text: str) -> str:
    text = text.lower()
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = re.sub(r"[^\w\s]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


async def check_rights(
    session: AsyncSession,
    *,
    brand_id: UUID,
    model_set_id: UUID | None,
    prompt: str,
    restrictions: str,
) -> dict[str, Any]:
    records = (await session.execute(select(RightsRecord).where(RightsRecord.brand_id == brand_id))).scalars().all()
    model_set = await session.get(ModelReferenceSet, model_set_id) if model_set_id else None
    linked_record_id = model_set.rights_record_id if model_set else None

    if model_set and model_set.kind == "real_person":
        if linked_record_id is None:
            return {"ok": False, "records": [], "reason": "missing_rights_record", "subjects": []}
        rec = await session.get(RightsRecord, linked_record_id)
        if rec is None or rec.status != "cleared" or (rec.valid_until and rec.valid_until < date.today()):
            return {
                "ok": False,
                "records": [str(linked_record_id)] if linked_record_id else [],
                "reason": "model_rights_not_cleared",
                "subjects": [rec.subject_name] if rec else [],
            }

    hay = _normalize(f"{prompt} {restrictions}")
    blocked_subjects = []
    blocked_ids = []
    for rec in records:
        names = [_normalize(rec.subject_name), *[_normalize(a) for a in (rec.aliases or [])]]
        hit = any(n and n in hay for n in names)
        if not hit:
            continue
        if linked_record_id == rec.id and rec.status == "cleared" and not (rec.valid_until and rec.valid_until < date.today()):
            continue
        blocked_subjects.append(rec.subject_name)
        blocked_ids.append(str(rec.id))
    if blocked_subjects:
        return {"ok": False, "records": blocked_ids, "reason": "named_subject", "subjects": blocked_subjects}
    return {"ok": True, "records": [str(linked_record_id)] if linked_record_id else [], "reason": None, "subjects": []}
