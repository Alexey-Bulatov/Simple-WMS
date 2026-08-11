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
    Index,
    Integer,
    JSON,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.constants import DEFAULT_UNIT
from app.db.session import Base
from app.models.enums import (
    AuthenticationEventType,
    AuthenticationMethod,
    InventoryLineStatus,
    InventoryLocationStatus,
    InventoryStatus,
    LocationKind,
    LogisticUnitStatus,
    ShipmentStatus,
    StockDocumentStatus,
    StockReservationKind,
    StockReservationResult,
    StockReservationStatus,
    TransferKind,
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
    password_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)
    password_changed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    failed_login_count: Mapped[int] = mapped_column(Integer, default=0)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    must_change_password: Mapped[bool] = mapped_column(Boolean, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    warehouse_accesses: Mapped[list["UserWarehouseAccess"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
        foreign_keys="UserWarehouseAccess.user_id",
    )
    sessions: Mapped[list["AuthenticationSession"]] = relationship(
        back_populates="user",
        foreign_keys="AuthenticationSession.user_id",
    )
    access_passes: Mapped[list["UserAccessPass"]] = relationship(
        back_populates="user",
        foreign_keys="UserAccessPass.user_id",
    )


class UserWarehouseAccess(Base):
    __tablename__ = "user_warehouse_accesses"
    __table_args__ = (
        UniqueConstraint("user_id", "warehouse_id", name="uq_user_warehouse_access"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    warehouse_id: Mapped[int] = mapped_column(
        ForeignKey("warehouses.id", ondelete="CASCADE"), index=True
    )
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)
    assigned_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    user: Mapped[User] = relationship(
        back_populates="warehouse_accesses",
        foreign_keys=[user_id],
    )
    warehouse: Mapped["Warehouse"] = relationship(foreign_keys=[warehouse_id])
    assigned_by: Mapped[User | None] = relationship(foreign_keys=[assigned_by_user_id])


class WarehouseWorkstation(Base):
    __tablename__ = "warehouse_workstations"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(160))
    warehouse_id: Mapped[int] = mapped_column(
        ForeignKey("warehouses.id", ondelete="CASCADE"), index=True
    )
    pass_login_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    warehouse: Mapped["Warehouse"] = relationship()


class AuthenticationSession(Base):
    __tablename__ = "authentication_sessions"

    id: Mapped[int] = mapped_column(primary_key=True)
    uid: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    authentication_method: Mapped[AuthenticationMethod] = mapped_column(
        Enum(AuthenticationMethod, native_enum=False, length=24), index=True
    )
    workstation_id: Mapped[int | None] = mapped_column(
        ForeignKey("warehouse_workstations.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    client_ip: Mapped[str | None] = mapped_column(String(64), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(300), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoke_reason: Mapped[str | None] = mapped_column(String(240), nullable=True)

    user: Mapped[User] = relationship(back_populates="sessions")
    workstation: Mapped[WarehouseWorkstation | None] = relationship()


class UserAccessPass(Base):
    __tablename__ = "user_access_passes"

    id: Mapped[int] = mapped_column(primary_key=True)
    uid: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    workstation_id: Mapped[int] = mapped_column(
        ForeignKey("warehouse_workstations.id", ondelete="CASCADE"), index=True
    )
    issued_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    issued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoke_reason: Mapped[str | None] = mapped_column(String(240), nullable=True)

    user: Mapped[User] = relationship(
        back_populates="access_passes",
        foreign_keys=[user_id],
    )
    workstation: Mapped[WarehouseWorkstation] = relationship()
    issued_by: Mapped[User | None] = relationship(foreign_keys=[issued_by_user_id])


class AuthenticationEvent(Base):
    __tablename__ = "authentication_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    event_type: Mapped[AuthenticationEventType] = mapped_column(
        Enum(AuthenticationEventType, native_enum=False, length=32), index=True
    )
    authentication_method: Mapped[AuthenticationMethod | None] = mapped_column(
        Enum(AuthenticationMethod, native_enum=False, length=24),
        nullable=True,
        index=True,
    )
    username: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)
    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    session_uid: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    workstation_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    client_ip: Mapped[str | None] = mapped_column(String(64), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(300), nullable=True)
    succeeded: Mapped[bool] = mapped_column(Boolean, index=True)
    reason: Mapped[str | None] = mapped_column(String(240), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)

    user: Mapped[User | None] = relationship()


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
    shelf_life_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    batches: Mapped[list["Batch"]] = relationship(back_populates="product")
    base_uom: Mapped[UnitOfMeasure | None] = relationship()
    packagings: Mapped[list["ProductPackaging"]] = relationship(
        back_populates="product",
        cascade="all, delete-orphan",
    )


class ProductPackaging(Base):
    __tablename__ = "product_packagings"
    __table_args__ = (
        UniqueConstraint("product_id", "code", name="uq_product_packaging_code"),
        CheckConstraint("quantity > 0", name="ck_product_packaging_quantity"),
        CheckConstraint("base_quantity > 0", name="ck_product_packaging_base_quantity"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), index=True)
    code: Mapped[str] = mapped_column(String(64), index=True)
    name: Mapped[str] = mapped_column(String(160))
    quantity: Mapped[Decimal] = mapped_column(Numeric(20, 8))
    uom_id: Mapped[int] = mapped_column(ForeignKey("units_of_measure.id"), index=True)
    base_quantity: Mapped[Decimal] = mapped_column(Numeric(20, 8))
    barcode: Mapped[str | None] = mapped_column(
        String(120),
        nullable=True,
        unique=True,
        index=True,
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    product: Mapped[Product] = relationship(back_populates="packagings")
    uom: Mapped[UnitOfMeasure] = relationship()


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


class StockOwner(Base):
    __tablename__ = "stock_owners"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(200))
    is_internal: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class StockPosition(Base):
    __tablename__ = "stock_positions"
    __table_args__ = (
        CheckConstraint("quantity > 0", name="ck_stock_position_quantity"),
        CheckConstraint(
            "serial_number IS NULL OR quantity = 1",
            name="ck_stock_position_serial_quantity",
        ),
        CheckConstraint(
            "((logistic_unit_id IS NOT NULL AND location_id IS NULL) OR "
            "(logistic_unit_id IS NULL AND location_id IS NOT NULL))",
            name="ck_stock_position_single_holder",
        ),
        Index(
            "uq_stock_position_unit_batch",
            "logistic_unit_id",
            "product_id",
            "batch_id",
            "owner_id",
            "quality_status",
            unique=True,
            sqlite_where=text(
                "logistic_unit_id IS NOT NULL AND batch_id IS NOT NULL AND serial_number IS NULL"
            ),
            postgresql_where=text(
                "logistic_unit_id IS NOT NULL AND batch_id IS NOT NULL AND serial_number IS NULL"
            ),
        ),
        Index(
            "uq_stock_position_unit_no_batch",
            "logistic_unit_id",
            "product_id",
            "owner_id",
            "quality_status",
            unique=True,
            sqlite_where=text(
                "logistic_unit_id IS NOT NULL AND batch_id IS NULL AND serial_number IS NULL"
            ),
            postgresql_where=text(
                "logistic_unit_id IS NOT NULL AND batch_id IS NULL AND serial_number IS NULL"
            ),
        ),
        Index(
            "uq_stock_position_location_batch",
            "location_id",
            "product_id",
            "batch_id",
            "owner_id",
            "quality_status",
            unique=True,
            sqlite_where=text(
                "location_id IS NOT NULL AND batch_id IS NOT NULL AND serial_number IS NULL"
            ),
            postgresql_where=text(
                "location_id IS NOT NULL AND batch_id IS NOT NULL AND serial_number IS NULL"
            ),
        ),
        Index(
            "uq_stock_position_location_no_batch",
            "location_id",
            "product_id",
            "owner_id",
            "quality_status",
            unique=True,
            sqlite_where=text(
                "location_id IS NOT NULL AND batch_id IS NULL AND serial_number IS NULL"
            ),
            postgresql_where=text(
                "location_id IS NOT NULL AND batch_id IS NULL AND serial_number IS NULL"
            ),
        ),
        Index(
            "uq_stock_position_product_serial_owner",
            "product_id",
            "serial_number",
            "owner_id",
            unique=True,
            sqlite_where=text("serial_number IS NOT NULL"),
            postgresql_where=text("serial_number IS NOT NULL"),
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), index=True)
    batch_id: Mapped[int | None] = mapped_column(ForeignKey("batches.id"), nullable=True, index=True)
    owner_id: Mapped[int] = mapped_column(ForeignKey("stock_owners.id"), index=True)
    quality_status: Mapped[str] = mapped_column(String(40), default="released", index=True)
    serial_number: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    quantity: Mapped[Decimal] = mapped_column(Numeric(20, 6))
    logistic_unit_id: Mapped[int | None] = mapped_column(
        ForeignKey("logistic_units.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    location_id: Mapped[int | None] = mapped_column(
        ForeignKey("locations.id"),
        nullable=True,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    product: Mapped[Product] = relationship()
    batch: Mapped[Batch | None] = relationship()
    owner: Mapped[StockOwner] = relationship()
    logistic_unit: Mapped[LogisticUnit | None] = relationship()
    location: Mapped["Location | None"] = relationship()


class StockReservationRequest(Base):
    __tablename__ = "stock_reservation_requests"
    __table_args__ = (
        CheckConstraint(
            "((requested_stock_position_id IS NOT NULL AND requested_logistic_unit_id IS NULL) OR "
            "(requested_stock_position_id IS NULL AND requested_logistic_unit_id IS NOT NULL))",
            name="ck_stock_reservation_request_single_target",
        ),
        CheckConstraint(
            "requested_quantity IS NULL OR requested_quantity > 0",
            name="ck_stock_reservation_request_quantity",
        ),
        CheckConstraint(
            "reserved_quantity IS NULL OR reserved_quantity >= 0",
            name="ck_stock_reservation_request_reserved_quantity",
        ),
        CheckConstraint(
            "input_quantity IS NULL OR input_quantity > 0",
            name="ck_stock_reservation_request_input_quantity",
        ),
        CheckConstraint(
            "conversion_factor IS NULL OR conversion_factor > 0",
            name="ck_stock_reservation_request_conversion_factor",
        ),
        CheckConstraint(
            "expected_position_count >= 0 AND allocation_count >= 0",
            name="ck_stock_reservation_request_counts",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    uid: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    kind: Mapped[StockReservationKind] = mapped_column(
        Enum(StockReservationKind, native_enum=False, length=24),
        index=True,
    )
    result: Mapped[StockReservationResult] = mapped_column(
        Enum(StockReservationResult, native_enum=False, length=24),
        index=True,
    )
    requested_stock_position_id: Mapped[int | None] = mapped_column(
        Integer, nullable=True, index=True
    )
    requested_logistic_unit_id: Mapped[int | None] = mapped_column(
        Integer, nullable=True, index=True
    )
    requested_logistic_unit_uid: Mapped[str | None] = mapped_column(
        String(64), nullable=True, index=True
    )
    requested_quantity: Mapped[Decimal | None] = mapped_column(Numeric(20, 6), nullable=True)
    reserved_quantity: Mapped[Decimal | None] = mapped_column(Numeric(20, 6), nullable=True)
    base_uom_id: Mapped[int | None] = mapped_column(
        ForeignKey("units_of_measure.id"), nullable=True
    )
    input_quantity: Mapped[Decimal | None] = mapped_column(Numeric(20, 8), nullable=True)
    input_uom_id: Mapped[int | None] = mapped_column(
        ForeignKey("units_of_measure.id"), nullable=True
    )
    conversion_factor: Mapped[Decimal | None] = mapped_column(Numeric(20, 8), nullable=True)
    allow_partial: Mapped[bool] = mapped_column(Boolean, default=True)
    expected_position_count: Mapped[int] = mapped_column(Integer, default=0)
    allocation_count: Mapped[int] = mapped_column(Integer, default=0)
    reference_type: Mapped[str] = mapped_column(String(40), index=True)
    reference_uid: Mapped[str] = mapped_column(String(80), index=True)
    reference_line_uid: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)
    task_id: Mapped[int | None] = mapped_column(
        ForeignKey("logistic_tasks.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    idempotency_key: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    command_hash: Mapped[str] = mapped_column(String(64))
    actor: Mapped[str] = mapped_column(String(80), default="system", index=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    base_uom: Mapped[UnitOfMeasure | None] = relationship(foreign_keys=[base_uom_id])
    input_uom: Mapped[UnitOfMeasure | None] = relationship(foreign_keys=[input_uom_id])
    task: Mapped["LogisticTask | None"] = relationship()
    reservations: Mapped[list["StockReservation"]] = relationship(
        back_populates="request",
        foreign_keys="StockReservation.request_id",
    )


class StockReservation(Base):
    __tablename__ = "stock_reservations"
    __table_args__ = (
        CheckConstraint("quantity > 0", name="ck_stock_reservation_quantity"),
        CheckConstraint("input_quantity > 0", name="ck_stock_reservation_input_quantity"),
        CheckConstraint("conversion_factor > 0", name="ck_stock_reservation_conversion_factor"),
        CheckConstraint(
            "NOT (logistic_unit_id IS NOT NULL AND location_id IS NOT NULL)",
            name="ck_stock_reservation_single_holder",
        ),
        CheckConstraint(
            "((logistic_unit_uid IS NOT NULL AND location_code IS NULL) OR "
            "(logistic_unit_uid IS NULL AND location_code IS NOT NULL))",
            name="ck_stock_reservation_holder_snapshot",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    uid: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    request_id: Mapped[int | None] = mapped_column(
        ForeignKey("stock_reservation_requests.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    status: Mapped[StockReservationStatus] = mapped_column(
        Enum(StockReservationStatus, native_enum=False, length=24),
        default=StockReservationStatus.ACTIVE,
        index=True,
    )
    stock_position_id: Mapped[int | None] = mapped_column(
        ForeignKey("stock_positions.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), index=True)
    batch_id: Mapped[int | None] = mapped_column(
        ForeignKey("batches.id"),
        nullable=True,
        index=True,
    )
    serial_number: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    owner_id: Mapped[int] = mapped_column(ForeignKey("stock_owners.id"), index=True)
    quality_status: Mapped[str] = mapped_column(String(40), index=True)
    quantity: Mapped[Decimal] = mapped_column(Numeric(20, 6))
    base_uom_id: Mapped[int] = mapped_column(ForeignKey("units_of_measure.id"), index=True)
    input_quantity: Mapped[Decimal] = mapped_column(Numeric(20, 8))
    input_uom_id: Mapped[int] = mapped_column(ForeignKey("units_of_measure.id"), index=True)
    conversion_factor: Mapped[Decimal] = mapped_column(Numeric(20, 8))
    logistic_unit_id: Mapped[int | None] = mapped_column(
        ForeignKey("logistic_units.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    location_id: Mapped[int | None] = mapped_column(
        ForeignKey("locations.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    logistic_unit_uid: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    location_code: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    reference_type: Mapped[str] = mapped_column(String(40), index=True)
    reference_uid: Mapped[str] = mapped_column(String(80), index=True)
    reference_line_uid: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)
    task_id: Mapped[int | None] = mapped_column(
        ForeignKey("logistic_tasks.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    idempotency_key: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    command_hash: Mapped[str] = mapped_column(String(64))
    actor: Mapped[str] = mapped_column(String(80), default="system", index=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    released_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    release_idempotency_key: Mapped[str | None] = mapped_column(
        String(120),
        nullable=True,
        unique=True,
        index=True,
    )
    release_command_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    release_actor: Mapped[str | None] = mapped_column(String(80), nullable=True)
    release_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    consumed_by_document_id: Mapped[int | None] = mapped_column(
        ForeignKey("stock_documents.id"),
        nullable=True,
        index=True,
    )
    consume_idempotency_key: Mapped[str | None] = mapped_column(
        String(120),
        nullable=True,
        unique=True,
        index=True,
    )
    consume_command_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    consume_actor: Mapped[str | None] = mapped_column(String(80), nullable=True)
    consume_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    stock_position: Mapped[StockPosition | None] = relationship()
    product: Mapped[Product] = relationship()
    batch: Mapped[Batch | None] = relationship()
    owner: Mapped[StockOwner] = relationship()
    base_uom: Mapped[UnitOfMeasure] = relationship(foreign_keys=[base_uom_id])
    input_uom: Mapped[UnitOfMeasure] = relationship(foreign_keys=[input_uom_id])
    logistic_unit: Mapped[LogisticUnit | None] = relationship()
    location: Mapped["Location | None"] = relationship()
    task: Mapped["LogisticTask | None"] = relationship()
    consumed_by_document: Mapped["StockDocument | None"] = relationship()
    request: Mapped[StockReservationRequest | None] = relationship(
        back_populates="reservations",
        foreign_keys=[request_id],
    )


class StockDocument(Base):
    __tablename__ = "stock_documents"

    id: Mapped[int] = mapped_column(primary_key=True)
    uid: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    document_type: Mapped[str] = mapped_column(String(40), index=True)
    status: Mapped[StockDocumentStatus] = mapped_column(
        Enum(StockDocumentStatus, native_enum=False, length=24),
        default=StockDocumentStatus.DRAFT,
        index=True,
    )
    reference_type: Mapped[str | None] = mapped_column(String(40), nullable=True, index=True)
    reference_uid: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)
    idempotency_key: Mapped[str | None] = mapped_column(
        String(120),
        nullable=True,
        unique=True,
        index=True,
    )
    reversal_of_id: Mapped[int | None] = mapped_column(
        ForeignKey("stock_documents.id"),
        nullable=True,
        unique=True,
        index=True,
    )
    actor: Mapped[str] = mapped_column(String(80), default="system", index=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    attributes: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    posted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    reversed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    reversal_of: Mapped["StockDocument | None"] = relationship(
        remote_side="StockDocument.id",
        foreign_keys=[reversal_of_id],
    )
    movements: Mapped[list["StockMovement"]] = relationship(
        back_populates="document",
        cascade="all, delete-orphan",
        order_by="StockMovement.sequence_no",
    )


class StockMovement(Base):
    __tablename__ = "stock_movements"
    __table_args__ = (
        UniqueConstraint("document_id", "sequence_no", name="uq_stock_movement_document_sequence"),
        CheckConstraint("quantity > 0", name="ck_stock_movement_quantity"),
        CheckConstraint("input_quantity > 0", name="ck_stock_movement_input_quantity"),
        CheckConstraint("conversion_factor > 0", name="ck_stock_movement_conversion_factor"),
        CheckConstraint(
            "serial_number IS NULL OR quantity = 1",
            name="ck_stock_movement_serial_quantity",
        ),
        CheckConstraint(
            "NOT (source_logistic_unit_id IS NOT NULL AND source_location_id IS NOT NULL)",
            name="ck_stock_movement_single_source",
        ),
        CheckConstraint(
            "NOT (destination_logistic_unit_id IS NOT NULL AND destination_location_id IS NOT NULL)",
            name="ck_stock_movement_single_destination",
        ),
        CheckConstraint(
            "source_logistic_unit_id IS NOT NULL OR source_location_id IS NOT NULL OR "
            "destination_logistic_unit_id IS NOT NULL OR destination_location_id IS NOT NULL",
            name="ck_stock_movement_has_holder",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    document_id: Mapped[int] = mapped_column(
        ForeignKey("stock_documents.id", ondelete="CASCADE"),
        index=True,
    )
    sequence_no: Mapped[int] = mapped_column(Integer)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), index=True)
    batch_id: Mapped[int | None] = mapped_column(ForeignKey("batches.id"), nullable=True, index=True)
    serial_number: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    owner_id: Mapped[int] = mapped_column(ForeignKey("stock_owners.id"), index=True)
    source_quality_status: Mapped[str | None] = mapped_column(String(40), nullable=True, index=True)
    destination_quality_status: Mapped[str | None] = mapped_column(String(40), nullable=True, index=True)
    quantity: Mapped[Decimal] = mapped_column(Numeric(20, 6))
    base_uom_id: Mapped[int] = mapped_column(ForeignKey("units_of_measure.id"), index=True)
    input_quantity: Mapped[Decimal] = mapped_column(Numeric(20, 8))
    input_uom_id: Mapped[int] = mapped_column(ForeignKey("units_of_measure.id"), index=True)
    conversion_factor: Mapped[Decimal] = mapped_column(Numeric(20, 8))
    source_logistic_unit_id: Mapped[int | None] = mapped_column(
        ForeignKey("logistic_units.id"),
        nullable=True,
        index=True,
    )
    source_location_id: Mapped[int | None] = mapped_column(
        ForeignKey("locations.id"),
        nullable=True,
        index=True,
    )
    destination_logistic_unit_id: Mapped[int | None] = mapped_column(
        ForeignKey("logistic_units.id"),
        nullable=True,
        index=True,
    )
    destination_location_id: Mapped[int | None] = mapped_column(
        ForeignKey("locations.id"),
        nullable=True,
        index=True,
    )
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)

    document: Mapped[StockDocument] = relationship(back_populates="movements")
    product: Mapped[Product] = relationship()
    batch: Mapped[Batch | None] = relationship()
    owner: Mapped[StockOwner] = relationship()
    base_uom: Mapped[UnitOfMeasure] = relationship(foreign_keys=[base_uom_id])
    input_uom: Mapped[UnitOfMeasure] = relationship(foreign_keys=[input_uom_id])
    source_logistic_unit: Mapped[LogisticUnit | None] = relationship(
        foreign_keys=[source_logistic_unit_id]
    )
    source_location: Mapped["Location | None"] = relationship(foreign_keys=[source_location_id])
    destination_logistic_unit: Mapped[LogisticUnit | None] = relationship(
        foreign_keys=[destination_logistic_unit_id]
    )
    destination_location: Mapped["Location | None"] = relationship(
        foreign_keys=[destination_location_id]
    )


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
    aisles: Mapped[list["Aisle"]] = relationship(back_populates="zone")
    locations: Mapped[list["Location"]] = relationship(back_populates="zone")


class Aisle(Base):
    __tablename__ = "aisles"
    __table_args__ = (UniqueConstraint("zone_id", "code", name="uq_aisle_zone_code"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    zone_id: Mapped[int] = mapped_column(ForeignKey("zones.id"), index=True)
    code: Mapped[str] = mapped_column(String(32), index=True)
    name: Mapped[str] = mapped_column(String(160))
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    zone: Mapped[Zone] = relationship(back_populates="aisles")
    racks: Mapped[list["Rack"]] = relationship(back_populates="aisle")


class Rack(Base):
    __tablename__ = "racks"
    __table_args__ = (UniqueConstraint("aisle_id", "code", name="uq_rack_aisle_code"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    aisle_id: Mapped[int] = mapped_column(ForeignKey("aisles.id"), index=True)
    code: Mapped[str] = mapped_column(String(32), index=True)
    name: Mapped[str] = mapped_column(String(160))
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    aisle: Mapped[Aisle] = relationship(back_populates="racks")
    sections: Mapped[list["RackSection"]] = relationship(back_populates="rack")


class RackSection(Base):
    __tablename__ = "rack_sections"
    __table_args__ = (UniqueConstraint("rack_id", "code", name="uq_rack_section_code"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    rack_id: Mapped[int] = mapped_column(ForeignKey("racks.id"), index=True)
    code: Mapped[str] = mapped_column(String(32), index=True)
    name: Mapped[str] = mapped_column(String(160))
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    rack: Mapped[Rack] = relationship(back_populates="sections")
    levels: Mapped[list["RackLevel"]] = relationship(back_populates="section")


class RackLevel(Base):
    __tablename__ = "rack_levels"
    __table_args__ = (
        UniqueConstraint("section_id", "code", name="uq_rack_level_code"),
        CheckConstraint(
            "elevation_mm IS NULL OR elevation_mm >= 0",
            name="ck_rack_level_elevation",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    section_id: Mapped[int] = mapped_column(ForeignKey("rack_sections.id"), index=True)
    code: Mapped[str] = mapped_column(String(32), index=True)
    name: Mapped[str] = mapped_column(String(160))
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    elevation_mm: Mapped[int | None] = mapped_column(Integer, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    section: Mapped[RackSection] = relationship(back_populates="levels")
    locations: Mapped[list["Location"]] = relationship(back_populates="level")


class Location(Base):
    __tablename__ = "locations"
    __table_args__ = (
        UniqueConstraint("level_id", "position_code", name="uq_location_level_position"),
        CheckConstraint(
            "(aisle_id IS NULL AND rack_id IS NULL AND section_id IS NULL "
            "AND level_id IS NULL AND position_code IS NULL) OR "
            "(aisle_id IS NOT NULL AND rack_id IS NOT NULL AND section_id IS NOT NULL "
            "AND level_id IS NOT NULL AND position_code IS NOT NULL)",
            name="ck_location_complete_address",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    warehouse_id: Mapped[int] = mapped_column(ForeignKey("warehouses.id"))
    zone_id: Mapped[int] = mapped_column(ForeignKey("zones.id"))
    aisle_id: Mapped[int | None] = mapped_column(ForeignKey("aisles.id"), nullable=True, index=True)
    rack_id: Mapped[int | None] = mapped_column(ForeignKey("racks.id"), nullable=True, index=True)
    section_id: Mapped[int | None] = mapped_column(ForeignKey("rack_sections.id"), nullable=True, index=True)
    level_id: Mapped[int | None] = mapped_column(ForeignKey("rack_levels.id"), nullable=True, index=True)
    position_code: Mapped[str | None] = mapped_column(String(32), nullable=True)
    code: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    name: Mapped[str | None] = mapped_column(String(160), nullable=True)
    kind: Mapped[LocationKind] = mapped_column(Enum(LocationKind), default=LocationKind.STORAGE)
    capacity_units: Mapped[int] = mapped_column(Integer, default=1)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    zone: Mapped[Zone] = relationship(back_populates="locations")
    aisle: Mapped[Aisle | None] = relationship()
    rack: Mapped[Rack | None] = relationship()
    section: Mapped[RackSection | None] = relationship()
    level: Mapped[RackLevel | None] = relationship(back_populates="locations")


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
    transfer_kind: Mapped[TransferKind] = mapped_column(
        Enum(TransferKind, native_enum=False, length=32),
        default=TransferKind.TRANSPORT,
        index=True,
    )
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


class LogisticInventory(Base):
    __tablename__ = "logistic_inventories"

    id: Mapped[int] = mapped_column(primary_key=True)
    inventory_uid: Mapped[str] = mapped_column(String(40), unique=True, index=True)
    warehouse_id: Mapped[int] = mapped_column(ForeignKey("warehouses.id"), index=True)
    scope_type: Mapped[str] = mapped_column(String(32), default="warehouse", index=True)
    scope_parameters: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    current_location_id: Mapped[int | None] = mapped_column(
        ForeignKey("locations.id"),
        nullable=True,
    )
    status: Mapped[InventoryStatus] = mapped_column(
        Enum(InventoryStatus, native_enum=False, length=32),
        default=InventoryStatus.OPEN,
        index=True,
    )
    actor: Mapped[str] = mapped_column(String(80), default="system")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    locations: Mapped[list["LogisticInventoryLocation"]] = relationship(
        back_populates="inventory",
        cascade="all, delete-orphan",
    )
    lines: Mapped[list["LogisticInventoryLine"]] = relationship(
        back_populates="inventory",
        cascade="all, delete-orphan",
    )


class LogisticInventoryLocation(Base):
    __tablename__ = "logistic_inventory_locations"
    __table_args__ = (
        UniqueConstraint(
            "inventory_id",
            "location_id",
            name="uq_logistic_inventory_location",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    inventory_id: Mapped[int] = mapped_column(
        ForeignKey("logistic_inventories.id"),
        index=True,
    )
    location_id: Mapped[int] = mapped_column(ForeignKey("locations.id"), index=True)
    expected_unit_count: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[InventoryLocationStatus] = mapped_column(
        Enum(InventoryLocationStatus, native_enum=False, length=32),
        default=InventoryLocationStatus.UNCHECKED,
        index=True,
    )
    checked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    checked_by: Mapped[str | None] = mapped_column(String(80), nullable=True)

    inventory: Mapped[LogisticInventory] = relationship(back_populates="locations")


class LogisticInventoryLine(Base):
    __tablename__ = "logistic_inventory_lines"
    __table_args__ = (
        UniqueConstraint(
            "inventory_id",
            "logistic_unit_id",
            name="uq_logistic_inventory_unit",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    inventory_id: Mapped[int] = mapped_column(
        ForeignKey("logistic_inventories.id"),
        index=True,
    )
    logistic_unit_id: Mapped[int] = mapped_column(
        ForeignKey("logistic_units.id"),
        index=True,
    )
    expected_location_id: Mapped[int | None] = mapped_column(
        ForeignKey("locations.id"),
        nullable=True,
        index=True,
    )
    actual_location_id: Mapped[int | None] = mapped_column(
        ForeignKey("locations.id"),
        nullable=True,
        index=True,
    )
    status: Mapped[InventoryLineStatus] = mapped_column(
        Enum(InventoryLineStatus, native_enum=False, length=32),
        default=InventoryLineStatus.EXPECTED,
        index=True,
    )
    scanned_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    resolution_action: Mapped[str | None] = mapped_column(String(40), nullable=True)
    resolution_actor: Mapped[str | None] = mapped_column(String(80), nullable=True)
    resolution_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    inventory: Mapped[LogisticInventory] = relationship(back_populates="lines")


class LogisticTask(Base):
    __tablename__ = "logistic_tasks"

    id: Mapped[int] = mapped_column(primary_key=True)
    task_uid: Mapped[str] = mapped_column(String(40), unique=True, index=True)
    warehouse_id: Mapped[int] = mapped_column(
        ForeignKey("warehouses.id"),
        index=True,
    )
    task_type: Mapped[TaskType] = mapped_column(
        Enum(TaskType, native_enum=False, length=32),
        index=True,
    )
    status: Mapped[TaskStatus] = mapped_column(
        Enum(TaskStatus, native_enum=False, length=32),
        default=TaskStatus.NEW,
        index=True,
    )
    priority: Mapped[TaskPriority] = mapped_column(
        Enum(TaskPriority, native_enum=False, length=32),
        default=TaskPriority.NORMAL,
        index=True,
    )
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(String(500), nullable=True)
    object_type: Mapped[str] = mapped_column(String(40), index=True)
    object_uid: Mapped[str] = mapped_column(String(120), index=True)
    parameters: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    assigned_to: Mapped[str | None] = mapped_column(
        String(80),
        nullable=True,
        index=True,
    )
    created_by: Mapped[str] = mapped_column(String(80), default="system")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utcnow,
        index=True,
    )
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )


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
