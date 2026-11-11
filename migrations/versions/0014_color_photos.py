"""photos of a product printed in different colours; a note on the product page

Revision ID: 0014
Revises: 0013
Create Date: 2026-11-11
"""
from alembic import op
import sqlalchemy as sa

revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("product_media", sa.Column("color_id", sa.Integer,
                                             sa.ForeignKey("filament_colors.id", ondelete="SET NULL"), nullable=True))
    op.create_index("ix_product_media_color_id", "product_media", ["color_id"])
    op.add_column("products", sa.Column("note", sa.Text, nullable=False, server_default=""))


def downgrade() -> None:
    op.drop_column("products", "note")
    op.drop_index("ix_product_media_color_id", "product_media")
    op.drop_column("product_media", "color_id")
