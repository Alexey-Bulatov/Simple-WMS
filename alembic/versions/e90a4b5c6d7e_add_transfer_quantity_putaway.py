"""add transfer quantity putaway

Revision ID: e90a4b5c6d7e
Revises: d90a4b5c6d7e
"""

from alembic import op
import sqlalchemy as sa


revision = "e90a4b5c6d7e"
down_revision = "d90a4b5c6d7e"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("logistic_transfer_allocations") as batch_op:
        batch_op.add_column(
            sa.Column("storage_location_id", sa.Integer(), nullable=True)
        )
        batch_op.add_column(
            sa.Column("placement_stock_document_id", sa.Integer(), nullable=True)
        )
        batch_op.add_column(
            sa.Column("placed_at", sa.DateTime(timezone=True), nullable=True)
        )
        batch_op.create_foreign_key(
            "fk_transfer_allocation_storage_location",
            "locations",
            ["storage_location_id"],
            ["id"],
        )
        batch_op.create_foreign_key(
            "fk_transfer_allocation_placement_document",
            "stock_documents",
            ["placement_stock_document_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch_op.create_index(
            "ix_logistic_transfer_allocations_storage_location_id",
            ["storage_location_id"],
        )
        batch_op.create_index(
            "ix_logistic_transfer_allocations_placement_stock_document_id",
            ["placement_stock_document_id"],
            unique=True,
        )


def downgrade() -> None:
    with op.batch_alter_table("logistic_transfer_allocations") as batch_op:
        batch_op.drop_index(
            "ix_logistic_transfer_allocations_placement_stock_document_id"
        )
        batch_op.drop_index(
            "ix_logistic_transfer_allocations_storage_location_id"
        )
        batch_op.drop_constraint(
            "fk_transfer_allocation_placement_document", type_="foreignkey"
        )
        batch_op.drop_constraint(
            "fk_transfer_allocation_storage_location", type_="foreignkey"
        )
        batch_op.drop_column("placed_at")
        batch_op.drop_column("placement_stock_document_id")
        batch_op.drop_column("storage_location_id")
