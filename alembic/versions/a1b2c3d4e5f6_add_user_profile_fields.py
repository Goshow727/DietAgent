"""add user profile fields

Revision ID: a1b2c3d4e5f6
Revises: f31688d4fa51
Create Date: 2026-04-20 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, None] = 'f31688d4fa51'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_DEFAULT_AVATAR = "https://test-zsp-oss.oss-cn-guangzhou.aliyuncs.com/avatars/default.png"
_GOSHOW_HASH = "$2b$12$BDTYraBJ3sERF180hnHxGeWB9uDEQHYs3m/KuPXdDZnqiq3xxw1Wm"


def upgrade() -> None:
    op.add_column('users', sa.Column('nickname', sa.String(length=64), nullable=True))
    op.add_column('users', sa.Column('avatar_url', sa.String(length=512), nullable=True))
    op.add_column('users', sa.Column('height', sa.Float(), nullable=True))
    op.add_column('users', sa.Column('weight', sa.Float(), nullable=True))
    op.add_column('users', sa.Column('age', sa.Integer(), nullable=True))
    op.add_column('users', sa.Column('gender', sa.String(length=16), nullable=True))

    op.execute(
        sa.text(
            "INSERT INTO users (username, hashed_password, is_active, nickname, avatar_url, height, weight, age, gender) "
            "VALUES (:username, :pwd, TRUE, :nickname, :avatar_url, :height, :weight, :age, :gender) "
            "ON CONFLICT (username) DO NOTHING"
        ).bindparams(
            username="goshow",
            pwd=_GOSHOW_HASH,
            nickname="goshow",
            avatar_url=_DEFAULT_AVATAR,
            height=175.0,
            weight=70.0,
            age=25,
            gender="male",
        )
    )


def downgrade() -> None:
    op.drop_column('users', 'gender')
    op.drop_column('users', 'age')
    op.drop_column('users', 'weight')
    op.drop_column('users', 'height')
    op.drop_column('users', 'avatar_url')
    op.drop_column('users', 'nickname')
