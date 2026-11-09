"""personal account: saved contacts and address for the next orders

Revision ID: 0009
Revises: 0008
Create Date: 2026-11-09
"""
from alembic import op
import sqlalchemy as sa

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("phone", sa.String(60), nullable=False, server_default=""))
    op.add_column("users", sa.Column("email", sa.String(160), nullable=False, server_default=""))
    op.add_column("users", sa.Column("address", sa.String(1000), nullable=False, server_default=""))
    op.add_column("users", sa.Column("delivery", sa.String(40), nullable=False, server_default=""))


def downgrade() -> None:
    for c in ("delivery", "address", "email", "phone"):
        op.drop_column("users", c)
