from datetime import date, datetime
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.core.constants import DEFAULT_UNIT, DEFAULT_WAREHOUSE_CODE, DEFAULT_WAREHOUSE_NAME
from app.models.enums import (
    EquipmentConnection,
    EquipmentKind,
    InventoryLineStatus,
    InventoryLocationStatus,
    InventoryStatus,
    LocationKind,
    LogisticUnitStatus,
    MeasurementDimension,
    ShipmentStatus,
    StockDocumentStatus,
    TransferKind,
    TransferStatus,
    TaskPriority,
    TaskStatus,
    TaskType,
    UserRole,
)


class UserCreate(BaseModel):
    username: str = Field(min_length=2, max_length=80)
    full_name: str = Field(min_length=2, max_length=160)
    role: UserRole = UserRole.ADMIN


class UserRead(UserCreate):
    id: int
    is_active: bool
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class UnitOfMeasureCreate(BaseModel):
    code: str = Field(min_length=1, max_length=32)
    name: str = Field(min_length=1, max_length=120)
    symbol: str = Field(min_length=1, max_length=24)
    dimension: MeasurementDimension
    decimal_precision: int = Field(default=0, ge=0, le=6)
    factor_to_base: Decimal = Field(default=Decimal("1"), gt=0, max_digits=20, decimal_places=8)
    is_base: bool = False

    @model_validator(mode="after")
    def validate_base_factor(self):
        if self.is_base and self.factor_to_base != Decimal("1"):
            raise ValueError("base unit factor_to_base must equal 1")
        return self


class UnitOfMeasureRead(UnitOfMeasureCreate):
    id: int
    is_active: bool

    model_config = ConfigDict(from_attributes=True)


class LogisticUnitTypeCreate(BaseModel):
    code: str = Field(min_length=1, max_length=32)
    name: str = Field(min_length=1, max_length=120)
    identifier_prefix: str = Field(min_length=1, max_length=16)
    tare_weight: Decimal | None = Field(default=None, ge=0, max_digits=18, decimal_places=6)
    tare_weight_uom_id: int | None = None
    max_weight: Decimal | None = Field(default=None, gt=0, max_digits=18, decimal_places=6)
    max_weight_uom_id: int | None = None
    length_mm: int | None = Field(default=None, gt=0)
    width_mm: int | None = Field(default=None, gt=0)
    height_mm: int | None = Field(default=None, gt=0)
    can_contain_goods: bool = True
    can_contain_units: bool = False
    is_returnable: bool = False
    barcode_template: str = Field(default="{uid}", min_length=1, max_length=240)
    label_profile: str | None = Field(default=None, max_length=80)
    allowed_child_type_ids: list[int] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_weight_units(self):
        if self.tare_weight is not None and self.tare_weight_uom_id is None:
            raise ValueError("tare_weight_uom_id is required when tare_weight is set")
        if self.max_weight is not None and self.max_weight_uom_id is None:
            raise ValueError("max_weight_uom_id is required when max_weight is set")
        if self.allowed_child_type_ids and not self.can_contain_units:
            raise ValueError("can_contain_units must be enabled when allowed child types are set")
        if len(self.allowed_child_type_ids) != len(set(self.allowed_child_type_ids)):
            raise ValueError("allowed_child_type_ids must be unique")
        return self


class LogisticUnitTypeRead(LogisticUnitTypeCreate):
    id: int
    is_active: bool

    model_config = ConfigDict(from_attributes=True)


class LogisticUnitCreate(BaseModel):
    type_id: int
    uid: str | None = Field(default=None, min_length=1, max_length=64)
    measured_gross_weight: Decimal | None = Field(
        default=None,
        gt=0,
        max_digits=18,
        decimal_places=6,
    )
    weight_uom_id: int | None = None
    length_mm: int | None = Field(default=None, gt=0)
    width_mm: int | None = Field(default=None, gt=0)
    height_mm: int | None = Field(default=None, gt=0)
    actor: str = Field(default="system", min_length=1, max_length=80)

    @model_validator(mode="after")
    def validate_weight(self):
        if self.measured_gross_weight is not None and self.weight_uom_id is None:
            raise ValueError("weight_uom_id is required when measured_gross_weight is set")
        if self.measured_gross_weight is None and self.weight_uom_id is not None:
            raise ValueError("measured_gross_weight is required when weight_uom_id is set")
        return self


class LogisticUnitContentCreate(BaseModel):
    product_id: int
    batch_id: int | None = None
    quantity: Decimal = Field(gt=0, max_digits=20, decimal_places=6)
    uom_id: int
    actor: str = Field(default="system", min_length=1, max_length=80)
    idempotency_key: str | None = Field(default=None, min_length=1, max_length=120)


class LogisticUnitContentRemoveRequest(BaseModel):
    quantity: Decimal = Field(gt=0, max_digits=20, decimal_places=6)
    actor: str = Field(default="system", min_length=1, max_length=80)
    reason: str | None = Field(default=None, max_length=500)
    idempotency_key: str | None = Field(default=None, min_length=1, max_length=120)


class LogisticUnitChildRequest(BaseModel):
    child_uid: str = Field(min_length=1, max_length=64)
    actor: str = Field(default="system", min_length=1, max_length=80)


class LogisticUnitActionRequest(BaseModel):
    actor: str = Field(default="system", min_length=1, max_length=80)
    reason: str | None = Field(default=None, max_length=500)


class LogisticUnitAcceptRequest(BaseModel):
    location_code: str = Field(min_length=1, max_length=120)
    actor: str = Field(default="system", min_length=1, max_length=80)
    reason: str | None = Field(default=None, max_length=500)


class LogisticUnitHoldRequest(BaseModel):
    actor: str = Field(default="system", min_length=1, max_length=80)
    reason: str = Field(min_length=1, max_length=500)


class LogisticUnitLocationRequest(BaseModel):
    location_code: str = Field(min_length=1, max_length=120)
    actor: str = Field(default="system", min_length=1, max_length=80)
    reason: str | None = Field(default=None, max_length=500)


class LogisticUnitContentRead(BaseModel):
    id: int
    product_id: int
    product_code: str
    batch_id: int | None
    batch_number: str | None
    quantity: Decimal
    uom_id: int
    uom_code: str
    uom_symbol: str
    added_at: datetime


class LogisticUnitChildRead(BaseModel):
    id: int
    uid: str
    type_id: int
    type_code: str
    type_name: str
    status: LogisticUnitStatus


class LogisticUnitRead(BaseModel):
    id: int
    uid: str
    type_id: int
    type_code: str
    type_name: str
    status: LogisticUnitStatus
    parent_uid: str | None
    current_location_id: int | None
    current_location_code: str | None
    measured_gross_weight: Decimal | None
    weight_uom_id: int | None
    weight_uom_code: str | None
    length_mm: int | None
    width_mm: int | None
    height_mm: int | None
    status_before_hold: LogisticUnitStatus | None
    created_at: datetime
    accepted_at: datetime | None
    closed_at: datetime | None
    contents: list[LogisticUnitContentRead] = Field(default_factory=list)
    child_units: list[LogisticUnitChildRead] = Field(default_factory=list)


class EquipmentProfileCreate(BaseModel):
    code: str = Field(min_length=1, max_length=48)
    name: str = Field(min_length=1, max_length=160)
    device_kind: EquipmentKind
    manufacturer: str | None = Field(default=None, max_length=120)
    model: str | None = Field(default=None, max_length=120)
    connection_type: EquipmentConnection
    host: str | None = Field(default=None, min_length=1, max_length=255)
    port: int | None = Field(default=None, ge=1, le=65535)
    queue_name: str | None = Field(default=None, min_length=1, max_length=120)
    serial_device: str | None = Field(default=None, min_length=1, max_length=160)
    driver_code: str | None = Field(default=None, max_length=80)
    warehouse_id: int | None = None
    parameters: dict[str, Any] = Field(default_factory=dict)
    is_default: bool = False

    @model_validator(mode="after")
    def validate_connection(self):
        if self.connection_type == EquipmentConnection.RAW_TCP and (self.host is None or self.port is None):
            raise ValueError("host and port are required for RAW TCP equipment")
        if self.connection_type == EquipmentConnection.SYSTEM_QUEUE and self.queue_name is None:
            raise ValueError("queue_name is required for system queue equipment")
        if self.connection_type == EquipmentConnection.SERIAL and self.serial_device is None:
            raise ValueError("serial_device is required for serial equipment")
        return self


class EquipmentProfileRead(EquipmentProfileCreate):
    id: int
    is_active: bool
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class EquipmentProfileUpdate(EquipmentProfileCreate):
    is_active: bool = True


class ProductCreate(BaseModel):
    code: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=240)
    unit: str = DEFAULT_UNIT
    base_uom_id: int | None = None
    shelf_life_days: int | None = Field(default=None, ge=1)


class ProductRead(ProductCreate):
    id: int
    is_active: bool

    model_config = ConfigDict(from_attributes=True)


class ProductPackagingCreate(BaseModel):
    product_id: int
    code: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=160)
    quantity: Decimal = Field(gt=0, max_digits=20, decimal_places=8)
    uom_id: int
    barcode: str | None = Field(default=None, min_length=1, max_length=120)


class ProductPackagingRead(ProductPackagingCreate):
    id: int
    base_quantity: Decimal
    is_active: bool
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class StockOwnerCreate(BaseModel):
    code: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=200)
    is_internal: bool = False


class StockOwnerRead(StockOwnerCreate):
    id: int
    is_active: bool
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class StockPositionRead(BaseModel):
    id: int
    product_id: int
    product_code: str
    product_name: str
    batch_id: int | None
    batch_number: str | None
    owner_id: int
    owner_code: str
    owner_name: str
    quality_status: str
    serial_number: str | None
    quantity: Decimal
    available_quantity: Decimal
    reserved_quantity: Decimal
    in_transit_quantity: Decimal
    blocked_quantity: Decimal
    base_uom_id: int
    base_uom_code: str
    base_uom_symbol: str
    holder_kind: Literal["logistic_unit", "location"]
    logistic_unit_id: int | None
    logistic_unit_uid: str | None
    root_logistic_unit_uid: str | None
    holder_status: LogisticUnitStatus | None
    location_id: int | None
    location_code: str | None
    warehouse_id: int | None
    warehouse_code: str | None
    created_at: datetime
    updated_at: datetime


class StockMovementPost(BaseModel):
    product_id: int
    batch_id: int | None = None
    serial_number: str | None = Field(default=None, max_length=120)
    owner_id: int
    source_quality_status: str | None = Field(default=None, min_length=1, max_length=40)
    destination_quality_status: str | None = Field(default=None, min_length=1, max_length=40)
    input_quantity: Decimal = Field(gt=0, max_digits=20, decimal_places=8)
    input_uom_id: int
    source_logistic_unit_id: int | None = None
    source_location_id: int | None = None
    destination_logistic_unit_id: int | None = None
    destination_location_id: int | None = None

    @field_validator("serial_number")
    @classmethod
    def normalize_serial_number(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip().upper()
        return normalized or None

    @field_validator("source_quality_status", "destination_quality_status")
    @classmethod
    def normalize_quality_status(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None

    @model_validator(mode="after")
    def validate_holders(self):
        source_count = sum(
            value is not None
            for value in (self.source_logistic_unit_id, self.source_location_id)
        )
        destination_count = sum(
            value is not None
            for value in (self.destination_logistic_unit_id, self.destination_location_id)
        )
        if source_count > 1 or destination_count > 1:
            raise ValueError("source and destination must each reference at most one holder")
        if source_count + destination_count == 0:
            raise ValueError("movement must reference a source or destination holder")
        if source_count and not self.source_quality_status:
            raise ValueError("source_quality_status is required for a source movement")
        if destination_count and not self.destination_quality_status:
            raise ValueError("destination_quality_status is required for a destination movement")
        if not source_count and self.source_quality_status:
            raise ValueError("source_quality_status requires a source holder")
        if not destination_count and self.destination_quality_status:
            raise ValueError("destination_quality_status requires a destination holder")
        return self


class StockDocumentPost(BaseModel):
    uid: str | None = Field(default=None, min_length=1, max_length=64)
    document_type: str = Field(min_length=1, max_length=40)
    reference_type: str | None = Field(default=None, max_length=40)
    reference_uid: str | None = Field(default=None, max_length=80)
    idempotency_key: str = Field(min_length=1, max_length=120)
    actor: str = Field(default="system", min_length=1, max_length=80)
    reason: str | None = None
    attributes: dict[str, Any] = Field(default_factory=dict)
    movements: list[StockMovementPost] = Field(min_length=1)

    @field_validator("uid", "reference_type", "reference_uid", "reason")
    @classmethod
    def normalize_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None

    @field_validator("document_type", "idempotency_key", "actor")
    @classmethod
    def normalize_required_text(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("value must not be blank")
        return normalized


class StockMovementRead(BaseModel):
    id: int
    document_id: int
    document_uid: str
    sequence_no: int
    product_id: int
    product_code: str
    batch_id: int | None
    batch_number: str | None
    serial_number: str | None
    owner_id: int
    owner_code: str
    source_quality_status: str | None
    destination_quality_status: str | None
    quantity: Decimal
    base_uom_id: int
    base_uom_code: str
    input_quantity: Decimal
    input_uom_id: int
    input_uom_code: str
    conversion_factor: Decimal
    source_logistic_unit_id: int | None
    source_logistic_unit_uid: str | None
    source_location_id: int | None
    source_location_code: str | None
    destination_logistic_unit_id: int | None
    destination_logistic_unit_uid: str | None
    destination_location_id: int | None
    destination_location_code: str | None
    occurred_at: datetime


class StockDocumentRead(BaseModel):
    id: int
    uid: str
    document_type: str
    status: StockDocumentStatus
    reference_type: str | None
    reference_uid: str | None
    idempotency_key: str | None
    reversal_of_id: int | None
    reversal_of_uid: str | None
    actor: str
    reason: str | None
    attributes: dict[str, Any]
    movement_count: int
    created_at: datetime
    posted_at: datetime | None
    reversed_at: datetime | None


class StockDocumentDetailRead(StockDocumentRead):
    movements: list[StockMovementRead]


class StockReconciliationIssueRead(BaseModel):
    kind: Literal[
        "missing_position",
        "unexpected_position",
        "quantity_mismatch",
        "negative_ledger_balance",
        "invalid_movement",
        "base_uom_mismatch",
        "duplicate_position",
    ]
    message: str
    movement_id: int | None = None
    document_uid: str | None = None
    position_id: int | None = None
    product_id: int | None = None
    product_code: str | None = None
    product_name: str | None = None
    batch_id: int | None = None
    batch_number: str | None = None
    serial_number: str | None = None
    owner_id: int | None = None
    owner_code: str | None = None
    quality_status: str | None = None
    holder_kind: Literal["logistic_unit", "location"] | None = None
    logistic_unit_id: int | None = None
    logistic_unit_uid: str | None = None
    location_id: int | None = None
    location_code: str | None = None
    base_uom_id: int | None = None
    base_uom_code: str | None = None
    ledger_base_uom_ids: list[int] = Field(default_factory=list)
    expected_quantity: Decimal | None = None
    actual_quantity: Decimal | None = None
    delta_quantity: Decimal | None = None


class StockReconciliationRead(BaseModel):
    checked_at: datetime
    is_consistent: bool
    movement_count: int
    ignored_movement_count: int
    position_count: int
    checked_identity_count: int
    matched_identity_count: int
    zero_balance_identity_count: int
    discrepancy_count: int
    negative_ledger_count: int
    issues: list[StockReconciliationIssueRead]


class BatchCreate(BaseModel):
    batch_number: str = Field(min_length=1, max_length=80)
    product_id: int
    production_date: date
    expiry_date: date
    quality_status: str = "released"
    operation_status: str = "allowed"


class BatchRead(BatchCreate):
    id: int

    model_config = ConfigDict(from_attributes=True)


class WarehouseCreate(BaseModel):
    code: str = Field(min_length=1, max_length=32)
    name: str = Field(min_length=1, max_length=160)
    city: str | None = None
    timezone: str = "Europe/Moscow"


class WarehouseRead(WarehouseCreate):
    id: int

    model_config = ConfigDict(from_attributes=True)


class ZoneCreate(BaseModel):
    warehouse_id: int
    code: str = Field(min_length=1, max_length=48)
    name: str = Field(min_length=1, max_length=160)
    kind: LocationKind = LocationKind.STORAGE


class ZoneRead(ZoneCreate):
    id: int

    model_config = ConfigDict(from_attributes=True)


class AisleCreate(BaseModel):
    zone_id: int
    code: str = Field(min_length=1, max_length=32)
    name: str = Field(min_length=1, max_length=160)
    sort_order: int = 0


class AisleRead(AisleCreate):
    id: int
    is_active: bool

    model_config = ConfigDict(from_attributes=True)


class RackCreate(BaseModel):
    aisle_id: int
    code: str = Field(min_length=1, max_length=32)
    name: str = Field(min_length=1, max_length=160)
    sort_order: int = 0


class RackRead(RackCreate):
    id: int
    is_active: bool

    model_config = ConfigDict(from_attributes=True)


class RackSectionCreate(BaseModel):
    rack_id: int
    code: str = Field(min_length=1, max_length=32)
    name: str = Field(min_length=1, max_length=160)
    sort_order: int = 0


class RackSectionRead(RackSectionCreate):
    id: int
    is_active: bool

    model_config = ConfigDict(from_attributes=True)


class RackLevelCreate(BaseModel):
    section_id: int
    code: str = Field(min_length=1, max_length=32)
    name: str = Field(min_length=1, max_length=160)
    sort_order: int = 0
    elevation_mm: int | None = Field(default=None, ge=0)


class RackLevelRead(RackLevelCreate):
    id: int
    is_active: bool

    model_config = ConfigDict(from_attributes=True)


class LocationCreate(BaseModel):
    warehouse_id: int
    zone_id: int
    aisle_id: int | None = None
    rack_id: int | None = None
    section_id: int | None = None
    level_id: int | None = None
    position_code: str | None = Field(default=None, min_length=1, max_length=32)
    code: str | None = Field(default=None, min_length=1, max_length=120)
    name: str | None = None
    kind: LocationKind = LocationKind.STORAGE
    capacity_units: int = Field(default=1, ge=1)

    @model_validator(mode="after")
    def validate_address(self):
        address = (
            self.aisle_id,
            self.rack_id,
            self.section_id,
            self.level_id,
            self.position_code,
        )
        if any(value is not None for value in address) and not all(
            value is not None for value in address
        ):
            raise ValueError("structured location requires aisle, rack, section, level and position")
        if not all(value is not None for value in address) and self.code is None:
            raise ValueError("code is required for a zone-level location")
        return self


class LocationRead(LocationCreate):
    id: int
    code: str
    is_active: bool

    model_config = ConfigDict(from_attributes=True)


class WarehouseMapRowCreate(BaseModel):
    zone_code: str = Field(default="ST01", min_length=1, max_length=48)
    row_code: str = Field(min_length=1, max_length=32)
    label: str = Field(min_length=1, max_length=160)
    location_count: int = Field(default=4, ge=1, le=8)
    orientation: Literal["horizontal", "vertical"] = "horizontal"
    x: int = Field(default=80, ge=0, le=950)
    y: int = Field(default=100, ge=0, le=550)
    actor: str = "map-editor"


class WarehouseMapLocationCreate(BaseModel):
    zone_code: str = Field(default="ST01", min_length=1, max_length=48)
    code: str = Field(min_length=1, max_length=120)
    label: str = Field(min_length=1, max_length=160)
    x: int = Field(default=80, ge=0, le=950)
    y: int = Field(default=100, ge=0, le=550)
    width: int = Field(default=110, ge=45, le=300)
    height: int = Field(default=64, ge=36, le=180)
    actor: str = "map-editor"


class WarehouseMapLabelCreate(BaseModel):
    label: str = Field(min_length=1, max_length=160)
    x: int = Field(default=80, ge=0, le=950)
    y: int = Field(default=40, ge=0, le=550)
    width: int = Field(default=220, ge=60, le=500)
    height: int = Field(default=44, ge=28, le=160)
    actor: str = "map-editor"


class WarehouseMapItemUpdate(BaseModel):
    x: int | None = Field(default=None, ge=0, le=950)
    y: int | None = Field(default=None, ge=0, le=550)
    width: int | None = Field(default=None, ge=36, le=900)
    height: int | None = Field(default=None, ge=28, le=550)
    rotation: Literal[0, 90] | None = None
    label: str | None = Field(default=None, min_length=1, max_length=160)
    actor: str = "map-editor"


class WarehouseMapActionRequest(BaseModel):
    actor: str = "map-editor"


class DemoCatalogRequest(BaseModel):
    warehouse_code: str = Field(default=DEFAULT_WAREHOUSE_CODE, min_length=1, max_length=32)
    warehouse_name: str = Field(default=DEFAULT_WAREHOUSE_NAME, min_length=1, max_length=160)
    storage_locations: int = Field(default=10, ge=1, le=80)
    actor: str = "demo-generator"


class DemoLogisticUnitsRequest(BaseModel):
    warehouse_code: str = Field(default=DEFAULT_WAREHOUSE_CODE, min_length=1, max_length=32)
    warehouse_name: str = Field(default=DEFAULT_WAREHOUSE_NAME, min_length=1, max_length=160)
    storage_locations: int = Field(default=10, ge=1, le=80)
    batch_id: int | None = None
    quantity: int = Field(default=5, ge=1, le=50)
    parent_type_code: str = Field(default="PALLET", min_length=1, max_length=32)
    child_type_code: str | None = Field(default="BOX", max_length=32)
    child_units_per_parent: int = Field(default=4, ge=1, le=40)
    content_uom_code: str = Field(default="PCS", min_length=1, max_length=32)
    content_quantity: Decimal = Field(default=Decimal("24"), gt=0, max_digits=20, decimal_places=6)
    place_to_empty_locations: bool = True
    actor: str = Field(default="demo-generator", min_length=1, max_length=80)

    @field_validator("child_type_code")
    @classmethod
    def normalize_optional_code(cls, value: str | None) -> str | None:
        normalized = (value or "").strip().upper()
        return normalized or None


class DemoGenerateRead(BaseModel):
    created_products: int = 0
    created_batches: int = 0
    created_warehouses: int = 0
    created_zones: int = 0
    created_aisles: int = 0
    created_racks: int = 0
    created_sections: int = 0
    created_levels: int = 0
    created_locations: int = 0
    created_logistic_units: int = 0
    created_child_units: int = 0
    placed_logistic_units: int = 0
    waiting_logistic_units: int = 0
    product_ids: list[int] = Field(default_factory=list)
    batch_ids: list[int] = Field(default_factory=list)
    logistic_unit_uids: list[str] = Field(default_factory=list)
    parent_type_code: str | None = None
    child_type_code: str | None = None
    content_uom_code: str | None = None
    content_quantity: Decimal | None = None


class EventRead(BaseModel):
    id: int
    operation: str
    object_type: str
    object_uid: str
    actor: str
    reason: str | None
    before: dict | None
    after: dict | None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class LogisticDocumentUnitRequest(BaseModel):
    unit_uid: str = Field(min_length=1, max_length=64)
    actor: str = Field(default="system", min_length=1, max_length=80)
    reason: str | None = Field(default=None, max_length=500)


class LogisticDocumentStageRequest(BaseModel):
    location_code: str = Field(min_length=1, max_length=120)
    actor: str = Field(default="system", min_length=1, max_length=80)
    reason: str | None = Field(default=None, max_length=500)


class LogisticDocumentActionRequest(BaseModel):
    actor: str = Field(default="system", min_length=1, max_length=80)
    reason: str | None = Field(default=None, max_length=500)


class LogisticDocumentUnitRead(BaseModel):
    id: int
    unit_uid: str
    type_code: str
    unit_status: LogisticUnitStatus
    item_status: str
    source_location_code: str
    current_location_code: str | None
    reserved_at: datetime
    moved_to_expedition_at: datetime | None
    loaded_at: datetime | None
    received_at: datetime | None = None


class LogisticShipmentCreate(BaseModel):
    warehouse_code: str = Field(min_length=1, max_length=32)
    customer_name: str = Field(min_length=1, max_length=160)
    destination: str = Field(min_length=1, max_length=160)
    planned_date: date | None = None
    actor: str = Field(default="system", min_length=1, max_length=80)


class LogisticShipmentRead(BaseModel):
    id: int
    shipment_uid: str
    warehouse_id: int
    warehouse_code: str
    customer_name: str
    destination: str
    status: ShipmentStatus
    planned_date: date | None
    created_at: datetime
    closed_at: datetime | None
    unit_count: int
    loaded_count: int
    units: list[LogisticDocumentUnitRead]


class LogisticTransferCreate(BaseModel):
    source_warehouse_code: str = Field(min_length=1, max_length=32)
    destination_warehouse_code: str = Field(min_length=1, max_length=32)
    transfer_kind: TransferKind = TransferKind.TRANSPORT
    planned_date: date | None = None
    vehicle_number: str | None = Field(default=None, max_length=80)
    actor: str = Field(default="system", min_length=1, max_length=80)


class LogisticTransferRead(BaseModel):
    id: int
    transfer_uid: str
    source_warehouse_id: int
    source_warehouse_code: str
    destination_warehouse_id: int
    destination_warehouse_code: str
    transfer_kind: TransferKind
    status: TransferStatus
    planned_date: date | None
    vehicle_number: str | None
    created_at: datetime
    dispatched_at: datetime | None
    completed_at: datetime | None
    unit_count: int
    loaded_count: int
    received_count: int
    units: list[LogisticDocumentUnitRead]


class LogisticInventoryStartRequest(BaseModel):
    warehouse_code: str = Field(min_length=1, max_length=32)
    scope_type: Literal["warehouse"] = "warehouse"
    actor: str = Field(default="system", min_length=1, max_length=80)


class LogisticInventoryLocationRequest(BaseModel):
    location_code: str = Field(min_length=1, max_length=120)
    actor: str = Field(default="system", min_length=1, max_length=80)


class LogisticInventoryUnitRequest(BaseModel):
    unit_uid: str = Field(min_length=1, max_length=64)
    finish_location: bool | None = None
    actor: str = Field(default="system", min_length=1, max_length=80)


class LogisticInventoryResolveRequest(BaseModel):
    actor: str = Field(default="system", min_length=1, max_length=80)
    reason: str | None = Field(default=None, max_length=500)


class LogisticInventoryLocationRead(BaseModel):
    id: int
    location_id: int
    location_code: str
    expected_unit_count: int
    scanned_unit_count: int
    problem_count: int
    status: InventoryLocationStatus
    checked_at: datetime | None
    checked_by: str | None


class LogisticInventoryLineRead(BaseModel):
    id: int
    unit_uid: str
    type_code: str
    unit_status: LogisticUnitStatus
    status: InventoryLineStatus
    expected_location_code: str | None
    actual_location_code: str | None
    scanned_at: datetime | None
    resolution_action: str | None
    resolution_actor: str | None
    resolution_reason: str | None
    resolved_at: datetime | None


class LogisticInventoryRead(BaseModel):
    id: int
    inventory_uid: str
    warehouse_id: int
    warehouse_code: str
    scope_type: str
    scope_parameters: dict[str, Any]
    current_location_id: int | None
    current_location_code: str | None
    status: InventoryStatus
    actor: str
    created_at: datetime
    completed_at: datetime | None
    total_locations: int
    checked_locations: int
    unchecked_locations: int
    progress_percent: float
    expected_count: int
    scanned_count: int
    missing_count: int
    extra_count: int
    wrong_location_count: int
    unresolved_problem_count: int
    locations: list[LogisticInventoryLocationRead]
    lines: list[LogisticInventoryLineRead]


class LogisticTaskCreate(BaseModel):
    warehouse_code: str = Field(min_length=1, max_length=32)
    task_type: TaskType
    priority: TaskPriority = TaskPriority.NORMAL
    title: str | None = Field(default=None, max_length=200)
    description: str | None = Field(default=None, max_length=500)
    object_uid: str = Field(min_length=1, max_length=120)
    parameters: dict[str, Any] = Field(default_factory=dict)
    assigned_to: str | None = Field(default=None, max_length=80)
    actor: str = Field(default="system", min_length=1, max_length=80)


class LogisticTaskRead(BaseModel):
    id: int
    task_uid: str
    warehouse_id: int
    warehouse_code: str
    warehouse_name: str
    task_type: TaskType
    status: TaskStatus
    priority: TaskPriority
    title: str
    description: str | None
    object_type: str
    object_uid: str
    object_status: str | None
    object_url: str
    parameters: dict[str, Any]
    assigned_to: str | None
    created_by: str
    created_at: datetime
    started_at: datetime | None
    completed_at: datetime | None


class TaskActionRequest(BaseModel):
    actor: str = "system"


class TaskAssignRequest(BaseModel):
    assigned_to: str | None = Field(default=None, max_length=80)
    actor: str = "system"


class TaskSyncRequest(BaseModel):
    warehouse_code: str = Field(min_length=1, max_length=32)
    actor: str = "system"
