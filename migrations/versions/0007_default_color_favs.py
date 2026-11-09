"""standard colour of a product, favourites of every visitor (for the statistics)

Revision ID: 0007
Revises: 0006
Create Date: 2026-11-09
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("products", sa.Column("default_color", sa.Integer, nullable=True))
    op.add_column("carts", sa.Column("favs", JSONB, nullable=False, server_default="[]"))
    op.add_column("orders", sa.Column("source", sa.String(60), nullable=False, server_default=""))


def downgrade() -> None:
    op.drop_column("orders", "source")
    op.drop_column("carts", "favs")
    op.drop_column("products", "default_color")
