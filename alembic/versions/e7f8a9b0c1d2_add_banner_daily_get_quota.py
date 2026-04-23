"""add banner_daily_get_quota and red_cut cleanup index

Revision ID: e7f8a9b0c1d2
Revises: a8f0c1d2e3b4
Create Date: 2026-04-23 18:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "e7f8a9b0c1d2"
down_revision: Union[str, None] = "a8f0c1d2e3b4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "banner_daily_get_quota",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("quota_date", sa.Date(), nullable=False),
        sa.Column("request_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "quota_date", name="uq_banner_daily_get_user_date"),
    )
    op.create_index(
        "ix_banner_daily_get_quota_user_id", "banner_daily_get_quota", ["user_id"]
    )
    op.create_index(
        "ix_recommendation_cards_red_cut_cleanup",
        "recommendation_cards",
        ["status", "red_cut_at"],
        postgresql_where=sa.text("status = 'red_cut' AND red_cut_at IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index(
        "ix_recommendation_cards_red_cut_cleanup",
        table_name="recommendation_cards",
    )
    op.drop_index("ix_banner_daily_get_quota_user_id", table_name="banner_daily_get_quota")
    op.drop_table("banner_daily_get_quota")
