"""add logistic tasks

Revision ID: e71bc4d20a9f
Revises: d95a7b3e41c2
Create Date: 2026-07-27 23:45:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "e71bc4d20a9f"
down_revision: Union[str, Sequence[str], None] = "d95a7b3e41c2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "logistic_tasks",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("task_uid", sa.String(length=40), nullable=False),
        sa.Column("warehouse_id", sa.Integer(), nullable=False),
        sa.Column(
            "task_type",
            sa.Enum(
                "BUILD",
                "PLACE",
                "MOVE",
                "SHIP",
                "INVENTORY",
                "TRANSFER",
                name="logistictasktype",
                native_enum=False,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.Enum(
                "NEW",
                "IN_PROGRESS",
                "COMPLETED",
                "CANCELLED",
                name="logistictaskstatus",
                native_enum=False,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column(
            "priority",
            sa.Enum(
                "LOW",
                "NORMAL",
                "HIGH",
                "URGENT",
                name="logistictaskpriority",
                native_enum=False,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("description", sa.String(length=500), nullable=True),
        sa.Column("object_type", sa.String(length=40), nullable=False),
        sa.Column("object_uid", sa.String(length=120), nullable=False),
        sa.Column("parameters", sa.JSON(), nullable=False),
        sa.Column("assigned_to", sa.String(length=80), nullable=True),
        sa.Column("created_by", sa.String(length=80), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["warehouse_id"], ["warehouses.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_logistic_tasks_assigned_to"),
        "logistic_tasks",
        ["assigned_to"],
    )
    op.create_index(
        op.f("ix_logistic_tasks_created_at"),
        "logistic_tasks",
        ["created_at"],
    )
    op.create_index(
        op.f("ix_logistic_tasks_object_type"),
        "logistic_tasks",
        ["object_type"],
    )
    op.create_index(
        op.f("ix_logistic_tasks_object_uid"),
        "logistic_tasks",
        ["object_uid"],
    )
    op.create_index(
        op.f("ix_logistic_tasks_priority"),
        "logistic_tasks",
        ["priority"],
    )
    op.create_index(
        op.f("ix_logistic_tasks_status"),
        "logistic_tasks",
        ["status"],
    )
    op.create_index(
        op.f("ix_logistic_tasks_task_type"),
        "logistic_tasks",
        ["task_type"],
    )
    op.create_index(
        op.f("ix_logistic_tasks_task_uid"),
        "logistic_tasks",
        ["task_uid"],
        unique=True,
    )
    op.create_index(
        op.f("ix_logistic_tasks_warehouse_id"),
        "logistic_tasks",
        ["warehouse_id"],
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_logistic_tasks_warehouse_id"),
        table_name="logistic_tasks",
    )
    op.drop_index(
        op.f("ix_logistic_tasks_task_uid"),
        table_name="logistic_tasks",
    )
    op.drop_index(
        op.f("ix_logistic_tasks_task_type"),
        table_name="logistic_tasks",
    )
    op.drop_index(
        op.f("ix_logistic_tasks_status"),
        table_name="logistic_tasks",
    )
    op.drop_index(
        op.f("ix_logistic_tasks_priority"),
        table_name="logistic_tasks",
    )
    op.drop_index(
        op.f("ix_logistic_tasks_object_uid"),
        table_name="logistic_tasks",
    )
    op.drop_index(
        op.f("ix_logistic_tasks_object_type"),
        table_name="logistic_tasks",
    )
    op.drop_index(
        op.f("ix_logistic_tasks_created_at"),
        table_name="logistic_tasks",
    )
    op.drop_index(
        op.f("ix_logistic_tasks_assigned_to"),
        table_name="logistic_tasks",
    )
    op.drop_table("logistic_tasks")
