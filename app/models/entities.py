from datetime import date, datetime, timezone
from typing import Any

from decimal import Decimal

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    JSON,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.constants import DEFAULT_UNIT
from app.db.session import Base
from app.models.enums import (
    BoxStatus,
    InventoryLineStatus,
    InventoryStatus,
    LocationKind,
    LogisticUnitStatus,
    PalletStatus,
    ShipmentStatus,
    TransferStatus,
    TaskPriority,
    TaskStatus,
    TaskType,
    UserRole,
)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    full_name: Mapped[str] = mapped_column(String(160))
    role: Mapped[UserRole] = mapped_column(Enum(UserRole), default=UserRole.ADMIN)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class UnitOfMeasure(Base):
    __tablename__ = "units_of_measure"
    __table_args__ = (
        CheckConstraint("decimal_precision >= 0 AND decimal_precision <= 6", name="ck_uom_decimal_precision"),
        CheckConstraint("factor_to_base > 0", name="ck_uom_factor_positive"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(120))
    symbol: Mapped[str] = mapped_column(String(24))
    dimension: Mapped[str] = mapped_column(String(32), index=True)
    decimal_precision: Mapped[int] = mapped_column(Integer, default=0)
    factor_to_base: Mapped[Decimal] = mapped_column(Numeric(20, 8), default=Decimal("1"))
    is_base: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class LogisticUnitTypeAllowedChild(Base):
    __tablename__ = "logistic_unit_type_allowed_children"
    __table_args__ = (
        UniqueConstraint("parent_type_id", "child_type_id", name="uq_logistic_type_allowed_child"),
        CheckConstraint("parent_type_id <> child_type_id", name="ck_logistic_type_no_self_child"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    parent_type_id: Mapped[int] = mapped_column(ForeignKey("logistic_unit_types.id", ondelete="CASCADE"), index=True)
    child_type_id: Mapped[int] = mapped_column(ForeignKey("logistic_unit_types.id", ondelete="CASCADE"), index=True)


class LogisticUnitType(Base):
    __tablename__ = "logistic_unit_types"
    __table_args__ = (
        CheckConstraint("tare_weight IS NULL OR tare_weight >= 0", name="ck_logistic_type_tare_weight"),
        CheckConstraint("max_weight IS NULL OR max_weight > 0", name="ck_logistic_type_max_weight"),
        CheckConstraint("length_mm IS NULL OR length_mm > 0", name="ck_logistic_type_length"),
        CheckConstraint("width_mm IS NULL OR width_mm > 0", name="ck_logistic_type_width"),
        CheckConstraint("height_mm IS NULL OR height_mm > 0", name="ck_logistic_type_height"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(120))
    identifier_prefix: Mapped[str] = mapped_column(String(16), unique=True, index=True)
    tare_weight: Mapped[Decimal | None] = mapped_column(Numeric(18, 6), nullable=True)
    tare_weight_uom_id: Mapped[int | None] = mapped_column(ForeignKey("units_of_measure.id"), nullable=True)
    max_weight: Mapped[Decimal | None] = mapped_column(Numeric(18, 6), nullable=True)
    max_weight_uom_id: Mapped[int | None] = mapped_column(ForeignKey("units_of_measure.id"), nullable=True)
    length_mm: Mapped[int | None] = mapped_column(Integer, nullable=True)
    width_mm: Mapped[int | None] = mapped_column(Integer, nullable=True)
    height_mm: Mapped[int | None] = mapped_column(Integer, nullable=True)
    can_contain_goods: Mapped[bool] = mapped_column(Boolean, default=True)
    can_contain_units: Mapped[bool] = mapped_column(Boolean, default=False)
    is_returnable: Mapped[bool] = mapped_column(Boolean, default=False)
    barcode_template: Mapped[str] = mapped_column(String(240), default="{uid}")
    label_profile: Mapped[str | None] = mapped_column(String(80), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    tare_weight_uom: Mapped[UnitOfMeasure | None] = relationship(foreign_keys=[tare_weight_uom_id])
    max_weight_uom: Mapped[UnitOfMeasure | None] = relationship(foreign_keys=[max_weight_uom_id])
    allowed_children: Mapped[list[LogisticUnitTypeAllowedChild]] = relationship(
        foreign_keys=[LogisticUnitTypeAllowedChild.parent_type_id],
        cascade="all, delete-orphan",
    )

    @property
    def allowed_child_type_ids(self) -> list[int]:
        return sorted(row.child_type_id for row in self.allowed_children)


class LogisticUnit(Base):
    __tablename__ = "logistic_units"
    __table_args__ = (
        CheckConstraint("parent_unit_id IS NULL OR parent_unit_id <> id", name="ck_logistic_unit_no_self_parent"),
        CheckConstraint(
            "measured_gross_weight IS NULL OR measured_gross_weight > 0",
            name="ck_logistic_unit_gross_weight",
        ),
        CheckConstraint("length_mm IS NULL OR length_mm > 0", name="ck_logistic_unit_length"),
        CheckConstraint("width_mm IS NULL OR width_mm > 0", name="ck_logistic_unit_width"),
        CheckConstraint("height_mm IS NULL OR height_mm > 0", name="ck_logistic_unit_height"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    uid: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    type_id: Mapped[int] = mapped_column(ForeignKey("logistic_unit_types.id"), index=True)
    status: Mapped[LogisticUnitStatus] = mapped_column(
        Enum(LogisticUnitStatus),
        default=LogisticUnitStatus.OPEN,
        index=True,
    )
    parent_unit_id: Mapped[int | None] = mapped_column(
        ForeignKey("logistic_units.id"),
        nullable=True,
        index=True,
    )
    current_location_id: Mapped[int | None] = mapped_column(
        ForeignKey("locations.id"),
        nullable=True,
        index=True,
    )
    measured_gross_weight: Mapped[Decimal | None] = mapped_column(Numeric(18, 6), nullable=True)
    weight_uom_id: Mapped[int | None] = mapped_column(
        ForeignKey("units_of_measure.id"),
        nullable=True,
    )
    length_mm: Mapped[int | None] = mapped_column(Integer, nullable=True)
    width_mm: Mapped[int | None] = mapped_column(Integer, nullable=True)
    height_mm: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status_before_hold: Mapped[str | None] = mapped_column(String(32), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    type: Mapped[LogisticUnitType] = relationship()
    parent_unit: Mapped["LogisticUnit | None"] = relationship(
        remote_side="LogisticUnit.id",
        back_populates="child_units",
        foreign_keys=[parent_unit_id],
    )
    child_units: Mapped[list["LogisticUnit"]] = relationship(
        back_populates="parent_unit",
        foreign_keys=[parent_unit_id],
    )
    contents: Mapped[list["LogisticUnitContent"]] = relationship(
        back_populates="logistic_unit",
        cascade="all, delete-orphan",
    )
    weight_uom: Mapped[UnitOfMeasure | None] = relationship(foreign_keys=[weight_uom_id])


class LogisticUnitContent(Base):
    __tablename__ = "logistic_unit_contents"
    __table_args__ = (
        CheckConstraint("quantity > 0", name="ck_logistic_unit_content_quantity"),
        UniqueConstraint(
            "logistic_unit_id",
            "product_id",
            "batch_id",
            "uom_id",
            name="uq_logistic_unit_content_line",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    logistic_unit_id: Mapped[int] = mapped_column(
        ForeignKey("logistic_units.id", ondelete="CASCADE"),
        index=True,
    )
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), index=True)
    batch_id: Mapped[int | None] = mapped_column(ForeignKey("batches.id"), nullable=True, index=True)
    quantity: Mapped[Decimal] = mapped_column(Numeric(20, 6))
    uom_id: Mapped[int] = mapped_column(ForeignKey("units_of_measure.id"))
    added_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    logistic_unit: Mapped[LogisticUnit] = relationship(back_populates="contents")
    product: Mapped["Product"] = relationship(foreign_keys=[product_id])
    batch: Mapped["Batch | None"] = relationship(foreign_keys=[batch_id])
    uom: Mapped[UnitOfMeasure] = relationship(foreign_keys=[uom_id])


class Product(Base):
    __tablename__ = "products"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(240))
    unit: Mapped[str] = mapped_column(String(32), default=DEFAULT_UNIT)
    base_uom_id: Mapped[int | None] = mapped_column(ForeignKey("units_of_measure.id"), nullable=True, index=True)
    quantity_per_box: Mapped[int] = mapped_column(Integer, default=1)
    boxes_per_pallet: Mapped[int] = mapped_column(Integer, default=1)
    shelf_life_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    batches: Mapped[list["Batch"]] = relationship(back_populates="product")
    base_uom: Mapped[UnitOfMeasure | None] = relationship()


class Batch(Base):
    __tablename__ = "batches"
    __table_args__ = (UniqueConstraint("product_id", "batch_number", name="uq_batch_product_number"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    batch_number: Mapped[str] = mapped_column(String(80), index=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"))
    production_date: Mapped[date] = mapped_column(Date)
    expiry_date: Mapped[date] = mapped_column(Date)
    quality_status: Mapped[str] = mapped_column(String(40), default="released")
    operation_status: Mapped[str] = mapped_column(String(40), default="allowed")

    product: Mapped[Product] = relationship(back_populates="batches")


class Warehouse(Base):
    __tablename__ = "warehouses"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(160))
    city: Mapped[str | None] = mapped_column(String(120), nullable=True)
    timezone: Mapped[str] = mapped_column(String(80), default="Europe/Moscow")

    zones: Mapped[list["Zone"]] = relationship(back_populates="warehouse")


class EquipmentProfile(Base):
    __tablename__ = "equipment_profiles"
    __table_args__ = (
        CheckConstraint("port IS NULL OR (port >= 1 AND port <= 65535)", name="ck_equipment_port"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(48), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(160))
    device_kind: Mapped[str] = mapped_column(String(32), index=True)
    manufacturer: Mapped[str | None] = mapped_column(String(120), nullable=True)
    model: Mapped[str | None] = mapped_column(String(120), nullable=True)
    connection_type: Mapped[str] = mapped_column(String(32), index=True)
    host: Mapped[str | None] = mapped_column(String(255), nullable=True)
    port: Mapped[int | None] = mapped_column(Integer, nullable=True)
    queue_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    serial_device: Mapped[str | None] = mapped_column(String(160), nullable=True)
    driver_code: Mapped[str | None] = mapped_column(String(80), nullable=True)
    warehouse_id: Mapped[int | None] = mapped_column(ForeignKey("warehouses.id"), nullable=True, index=True)
    parameters: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    warehouse: Mapped[Warehouse | None] = relationship()


class Zone(Base):
    __tablename__ = "zones"
    __table_args__ = (UniqueConstraint("warehouse_id", "code", name="uq_zone_warehouse_code"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    warehouse_id: Mapped[int] = mapped_column(ForeignKey("warehouses.id"))
    code: Mapped[str] = mapped_column(String(48), index=True)
    name: Mapped[str] = mapped_column(String(160))
    kind: Mapped[LocationKind] = mapped_column(Enum(LocationKind), default=LocationKind.STORAGE)

    warehouse: Mapped[Warehouse] = relationship(back_populates="zones")
    locations: Mapped[list["Location"]] = relationship(back_populates="zone")


class Location(Base):
    __tablename__ = "locations"

    id: Mapped[int] = mapped_column(primary_key=True)
    warehouse_id: Mapped[int] = mapped_column(ForeignKey("warehouses.id"))
    zone_id: Mapped[int] = mapped_column(ForeignKey("zones.id"))
    code: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    name: Mapped[str | None] = mapped_column(String(160), nullable=True)
    kind: Mapped[LocationKind] = mapped_column(Enum(LocationKind), default=LocationKind.STORAGE)
    capacity_pallets: Mapped[int] = mapped_column(Integer, default=1)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    zone: Mapped[Zone] = relationship(back_populates="locations")


class LogisticShipment(Base):
    __tablename__ = "logistic_shipments"

    id: Mapped[int] = mapped_column(primary_key=True)
    shipment_uid: Mapped[str] = mapped_column(String(40), unique=True, index=True)
    warehouse_id: Mapped[int] = mapped_column(ForeignKey("warehouses.id"), index=True)
    customer_name: Mapped[str] = mapped_column(String(160))
    destination: Mapped[str] = mapped_column(String(160))
    status: Mapped[ShipmentStatus] = mapped_column(
        Enum(ShipmentStatus, native_enum=False, length=32),
        default=ShipmentStatus.DRAFT,
        index=True,
    )
    planned_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    units: Mapped[list["LogisticShipmentUnit"]] = relationship(
        back_populates="shipment",
        cascade="all, delete-orphan",
    )


class LogisticShipmentUnit(Base):
    __tablename__ = "logistic_shipment_units"
    __table_args__ = (
        UniqueConstraint(
            "shipment_id",
            "logistic_unit_id",
            name="uq_logistic_shipment_unit",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    shipment_id: Mapped[int] = mapped_column(ForeignKey("logistic_shipments.id"), index=True)
    logistic_unit_id: Mapped[int] = mapped_column(ForeignKey("logistic_units.id"), index=True)
    source_location_id: Mapped[int] = mapped_column(ForeignKey("locations.id"))
    status: Mapped[str] = mapped_column(String(32), default="reserved", index=True)
    reserved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    moved_to_expedition_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    loaded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    shipment: Mapped[LogisticShipment] = relationship(back_populates="units")


class LogisticTransfer(Base):
    __tablename__ = "logistic_transfers"

    id: Mapped[int] = mapped_column(primary_key=True)
    transfer_uid: Mapped[str] = mapped_column(String(40), unique=True, index=True)
    source_warehouse_id: Mapped[int] = mapped_column(ForeignKey("warehouses.id"), index=True)
    destination_warehouse_id: Mapped[int] = mapped_column(ForeignKey("warehouses.id"), index=True)
    status: Mapped[TransferStatus] = mapped_column(
        Enum(TransferStatus, native_enum=False, length=32),
        default=TransferStatus.DRAFT,
        index=True,
    )
    planned_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    vehicle_number: Mapped[str | None] = mapped_column(String(80), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    dispatched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    units: Mapped[list["LogisticTransferUnit"]] = relationship(
        back_populates="transfer",
        cascade="all, delete-orphan",
    )


class LogisticTransferUnit(Base):
    __tablename__ = "logistic_transfer_units"
    __table_args__ = (
        UniqueConstraint(
            "transfer_id",
            "logistic_unit_id",
            name="uq_logistic_transfer_unit",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    transfer_id: Mapped[int] = mapped_column(ForeignKey("logistic_transfers.id"), index=True)
    logistic_unit_id: Mapped[int] = mapped_column(ForeignKey("logistic_units.id"), index=True)
    source_location_id: Mapped[int] = mapped_column(ForeignKey("locations.id"))
    status: Mapped[str] = mapped_column(String(32), default="reserved", index=True)
    reserved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    moved_to_expedition_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    loaded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    received_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    transfer: Mapped[LogisticTransfer] = relationship(back_populates="units")


class WarehouseMapItem(Base):
    __tablename__ = "warehouse_map_items"
    __table_args__ = (
        UniqueConstraint("warehouse_id", "item_key", name="uq_warehouse_map_item_key"),
        UniqueConstraint("location_id", name="uq_warehouse_map_location"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    warehouse_id: Mapped[int] = mapped_column(ForeignKey("warehouses.id"), index=True)
    zone_id: Mapped[int | None] = mapped_column(ForeignKey("zones.id"), nullable=True)
    location_id: Mapped[int | None] = mapped_column(ForeignKey("locations.id"), nullable=True)
    parent_id: Mapped[int | None] = mapped_column(ForeignKey("warehouse_map_items.id"), nullable=True, index=True)
    item_type: Mapped[str] = mapped_column(String(32), index=True)
    item_key: Mapped[str] = mapped_column(String(120))
    label: Mapped[str] = mapped_column(String(160))
    x: Mapped[int] = mapped_column(Integer, default=0)
    y: Mapped[int] = mapped_column(Integer, default=0)
    width: Mapped[int] = mapped_column(Integer, default=100)
    height: Mapped[int] = mapped_column(Integer, default=60)
    rotation: Mapped[int] = mapped_column(Integer, default=0)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    is_locked: Mapped[bool] = mapped_column(Boolean, default=False)


class Pallet(Base):
    __tablename__ = "pallets"

    id: Mapped[int] = mapped_column(primary_key=True)
    pallet_uid: Mapped[str] = mapped_column(String(40), unique=True, index=True)
    product_id: Mapped[int | None] = mapped_column(ForeignKey("products.id"), nullable=True)
    batch_id: Mapped[int | None] = mapped_column(ForeignKey("batches.id"), nullable=True)
    status: Mapped[PalletStatus] = mapped_column(Enum(PalletStatus), default=PalletStatus.OPEN, index=True)
    current_location_id: Mapped[int | None] = mapped_column(ForeignKey("locations.id"), nullable=True)
    is_mixed: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    boxes: Mapped[list["PalletBox"]] = relationship(back_populates="pallet")


class Box(Base):
    __tablename__ = "boxes"

    id: Mapped[int] = mapped_column(primary_key=True)
    box_uid: Mapped[str] = mapped_column(String(40), unique=True, index=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"))
    batch_id: Mapped[int] = mapped_column(ForeignKey("batches.id"))
    status: Mapped[BoxStatus] = mapped_column(Enum(BoxStatus), default=BoxStatus.LABEL_CREATED, index=True)
    current_pallet_id: Mapped[int | None] = mapped_column(ForeignKey("pallets.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class PalletBox(Base):
    __tablename__ = "pallet_boxes"
    __table_args__ = (UniqueConstraint("box_id", name="uq_pallet_box_current_box"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    pallet_id: Mapped[int] = mapped_column(ForeignKey("pallets.id"))
    box_id: Mapped[int] = mapped_column(ForeignKey("boxes.id"))
    added_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    pallet: Mapped[Pallet] = relationship(back_populates="boxes")


class Shipment(Base):
    __tablename__ = "shipments"

    id: Mapped[int] = mapped_column(primary_key=True)
    shipment_uid: Mapped[str] = mapped_column(String(40), unique=True, index=True)
    customer_name: Mapped[str] = mapped_column(String(160))
    destination: Mapped[str] = mapped_column(String(160))
    status: Mapped[ShipmentStatus] = mapped_column(Enum(ShipmentStatus), default=ShipmentStatus.DRAFT, index=True)
    planned_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    pallets: Mapped[list["ShipmentPallet"]] = relationship(back_populates="shipment")


class ShipmentPallet(Base):
    __tablename__ = "shipment_pallets"
    __table_args__ = (
        UniqueConstraint("shipment_id", "pallet_id", name="uq_shipment_pallet"),
        UniqueConstraint("pallet_id", name="uq_active_shipment_pallet"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    shipment_id: Mapped[int] = mapped_column(ForeignKey("shipments.id"))
    pallet_id: Mapped[int] = mapped_column(ForeignKey("pallets.id"))
    status: Mapped[str] = mapped_column(String(40), default="reserved", index=True)
    reserved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    moved_to_expedition_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    loaded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    shipment: Mapped[Shipment] = relationship(back_populates="pallets")


class WarehouseTransfer(Base):
    __tablename__ = "warehouse_transfers"

    id: Mapped[int] = mapped_column(primary_key=True)
    transfer_uid: Mapped[str] = mapped_column(String(40), unique=True, index=True)
    source_warehouse_id: Mapped[int] = mapped_column(ForeignKey("warehouses.id"), index=True)
    destination_warehouse_id: Mapped[int] = mapped_column(ForeignKey("warehouses.id"), index=True)
    status: Mapped[TransferStatus] = mapped_column(Enum(TransferStatus), default=TransferStatus.DRAFT, index=True)
    planned_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    vehicle_number: Mapped[str | None] = mapped_column(String(80), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    dispatched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    pallets: Mapped[list["WarehouseTransferPallet"]] = relationship(back_populates="transfer")


class WarehouseTransferPallet(Base):
    __tablename__ = "warehouse_transfer_pallets"
    __table_args__ = (UniqueConstraint("transfer_id", "pallet_id", name="uq_transfer_pallet"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    transfer_id: Mapped[int] = mapped_column(ForeignKey("warehouse_transfers.id"), index=True)
    pallet_id: Mapped[int] = mapped_column(ForeignKey("pallets.id"), index=True)
    source_location_id: Mapped[int | None] = mapped_column(ForeignKey("locations.id"), nullable=True)
    status: Mapped[str] = mapped_column(String(40), default="reserved", index=True)
    reserved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    moved_to_expedition_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    loaded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    received_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    transfer: Mapped[WarehouseTransfer] = relationship(back_populates="pallets")


class InventorySession(Base):
    __tablename__ = "inventory_sessions"

    id: Mapped[int] = mapped_column(primary_key=True)
    inventory_uid: Mapped[str] = mapped_column(String(40), unique=True, index=True)
    warehouse_id: Mapped[int | None] = mapped_column(ForeignKey("warehouses.id"), nullable=True)
    location_id: Mapped[int | None] = mapped_column(ForeignKey("locations.id"), nullable=True)
    current_location_id: Mapped[int | None] = mapped_column(ForeignKey("locations.id"), nullable=True)
    status: Mapped[InventoryStatus] = mapped_column(Enum(InventoryStatus), default=InventoryStatus.OPEN, index=True)
    actor: Mapped[str] = mapped_column(String(80), default="system")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    lines: Mapped[list["InventoryLine"]] = relationship(back_populates="inventory")


class InventoryLine(Base):
    __tablename__ = "inventory_lines"
    __table_args__ = (UniqueConstraint("inventory_id", "pallet_id", name="uq_inventory_pallet"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    inventory_id: Mapped[int] = mapped_column(ForeignKey("inventory_sessions.id"))
    pallet_id: Mapped[int] = mapped_column(ForeignKey("pallets.id"))
    expected_location_id: Mapped[int | None] = mapped_column(ForeignKey("locations.id"), nullable=True)
    actual_location_id: Mapped[int | None] = mapped_column(ForeignKey("locations.id"), nullable=True)
    status: Mapped[InventoryLineStatus] = mapped_column(Enum(InventoryLineStatus), default=InventoryLineStatus.EXPECTED, index=True)
    scanned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    inventory: Mapped[InventorySession] = relationship(back_populates="lines")


class WarehouseTask(Base):
    __tablename__ = "warehouse_tasks"

    id: Mapped[int] = mapped_column(primary_key=True)
    task_uid: Mapped[str] = mapped_column(String(40), unique=True, index=True)
    warehouse_id: Mapped[int] = mapped_column(ForeignKey("warehouses.id"), index=True)
    task_type: Mapped[TaskType] = mapped_column(Enum(TaskType), index=True)
    status: Mapped[TaskStatus] = mapped_column(Enum(TaskStatus), default=TaskStatus.NEW, index=True)
    priority: Mapped[TaskPriority] = mapped_column(Enum(TaskPriority), default=TaskPriority.NORMAL, index=True)
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(String(500), nullable=True)
    object_type: Mapped[str | None] = mapped_column(String(40), nullable=True, index=True)
    object_uid: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    assigned_to: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)
    created_by: Mapped[str] = mapped_column(String(80), default="system")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class OperationEvent(Base):
    __tablename__ = "operation_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    operation: Mapped[str] = mapped_column(String(80), index=True)
    object_type: Mapped[str] = mapped_column(String(80), index=True)
    object_uid: Mapped[str] = mapped_column(String(120), index=True)
    actor: Mapped[str] = mapped_column(String(80), default="system")
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    before: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    after: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
