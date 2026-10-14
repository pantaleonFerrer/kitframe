"""asset assignments for editor revisions

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-01

Note: 0001 uses Base.metadata.create_all(), so on a fresh install the current
models (including asset_assignments) already exist. This revision is idempotent.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "asset_assignments" in inspector.get_table_names():
        return

    op.create_table(
        "asset_assignments",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("brand_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("brands.id"), nullable=False),
        sa.Column("product_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("products.id"), nullable=False),
        sa.Column("asset_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("assets.id"), nullable=False),
        sa.Column("review_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("reviews.id")),
        sa.Column("assigned_to", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("assigned_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("phase", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False, server_default="open"),
        sa.Column("note", sa.Text(), nullable=False, server_default=""),
        sa.Column("completed_version_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("asset_versions.id")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_asset_assignments_brand_id", "asset_assignments", ["brand_id"])
    op.create_index("ix_asset_assignments_product_id", "asset_assignments", ["product_id"])
    op.create_index("ix_asset_assignments_asset_id", "asset_assignments", ["asset_id"])
    op.create_index("ix_asset_assignments_assigned_to", "asset_assignments", ["assigned_to"])
    op.create_index("ix_asset_assignments_review_id", "asset_assignments", ["review_id"])


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "asset_assignments" in inspector.get_table_names():
        op.drop_table("asset_assignments")
