"""catalogue preview without price, carts, favourites, reviews

Revision ID: 0006
Revises: 0005
Create Date: 2026-11-09
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("products", sa.Column("tile", sa.LargeBinary, nullable=True))
    op.create_table(
        "carts",
        sa.Column("token", sa.String(40), primary_key=True),
        sa.Column("user_id", sa.String(32), sa.ForeignKey("users.id", ondelete="SET NULL"), index=True),
        sa.Column("items", JSONB, nullable=False, server_default="[]"),
        sa.Column("total", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_table(
        "favorites",
        sa.Column("user_id", sa.String(32), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("product_id", sa.Integer, sa.ForeignKey("products.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_table(
        "reviews",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("product_id", sa.Integer, sa.ForeignKey("products.id", ondelete="CASCADE"), index=True, nullable=False),
        sa.Column("user_id", sa.String(32), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("name", sa.String(80), nullable=False),
        sa.Column("rating", sa.Integer, nullable=False),
        sa.Column("text", sa.Text, nullable=False, server_default=""),
        sa.Column("status", sa.String(12), nullable=False, server_default="pending", index=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_table(
        "review_photos",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("review_id", sa.Integer, sa.ForeignKey("reviews.id", ondelete="CASCADE"), index=True, nullable=False),
        sa.Column("data", sa.LargeBinary, nullable=False),
        sa.Column("thumb", sa.LargeBinary, nullable=False),
    )


def downgrade() -> None:
    for t in ("review_photos", "reviews", "favorites", "carts"):
        op.drop_table(t)
    op.drop_column("products", "tile")
