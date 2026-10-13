"""add review_id to asset_versions for review threads

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-01
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
    op.add_column(
        "asset_versions",
        sa.Column("review_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("reviews.id")),
    )
    op.create_index("ix_asset_versions_review_id", "asset_versions", ["review_id"])


def downgrade() -> None:
    op.drop_index("ix_asset_versions_review_id", table_name="asset_versions")
    op.drop_column("asset_versions", "review_id")
