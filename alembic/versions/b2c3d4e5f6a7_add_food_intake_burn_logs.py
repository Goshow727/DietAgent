"""add food intake burn logs

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-04-20 12:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'b2c3d4e5f6a7'
down_revision: Union[str, None] = 'a1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_SEED_FOODS = [
    ("鸡胸肉", 165.0, 31.0, 0.0, 3.6),
    ("糙米", 112.0, 2.6, 23.5, 0.9),
    ("三文鱼", 208.0, 20.0, 0.0, 13.0),
    ("鸡蛋", 155.0, 13.0, 1.1, 11.0),
    ("西兰花", 34.0, 2.8, 7.0, 0.4),
    ("牛肉", 250.0, 26.0, 0.0, 17.0),
    ("豆腐", 76.0, 8.0, 1.9, 4.8),
    ("燕麦", 389.0, 17.0, 66.0, 7.0),
    ("香蕉", 89.0, 1.1, 23.0, 0.3),
    ("蓝莓", 57.0, 0.7, 14.0, 0.3),
    ("杏仁", 579.0, 21.0, 22.0, 50.0),
    ("花生酱", 588.0, 25.0, 20.0, 50.0),
    ("希腊酸奶", 59.0, 10.0, 3.6, 0.4),
    ("番薯", 86.0, 1.6, 20.0, 0.1),
    ("菠菜", 23.0, 2.9, 3.6, 0.4),
    ("鳄梨", 160.0, 2.0, 9.0, 15.0),
    ("藜麦", 120.0, 4.4, 21.0, 1.9),
    ("橙子", 47.0, 0.9, 12.0, 0.1),
    ("胡萝卜", 41.0, 0.9, 10.0, 0.2),
    ("全脂牛奶", 61.0, 3.2, 4.8, 3.3),
]


def upgrade() -> None:
    op.create_table(
        "foods",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("kcal_per_100g", sa.Float(), nullable=False),
        sa.Column("protein_per_100g", sa.Float(), nullable=False),
        sa.Column("carb_per_100g", sa.Float(), nullable=False),
        sa.Column("fat_per_100g", sa.Float(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_foods_name"), "foods", ["name"], unique=False)

    op.create_table(
        "intake_logs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("food_id", sa.Integer(), nullable=False),
        sa.Column("food_name", sa.String(length=128), nullable=False),
        sa.Column("weight_grams", sa.Float(), nullable=False),
        sa.Column("protein_g", sa.Float(), nullable=False),
        sa.Column("carb_g", sa.Float(), nullable=False),
        sa.Column("fat_g", sa.Float(), nullable=False),
        sa.Column("kcal", sa.Float(), nullable=False),
        sa.Column("logged_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["food_id"], ["foods.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_intake_logs_user_id"), "intake_logs", ["user_id"], unique=False)

    op.create_table(
        "burn_logs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("exercise_type", sa.String(length=32), nullable=False),
        sa.Column("intensity", sa.Integer(), nullable=False),
        sa.Column("duration_minutes", sa.Integer(), nullable=False),
        sa.Column("kcal", sa.Float(), nullable=False),
        sa.Column("logged_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_burn_logs_user_id"), "burn_logs", ["user_id"], unique=False)

    foods_table = sa.table(
        "foods",
        sa.column("name", sa.String),
        sa.column("kcal_per_100g", sa.Float),
        sa.column("protein_per_100g", sa.Float),
        sa.column("carb_per_100g", sa.Float),
        sa.column("fat_per_100g", sa.Float),
    )
    op.bulk_insert(
        foods_table,
        [
            {
                "name": name,
                "kcal_per_100g": kcal,
                "protein_per_100g": protein,
                "carb_per_100g": carb,
                "fat_per_100g": fat,
            }
            for name, kcal, protein, carb, fat in _SEED_FOODS
        ],
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_burn_logs_user_id"), table_name="burn_logs")
    op.drop_table("burn_logs")
    op.drop_index(op.f("ix_intake_logs_user_id"), table_name="intake_logs")
    op.drop_table("intake_logs")
    op.drop_index(op.f("ix_foods_name"), table_name="foods")
    op.drop_table("foods")
