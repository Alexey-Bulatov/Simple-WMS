"""add reservation consumption and task linkage

Revision ID: f60718293a4b
Revises: e5f60718293a
Create Date: 2026-08-11 18:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "f60718293a4b"
down_revision: Union[str, Sequence[str], None] = "e5f60718293a"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("stock_reservations") as batch_op:
        batch_op.add_column(sa.Column("task_id", sa.Integer(), nullable=True))
        batch_op.add_column(
            sa.Column("consume_idempotency_key", sa.String(length=120), nullable=True)
        )
        batch_op.add_column(
            sa.Column("consume_command_hash", sa.String(length=64), nullable=True)
        )
        batch_op.add_column(
            sa.Column("consume_actor", sa.String(length=80), nullable=True)
        )
        batch_op.add_column(sa.Column("consume_reason", sa.Text(), nullable=True))
        batch_op.create_foreign_key(
            "fk_stock_reservations_task_id_logistic_tasks",
            "logistic_tasks",
            ["task_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch_op.create_index(
            op.f("ix_stock_reservations_task_id"),
            ["task_id"],
            unique=False,
        )
        batch_op.create_index(
            op.f("ix_stock_reservations_consume_idempotency_key"),
            ["consume_idempotency_key"],
            unique=True,
        )


def downgrade() -> None:
    with op.batch_alter_table("stock_reservations") as batch_op:
        batch_op.drop_index(op.f("ix_stock_reservations_consume_idempotency_key"))
        batch_op.drop_index(op.f("ix_stock_reservations_task_id"))
        batch_op.drop_constraint(
            "fk_stock_reservations_task_id_logistic_tasks",
            type_="foreignkey",
        )
        batch_op.drop_column("consume_reason")
        batch_op.drop_column("consume_actor")
        batch_op.drop_column("consume_command_hash")
        batch_op.drop_column("consume_idempotency_key")
        batch_op.drop_column("task_id")
