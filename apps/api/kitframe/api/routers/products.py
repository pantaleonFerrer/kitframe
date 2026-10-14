from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any
from uuid import UUID

from fastapi import APIRouter
from pydantic import BaseModel, Field
from sqlalchemy import select

from kitframe.api.deps import BrandAuthDep, SessionDep, SettingsDep
from kitframe.auth.permissions import allowed_actions, can
from kitframe.db.models import (
    Asset,
    AssetAssignment,
    AuditLog,
    Brand,
    Comment,
    Export,
    Product,
    ProductPhase,
    Project,
    Review,
    User,
    Variant,
)
from kitframe.errors import AppError, ErrorCode
from kitframe.jobs.enqueue import enqueue_job
from kitframe.studio.assignments import create_assignments, list_editors_for_project, ser_assignment
from kitframe.studio.reviews import get_review_detail, list_review_summaries, open_thread_review
from kitframe.workflow import transitions
from kitframe.workflow.criteria import evaluate_exit_criteria

router = APIRouter(tags=["products"])


class ProductPatch(BaseModel):
    structured_data: dict[str, Any] | None = None
    content: dict[str, Any] | None = None
    garment_category: str | None = None
    confirmed_fields: list[str] | None = None


class ConfirmFields(BaseModel):
    keys: list[str]


class GenerateCopyBody(BaseModel):
    overwrite_manual: bool = False
    mode: str = "generate"  # generate | translate
    source_locale: str = "es"


class PhasePatch(BaseModel):
    assignee_user_id: UUID | None = None
    reviewer_user_id: UUID | None = None
    due_date: date | None = None


class ReviewAssignmentIn(BaseModel):
    asset_id: UUID
    assigned_to: UUID
    note: str = ""


class ReviewBody(BaseModel):
    decision: str
    comment: str | None = None
    target_phase: str | None = None
    requirements_checked: list[str] = Field(default_factory=list)
    assignments: list[ReviewAssignmentIn] = Field(default_factory=list)


class PublishBody(BaseModel):
    confirm_text: str


class VariantIn(BaseModel):
    color: str | None = None
    size: str | None = None
    sku: str
    barcode: str | None = None
    price_eur: Decimal | None = None
    compare_at_price_eur: Decimal | None = None
    sort_order: int = 0


class CommentIn(BaseModel):
    body: str = Field(min_length=1, max_length=4000)
    phase: str | None = None
    review_id: UUID | None = None
    asset_version_id: UUID | None = None
    annotation: dict[str, Any] | None = None
    mentions: list[UUID] = Field(default_factory=list)


class ExportIn(BaseModel):
    channels: list[str]


@router.get("/products/{product_id}")
async def get_product(product_id: UUID, ctx: BrandAuthDep, session: SessionDep) -> dict[str, Any]:
    product = await _product(session, ctx.brand_id, product_id)
    actions = await allowed_actions(session, ctx, product)
    phases = (await session.execute(select(ProductPhase).where(ProductPhase.product_id == product.id))).scalars().all()
    return {**_ser_product(product), "allowed_actions": actions, "phases": [_ser_phase(p) for p in phases]}


@router.patch("/products/{product_id}")
async def patch_product(product_id: UUID, body: ProductPatch, ctx: BrandAuthDep, session: SessionDep) -> dict[str, Any]:
    product = await _product(session, ctx.brand_id, product_id)
    if not await can(session, ctx, "product.edit_data", product=product):
        raise AppError(ErrorCode.FORBIDDEN, "Forbidden", status_code=403)
    data = body.model_dump(exclude_unset=True)
    only_content = set(data.keys()) <= {"content"}
    if not only_content:
        if product.current_phase != "data" and ctx.membership.role not in ("admin", "owner"):
            raise AppError(ErrorCode.PHASE_LOCKED, "Data locked after data phase", status_code=409)
        phase = await transitions.get_phase(session, product.id, product.current_phase) if product.current_phase != "published" else None
        if phase:
            transitions.assert_not_locked(phase)
    for k, v in data.items():
        setattr(product, k, v)
    if "structured_data" in data and "garment_category" in (data["structured_data"] or {}):
        product.garment_category = data["structured_data"]["garment_category"]
    session.add(
        AuditLog(
            brand_id=ctx.brand_id,
            user_id=ctx.user.id,
            entity_type="product",
            entity_id=product.id,
            action="update",
            detail={"fields": list(data.keys())},
            request_id=ctx.request_id,
        )
    )
    await session.commit()
    return await get_product(product_id, ctx, session)


@router.post("/products/{product_id}/confirm-fields")
async def confirm_fields(product_id: UUID, body: ConfirmFields, ctx: BrandAuthDep, session: SessionDep) -> dict[str, Any]:
    product = await _product(session, ctx.brand_id, product_id)
    if not await can(session, ctx, "product.edit_data", product=product):
        raise AppError(ErrorCode.FORBIDDEN, "Forbidden", status_code=403)
    confirmed = set(product.confirmed_fields or [])
    confirmed.update(body.keys)
    product.confirmed_fields = list(confirmed)
    await session.commit()
    return await get_product(product_id, ctx, session)


@router.post("/products/{product_id}/generate-copy")
async def generate_copy(product_id: UUID, body: GenerateCopyBody, ctx: BrandAuthDep, session: SessionDep) -> dict[str, Any]:
    from kitframe.content.locales import CONTENT_LOCALES

    product = await _product(session, ctx.brand_id, product_id)
    if not await can(session, ctx, "product.edit_data", product=product):
        raise AppError(ErrorCode.FORBIDDEN, "Forbidden", status_code=403)
    mode = (body.mode or "generate").strip().lower()
    if mode not in ("generate", "translate"):
        raise AppError(ErrorCode.VALIDATION_ERROR, "Invalid mode", status_code=422)
    source = (body.source_locale or "es").strip().lower()
    if source not in CONTENT_LOCALES:
        raise AppError(ErrorCode.VALIDATION_ERROR, "Invalid source_locale", status_code=422)
    if mode == "translate":
        src = (product.content or {}).get(source) or {}
        if not (src.get("name") or src.get("description")):
            raise AppError(
                ErrorCode.VALIDATION_ERROR,
                f"No source copy in locale {source} to translate",
                status_code=422,
            )
    if body.overwrite_manual:
        content = dict(product.content or {})
        for loc, payload in list(content.items()):
            if isinstance(payload, dict):
                content[loc] = {**payload, "manually_edited": []}
        product.content = content
    job = await enqueue_job(
        session,
        brand_id=ctx.brand_id,
        type="generate_copy",
        entity_type="product",
        entity_id=product.id,
        requested_by=ctx.user.id,
        payload={
            "mode": mode,
            "source_locale": source,
            "overwrite_manual": body.overwrite_manual,
        },
    )
    await session.commit()
    return {"job_id": str(job.id), "mode": mode}


@router.get("/products/{product_id}/checklist")
async def checklist(product_id: UUID, ctx: BrandAuthDep, session: SessionDep) -> dict[str, Any]:
    product = await _product(session, ctx.brand_id, product_id)
    brand = await session.get(Brand, product.brand_id)
    assert brand is not None
    phase = product.current_phase if product.current_phase != "published" else "approval"
    criteria = await evaluate_exit_criteria(session, product, brand, phase)
    return {"phase": phase, "criteria": criteria, "ok": all(c["ok"] for c in criteria)}


@router.get("/products/{product_id}/phases")
async def phases(product_id: UUID, ctx: BrandAuthDep, session: SessionDep) -> dict[str, Any]:
    product = await _product(session, ctx.brand_id, product_id)
    rows = (await session.execute(select(ProductPhase).where(ProductPhase.product_id == product.id))).scalars().all()
    return {"data": [_ser_phase(p) for p in rows]}


@router.patch("/products/{product_id}/phases/{phase}")
async def patch_phase(product_id: UUID, phase: str, body: PhasePatch, ctx: BrandAuthDep, session: SessionDep) -> dict[str, Any]:
    product = await _product(session, ctx.brand_id, product_id)
    project = await session.get(Project, product.project_id)
    if not await can(session, ctx, "project.lead", product=product, project=project):
        raise AppError(ErrorCode.FORBIDDEN, "Forbidden", status_code=403)
    row = await transitions.get_phase(session, product.id, phase)
    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(row, k, v)
    await session.commit()
    return _ser_phase(row)


@router.post("/products/{product_id}/start")
async def start(product_id: UUID, ctx: BrandAuthDep, session: SessionDep) -> dict[str, Any]:
    product = await _product(session, ctx.brand_id, product_id)
    if not await can(session, ctx, "product.edit_current_phase", product=product):
        raise AppError(ErrorCode.FORBIDDEN, "Forbidden", status_code=403)
    await transitions.start_phase(session, product, ctx.user.id)
    await session.commit()
    return await get_product(product_id, ctx, session)


@router.post("/products/{product_id}/submit")
async def submit(product_id: UUID, ctx: BrandAuthDep, session: SessionDep) -> dict[str, Any]:
    product = await _product(session, ctx.brand_id, product_id)
    if not await can(session, ctx, "product.edit_current_phase", product=product):
        raise AppError(ErrorCode.FORBIDDEN, "Forbidden", status_code=403)
    brand = await session.get(Brand, product.brand_id)
    await transitions.submit_phase(session, product, brand, ctx.user.id)
    await session.commit()
    return await get_product(product_id, ctx, session)


@router.post("/products/{product_id}/review")
async def review(product_id: UUID, body: ReviewBody, ctx: BrandAuthDep, session: SessionDep) -> dict[str, Any]:
    product = await _product(session, ctx.brand_id, product_id)
    if not await can(session, ctx, "product.review_current_phase", product=product):
        raise AppError(ErrorCode.FORBIDDEN, "Forbidden", status_code=403)
    brand = await session.get(Brand, product.brand_id)
    project = await session.get(Project, product.project_id)
    assert brand is not None and project is not None
    brand._project_requirements = project.requirements  # type: ignore[attr-defined]
    phase_row = await transitions.get_phase(session, product.id, product.current_phase)
    self_review = phase_row.submitted_by == ctx.user.id
    if self_review and ctx.membership.role not in ("admin", "owner"):
        # allowed only if only possible reviewer — simplified: allow and mark
        pass
    phase_row, review = await transitions.review_phase(
        session,
        product,
        brand,
        ctx.user.id,
        body.decision,
        body.comment,
        body.target_phase,
        body.requirements_checked,
        self_review=self_review,
    )
    if body.decision == "changes_requested" and body.comment:
        await session.flush()
        session.add(
            Comment(
                brand_id=ctx.brand_id,
                product_id=product.id,
                phase=product.current_phase,
                author_id=ctx.user.id,
                body=body.comment,
                review_id=review.id,
            )
        )
    if body.assignments:
        if body.decision not in ("changes_requested", "approved"):
            raise AppError(
                ErrorCode.VALIDATION_ERROR,
                "assignments only allowed with changes_requested or approved",
                status_code=422,
            )
        await session.flush()
        if body.decision == "changes_requested":
            assign_phase = product.current_phase
        else:
            assign_phase = body.target_phase or (
                "retouch" if phase_row.phase == "visuals" else product.current_phase
            )
        await create_assignments(
            session,
            brand_id=ctx.brand_id,
            product=product,
            review_id=review.id,
            assigned_by=ctx.user.id,
            items=[a.model_dump() for a in body.assignments],
            phase=assign_phase,
        )
    await session.commit()
    return await get_product(product_id, ctx, session)


class AssignmentPatch(BaseModel):
    status: str | None = None
    note: str | None = None


@router.get("/products/{product_id}/editors")
async def product_editors(product_id: UUID, ctx: BrandAuthDep, session: SessionDep) -> dict[str, Any]:
    product = await _product(session, ctx.brand_id, product_id)
    editors = await list_editors_for_project(
        session,
        brand_id=ctx.brand_id,
        project_id=product.project_id,
        phase=product.current_phase if product.current_phase != "approval" else "retouch",
    )
    # Also include editors for retouch when reviewing visuals
    if product.current_phase == "visuals":
        more = await list_editors_for_project(
            session, brand_id=ctx.brand_id, project_id=product.project_id, phase="retouch"
        )
        by_id = {e["user_id"]: e for e in editors}
        for e in more:
            by_id[e["user_id"]] = e
        editors = list(by_id.values())
    return {"data": editors}


@router.get("/products/{product_id}/assignments")
async def product_assignments(product_id: UUID, ctx: BrandAuthDep, session: SessionDep) -> dict[str, Any]:
    product = await _product(session, ctx.brand_id, product_id)
    rows = (
        await session.execute(
            select(AssetAssignment, Asset, User)
            .join(Asset, Asset.id == AssetAssignment.asset_id)
            .join(User, User.id == AssetAssignment.assigned_to)
            .where(AssetAssignment.product_id == product.id)
            .order_by(AssetAssignment.created_at.desc())
        )
    ).all()
    return {"data": [ser_assignment(a, asset=asset, user=user) for a, asset, user in rows]}


@router.get("/assignments/mine")
async def my_assignments(ctx: BrandAuthDep, session: SessionDep) -> dict[str, Any]:
    rows = (
        await session.execute(
            select(AssetAssignment, Asset, Product)
            .join(Asset, Asset.id == AssetAssignment.asset_id)
            .join(Product, Product.id == AssetAssignment.product_id)
            .where(
                AssetAssignment.brand_id == ctx.brand_id,
                AssetAssignment.assigned_to == ctx.user.id,
                AssetAssignment.status.in_(("open", "in_progress")),
            )
            .order_by(AssetAssignment.created_at.desc())
        )
    ).all()
    data = []
    for a, asset, product in rows:
        item = ser_assignment(a, asset=asset)
        item["internal_reference"] = product.internal_reference
        item["product_name"] = ((product.content or {}).get("es") or {}).get("name")
        data.append(item)
    return {"data": data}


@router.patch("/assignments/{assignment_id}")
async def patch_assignment(
    assignment_id: UUID, body: AssignmentPatch, ctx: BrandAuthDep, session: SessionDep
) -> dict[str, Any]:
    row = await session.get(AssetAssignment, assignment_id)
    if row is None or row.brand_id != ctx.brand_id:
        raise AppError(ErrorCode.NOT_FOUND, "Assignment not found", status_code=404)
    is_assignee = row.assigned_to == ctx.user.id
    is_admin = ctx.membership.role in ("admin", "owner")
    if not is_assignee and not is_admin:
        raise AppError(ErrorCode.FORBIDDEN, "Forbidden", status_code=403)
    if body.status is not None:
        if body.status not in ("open", "in_progress", "cancelled"):
            raise AppError(ErrorCode.VALIDATION_ERROR, "Invalid status", status_code=422)
        if body.status == "cancelled" and not is_admin and row.assigned_by != ctx.user.id:
            raise AppError(ErrorCode.FORBIDDEN, "Forbidden", status_code=403)
        row.status = body.status
    if body.note is not None:
        row.note = body.note
    await session.commit()
    asset = await session.get(Asset, row.asset_id)
    user = await session.get(User, row.assigned_to)
    return ser_assignment(row, asset=asset, user=user)


@router.post("/products/{product_id}/publish")
async def publish(product_id: UUID, body: PublishBody, ctx: BrandAuthDep, session: SessionDep) -> dict[str, Any]:
    product = await _product(session, ctx.brand_id, product_id)
    if product.current_phase not in ("approval", "published"):
        raise AppError(ErrorCode.INVALID_TRANSITION, "Not in approval", status_code=409)
    if body.confirm_text != product.internal_reference:
        raise AppError(ErrorCode.VALIDATION_ERROR, "confirm_text must equal reference", status_code=422)
    if not await can(session, ctx, "product.review_current_phase", product=product) and ctx.membership.role not in ("admin", "owner"):
        raise AppError(ErrorCode.FORBIDDEN, "Forbidden", status_code=403)
    brand = await session.get(Brand, product.brand_id)
    criteria = await evaluate_exit_criteria(session, product, brand, "approval")
    if not all(c["ok"] for c in criteria):
        raise AppError(ErrorCode.EXIT_CRITERIA_NOT_MET, "Exit criteria not met", status_code=409, details={"criteria": criteria})
    job = await enqueue_job(
        session,
        brand_id=ctx.brand_id,
        type="publish_shopify",
        entity_type="product",
        entity_id=product.id,
        requested_by=ctx.user.id,
    )
    await session.commit()
    return {"job_id": str(job.id), "status": "queued"}


@router.get("/products/{product_id}/history")
async def history(product_id: UUID, ctx: BrandAuthDep, session: SessionDep) -> dict[str, Any]:
    from kitframe.db.models import AssetVersion

    product = await _product(session, ctx.brand_id, product_id)
    phases = (
        await session.execute(select(ProductPhase).where(ProductPhase.product_id == product.id))
    ).scalars().all()
    phase_by_id = {p.id: p for p in phases}
    phase_ids = list(phase_by_id.keys())

    reviews = []
    if phase_ids:
        reviews = (
            await session.execute(
                select(Review).where(Review.product_phase_id.in_(phase_ids)).order_by(Review.created_at.desc())
            )
        ).scalars().all()

    comments = (
        await session.execute(
            select(Comment).where(Comment.product_id == product.id).order_by(Comment.created_at.desc())
        )
    ).scalars().all()

    assignments = (
        await session.execute(
            select(AssetAssignment, Asset, User)
            .join(Asset, Asset.id == AssetAssignment.asset_id)
            .join(User, User.id == AssetAssignment.assigned_to)
            .where(AssetAssignment.product_id == product.id)
            .order_by(AssetAssignment.created_at.desc())
        )
    ).all()

    assets = (
        await session.execute(select(Asset).where(Asset.product_id == product.id))
    ).scalars().all()
    asset_by_id = {a.id: a for a in assets}
    versions: list[AssetVersion] = []
    if assets:
        versions = (
            await session.execute(
                select(AssetVersion)
                .where(AssetVersion.asset_id.in_([a.id for a in assets]))
                .order_by(AssetVersion.created_at.desc())
            )
        ).scalars().all()

    user_ids = {
        *[r.reviewer_user_id for r in reviews],
        *[c.author_id for c in comments],
        *[v.created_by for v in versions if v.created_by],
        *[a.assigned_by for a, _asset, _u in assignments],
    }
    users = {}
    if user_ids:
        for u in (
            await session.execute(select(User).where(User.id.in_(list(user_ids))))
        ).scalars().all():
            users[u.id] = u

    review_rows = []
    for r in reviews:
        phase_row = phase_by_id.get(r.product_phase_id)
        reviewer = users.get(r.reviewer_user_id)
        review_rows.append(
            {
                "id": str(r.id),
                "type": "review",
                "decision": r.decision,
                "comment": r.comment,
                "target_phase": r.target_phase,
                "self_review": r.self_review,
                "phase": phase_row.phase if phase_row else None,
                "reviewer_id": str(r.reviewer_user_id),
                "reviewer_name": reviewer.name if reviewer else None,
                "created_at": r.created_at.isoformat(),
            }
        )

    comment_rows = []
    for c in comments:
        author = users.get(c.author_id)
        comment_rows.append(
            {
                "id": str(c.id),
                "type": "comment",
                "body": c.body,
                "phase": c.phase,
                "author_id": str(c.author_id),
                "author_name": author.name if author else None,
                "review_id": str(c.review_id) if c.review_id else None,
                "asset_version_id": str(c.asset_version_id) if c.asset_version_id else None,
                "resolved_at": c.resolved_at.isoformat() if c.resolved_at else None,
                "created_at": c.created_at.isoformat(),
            }
        )

    assignment_rows = [
        {
            **ser_assignment(a, asset=asset, user=user),
            "type": "assignment",
            "assigner_name": users.get(a.assigned_by).name if users.get(a.assigned_by) else None,
        }
        for a, asset, user in assignments
    ]

    upload_rows = []
    for v in versions:
        asset = asset_by_id.get(v.asset_id)
        author = users.get(v.created_by) if v.created_by else None
        upload_rows.append(
            {
                "id": str(v.id),
                "type": "upload",
                "asset_id": str(v.asset_id),
                "shot_type": asset.shot_type if asset else None,
                "version_number": v.version_number,
                "source": v.source,
                "author_id": str(v.created_by) if v.created_by else None,
                "author_name": author.name if author else None,
                "created_at": v.created_at.isoformat(),
            }
        )

    timeline = sorted(
        [*review_rows, *comment_rows, *assignment_rows, *upload_rows],
        key=lambda x: x["created_at"],
        reverse=True,
    )

    audits = (
        await session.execute(
            select(AuditLog)
            .where(AuditLog.entity_type == "product", AuditLog.entity_id == product.id)
            .order_by(AuditLog.created_at.desc())
        )
    ).scalars().all()

    return {
        "reviews": review_rows,
        "comments": comment_rows,
        "assignments": assignment_rows,
        "uploads": upload_rows,
        "timeline": timeline,
        "audit": [
            {
                "id": str(a.id),
                "action": a.action,
                "detail": a.detail,
                "created_at": a.created_at.isoformat(),
            }
            for a in audits
        ],
    }


@router.get("/products/{product_id}/variants")
async def list_variants(product_id: UUID, ctx: BrandAuthDep, session: SessionDep) -> dict[str, Any]:
    await _product(session, ctx.brand_id, product_id)
    rows = (await session.execute(select(Variant).where(Variant.product_id == product_id).order_by(Variant.sort_order))).scalars().all()
    return {"data": [_ser_variant(v) for v in rows]}


@router.post("/products/{product_id}/variants")
async def create_variant(product_id: UUID, body: VariantIn, ctx: BrandAuthDep, session: SessionDep) -> dict[str, Any]:
    product = await _product(session, ctx.brand_id, product_id)
    if not await can(session, ctx, "product.edit_data", product=product):
        raise AppError(ErrorCode.FORBIDDEN, "Forbidden", status_code=403)
    v = Variant(brand_id=ctx.brand_id, product_id=product_id, **body.model_dump())
    session.add(v)
    await session.commit()
    return _ser_variant(v)


@router.patch("/variants/{variant_id}")
async def patch_variant(variant_id: UUID, body: VariantIn, ctx: BrandAuthDep, session: SessionDep) -> dict[str, Any]:
    v = await session.get(Variant, variant_id)
    if v is None or v.brand_id != ctx.brand_id:
        raise AppError(ErrorCode.NOT_FOUND, "Not found", status_code=404)
    product = await session.get(Product, v.product_id)
    if not await can(session, ctx, "product.edit_data", product=product):
        raise AppError(ErrorCode.FORBIDDEN, "Forbidden", status_code=403)
    for k, val in body.model_dump(exclude_unset=True).items():
        setattr(v, k, val)
    await session.commit()
    return _ser_variant(v)


@router.delete("/variants/{variant_id}", status_code=204)
async def delete_variant(variant_id: UUID, ctx: BrandAuthDep, session: SessionDep) -> None:
    v = await session.get(Variant, variant_id)
    if v is None or v.brand_id != ctx.brand_id:
        raise AppError(ErrorCode.NOT_FOUND, "Not found", status_code=404)
    product = await session.get(Product, v.product_id)
    if not await can(session, ctx, "product.edit_data", product=product):
        raise AppError(ErrorCode.FORBIDDEN, "Forbidden", status_code=403)
    await session.delete(v)
    await session.commit()


@router.get("/products/{product_id}/reviews")
async def list_reviews(product_id: UUID, ctx: BrandAuthDep, session: SessionDep) -> dict[str, Any]:
    product = await _product(session, ctx.brand_id, product_id)
    return {"data": await list_review_summaries(session, product)}


@router.get("/products/{product_id}/reviews/{review_id}")
async def get_review(
    product_id: UUID,
    review_id: UUID,
    ctx: BrandAuthDep,
    session: SessionDep,
    settings: SettingsDep,
) -> dict[str, Any]:
    product = await _product(session, ctx.brand_id, product_id)
    review = await session.get(Review, review_id)
    if review is None:
        raise AppError(ErrorCode.NOT_FOUND, "Review not found", status_code=404)
    phase = await session.get(ProductPhase, review.product_phase_id)
    if phase is None or phase.product_id != product.id:
        raise AppError(ErrorCode.NOT_FOUND, "Review not found", status_code=404)
    detail = await get_review_detail(
        session, brand_id=ctx.brand_id, product=product, review=review, settings=settings
    )
    open_r = await open_thread_review(session, product)
    is_active = open_r is not None and open_r.id == review.id
    detail["is_open"] = is_active
    detail["awaiting_resubmit"] = is_active and phase.status == "changes_requested"
    detail["can_reply"] = is_active and await can(session, ctx, "product.comment", product=product)
    actions = await allowed_actions(session, ctx, product)
    detail["can_upload"] = is_active and "upload_asset" in actions and phase.status != "in_review"
    detail["can_decide"] = (
        is_active
        and phase.status == "in_review"
        and await can(session, ctx, "product.review_current_phase", product=product)
    )
    return detail


@router.get("/products/{product_id}/comments")
async def list_comments(product_id: UUID, ctx: BrandAuthDep, session: SessionDep, phase: str | None = None) -> dict[str, Any]:
    await _product(session, ctx.brand_id, product_id)
    q = select(Comment).where(Comment.product_id == product_id).order_by(Comment.created_at.desc())
    if phase:
        q = q.where(Comment.phase == phase)
    rows = (await session.execute(q)).scalars().all()
    authors = {}
    author_ids = {c.author_id for c in rows}
    if author_ids:
        for u in (await session.execute(select(User).where(User.id.in_(list(author_ids))))).scalars().all():
            authors[u.id] = u
    return {
        "data": [
            {
                "id": str(c.id),
                "body": c.body,
                "phase": c.phase,
                "author_id": str(c.author_id),
                "author_name": authors[c.author_id].name if c.author_id in authors else None,
                "review_id": str(c.review_id) if c.review_id else None,
                "asset_version_id": str(c.asset_version_id) if c.asset_version_id else None,
                "annotation": c.annotation,
                "resolved_at": c.resolved_at.isoformat() if c.resolved_at else None,
                "created_at": c.created_at.isoformat(),
            }
            for c in rows
        ]
    }


@router.post("/products/{product_id}/comments")
async def create_comment(product_id: UUID, body: CommentIn, ctx: BrandAuthDep, session: SessionDep) -> dict[str, Any]:
    product = await _product(session, ctx.brand_id, product_id)
    if not await can(session, ctx, "product.comment", product=product):
        raise AppError(ErrorCode.FORBIDDEN, "Forbidden", status_code=403)
    phase = body.phase or product.current_phase
    review_id = body.review_id
    if review_id is None:
        open_r = await open_thread_review(session, product)
        if open_r is not None:
            review_id = open_r.id
    elif review_id is not None:
        review = await session.get(Review, review_id)
        if review is None:
            raise AppError(ErrorCode.NOT_FOUND, "Review not found", status_code=404)
        phase_row = await session.get(ProductPhase, review.product_phase_id)
        if phase_row is None or phase_row.product_id != product.id:
            raise AppError(ErrorCode.NOT_FOUND, "Review not found", status_code=404)
    annotation = body.annotation
    if annotation is not None:
        try:
            x = float(annotation.get("x", 0))
            y = float(annotation.get("y", 0))
            w = float(annotation.get("w", 0))
            h = float(annotation.get("h", 0))
        except (TypeError, ValueError):
            raise AppError(ErrorCode.VALIDATION_ERROR, "Invalid annotation", status_code=422)
        if not (
            0 <= x <= 1
            and 0 <= y <= 1
            and 0 < w <= 1
            and 0 < h <= 1
            and x + w <= 1.01
            and y + h <= 1.01
        ):
            raise AppError(ErrorCode.VALIDATION_ERROR, "Annotation out of bounds", status_code=422)
        color = annotation.get("color") or "#7A1F2B"
        if not isinstance(color, str) or not color.startswith("#") or len(color) not in (4, 7):
            color = "#7A1F2B"
        annotation = {"x": x, "y": y, "w": w, "h": h, "color": color}

    c = Comment(
        brand_id=ctx.brand_id,
        product_id=product_id,
        phase=phase,
        asset_version_id=body.asset_version_id,
        annotation=annotation,
        author_id=ctx.user.id,
        body=body.body,
        mentions=body.mentions,
        review_id=review_id,
    )
    session.add(c)
    await session.commit()
    return {
        "id": str(c.id),
        "body": c.body,
        "phase": c.phase,
        "author_id": str(c.author_id),
        "author_name": ctx.user.name,
        "review_id": str(c.review_id) if c.review_id else None,
        "asset_version_id": str(c.asset_version_id) if c.asset_version_id else None,
        "annotation": c.annotation,
        "created_at": c.created_at.isoformat() if c.created_at else None,
    }


@router.post("/comments/{comment_id}/resolve")
async def resolve_comment(comment_id: UUID, ctx: BrandAuthDep, session: SessionDep) -> dict[str, Any]:
    from datetime import UTC, datetime
    c = await session.get(Comment, comment_id)
    if c is None or c.brand_id != ctx.brand_id:
        raise AppError(ErrorCode.NOT_FOUND, "Not found", status_code=404)
    c.resolved_at = datetime.now(UTC)
    c.resolved_by = ctx.user.id
    await session.commit()
    return {"id": str(c.id), "resolved_at": c.resolved_at.isoformat()}


@router.post("/products/{product_id}/exports")
async def create_export(product_id: UUID, body: ExportIn, ctx: BrandAuthDep, session: SessionDep) -> dict[str, Any]:
    product = await _product(session, ctx.brand_id, product_id)
    if ctx.membership.role == "viewer":
        raise AppError(ErrorCode.FORBIDDEN, "Forbidden", status_code=403)
    exp = Export(brand_id=ctx.brand_id, product_id=product.id, channels=body.channels, requested_by=ctx.user.id)
    session.add(exp)
    await session.flush()
    job = await enqueue_job(session, brand_id=ctx.brand_id, type="build_export", entity_type="export", entity_id=exp.id, requested_by=ctx.user.id)
    await session.commit()
    return {"id": str(exp.id), "job_id": str(job.id), "status": exp.status}


@router.get("/exports/{export_id}")
async def get_export(export_id: UUID, ctx: BrandAuthDep, session: SessionDep, settings: SettingsDep) -> dict[str, Any]:
    exp = await session.get(Export, export_id)
    if exp is None or exp.brand_id != ctx.brand_id:
        raise AppError(ErrorCode.NOT_FOUND, "Not found", status_code=404)
    url = None
    if exp.storage_key:
        from kitframe.media.storage import presign_get
        url = presign_get(settings, exp.storage_key, expires=86400)
    return {"id": str(exp.id), "status": exp.status, "download_url": url, "channels": exp.channels}


@router.get("/tareas")
async def mis_tareas(ctx: BrandAuthDep, session: SessionDep) -> dict[str, Any]:
    """Tasks for current user across brand projects."""
    phases = (await session.execute(select(ProductPhase))).scalars().all()
    para_revisar = []
    cambios = []
    en_curso = []
    pendientes = []
    for ph in phases:
        product = await session.get(Product, ph.product_id)
        if product is None or product.brand_id != ctx.brand_id:
            continue
        if product.current_phase != ph.phase:
            continue
        brief = {
            "product_id": str(product.id),
            "internal_reference": product.internal_reference,
            "name": ((product.content or {}).get("es") or {}).get("name"),
            "project_id": str(product.project_id),
            "phase": ph.phase,
            "status": ph.status,
            "due_date": ph.due_date.isoformat() if ph.due_date else None,
        }
        can_review = await can(session, ctx, "product.review_current_phase", product=product)
        if ph.status == "in_review" and can_review:
            para_revisar.append(brief)
        elif ph.status == "changes_requested" and (ph.assignee_user_id == ctx.user.id or ph.assignee_user_id is None):
            cambios.append(brief)
        elif ph.status == "in_progress" and ph.assignee_user_id == ctx.user.id:
            en_curso.append(brief)
        elif ph.status == "todo" and ph.assignee_user_id == ctx.user.id:
            pendientes.append(brief)

    assign_rows = (
        await session.execute(
            select(AssetAssignment, Asset, Product)
            .join(Asset, Asset.id == AssetAssignment.asset_id)
            .join(Product, Product.id == AssetAssignment.product_id)
            .where(
                AssetAssignment.brand_id == ctx.brand_id,
                AssetAssignment.assigned_to == ctx.user.id,
                AssetAssignment.status.in_(("open", "in_progress")),
            )
            .order_by(AssetAssignment.created_at.desc())
        )
    ).all()
    imagenes_asignadas = []
    for a, asset, product in assign_rows:
        imagenes_asignadas.append(
            {
                "assignment_id": str(a.id),
                "product_id": str(product.id),
                "asset_id": str(asset.id),
                "internal_reference": product.internal_reference,
                "name": ((product.content or {}).get("es") or {}).get("name"),
                "shot_type": asset.shot_type,
                "phase": a.phase,
                "status": a.status,
                "note": a.note,
                "project_id": str(product.project_id),
            }
        )
    return {
        "para_revisar": para_revisar,
        "cambios_solicitados": cambios,
        "en_curso": en_curso,
        "pendientes": pendientes,
        "imagenes_asignadas": imagenes_asignadas,
    }


async def _product(session: SessionDep, brand_id: UUID, product_id: UUID) -> Product:
    product = await session.get(Product, product_id)
    if product is None or product.brand_id != brand_id:
        raise AppError(ErrorCode.NOT_FOUND, "Product not found", status_code=404)
    return product


def _ser_product(p: Product) -> dict[str, Any]:
    return {
        "id": str(p.id),
        "project_id": str(p.project_id),
        "internal_reference": p.internal_reference,
        "garment_category": p.garment_category,
        "current_phase": p.current_phase,
        "structured_data": p.structured_data,
        "field_confidence": p.field_confidence,
        "confirmed_fields": p.confirmed_fields,
        "content": p.content,
        "content_warnings": p.content_warnings,
        "shopify_ids": p.shopify_ids,
        "published_at": p.published_at.isoformat() if p.published_at else None,
    }


def _ser_phase(p: ProductPhase) -> dict[str, Any]:
    return {
        "id": str(p.id),
        "phase": p.phase,
        "status": p.status,
        "assignee_user_id": str(p.assignee_user_id) if p.assignee_user_id else None,
        "reviewer_user_id": str(p.reviewer_user_id) if p.reviewer_user_id else None,
        "due_date": p.due_date.isoformat() if p.due_date else None,
        "entered_at": p.entered_at.isoformat() if p.entered_at else None,
        "submitted_at": p.submitted_at.isoformat() if p.submitted_at else None,
        "completed_at": p.completed_at.isoformat() if p.completed_at else None,
    }


def _ser_variant(v: Variant) -> dict[str, Any]:
    return {
        "id": str(v.id),
        "color": v.color,
        "size": v.size,
        "sku": v.sku,
        "barcode": v.barcode,
        "price_eur": str(v.price_eur) if v.price_eur is not None else None,
        "compare_at_price_eur": str(v.compare_at_price_eur) if v.compare_at_price_eur is not None else None,
        "sort_order": v.sort_order,
    }
