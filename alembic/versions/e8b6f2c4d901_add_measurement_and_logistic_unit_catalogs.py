"""add product reference catalogs

Revision ID: e8b6f2c4d901
Revises: c7f4a8219b12
Create Date: 2026-07-24 20:10:00
"""

from decimal import Decimal
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "e8b6f2c4d901"
down_revision: Union[str, Sequence[str], None] = "c7f4a8219b12"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "units_of_measure",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("code", sa.String(length=32), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("symbol", sa.String(length=24), nullable=False),
        sa.Column("dimension", sa.String(length=32), nullable=False),
        sa.Column("decimal_precision", sa.Integer(), nullable=False),
        sa.Column("factor_to_base", sa.Numeric(precision=20, scale=8), nullable=False),
        sa.Column("is_base", sa.Boolean(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.CheckConstraint(
            "decimal_precision >= 0 AND decimal_precision <= 6",
            name="ck_uom_decimal_precision",
        ),
        sa.CheckConstraint("factor_to_base > 0", name="ck_uom_factor_positive"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_units_of_measure_code"), "units_of_measure", ["code"], unique=True)
    op.create_index(op.f("ix_units_of_measure_dimension"), "units_of_measure", ["dimension"], unique=False)
    op.create_index(op.f("ix_units_of_measure_is_base"), "units_of_measure", ["is_base"], unique=False)

    op.create_table(
        "logistic_unit_types",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("code", sa.String(length=32), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("identifier_prefix", sa.String(length=16), nullable=False),
        sa.Column("tare_weight", sa.Numeric(precision=18, scale=6), nullable=True),
        sa.Column("tare_weight_uom_id", sa.Integer(), nullable=True),
        sa.Column("max_weight", sa.Numeric(precision=18, scale=6), nullable=True),
        sa.Column("max_weight_uom_id", sa.Integer(), nullable=True),
        sa.Column("length_mm", sa.Integer(), nullable=True),
        sa.Column("width_mm", sa.Integer(), nullable=True),
        sa.Column("height_mm", sa.Integer(), nullable=True),
        sa.Column("can_contain_goods", sa.Boolean(), nullable=False),
        sa.Column("can_contain_units", sa.Boolean(), nullable=False),
        sa.Column("is_returnable", sa.Boolean(), nullable=False),
        sa.Column("barcode_template", sa.String(length=240), nullable=False),
        sa.Column("label_profile", sa.String(length=80), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.CheckConstraint("tare_weight IS NULL OR tare_weight >= 0", name="ck_logistic_type_tare_weight"),
        sa.CheckConstraint("max_weight IS NULL OR max_weight > 0", name="ck_logistic_type_max_weight"),
        sa.CheckConstraint("length_mm IS NULL OR length_mm > 0", name="ck_logistic_type_length"),
        sa.CheckConstraint("width_mm IS NULL OR width_mm > 0", name="ck_logistic_type_width"),
        sa.CheckConstraint("height_mm IS NULL OR height_mm > 0", name="ck_logistic_type_height"),
        sa.ForeignKeyConstraint(["max_weight_uom_id"], ["units_of_measure.id"]),
        sa.ForeignKeyConstraint(["tare_weight_uom_id"], ["units_of_measure.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_logistic_unit_types_code"),
        "logistic_unit_types",
        ["code"],
        unique=True,
    )
    op.create_index(
        op.f("ix_logistic_unit_types_identifier_prefix"),
        "logistic_unit_types",
        ["identifier_prefix"],
        unique=True,
    )

    op.create_table(
        "logistic_unit_type_allowed_children",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("parent_type_id", sa.Integer(), nullable=False),
        sa.Column("child_type_id", sa.Integer(), nullable=False),
        sa.CheckConstraint("parent_type_id <> child_type_id", name="ck_logistic_type_no_self_child"),
        sa.ForeignKeyConstraint(["child_type_id"], ["logistic_unit_types.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["parent_type_id"], ["logistic_unit_types.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "parent_type_id",
            "child_type_id",
            name="uq_logistic_type_allowed_child",
        ),
    )
    op.create_index(
        op.f("ix_logistic_unit_type_allowed_children_child_type_id"),
        "logistic_unit_type_allowed_children",
        ["child_type_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_logistic_unit_type_allowed_children_parent_type_id"),
        "logistic_unit_type_allowed_children",
        ["parent_type_id"],
        unique=False,
    )

    with op.batch_alter_table("products") as batch_op:
        batch_op.add_column(sa.Column("base_uom_id", sa.Integer(), nullable=True))
        batch_op.create_foreign_key(
            "fk_products_base_uom_id_units_of_measure",
            "units_of_measure",
            ["base_uom_id"],
            ["id"],
        )
        batch_op.create_index(batch_op.f("ix_products_base_uom_id"), ["base_uom_id"], unique=False)

    op.create_table(
        "equipment_profiles",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("code", sa.String(length=48), nullable=False),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("device_kind", sa.String(length=32), nullable=False),
        sa.Column("manufacturer", sa.String(length=120), nullable=True),
        sa.Column("model", sa.String(length=120), nullable=True),
        sa.Column("connection_type", sa.String(length=32), nullable=False),
        sa.Column("host", sa.String(length=255), nullable=True),
        sa.Column("port", sa.Integer(), nullable=True),
        sa.Column("queue_name", sa.String(length=120), nullable=True),
        sa.Column("serial_device", sa.String(length=160), nullable=True),
        sa.Column("driver_code", sa.String(length=80), nullable=True),
        sa.Column("warehouse_id", sa.Integer(), nullable=True),
        sa.Column("parameters", sa.JSON(), nullable=False),
        sa.Column("is_default", sa.Boolean(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("port IS NULL OR (port >= 1 AND port <= 65535)", name="ck_equipment_port"),
        sa.ForeignKeyConstraint(["warehouse_id"], ["warehouses.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_equipment_profiles_code"), "equipment_profiles", ["code"], unique=True)
    op.create_index(
        op.f("ix_equipment_profiles_connection_type"),
        "equipment_profiles",
        ["connection_type"],
        unique=False,
    )
    op.create_index(
        op.f("ix_equipment_profiles_device_kind"),
        "equipment_profiles",
        ["device_kind"],
        unique=False,
    )
    op.create_index(
        op.f("ix_equipment_profiles_is_default"),
        "equipment_profiles",
        ["is_default"],
        unique=False,
    )
    op.create_index(
        op.f("ix_equipment_profiles_warehouse_id"),
        "equipment_profiles",
        ["warehouse_id"],
        unique=False,
    )

    bind = op.get_bind()
    units = sa.table(
        "units_of_measure",
        sa.column("id", sa.Integer()),
        sa.column("code", sa.String()),
        sa.column("name", sa.String()),
        sa.column("symbol", sa.String()),
        sa.column("dimension", sa.String()),
        sa.column("decimal_precision", sa.Integer()),
        sa.column("factor_to_base", sa.Numeric()),
        sa.column("is_base", sa.Boolean()),
        sa.column("is_active", sa.Boolean()),
    )
    unit_rows = [
        ("PCS", "Штука", "шт", "quantity", 0, Decimal("1"), True),
        ("KG", "Килограмм", "кг", "mass", 3, Decimal("1"), True),
        ("G", "Грамм", "г", "mass", 3, Decimal("0.001"), False),
        ("L", "Литр", "л", "volume", 3, Decimal("1"), True),
        ("ML", "Миллилитр", "мл", "volume", 3, Decimal("0.001"), False),
        ("M3", "Кубический метр", "м³", "volume", 6, Decimal("1000"), False),
        ("M", "Метр", "м", "length", 3, Decimal("1"), True),
        ("M2", "Квадратный метр", "м²", "area", 3, Decimal("1"), True),
    ]
    for code, name, symbol, dimension, precision, factor, is_base in unit_rows:
        bind.execute(
            units.insert().values(
                code=code,
                name=name,
                symbol=symbol,
                dimension=dimension,
                decimal_precision=precision,
                factor_to_base=factor,
                is_base=is_base,
                is_active=True,
            )
        )

    logistic_types = sa.table(
        "logistic_unit_types",
        sa.column("id", sa.Integer()),
        sa.column("code", sa.String()),
        sa.column("name", sa.String()),
        sa.column("identifier_prefix", sa.String()),
        sa.column("can_contain_goods", sa.Boolean()),
        sa.column("can_contain_units", sa.Boolean()),
        sa.column("is_returnable", sa.Boolean()),
        sa.column("barcode_template", sa.String()),
        sa.column("is_active", sa.Boolean()),
    )
    type_rows = [
        ("BOX", "Коробка", "BOX", True, False, False),
        ("PALLET", "Палета", "PLT", False, True, True),
        ("CRATE", "Ящик", "CRT", True, False, True),
        ("DRUM", "Бочка", "DRM", True, False, True),
        ("CANISTER", "Канистра", "CAN", True, False, True),
        ("IBC", "Еврокуб", "IBC", True, False, True),
        ("ROLL", "Рулон", "ROL", True, False, False),
        ("CONTAINER", "Контейнер", "CNT", True, True, True),
    ]
    for code, name, prefix, goods, units_allowed, returnable in type_rows:
        bind.execute(
            logistic_types.insert().values(
                code=code,
                name=name,
                identifier_prefix=prefix,
                can_contain_goods=goods,
                can_contain_units=units_allowed,
                is_returnable=returnable,
                barcode_template="{uid}",
                is_active=True,
            )
        )

    unit_ids = {
        code: bind.execute(sa.select(units.c.id).where(units.c.code == code)).scalar_one()
        for code, *_ in unit_rows
    }
    type_ids = {
        code: bind.execute(sa.select(logistic_types.c.id).where(logistic_types.c.code == code)).scalar_one()
        for code, *_ in type_rows
    }
    allowed_children = sa.table(
        "logistic_unit_type_allowed_children",
        sa.column("parent_type_id", sa.Integer()),
        sa.column("child_type_id", sa.Integer()),
    )
    allowed = {
        "PALLET": ("BOX", "CRATE", "DRUM", "CANISTER"),
        "CONTAINER": ("BOX", "PALLET", "CRATE", "DRUM", "CANISTER", "IBC", "ROLL"),
    }
    for parent_code, child_codes in allowed.items():
        for child_code in child_codes:
            bind.execute(
                allowed_children.insert().values(
                    parent_type_id=type_ids[parent_code],
                    child_type_id=type_ids[child_code],
                )
            )

    products = sa.table(
        "products",
        sa.column("unit", sa.String()),
        sa.column("base_uom_id", sa.Integer()),
    )
    aliases = {
        "PCS": ("шт", "pcs", "piece"),
        "KG": ("кг", "kg"),
        "G": ("г", "g"),
        "L": ("л", "l"),
        "ML": ("мл", "ml"),
        "M3": ("м³", "m3"),
        "M": ("м", "m"),
        "M2": ("м²", "m2"),
    }
    for code, values in aliases.items():
        bind.execute(
            products.update()
            .where(sa.func.lower(products.c.unit).in_(values))
            .values(base_uom_id=unit_ids[code])
        )


def downgrade() -> None:
    op.drop_index(op.f("ix_equipment_profiles_warehouse_id"), table_name="equipment_profiles")
    op.drop_index(op.f("ix_equipment_profiles_is_default"), table_name="equipment_profiles")
    op.drop_index(op.f("ix_equipment_profiles_device_kind"), table_name="equipment_profiles")
    op.drop_index(op.f("ix_equipment_profiles_connection_type"), table_name="equipment_profiles")
    op.drop_index(op.f("ix_equipment_profiles_code"), table_name="equipment_profiles")
    op.drop_table("equipment_profiles")

    with op.batch_alter_table("products") as batch_op:
        batch_op.drop_index(batch_op.f("ix_products_base_uom_id"))
        batch_op.drop_constraint("fk_products_base_uom_id_units_of_measure", type_="foreignkey")
        batch_op.drop_column("base_uom_id")

    op.drop_index(
        op.f("ix_logistic_unit_type_allowed_children_parent_type_id"),
        table_name="logistic_unit_type_allowed_children",
    )
    op.drop_index(
        op.f("ix_logistic_unit_type_allowed_children_child_type_id"),
        table_name="logistic_unit_type_allowed_children",
    )
    op.drop_table("logistic_unit_type_allowed_children")
    op.drop_index(op.f("ix_logistic_unit_types_identifier_prefix"), table_name="logistic_unit_types")
    op.drop_index(op.f("ix_logistic_unit_types_code"), table_name="logistic_unit_types")
    op.drop_table("logistic_unit_types")
    op.drop_index(op.f("ix_units_of_measure_is_base"), table_name="units_of_measure")
    op.drop_index(op.f("ix_units_of_measure_dimension"), table_name="units_of_measure")
    op.drop_index(op.f("ix_units_of_measure_code"), table_name="units_of_measure")
    op.drop_table("units_of_measure")
