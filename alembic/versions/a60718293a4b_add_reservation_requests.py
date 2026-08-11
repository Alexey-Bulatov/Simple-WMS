"""add reservation requests and allocation results

Revision ID: a60718293a4b
Revises: f60718293a4b
Create Date: 2026-08-11 20:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "a60718293a4b"
down_revision: Union[str, Sequence[str], None] = "f60718293a4b"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "stock_reservation_requests",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("uid", sa.String(length=64), nullable=False),
        sa.Column("kind", sa.String(length=24), nullable=False),
        sa.Column("result", sa.String(length=24), nullable=False),
        sa.Column("requested_stock_position_id", sa.Integer(), nullable=True),
        sa.Column("requested_logistic_unit_id", sa.Integer(), nullable=True),
        sa.Column("requested_logistic_unit_uid", sa.String(length=64), nullable=True),
        sa.Column("requested_quantity", sa.Numeric(precision=20, scale=6), nullable=True),
        sa.Column("reserved_quantity", sa.Numeric(precision=20, scale=6), nullable=True),
        sa.Column("base_uom_id", sa.Integer(), nullable=True),
        sa.Column("input_quantity", sa.Numeric(precision=20, scale=8), nullable=True),
        sa.Column("input_uom_id", sa.Integer(), nullable=True),
        sa.Column("conversion_factor", sa.Numeric(precision=20, scale=8), nullable=True),
        sa.Column("allow_partial", sa.Boolean(), nullable=False),
        sa.Column("expected_position_count", sa.Integer(), nullable=False),
        sa.Column("allocation_count", sa.Integer(), nullable=False),
        sa.Column("reference_type", sa.String(length=40), nullable=False),
        sa.Column("reference_uid", sa.String(length=80), nullable=False),
        sa.Column("reference_line_uid", sa.String(length=80), nullable=True),
        sa.Column("task_id", sa.Integer(), nullable=True),
        sa.Column("idempotency_key", sa.String(length=120), nullable=False),
        sa.Column("command_hash", sa.String(length=64), nullable=False),
        sa.Column("actor", sa.String(length=80), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "((requested_stock_position_id IS NOT NULL AND requested_logistic_unit_id IS NULL) OR "
            "(requested_stock_position_id IS NULL AND requested_logistic_unit_id IS NOT NULL))",
            name="ck_stock_reservation_request_single_target",
        ),
        sa.CheckConstraint(
            "requested_quantity IS NULL OR requested_quantity > 0",
            name="ck_stock_reservation_request_quantity",
        ),
        sa.CheckConstraint(
            "reserved_quantity IS NULL OR reserved_quantity >= 0",
            name="ck_stock_reservation_request_reserved_quantity",
        ),
        sa.CheckConstraint(
            "input_quantity IS NULL OR input_quantity > 0",
            name="ck_stock_reservation_request_input_quantity",
        ),
        sa.CheckConstraint(
            "conversion_factor IS NULL OR conversion_factor > 0",
            name="ck_stock_reservation_request_conversion_factor",
        ),
        sa.CheckConstraint(
            "expected_position_count >= 0 AND allocation_count >= 0",
            name="ck_stock_reservation_request_counts",
        ),
        sa.ForeignKeyConstraint(["base_uom_id"], ["units_of_measure.id"]),
        sa.ForeignKeyConstraint(["input_uom_id"], ["units_of_measure.id"]),
        sa.ForeignKeyConstraint(["task_id"], ["logistic_tasks.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    for column in (
        "uid",
        "kind",
        "result",
        "requested_stock_position_id",
        "requested_logistic_unit_id",
        "requested_logistic_unit_uid",
        "reference_type",
        "reference_uid",
        "reference_line_uid",
        "task_id",
        "idempotency_key",
        "actor",
    ):
        op.create_index(
            op.f(f"ix_stock_reservation_requests_{column}"),
            "stock_reservation_requests",
            [column],
            unique=column in {"uid", "idempotency_key"},
        )

    with op.batch_alter_table("stock_reservations") as batch_op:
        batch_op.add_column(sa.Column("request_id", sa.Integer(), nullable=True))
        batch_op.create_foreign_key(
            "fk_stock_reservations_request_id_stock_reservation_requests",
            "stock_reservation_requests",
            ["request_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch_op.create_index(
            op.f("ix_stock_reservations_request_id"),
            ["request_id"],
            unique=False,
        )


def downgrade() -> None:
    with op.batch_alter_table("stock_reservations") as batch_op:
        batch_op.drop_index(op.f("ix_stock_reservations_request_id"))
        batch_op.drop_constraint(
            "fk_stock_reservations_request_id_stock_reservation_requests",
            type_="foreignkey",
        )
        batch_op.drop_column("request_id")
    op.drop_table("stock_reservation_requests")
