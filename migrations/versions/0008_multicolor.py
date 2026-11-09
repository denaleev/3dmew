"""several colours in one product: the price waits for the administrator (after the slicer)

Revision ID: 0008
Revises: 0007
Create Date: 2026-11-09
"""
from alembic import op
import sqlalchemy as sa

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("order_items", sa.Column("price_pending", sa.Boolean, nullable=False, server_default=sa.false()))


def downgrade() -> None:
    op.drop_column("order_items", "price_pending")
