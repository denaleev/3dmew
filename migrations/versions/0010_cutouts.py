"""cut-out product photos (background removed by the neural network) for the business card and booklet builder

Revision ID: 0010
Revises: 0009
Create Date: 2026-11-10
"""
from alembic import op
import sqlalchemy as sa

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "cutouts",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.String(32), sa.ForeignKey("users.id", ondelete="SET NULL"), index=True),
        sa.Column("source", sa.String(40)),
        sa.Column("name", sa.String(300), nullable=False, server_default=""),
        sa.Column("png", sa.LargeBinary, nullable=False),
        sa.Column("thumb", sa.LargeBinary),
        sa.Column("width", sa.Integer, nullable=False, server_default="0"),
        sa.Column("height", sa.Integer, nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("user_id", "source"),
    )
    # cards already saved in the library with a neural-network cut-out
    op.execute("""
        INSERT INTO cutouts (user_id, source, name, png)
        SELECT b.user_id, b.id, i.title, b.product FROM blobs b JOIN items i ON i.id = b.id
        WHERE i.kind = 'card' AND b.product_cut AND b.product IS NOT NULL
    """)


def downgrade() -> None:
    op.drop_table("cutouts")
