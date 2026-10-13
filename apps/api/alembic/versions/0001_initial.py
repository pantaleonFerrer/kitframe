"""initial schema

Revision ID: 0001
Revises:
Create Date: 2026-09-28
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS citext")
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")
    from kitframe.db.models import Base
    bind = op.get_bind()
    Base.metadata.create_all(bind=bind)
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS golden_one_approved
        ON golden_set_images (brand_id, garment_category, shot_type)
        WHERE status = 'approved'
        """
    )
    op.execute(
        """
        DO $$ BEGIN
          ALTER TABLE assets
            ADD CONSTRAINT assets_current_version_fk
            FOREIGN KEY (current_version_id) REFERENCES asset_versions(id)
            DEFERRABLE INITIALLY DEFERRED;
        EXCEPTION WHEN duplicate_object THEN NULL; END $$;
        """
    )


def downgrade() -> None:
    from kitframe.db.models import Base
    bind = op.get_bind()
    Base.metadata.drop_all(bind=bind)
