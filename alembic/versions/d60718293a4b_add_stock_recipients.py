"""add stock recipients

Revision ID: d60718293a4b
Revises: c60718293a4b
"""

from alembic import op
import sqlalchemy as sa


revision = "d60718293a4b"
down_revision = "c60718293a4b"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "stock_recipients",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("code", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("kind", sa.String(length=24), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_stock_recipients_code"),
        "stock_recipients",
        ["code"],
        unique=True,
    )
    op.create_index(
        op.f("ix_stock_recipients_name"),
        "stock_recipients",
        ["name"],
        unique=False,
    )
    op.create_index(
        op.f("ix_stock_recipients_kind"),
        "stock_recipients",
        ["kind"],
        unique=False,
    )
    op.create_index(
        op.f("ix_stock_recipients_is_active"),
        "stock_recipients",
        ["is_active"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_stock_recipients_is_active"), table_name="stock_recipients")
    op.drop_index(op.f("ix_stock_recipients_kind"), table_name="stock_recipients")
    op.drop_index(op.f("ix_stock_recipients_name"), table_name="stock_recipients")
    op.drop_index(op.f("ix_stock_recipients_code"), table_name="stock_recipients")
    op.drop_table("stock_recipients")
