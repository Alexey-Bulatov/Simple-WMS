"""add logistic unit operations

Revision ID: b72ce41f8a10
Revises: f3a91d7c5e42
Create Date: 2026-07-27 21:00:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "b72ce41f8a10"
down_revision: Union[str, Sequence[str], None] = "f3a91d7c5e42"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("logistic_units") as batch_op:
        batch_op.add_column(sa.Column("status_before_hold", sa.String(length=32), nullable=True))
        batch_op.add_column(sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("logistic_units") as batch_op:
        batch_op.drop_column("accepted_at")
        batch_op.drop_column("status_before_hold")
