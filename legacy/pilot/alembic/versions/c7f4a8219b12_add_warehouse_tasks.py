"""add warehouse tasks

Revision ID: c7f4a8219b12
Revises: a2efa5d8a2f4
Create Date: 2026-07-22 23:40:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c7f4a8219b12"
down_revision: Union[str, Sequence[str], None] = "a2efa5d8a2f4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "warehouse_tasks",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("task_uid", sa.String(length=40), nullable=False),
        sa.Column("warehouse_id", sa.Integer(), nullable=False),
        sa.Column(
            "task_type",
            sa.Enum("BUILD", "PLACE", "MOVE", "SHIP", "INVENTORY", "TRANSFER", name="tasktype"),
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.Enum("NEW", "IN_PROGRESS", "COMPLETED", "CANCELLED", name="taskstatus"),
            nullable=False,
        ),
        sa.Column(
            "priority",
            sa.Enum("LOW", "NORMAL", "HIGH", "URGENT", name="taskpriority"),
            nullable=False,
        ),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("description", sa.String(length=500), nullable=True),
        sa.Column("object_type", sa.String(length=40), nullable=True),
        sa.Column("object_uid", sa.String(length=120), nullable=True),
        sa.Column("assigned_to", sa.String(length=80), nullable=True),
        sa.Column("created_by", sa.String(length=80), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["warehouse_id"], ["warehouses.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_warehouse_tasks_assigned_to"), "warehouse_tasks", ["assigned_to"], unique=False)
    op.create_index(op.f("ix_warehouse_tasks_created_at"), "warehouse_tasks", ["created_at"], unique=False)
    op.create_index(op.f("ix_warehouse_tasks_object_type"), "warehouse_tasks", ["object_type"], unique=False)
    op.create_index(op.f("ix_warehouse_tasks_object_uid"), "warehouse_tasks", ["object_uid"], unique=False)
    op.create_index(op.f("ix_warehouse_tasks_priority"), "warehouse_tasks", ["priority"], unique=False)
    op.create_index(op.f("ix_warehouse_tasks_status"), "warehouse_tasks", ["status"], unique=False)
    op.create_index(op.f("ix_warehouse_tasks_task_type"), "warehouse_tasks", ["task_type"], unique=False)
    op.create_index(op.f("ix_warehouse_tasks_task_uid"), "warehouse_tasks", ["task_uid"], unique=True)
    op.create_index(op.f("ix_warehouse_tasks_warehouse_id"), "warehouse_tasks", ["warehouse_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_warehouse_tasks_warehouse_id"), table_name="warehouse_tasks")
    op.drop_index(op.f("ix_warehouse_tasks_task_uid"), table_name="warehouse_tasks")
    op.drop_index(op.f("ix_warehouse_tasks_task_type"), table_name="warehouse_tasks")
    op.drop_index(op.f("ix_warehouse_tasks_status"), table_name="warehouse_tasks")
    op.drop_index(op.f("ix_warehouse_tasks_priority"), table_name="warehouse_tasks")
    op.drop_index(op.f("ix_warehouse_tasks_object_uid"), table_name="warehouse_tasks")
    op.drop_index(op.f("ix_warehouse_tasks_object_type"), table_name="warehouse_tasks")
    op.drop_index(op.f("ix_warehouse_tasks_created_at"), table_name="warehouse_tasks")
    op.drop_index(op.f("ix_warehouse_tasks_assigned_to"), table_name="warehouse_tasks")
    op.drop_table("warehouse_tasks")
    if op.get_bind().dialect.name == "postgresql":
        sa.Enum(name="taskpriority").drop(op.get_bind(), checkfirst=True)
        sa.Enum(name="taskstatus").drop(op.get_bind(), checkfirst=True)
        sa.Enum(name="tasktype").drop(op.get_bind(), checkfirst=True)
