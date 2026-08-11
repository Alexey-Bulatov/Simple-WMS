"""add authentication, warehouse access and personal passes

Revision ID: b60718293a4b
Revises: a60718293a4b
Create Date: 2026-08-11 22:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "b60718293a4b"
down_revision: Union[str, Sequence[str], None] = "a60718293a4b"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        op.execute("ALTER TYPE userrole ADD VALUE IF NOT EXISTS 'AUDITOR'")
        op.execute("ALTER TYPE userrole ADD VALUE IF NOT EXISTS 'INTEGRATION'")

    with op.batch_alter_table("users") as batch_op:
        batch_op.add_column(sa.Column("password_hash", sa.String(length=255), nullable=True))
        batch_op.add_column(sa.Column("password_changed_at", sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(
            sa.Column("failed_login_count", sa.Integer(), server_default="0", nullable=False)
        )
        batch_op.add_column(sa.Column("locked_until", sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(
            sa.Column("must_change_password", sa.Boolean(), server_default=sa.false(), nullable=False)
        )
    with op.batch_alter_table("users") as batch_op:
        batch_op.alter_column("failed_login_count", server_default=None)
        batch_op.alter_column("must_change_password", server_default=None)

    op.create_table(
        "user_warehouse_accesses",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("warehouse_id", sa.Integer(), nullable=False),
        sa.Column("is_default", sa.Boolean(), nullable=False),
        sa.Column("assigned_by_user_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["assigned_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["warehouse_id"], ["warehouses.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "warehouse_id", name="uq_user_warehouse_access"),
    )
    op.create_index(
        op.f("ix_user_warehouse_accesses_user_id"),
        "user_warehouse_accesses",
        ["user_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_user_warehouse_accesses_warehouse_id"),
        "user_warehouse_accesses",
        ["warehouse_id"],
        unique=False,
    )

    op.create_table(
        "warehouse_workstations",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("code", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("warehouse_id", sa.Integer(), nullable=False),
        sa.Column("pass_login_enabled", sa.Boolean(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["warehouse_id"], ["warehouses.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_warehouse_workstations_code"),
        "warehouse_workstations",
        ["code"],
        unique=True,
    )
    op.create_index(
        op.f("ix_warehouse_workstations_warehouse_id"),
        "warehouse_workstations",
        ["warehouse_id"],
        unique=False,
    )

    op.create_table(
        "authentication_sessions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("uid", sa.String(length=64), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("authentication_method", sa.String(length=24), nullable=False),
        sa.Column("workstation_id", sa.Integer(), nullable=True),
        sa.Column("client_ip", sa.String(length=64), nullable=True),
        sa.Column("user_agent", sa.String(length=300), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoke_reason", sa.String(length=240), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["workstation_id"],
            ["warehouse_workstations.id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    for column in (
        "uid",
        "user_id",
        "token_hash",
        "authentication_method",
        "workstation_id",
        "expires_at",
    ):
        op.create_index(
            op.f(f"ix_authentication_sessions_{column}"),
            "authentication_sessions",
            [column],
            unique=column in {"uid", "token_hash"},
        )

    op.create_table(
        "user_access_passes",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("uid", sa.String(length=64), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("workstation_id", sa.Integer(), nullable=False),
        sa.Column("issued_by_user_id", sa.Integer(), nullable=True),
        sa.Column("issued_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoke_reason", sa.String(length=240), nullable=True),
        sa.ForeignKeyConstraint(["issued_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["workstation_id"],
            ["warehouse_workstations.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    for column in (
        "uid",
        "user_id",
        "token_hash",
        "workstation_id",
        "issued_by_user_id",
    ):
        op.create_index(
            op.f(f"ix_user_access_passes_{column}"),
            "user_access_passes",
            [column],
            unique=column in {"uid", "token_hash"},
        )

    op.create_table(
        "authentication_events",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("event_type", sa.String(length=32), nullable=False),
        sa.Column("authentication_method", sa.String(length=24), nullable=True),
        sa.Column("username", sa.String(length=80), nullable=True),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("session_uid", sa.String(length=64), nullable=True),
        sa.Column("workstation_code", sa.String(length=64), nullable=True),
        sa.Column("client_ip", sa.String(length=64), nullable=True),
        sa.Column("user_agent", sa.String(length=300), nullable=True),
        sa.Column("succeeded", sa.Boolean(), nullable=False),
        sa.Column("reason", sa.String(length=240), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    for column in (
        "event_type",
        "authentication_method",
        "username",
        "user_id",
        "session_uid",
        "succeeded",
        "created_at",
    ):
        op.create_index(
            op.f(f"ix_authentication_events_{column}"),
            "authentication_events",
            [column],
            unique=False,
        )


def downgrade() -> None:
    op.drop_table("authentication_events")
    op.drop_table("user_access_passes")
    op.drop_table("authentication_sessions")
    op.drop_table("warehouse_workstations")
    op.drop_table("user_warehouse_accesses")
    with op.batch_alter_table("users") as batch_op:
        batch_op.drop_column("must_change_password")
        batch_op.drop_column("last_login_at")
        batch_op.drop_column("locked_until")
        batch_op.drop_column("failed_login_count")
        batch_op.drop_column("password_changed_at")
        batch_op.drop_column("password_hash")
