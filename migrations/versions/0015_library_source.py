"""media library: files the card builder keeps up to date (a card and a card without the price plate)

Revision ID: 0015
Revises: 0014
Create Date: 2026-11-19
"""
from alembic import op
import sqlalchemy as sa

revision = "0015"
down_revision = "0014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("library_files", sa.Column("source", sa.String(80), nullable=True))
    op.create_index("ix_library_files_source", "library_files", ["source"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_library_files_source", "library_files")
    op.drop_column("library_files", "source")
