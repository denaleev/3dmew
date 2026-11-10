"""«Мяу-аркада»: game progress on the server and the leaderboard

Revision ID: 0012
Revises: 0011
Create Date: 2026-11-11
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "game_players",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.String(32), sa.ForeignKey("users.id", ondelete="CASCADE"), unique=True),
        sa.Column("token_hash", sa.String(64), unique=True),
        sa.Column("nick", sa.String(20), nullable=False, server_default=""),
        sa.Column("data", JSONB, nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_table(
        "game_scores",
        sa.Column("player_id", sa.Integer, sa.ForeignKey("game_players.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("game", sa.String(20), primary_key=True),
        sa.Column("mode", sa.String(20), primary_key=True),
        sa.Column("score", sa.Integer, nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_game_scores_board", "game_scores", ["game", "mode", "score"])


def downgrade() -> None:
    op.drop_table("game_scores")
    op.drop_table("game_players")
