"""media library: photos and videos uploaded straight into admin → «Библиотека»

Revision ID: 0011
Revises: 0010
Create Date: 2026-11-11
"""
from alembic import op
import sqlalchemy as sa

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "library_files",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.String(32), sa.ForeignKey("users.id", ondelete="SET NULL"), index=True),
        sa.Column("kind", sa.String(10), nullable=False),
        sa.Column("mime", sa.String(100), nullable=False),
        sa.Column("name", sa.String(300), nullable=False, server_default=""),
        sa.Column("size", sa.BigInteger, nullable=False, server_default="0"),
        sa.Column("data", sa.LargeBinary, nullable=False),
        sa.Column("thumb", sa.LargeBinary),
        sa.Column("width", sa.Integer, nullable=False, server_default="0"),
        sa.Column("height", sa.Integer, nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), index=True),
    )


def downgrade() -> None:
    op.drop_table("library_files")
