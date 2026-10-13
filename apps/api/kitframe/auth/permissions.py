from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from kitframe.db.models import BrandMembership, Product, ProductPhase, Project, ProjectMember, User


@dataclass
class AuthContext:
    user: User
    brand_id: UUID | None
    membership: BrandMembership | None
    request_id: str


ROLE_CAPS: dict[str, set[str]] = {
    "viewer": {"brand.read"},
    "member": {"brand.read"},
    "editor": {"brand.read"},
    "admin": {
        "brand.read",
        "projects.manage",
        "library.manage",
        "golden.manage",
        "rights.manage",
        "qc.override",
        "brand.admin",
    },
    "owner": {
        "brand.read",
        "projects.manage",
        "library.manage",
        "golden.manage",
        "rights.manage",
        "qc.override",
        "brand.admin",
        "users.manage",
        "brand.manage",
    },
}


async def get_membership(
    session: AsyncSession, user_id: UUID, brand_id: UUID
) -> BrandMembership | None:
    result = await session.execute(
        select(BrandMembership).where(
            BrandMembership.user_id == user_id, BrandMembership.brand_id == brand_id
        )
    )
    return result.scalar_one_or_none()


def brand_role_allows(role: str, permission: str) -> bool:
    return permission in ROLE_CAPS.get(role, set())


async def can(
    session: AsyncSession,
    ctx: AuthContext,
    permission: str,
    *,
    product: Product | None = None,
    project: Project | None = None,
    phase: str | None = None,
) -> bool:
    if ctx.membership is None or ctx.brand_id is None:
        return False
    role = ctx.membership.role

    if permission == "golden.approve":
        return brand_role_allows(role, "golden.manage") and ctx.membership.can_approve_golden_set

    if permission in ROLE_CAPS.get(role, set()):
        if permission != "brand.read" and role == "viewer":
            return False
        if permission.startswith("brand.") or permission in {
            "projects.manage",
            "library.manage",
            "golden.manage",
            "rights.manage",
            "qc.override",
            "users.manage",
        }:
            return True

    if role in ("admin", "owner") and (
        permission.startswith(("project.", "product.")) or permission == "studio.use"
    ):
        return True

    if role == "viewer":
        return permission == "brand.read"

    if project is None and product is not None:
        project = await session.get(Project, product.project_id)
    if project is None:
        return False

    if permission == "project.lead":
        return project.lead_user_id == ctx.user.id or role in ("admin", "owner")

    if permission.startswith("project.edit_phase:"):
        target_phase = permission.split(":", 1)[1]
        if project.lead_user_id == ctx.user.id or role in ("admin", "owner"):
            return True
        result = await session.execute(
            select(ProjectMember).where(
                ProjectMember.project_id == project.id,
                ProjectMember.phase == target_phase,
                ProjectMember.user_id == ctx.user.id,
                ProjectMember.role == "editor",
            )
        )
        return result.scalar_one_or_none() is not None

    if permission == "product.edit_data":
        if product is None:
            return False
        if product.current_phase == "data":
            return await can(session, ctx, "project.edit_phase:data", project=project)
        return role in ("admin", "owner")

    if permission == "product.edit_current_phase":
        if product is None:
            return False
        phase_row = await _current_phase(session, product)
        if phase_row and phase_row.status == "in_review":
            return False
        return await can(
            session, ctx, f"project.edit_phase:{product.current_phase}", project=project
        )

    if permission == "product.edit_assets":
        if product is None:
            return False
        if product.current_phase not in ("visuals", "retouch"):
            return False
        phase_row = await _current_phase(session, product)
        if phase_row and phase_row.status == "in_review":
            return False
        if await can(
            session, ctx, f"project.edit_phase:{product.current_phase}", project=project
        ):
            return True
        # Brand editors can keep uploading during an open revision cycle
        if role == "editor" and phase_row and phase_row.status in (
            "in_progress",
            "changes_requested",
        ):
            return True
        return False

    if permission == "product.review_current_phase":
        if product is None:
            return False
        return await _can_review(session, ctx, product, project)

    if permission == "product.comment":
        if project.lead_user_id == ctx.user.id or role in ("admin", "owner", "editor"):
            return True
        result = await session.execute(
            select(ProjectMember).where(
                ProjectMember.project_id == project.id, ProjectMember.user_id == ctx.user.id
            )
        )
        if result.scalar_one_or_none() is not None:
            return True
        if product is not None:
            from kitframe.db.models import AssetAssignment

            assign = (
                await session.execute(
                    select(AssetAssignment).where(
                        AssetAssignment.product_id == product.id,
                        AssetAssignment.assigned_to == ctx.user.id,
                        AssetAssignment.status.in_(("open", "in_progress")),
                    ).limit(1)
                )
            ).scalar_one_or_none()
            if assign is not None:
                return True
        return False

    if permission == "studio.use":
        if role in ("admin", "owner"):
            return True
        result = await session.execute(
            select(ProjectMember).where(
                ProjectMember.user_id == ctx.user.id,
                ProjectMember.phase == "visuals",
                ProjectMember.role == "editor",
            )
        )
        return result.scalar_one_or_none() is not None

    return False


async def _current_phase(session: AsyncSession, product: Product) -> ProductPhase | None:
    if product.current_phase == "published":
        return None
    result = await session.execute(
        select(ProductPhase).where(
            ProductPhase.product_id == product.id, ProductPhase.phase == product.current_phase
        )
    )
    return result.scalar_one_or_none()


async def _can_review(
    session: AsyncSession, ctx: AuthContext, product: Product, project: Project
) -> bool:
    if ctx.membership and ctx.membership.role in ("admin", "owner"):
        return True
    phase_row = await _current_phase(session, product)
    if phase_row is None:
        return False
    if phase_row.reviewer_user_id is not None:
        return phase_row.reviewer_user_id == ctx.user.id
    result = await session.execute(
        select(ProjectMember).where(
            ProjectMember.project_id == project.id,
            ProjectMember.phase == product.current_phase,
            ProjectMember.role == "reviewer",
            ProjectMember.user_id == ctx.user.id,
        )
    )
    if result.scalar_one_or_none() is not None:
        return True
    reviewers = await session.execute(
        select(ProjectMember).where(
            ProjectMember.project_id == project.id,
            ProjectMember.phase == product.current_phase,
            ProjectMember.role == "reviewer",
        )
    )
    if reviewers.scalars().first() is None:
        return project.lead_user_id == ctx.user.id
    return False


async def allowed_actions(session: AsyncSession, ctx: AuthContext, product: Product) -> list[str]:
    from kitframe.db.models import AssetAssignment

    project = await session.get(Project, product.project_id)
    actions: list[str] = []
    checks: list[tuple[str, str]] = [
        ("start", "product.edit_current_phase"),
        ("submit", "product.edit_current_phase"),
        ("review", "product.review_current_phase"),
        ("publish", "product.review_current_phase"),
        ("comment", "product.comment"),
        ("upload_asset", "product.edit_assets"),
        ("edit_data", "product.edit_data"),
        ("studio", "studio.use"),
    ]
    for action, perm in checks:
        if await can(session, ctx, perm, product=product, project=project):
            actions.append(action)
    if "upload_asset" not in actions:
        open_assign = (
            await session.execute(
                select(AssetAssignment).where(
                    AssetAssignment.product_id == product.id,
                    AssetAssignment.assigned_to == ctx.user.id,
                    AssetAssignment.status.in_(("open", "in_progress")),
                ).limit(1)
            )
        ).scalar_one_or_none()
        if open_assign is not None:
            actions.append("upload_asset")
    return actions


def serialize_user(user: User, memberships: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "id": str(user.id),
        "email": user.email,
        "name": user.name,
        "locale": user.locale,
        "memberships": memberships,
    }
