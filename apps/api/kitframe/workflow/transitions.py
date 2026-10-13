from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from kitframe.db.models import Product, ProductPhase, Review
from kitframe.errors import AppError, ErrorCode
from kitframe.workflow.criteria import evaluate_exit_criteria

PHASES = ("data", "visuals", "retouch", "approval")
NEXT_PHASE = {
    "data": "visuals",
    "visuals": "retouch",
    "retouch": "approval",
    "approval": "published",
}


async def get_phase(session: AsyncSession, product_id: UUID, phase: str) -> ProductPhase:
    result = await session.execute(
        select(ProductPhase).where(ProductPhase.product_id == product_id, ProductPhase.phase == phase)
    )
    row = result.scalar_one_or_none()
    if row is None:
        raise AppError(ErrorCode.NOT_FOUND, "Phase not found", status_code=404)
    return row


async def start_phase(session: AsyncSession, product: Product, user_id: UUID) -> ProductPhase:
    if product.current_phase == "published":
        raise AppError(ErrorCode.INVALID_TRANSITION, "Product already published", status_code=409)
    phase = await get_phase(session, product.id, product.current_phase)
    if phase.status not in ("todo", "changes_requested"):
        if phase.status == "in_progress":
            return phase
        raise AppError(ErrorCode.INVALID_TRANSITION, f"Cannot start from {phase.status}", status_code=409)
    if phase.status == "todo":
        phase.status = "in_progress"
        if phase.entered_at is None:
            phase.entered_at = datetime.now(UTC)
        if phase.assignee_user_id is None:
            phase.assignee_user_id = user_id
        phase.updated_at = datetime.now(UTC)
    return phase


async def submit_phase(
    session: AsyncSession,
    product: Product,
    brand: Any,
    user_id: UUID,
) -> ProductPhase:
    phase = await get_phase(session, product.id, product.current_phase)
    if phase.status not in ("in_progress", "changes_requested"):
        raise AppError(
            ErrorCode.INVALID_TRANSITION,
            f"Cannot submit from {phase.status}",
            status_code=409,
        )
    criteria = await evaluate_exit_criteria(session, product, brand, product.current_phase)
    if not all(c["ok"] for c in criteria):
        raise AppError(
            ErrorCode.EXIT_CRITERIA_NOT_MET,
            "Exit criteria not met",
            status_code=409,
            details={"criteria": criteria},
        )
    phase.status = "in_review"
    phase.submitted_by = user_id
    phase.submitted_at = datetime.now(UTC)
    phase.updated_at = datetime.now(UTC)
    return phase


async def review_phase(
    session: AsyncSession,
    product: Product,
    brand: Any,
    reviewer_id: UUID,
    decision: str,
    comment: str | None,
    target_phase: str | None,
    requirements_checked: list[str],
    self_review: bool = False,
) -> tuple[ProductPhase, Review]:
    phase = await get_phase(session, product.id, product.current_phase)
    if phase.status != "in_review":
        raise AppError(ErrorCode.INVALID_TRANSITION, "Phase is not in review", status_code=409)

    if decision == "changes_requested":
        if not comment:
            raise AppError(ErrorCode.VALIDATION_ERROR, "Comment required", status_code=422)
        phase.status = "changes_requested"
        phase.updated_at = datetime.now(UTC)
        review = Review(
            product_phase_id=phase.id,
            reviewer_user_id=reviewer_id,
            decision=decision,
            comment=comment,
            requirements_checked=requirements_checked,
            self_review=self_review,
        )
        session.add(review)
        return phase, review

    if decision == "sent_back":
        if not comment or not target_phase:
            raise AppError(ErrorCode.VALIDATION_ERROR, "Comment and target_phase required", status_code=422)
        if target_phase not in PHASES or PHASES.index(target_phase) >= PHASES.index(product.current_phase):
            raise AppError(ErrorCode.INVALID_TRANSITION, "Invalid send-back target", status_code=409)
        await _send_back(session, product, target_phase)
        review = Review(
            product_phase_id=phase.id,
            reviewer_user_id=reviewer_id,
            decision=decision,
            target_phase=target_phase,
            comment=comment,
            requirements_checked=requirements_checked,
            self_review=self_review,
        )
        session.add(review)
        target = await get_phase(session, product.id, target_phase)
        return target, review

    if decision != "approved":
        raise AppError(ErrorCode.VALIDATION_ERROR, "Invalid decision", status_code=422)

    # requirements come from project — caller may attach them as _project_requirements
    project_requirements = getattr(brand, "_project_requirements", None)
    if project_requirements is None and hasattr(brand, "requirements"):
        project_requirements = brand.requirements
    if product.current_phase in ("visuals", "retouch", "approval") and project_requirements:
        needed = {r["id"] for r in project_requirements}
        if not needed.issubset(set(requirements_checked)):
            raise AppError(
                ErrorCode.REQUIREMENTS_NOT_CHECKED,
                "All project requirements must be checked",
                status_code=422,
            )

    if product.current_phase == "approval":
        # Publish is separate; approval only marks done after publish succeeds
        raise AppError(
            ErrorCode.INVALID_TRANSITION,
            "Use publish endpoint for approval phase",
            status_code=409,
        )

    criteria = await evaluate_exit_criteria(session, product, brand, product.current_phase)
    if not all(c["ok"] for c in criteria):
        raise AppError(
            ErrorCode.EXIT_CRITERIA_NOT_MET,
            "Exit criteria not met",
            status_code=409,
            details={"criteria": criteria},
        )

    phase.status = "done"
    phase.completed_at = datetime.now(UTC)
    phase.updated_at = datetime.now(UTC)
    next_phase = NEXT_PHASE[product.current_phase]
    product.current_phase = next_phase
    product.updated_at = datetime.now(UTC)
    if next_phase != "published":
        nxt = await get_phase(session, product.id, next_phase)
        nxt.entered_at = datetime.now(UTC)
        if next_phase == "approval":
            nxt.status = "in_review"
        nxt.updated_at = datetime.now(UTC)

    review = Review(
        product_phase_id=phase.id,
        reviewer_user_id=reviewer_id,
        decision="approved",
        comment=comment,
        requirements_checked=requirements_checked,
        self_review=self_review,
    )
    session.add(review)
    return phase, review


async def mark_published(session: AsyncSession, product: Product, reviewer_id: UUID) -> ProductPhase:
    phase = await get_phase(session, product.id, "approval")
    if phase.status != "in_review":
        raise AppError(ErrorCode.INVALID_TRANSITION, "Approval not in review", status_code=409)
    phase.status = "done"
    phase.completed_at = datetime.now(UTC)
    phase.updated_at = datetime.now(UTC)
    product.current_phase = "published"
    product.published_at = datetime.now(UTC)
    product.updated_at = datetime.now(UTC)
    review = Review(
        product_phase_id=phase.id,
        reviewer_user_id=reviewer_id,
        decision="approved",
        requirements_checked=[],
    )
    session.add(review)
    return phase


async def _send_back(session: AsyncSession, product: Product, target_phase: str) -> None:
    target_idx = PHASES.index(target_phase)
    for i, phase_key in enumerate(PHASES):
        row = await get_phase(session, product.id, phase_key)
        if i == target_idx:
            row.status = "changes_requested"
            row.updated_at = datetime.now(UTC)
        elif i > target_idx:
            row.status = "todo"
            row.submitted_by = None
            row.submitted_at = None
            row.completed_at = None
            row.entered_at = None
            row.updated_at = datetime.now(UTC)
    product.current_phase = target_phase
    product.updated_at = datetime.now(UTC)


def assert_not_locked(phase: ProductPhase) -> None:
    if phase.status == "in_review":
        raise AppError(ErrorCode.PHASE_LOCKED, "Phase is locked while in review", status_code=409)
