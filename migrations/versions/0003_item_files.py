"""item_files: 3MF/STL/G-code files the card author keeps with a card for printing

Revision ID: 0003
Revises: 0002
Create Date: 2026-11-06
"""
from alembic import op
import sqlalchemy as sa

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "item_files",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("item_id", sa.String(40), sa.ForeignKey("items.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", sa.String(32), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(300), nullable=False),
        sa.Column("size", sa.BigInteger, nullable=False),
        sa.Column("note", sa.String(300), nullable=False, server_default=""),
        sa.Column("data", sa.LargeBinary, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_item_files_item_id", "item_files", ["item_id"])
    op.create_index("ix_item_files_user_id", "item_files", ["user_id"])


def downgrade() -> None:
    op.drop_table("item_files")
