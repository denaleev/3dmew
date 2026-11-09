"""categories with icons, plastic price per colour

Revision ID: 0005
Revises: 0004
Create Date: 2026-11-09
"""
from alembic import op
import sqlalchemy as sa

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("filament_colors", sa.Column("kg_price", sa.Numeric(10, 2), nullable=True))
    op.create_table(
        "categories",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("name", sa.String(80), nullable=False, unique=True),
        sa.Column("icon", sa.String(16), nullable=False, server_default="📦"),
        sa.Column("sort", sa.Integer, nullable=False, server_default="0"),
        sa.Column("active", sa.Boolean, nullable=False, server_default=sa.true()),
    )
    # groups that products already use
    op.execute("INSERT INTO categories (name, sort) SELECT category, row_number() OVER (ORDER BY count(*) DESC) * 10 "
               "FROM products WHERE category <> '' GROUP BY category")


def downgrade() -> None:
    op.drop_table("categories")
    op.drop_column("filament_colors", "kg_price")
