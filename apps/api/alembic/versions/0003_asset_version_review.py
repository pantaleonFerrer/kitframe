"""add review_id to asset_versions for review threads

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-01

Idempotent: 0001 create_all may already have added review_id on asset_versions.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0003"
down_revision: Union[str, None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {col["name"] for col in inspector.get_columns("asset_versions")}
    indexes = {idx["name"] for idx in inspector.get_indexes("asset_versions")}

    if "review_id" not in columns:
        op.add_column(
            "asset_versions",
            sa.Column("review_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("reviews.id")),
        )
    if "ix_asset_versions_review_id" not in indexes:
        op.create_index("ix_asset_versions_review_id", "asset_versions", ["review_id"])


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {col["name"] for col in inspector.get_columns("asset_versions")}
    indexes = {idx["name"] for idx in inspector.get_indexes("asset_versions")}

    if "ix_asset_versions_review_id" in indexes:
        op.drop_index("ix_asset_versions_review_id", table_name="asset_versions")
    if "review_id" in columns:
        op.drop_column("asset_versions", "review_id")
