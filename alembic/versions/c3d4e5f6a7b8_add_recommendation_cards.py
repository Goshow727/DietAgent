"""add recommendation cards

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-04-22 10:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'c3d4e5f6a7b8'
down_revision: Union[str, None] = 'b2c3d4e5f6a7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "recommendation_cards",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("desc", sa.Text(), nullable=False),
        sa.Column("image_url", sa.String(512), nullable=True),
        sa.Column("image_prompt", sa.Text(), nullable=True),
        sa.Column("category", sa.String(32), nullable=False, server_default="diet"),
        sa.Column("status", sa.String(16), nullable=False, server_default="queued"),
        sa.Column("red_cut_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_recommendation_cards_user_id", "recommendation_cards", ["user_id"]
    )
    op.create_index(
        "ix_recommendation_cards_user_status",
        "recommendation_cards",
        ["user_id", "status"],
    )


def downgrade() -> None:
    op.drop_index("ix_recommendation_cards_user_status", table_name="recommendation_cards")
    op.drop_index("ix_recommendation_cards_user_id", table_name="recommendation_cards")
    op.drop_table("recommendation_cards")
