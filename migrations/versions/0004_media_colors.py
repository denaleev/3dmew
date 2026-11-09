"""product photos/videos, filament colours, colour in order lines, feedback messages

Revision ID: 0004
Revises: 0003
Create Date: 2026-11-09
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("products", sa.Column("colors", JSONB, nullable=True))
    op.add_column("order_items", sa.Column("color", sa.String(120), nullable=False, server_default=""))
    op.create_table(
        "product_media",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("product_id", sa.Integer, sa.ForeignKey("products.id", ondelete="CASCADE"), nullable=False),
        sa.Column("kind", sa.String(10), nullable=False),
        sa.Column("mime", sa.String(100), nullable=False),
        sa.Column("name", sa.String(300), nullable=False, server_default=""),
        sa.Column("size", sa.BigInteger, nullable=False, server_default="0"),
        sa.Column("data", sa.LargeBinary, nullable=False),
        sa.Column("thumb", sa.LargeBinary, nullable=True),
        sa.Column("sort", sa.Integer, nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_product_media_product_id", "product_media", ["product_id"])
    op.create_table(
        "filament_colors",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("hex", sa.String(9), nullable=False, server_default="#cccccc"),
        sa.Column("hex2", sa.String(9), nullable=False, server_default=""),
        sa.Column("material", sa.String(60), nullable=False, server_default=""),
        sa.Column("note", sa.String(300), nullable=False, server_default=""),
        sa.Column("photo", sa.LargeBinary, nullable=True),
        sa.Column("thumb", sa.LargeBinary, nullable=True),
        sa.Column("active", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("sort", sa.Integer, nullable=False, server_default="0"),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_table(
        "feedback",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("contact", sa.String(200), nullable=False),
        sa.Column("text", sa.Text, nullable=False),
        sa.Column("done", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("emailed", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("feedback")
    op.drop_table("filament_colors")
    op.drop_index("ix_product_media_product_id", "product_media")
    op.drop_table("product_media")
    op.drop_column("order_items", "color")
    op.drop_column("products", "colors")
