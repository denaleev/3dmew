"""media library: a category for uploaded files («Фото пластика», «Логотипы»…)

Revision ID: 0013
Revises: 0012
Create Date: 2026-11-11
"""
from alembic import op
import sqlalchemy as sa

revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("library_files", sa.Column("category", sa.String(60), nullable=False, server_default=""))
    op.create_index("ix_library_files_category", "library_files", ["category"])


def downgrade() -> None:
    op.drop_index("ix_library_files_category", "library_files")
    op.drop_column("library_files", "category")
