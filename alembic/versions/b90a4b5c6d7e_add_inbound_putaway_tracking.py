"""add inbound putaway tracking

Revision ID: b90a4b5c6d7e
Revises: a8093a4b5c6d
"""

from alembic import op
import sqlalchemy as sa


revision = "b90a4b5c6d7e"
down_revision = "a8093a4b5c6d"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("inbound_receipt_results") as batch_op:
        batch_op.add_column(
            sa.Column("placement_stock_document_id", sa.Integer(), nullable=True)
        )
        batch_op.add_column(
            sa.Column("placed_at", sa.DateTime(timezone=True), nullable=True)
        )
        batch_op.create_foreign_key(
            "fk_inbound_receipt_results_placement_stock_document_id_stock_documents",
            "stock_documents",
            ["placement_stock_document_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch_op.create_index(
            op.f("ix_inbound_receipt_results_placement_stock_document_id"),
            ["placement_stock_document_id"],
            unique=True,
        )


def downgrade() -> None:
    with op.batch_alter_table("inbound_receipt_results") as batch_op:
        batch_op.drop_index(
            op.f("ix_inbound_receipt_results_placement_stock_document_id")
        )
        batch_op.drop_constraint(
            "fk_inbound_receipt_results_placement_stock_document_id_stock_documents",
            type_="foreignkey",
        )
        batch_op.drop_column("placed_at")
        batch_op.drop_column("placement_stock_document_id")
