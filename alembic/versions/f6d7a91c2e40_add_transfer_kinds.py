"""add transfer kinds

Revision ID: f6d7a91c2e40
Revises: e71bc4d20a9f
Create Date: 2026-07-28 12:00:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "f6d7a91c2e40"
down_revision: Union[str, Sequence[str], None] = "e71bc4d20a9f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


transfer_kind = sa.Enum(
    "LOCAL",
    "TRANSPORT",
    name="transferkind",
    native_enum=False,
    length=32,
)


def upgrade() -> None:
    op.add_column(
        "warehouse_transfers",
        sa.Column(
            "transfer_kind",
            transfer_kind,
            nullable=False,
            server_default="TRANSPORT",
        ),
    )
    op.create_index(
        op.f("ix_warehouse_transfers_transfer_kind"),
        "warehouse_transfers",
        ["transfer_kind"],
    )
    op.add_column(
        "logistic_transfers",
        sa.Column(
            "transfer_kind",
            transfer_kind,
            nullable=False,
            server_default="TRANSPORT",
        ),
    )
    op.create_index(
        op.f("ix_logistic_transfers_transfer_kind"),
        "logistic_transfers",
        ["transfer_kind"],
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_logistic_transfers_transfer_kind"),
        table_name="logistic_transfers",
    )
    op.drop_column("logistic_transfers", "transfer_kind")
    op.drop_index(
        op.f("ix_warehouse_transfers_transfer_kind"),
        table_name="warehouse_transfers",
    )
    op.drop_column("warehouse_transfers", "transfer_kind")
