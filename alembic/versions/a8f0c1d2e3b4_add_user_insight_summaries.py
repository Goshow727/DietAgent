"""add user insight summaries (home plan copy)

Revision ID: a8f0c1d2e3b4
Revises: d4e5f6a7b8c9
Create Date: 2026-04-23 14:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "a8f0c1d2e3b4"
down_revision: Union[str, None] = "d4e5f6a7b8c9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "user_insight_summaries",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("insight_type", sa.String(length=16), nullable=False),
        sa.Column("period_start", sa.Date(), nullable=False),
        sa.Column("period_end", sa.Date(), nullable=False),
        sa.Column("body", sa.Text(), nullable=False, server_default=""),
        sa.Column("tags", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="[]"),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="ok"),
        sa.Column("intake_distinct_days", sa.Integer(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "user_id", "insight_type", "period_start", name="uq_user_insight_user_type_period"
        ),
    )
    op.create_index(
        "ix_user_insight_summaries_user_id",
        "user_insight_summaries",
        ["user_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_user_insight_summaries_user_id", table_name="user_insight_summaries")
    op.drop_table("user_insight_summaries")
