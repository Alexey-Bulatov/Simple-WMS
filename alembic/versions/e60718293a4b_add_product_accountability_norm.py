"""add product accountability norm

Revision ID: e60718293a4b
Revises: d60718293a4b
Create Date: 2026-08-13
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "e60718293a4b"
down_revision: str | None = "d60718293a4b"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("products") as batch_op:
        batch_op.add_column(
            sa.Column("accountability_period_days", sa.Integer(), nullable=True),
        )
        batch_op.create_check_constraint(
            "ck_product_accountability_period_days",
            "accountability_period_days IS NULL OR accountability_period_days > 0",
        )


def downgrade() -> None:
    with op.batch_alter_table("products") as batch_op:
        batch_op.drop_constraint(
            "ck_product_accountability_period_days",
            type_="check",
        )
        batch_op.drop_column("accountability_period_days")
