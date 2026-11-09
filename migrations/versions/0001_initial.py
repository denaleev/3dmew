"""initial: users, sign-ins, sessions, cards and drafts, photos, images, settings

Revision ID: 0001
Revises:
Create Date: 2026-11-03
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("login", sa.String(160), nullable=True),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("password_hash", sa.String(255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_users_login", "users", ["login"], unique=True)
    op.create_table(
        "oauth_accounts",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.String(32), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("provider", sa.String(20), nullable=False),
        sa.Column("subject_hash", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("provider", "subject_hash"),
    )
    op.create_index("ix_oauth_accounts_user_id", "oauth_accounts", ["user_id"])
    op.create_table(
        "sessions",
        sa.Column("token_hash", sa.String(64), primary_key=True),
        sa.Column("user_id", sa.String(32), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_sessions_user_id", "sessions", ["user_id"])
    op.create_index("ix_sessions_expires_at", "sessions", ["expires_at"])
    op.create_table(
        "items",
        sa.Column("id", sa.String(40), primary_key=True),
        sa.Column("user_id", sa.String(32), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("kind", sa.String(10), nullable=False),
        sa.Column("title", sa.String(300), nullable=False, server_default=""),
        sa.Column("thumb", sa.Text, nullable=True),
        sa.Column("state", postgresql.JSONB, nullable=True),
        sa.Column("t", sa.BigInteger, nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_items_user_id", "items", ["user_id"])
    op.create_table(
        "photos",
        sa.Column("id", sa.String(40), primary_key=True),
        sa.Column("user_id", sa.String(32), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(300), nullable=False, server_default="фото"),
        sa.Column("size", sa.BigInteger, nullable=False, server_default="0"),
        sa.Column("thumb", sa.Text, nullable=True),
        sa.Column("t", sa.BigInteger, nullable=False),
    )
    op.create_index("ix_photos_user_id", "photos", ["user_id"])
    op.create_table(
        "blobs",
        sa.Column("id", sa.String(40), primary_key=True),
        sa.Column("user_id", sa.String(32), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("png", sa.LargeBinary, nullable=True),
        sa.Column("photo", sa.LargeBinary, nullable=True),
        sa.Column("photo_type", sa.String(80), nullable=True),
        sa.Column("product", sa.LargeBinary, nullable=True),
        sa.Column("product_cut", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("manual", sa.LargeBinary, nullable=True),
    )
    op.create_index("ix_blobs_user_id", "blobs", ["user_id"])
    op.create_table(
        "prefs",
        sa.Column("user_id", sa.String(32), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("data", postgresql.JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
    )


def downgrade() -> None:
    for t in ("prefs", "blobs", "photos", "items", "sessions", "oauth_accounts", "users"):
        op.drop_table(t)
