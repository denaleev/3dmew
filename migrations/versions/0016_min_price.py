"""products: the lowest price, whatever plastic is chosen

Revision ID: 0016
Revises: 0015
Create Date: 2026-11-23
"""
from alembic import op
import sqlalchemy as sa

revision = "0016"
down_revision = "0015"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("products", sa.Column("min_price", sa.Numeric(12, 2), nullable=True))


def downgrade() -> None:
    op.drop_column("products", "min_price")
