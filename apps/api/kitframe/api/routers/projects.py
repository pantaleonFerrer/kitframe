from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Any
from uuid import UUID, uuid4

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field
from sqlalchemy import select

from kitframe.api.deps import BrandAuthDep, SessionDep
from kitframe.auth.permissions import brand_role_allows, can
from kitframe.db.models import Product, ProductPhase, Project, ProjectMember, SourceDocument
from kitframe.errors import AppError, ErrorCode

router = APIRouter(tags=["projects"])

PHASES = ("data", "visuals", "retouch", "approval")


class ProjectCreate(BaseModel):
    name: str
    description: str = ""
    lead_user_id: UUID | None = None
    requirements: list[dict[str, Any]] = Field(default_factory=list)
    phase_due_dates: dict[str, Any] = Field(default_factory=dict)
    sample_arrival_date: date | None = None
    must_ship_date: date | None = None
    sale_date: date | None = None


class ProjectPatch(BaseModel):
    name: str | None = None
    description: str | None = None
    lead_user_id: UUID | None = None
    requirements: list[dict[str, Any]] | None = None
    phase_due_dates: dict[str, Any] | None = None
    sample_arrival_date: date | None = None
    must_ship_date: date | None = None
    sale_date: date | None = None


class MemberIn(BaseModel):
    phase: str
    user_id: UUID
    role: str


class SourceDocIn(BaseModel):
    storage_key: str
    file_name: str


@router.get("/projects")
async def list_projects(
    ctx: BrandAuthDep,
    session: SessionDep,
    status: str = Query(default="active"),
) -> dict[str, Any]:
    q = select(Project).where(Project.brand_id == ctx.brand_id)
    if status:
        q = q.where(Project.status == status)
    rows = (await session.execute(q.order_by(Project.created_at.desc()))).scalars().all()
    data = []
    for p in rows:
        products = (await session.execute(select(Product).where(Product.project_id == p.id))).scalars().all()
        counts: dict[str, int] = {ph: 0 for ph in (*PHASES, "published")}
        for prod in products:
            counts[prod.current_phase] = counts.get(prod.current_phase, 0) + 1
        data.append({**_ser_project(p), "counts": counts, "product_count": len(products)})
    return {"data": data, "total": len(data), "page": 1, "page_size": len(data)}


@router.post("/projects")
async def create_project(body: ProjectCreate, ctx: BrandAuthDep, session: SessionDep) -> dict[str, Any]:
    if not brand_role_allows(ctx.membership.role, "projects.manage"):
        raise AppError(ErrorCode.FORBIDDEN, "Forbidden", status_code=403)
    reqs = body.requirements or []
    for r in reqs:
        r.setdefault("id", str(uuid4()))
    project = Project(
        brand_id=ctx.brand_id,
        name=body.name,
        description=body.description,
        lead_user_id=body.lead_user_id or ctx.user.id,
        requirements=reqs,
        phase_due_dates=body.phase_due_dates,
        sample_arrival_date=body.sample_arrival_date,
        must_ship_date=body.must_ship_date,
        sale_date=body.sale_date,
    )
    session.add(project)
    await session.flush()
    await session.commit()
    return _ser_project(project)


@router.get("/projects/{project_id}")
async def get_project(project_id: UUID, ctx: BrandAuthDep, session: SessionDep) -> dict[str, Any]:
    project = await _get_project(session, ctx.brand_id, project_id)
    return _ser_project(project)


@router.patch("/projects/{project_id}")
async def patch_project(project_id: UUID, body: ProjectPatch, ctx: BrandAuthDep, session: SessionDep) -> dict[str, Any]:
    project = await _get_project(session, ctx.brand_id, project_id)
    if not await can(session, ctx, "project.lead", project=project):
        raise AppError(ErrorCode.FORBIDDEN, "Forbidden", status_code=403)
    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(project, k, v)
    project.updated_at = datetime.now(UTC)
    await session.commit()
    return _ser_project(project)


@router.post("/projects/{project_id}/archive")
async def archive_project(project_id: UUID, ctx: BrandAuthDep, session: SessionDep) -> dict[str, Any]:
    project = await _get_project(session, ctx.brand_id, project_id)
    if not await can(session, ctx, "project.lead", project=project):
        raise AppError(ErrorCode.FORBIDDEN, "Forbidden", status_code=403)
    project.status = "archived"
    await session.commit()
    return _ser_project(project)


@router.get("/projects/{project_id}/members")
async def get_members(project_id: UUID, ctx: BrandAuthDep, session: SessionDep) -> dict[str, Any]:
    await _get_project(session, ctx.brand_id, project_id)
    rows = (await session.execute(select(ProjectMember).where(ProjectMember.project_id == project_id))).scalars().all()
    return {"data": [{"id": str(m.id), "phase": m.phase, "user_id": str(m.user_id), "role": m.role} for m in rows]}


@router.put("/projects/{project_id}/members")
async def put_members(project_id: UUID, body: list[MemberIn], ctx: BrandAuthDep, session: SessionDep) -> dict[str, Any]:
    project = await _get_project(session, ctx.brand_id, project_id)
    if not await can(session, ctx, "project.lead", project=project):
        raise AppError(ErrorCode.FORBIDDEN, "Forbidden", status_code=403)
    existing = (await session.execute(select(ProjectMember).where(ProjectMember.project_id == project_id))).scalars().all()
    for e in existing:
        await session.delete(e)
    for m in body:
        session.add(ProjectMember(project_id=project_id, phase=m.phase, user_id=m.user_id, role=m.role))
    await session.commit()
    return await get_members(project_id, ctx, session)


@router.get("/projects/{project_id}/board")
async def board(project_id: UUID, ctx: BrandAuthDep, session: SessionDep) -> dict[str, Any]:
    await _get_project(session, ctx.brand_id, project_id)
    products = (await session.execute(select(Product).where(Product.project_id == project_id))).scalars().all()
    grouped: dict[str, list[dict[str, Any]]] = {ph: [] for ph in (*PHASES, "published")}
    for p in products:
        phase_row = None
        if p.current_phase != "published":
            phase_row = (
                await session.execute(
                    select(ProductPhase).where(ProductPhase.product_id == p.id, ProductPhase.phase == p.current_phase)
                )
            ).scalar_one_or_none()
        grouped[p.current_phase].append(
            {
                "id": str(p.id),
                "internal_reference": p.internal_reference,
                "name": ((p.content or {}).get("es") or {}).get("name"),
                "current_phase": p.current_phase,
                "phase_status": phase_row.status if phase_row else "done",
                "assignee_user_id": str(phase_row.assignee_user_id) if phase_row and phase_row.assignee_user_id else None,
                "due_date": phase_row.due_date.isoformat() if phase_row and phase_row.due_date else None,
            }
        )
    return {"columns": grouped}


@router.get("/projects/{project_id}/calendar")
async def calendar(project_id: UUID, ctx: BrandAuthDep, session: SessionDep) -> dict[str, Any]:
    project = await _get_project(session, ctx.brand_id, project_id)
    products = (await session.execute(select(Product).where(Product.project_id == project_id))).scalars().all()
    rows = []
    for p in products:
        phases = (await session.execute(select(ProductPhase).where(ProductPhase.product_id == p.id))).scalars().all()
        rows.append(
            {
                "product_id": str(p.id),
                "internal_reference": p.internal_reference,
                "phases": [
                    {
                        "phase": ph.phase,
                        "status": ph.status,
                        "entered_at": ph.entered_at.isoformat() if ph.entered_at else None,
                        "due_date": ph.due_date.isoformat() if ph.due_date else None,
                    }
                    for ph in phases
                ],
            }
        )
    return {
        "project": {
            "sample_arrival_date": project.sample_arrival_date.isoformat() if project.sample_arrival_date else None,
            "must_ship_date": project.must_ship_date.isoformat() if project.must_ship_date else None,
            "sale_date": project.sale_date.isoformat() if project.sale_date else None,
        },
        "products": rows,
    }


@router.get("/projects/{project_id}/products")
async def list_products(
    project_id: UUID,
    ctx: BrandAuthDep,
    session: SessionDep,
    phase: str | None = None,
    status: str | None = None,
    assignee: str | None = None,
) -> dict[str, Any]:
    await _get_project(session, ctx.brand_id, project_id)
    q = select(Product).where(Product.project_id == project_id)
    if phase:
        q = q.where(Product.current_phase == phase)
    products = (await session.execute(q)).scalars().all()
    data = []
    for p in products:
        phase_row = None
        if p.current_phase != "published":
            phase_row = (
                await session.execute(
                    select(ProductPhase).where(ProductPhase.product_id == p.id, ProductPhase.phase == p.current_phase)
                )
            ).scalar_one_or_none()
        if status and phase_row and phase_row.status != status:
            continue
        if assignee == "me" and phase_row and phase_row.assignee_user_id != ctx.user.id:
            continue
        data.append(_ser_product_brief(p, phase_row))
    return {"data": data, "total": len(data), "page": 1, "page_size": len(data)}


@router.post("/projects/{project_id}/products")
async def create_product(project_id: UUID, body: dict[str, Any], ctx: BrandAuthDep, session: SessionDep) -> dict[str, Any]:
    project = await _get_project(session, ctx.brand_id, project_id)
    if not await can(session, ctx, "project.edit_phase:data", project=project):
        raise AppError(ErrorCode.FORBIDDEN, "Forbidden", status_code=403)
    ref = body.get("internal_reference") or f"REF-{uuid4().hex[:8].upper()}"
    product = Product(
        brand_id=ctx.brand_id,
        project_id=project_id,
        internal_reference=ref,
        garment_category=body.get("garment_category"),
        structured_data=body.get("structured_data") or {},
        content=body.get("content") or {},
    )
    session.add(product)
    await session.flush()
    for phase in PHASES:
        due = None
        raw = (project.phase_due_dates or {}).get(phase)
        if raw:
            due = date.fromisoformat(raw) if isinstance(raw, str) else raw
        status = "todo"
        entered = None
        if phase == "data":
            entered = datetime.now(UTC)
        session.add(
            ProductPhase(
                product_id=product.id,
                phase=phase,
                status=status,
                due_date=due,
                entered_at=entered,
            )
        )
    await session.commit()
    return {"id": str(product.id), "internal_reference": product.internal_reference}


@router.post("/projects/{project_id}/source-documents")
async def add_source_doc(project_id: UUID, body: SourceDocIn, ctx: BrandAuthDep, session: SessionDep) -> dict[str, Any]:
    project = await _get_project(session, ctx.brand_id, project_id)
    if not await can(session, ctx, "project.edit_phase:data", project=project):
        raise AppError(ErrorCode.FORBIDDEN, "Forbidden", status_code=403)
    ext = body.file_name.rsplit(".", 1)[-1].lower()
    file_type = "pdf" if ext == "pdf" else "xlsx" if ext in ("xlsx", "xls") else "image"
    doc = SourceDocument(
        brand_id=ctx.brand_id,
        project_id=project_id,
        storage_key=body.storage_key,
        file_name=body.file_name,
        file_type=file_type,
        sha256="pending",
        uploaded_by=ctx.user.id,
        extraction_status="pending",
    )
    session.add(doc)
    await session.flush()
    from kitframe.jobs.enqueue import enqueue_job
    await enqueue_job(session, brand_id=ctx.brand_id, type="extract_document", entity_type="source_document", entity_id=doc.id, requested_by=ctx.user.id)
    await session.commit()
    return {"id": str(doc.id), "extraction_status": doc.extraction_status}


@router.get("/projects/{project_id}/source-documents")
async def list_source_docs(project_id: UUID, ctx: BrandAuthDep, session: SessionDep) -> dict[str, Any]:
    await _get_project(session, ctx.brand_id, project_id)
    rows = (await session.execute(select(SourceDocument).where(SourceDocument.project_id == project_id))).scalars().all()
    return {
        "data": [
            {
                "id": str(d.id),
                "file_name": d.file_name,
                "file_type": d.file_type,
                "extraction_status": d.extraction_status,
                "product_ids": [str(x) for x in (d.product_ids or [])],
                "error_detail": d.error_detail,
            }
            for d in rows
        ]
    }


async def _get_project(session: SessionDep, brand_id: UUID, project_id: UUID) -> Project:
    project = await session.get(Project, project_id)
    if project is None or project.brand_id != brand_id:
        raise AppError(ErrorCode.NOT_FOUND, "Project not found", status_code=404)
    return project


def _ser_project(p: Project) -> dict[str, Any]:
    return {
        "id": str(p.id),
        "name": p.name,
        "description": p.description,
        "lead_user_id": str(p.lead_user_id),
        "requirements": p.requirements,
        "phase_due_dates": p.phase_due_dates,
        "sample_arrival_date": p.sample_arrival_date.isoformat() if p.sample_arrival_date else None,
        "must_ship_date": p.must_ship_date.isoformat() if p.must_ship_date else None,
        "sale_date": p.sale_date.isoformat() if p.sale_date else None,
        "status": p.status,
    }


def _ser_product_brief(p: Product, phase_row: ProductPhase | None) -> dict[str, Any]:
    return {
        "id": str(p.id),
        "internal_reference": p.internal_reference,
        "current_phase": p.current_phase,
        "name": ((p.content or {}).get("es") or {}).get("name"),
        "phase_status": phase_row.status if phase_row else "done",
        "assignee_user_id": str(phase_row.assignee_user_id) if phase_row and phase_row.assignee_user_id else None,
        "due_date": phase_row.due_date.isoformat() if phase_row and phase_row.due_date else None,
    }
