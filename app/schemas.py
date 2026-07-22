from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.core.constants import DEFAULT_UNIT, DEFAULT_WAREHOUSE_CODE, DEFAULT_WAREHOUSE_NAME
from app.models.enums import (
    BoxStatus,
    InventoryLineStatus,
    InventoryStatus,
    LocationKind,
    PalletStatus,
    ShipmentStatus,
    TransferStatus,
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


class ProductCreate(BaseModel):
    code: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=240)
    unit: str = DEFAULT_UNIT
    quantity_per_box: int = Field(default=1, ge=1)
    boxes_per_pallet: int = Field(default=1, ge=1)
    shelf_life_days: int | None = Field(default=None, ge=1)


class ProductRead(ProductCreate):
    id: int
    is_active: bool

    model_config = ConfigDict(from_attributes=True)


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


class LocationCreate(BaseModel):
    warehouse_id: int
    zone_id: int
    code: str = Field(min_length=1, max_length=120)
    name: str | None = None
    kind: LocationKind = LocationKind.STORAGE
    capacity_pallets: int = Field(default=1, ge=1)


class LocationRead(LocationCreate):
    id: int
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


class BoxRead(BaseModel):
    id: int
    box_uid: str
    product_id: int
    batch_id: int
    status: BoxStatus
    current_pallet_id: int | None
    created_at: datetime
    accepted_at: datetime | None

    model_config = ConfigDict(from_attributes=True)


class GenerateBoxesRequest(BaseModel):
    batch_id: int
    quantity: int = Field(ge=1, le=10000)
    actor: str = "system"


class DemoCatalogRequest(BaseModel):
    warehouse_code: str = Field(default=DEFAULT_WAREHOUSE_CODE, min_length=1, max_length=32)
    warehouse_name: str = Field(default=DEFAULT_WAREHOUSE_NAME, min_length=1, max_length=160)
    storage_locations: int = Field(default=10, ge=1, le=80)
    actor: str = "demo-generator"


class DemoPalletsRequest(BaseModel):
    batch_id: int | None = None
    quantity: int = Field(default=5, ge=1, le=50)
    boxes_per_pallet: int = Field(default=4, ge=1, le=40)
    place_to_empty_locations: bool = True
    actor: str = "demo-generator"


class DemoGenerateRead(BaseModel):
    created_products: int = 0
    created_batches: int = 0
    created_warehouses: int = 0
    created_zones: int = 0
    created_locations: int = 0
    created_boxes: int = 0
    created_pallets: int = 0
    placed_pallets: int = 0
    waiting_pallets: int = 0
    product_ids: list[int] = []
    batch_ids: list[int] = []
    pallet_uids: list[str] = []


class PalletRead(BaseModel):
    id: int
    pallet_uid: str
    product_id: int | None
    batch_id: int | None
    status: PalletStatus
    current_location_id: int | None
    is_mixed: bool
    created_at: datetime
    closed_at: datetime | None

    model_config = ConfigDict(from_attributes=True)


class PalletSummaryRead(BaseModel):
    id: int
    pallet_uid: str
    product_id: int | None
    batch_id: int | None
    status: PalletStatus
    current_location_id: int | None
    current_location_code: str | None
    box_count: int
    created_at: datetime
    closed_at: datetime | None


class PalletActionRequest(BaseModel):
    actor: str = "system"
    reason: str | None = None


class PalletStatusRequest(PalletActionRequest):
    reason: str


class PlacePalletRequest(PalletActionRequest):
    location_code: str = Field(min_length=1, max_length=120)


class BoxTraceRead(BaseModel):
    box: BoxRead
    pallet: PalletSummaryRead | None
    location_code: str | None


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


class ShipmentCreate(BaseModel):
    customer_name: str = Field(default="Демо-клиент", min_length=1, max_length=160)
    destination: str = Field(default="Тестовая точка доставки", min_length=1, max_length=160)
    planned_date: date | None = None
    actor: str = "system"


class ShipmentRead(BaseModel):
    id: int
    shipment_uid: str
    customer_name: str
    destination: str
    status: ShipmentStatus
    planned_date: date | None
    created_at: datetime
    closed_at: datetime | None

    model_config = ConfigDict(from_attributes=True)


class ShipmentSummaryRead(ShipmentRead):
    pallet_count: int
    loaded_count: int


class ShipmentPalletRead(BaseModel):
    pallet: PalletSummaryRead
    shipment_pallet_status: str
    reserved_at: datetime
    moved_to_expedition_at: datetime | None
    loaded_at: datetime | None


class ShipmentActionRequest(BaseModel):
    actor: str = "system"
    reason: str | None = None


class TransferCreate(BaseModel):
    source_warehouse_code: str = Field(min_length=1, max_length=32)
    destination_warehouse_code: str = Field(min_length=1, max_length=32)
    planned_date: date | None = None
    vehicle_number: str | None = Field(default=None, max_length=80)
    actor: str = "system"


class TransferActionRequest(BaseModel):
    actor: str = "system"
    reason: str | None = None


class TransferRead(BaseModel):
    id: int
    transfer_uid: str
    source_warehouse_id: int
    source_warehouse_code: str
    source_warehouse_name: str
    destination_warehouse_id: int
    destination_warehouse_code: str
    destination_warehouse_name: str
    status: TransferStatus
    planned_date: date | None
    vehicle_number: str | None
    created_at: datetime
    dispatched_at: datetime | None
    completed_at: datetime | None
    pallet_count: int
    loaded_count: int
    received_count: int


class TransferPalletRead(BaseModel):
    pallet: PalletSummaryRead
    transfer_pallet_status: str
    source_location_code: str | None
    reserved_at: datetime
    moved_to_expedition_at: datetime | None
    loaded_at: datetime | None
    received_at: datetime | None


class InventoryStartRequest(BaseModel):
    warehouse_code: str | None = Field(default=None, max_length=32)
    location_code: str | None = Field(default=None, max_length=120)
    actor: str = "system"


class InventoryLocationScanRequest(BaseModel):
    location_code: str = Field(min_length=1, max_length=120)
    actor: str = "system"


class InventoryScanRequest(BaseModel):
    pallet_uid: str = Field(min_length=1, max_length=40)
    actor: str = "system"


class InventoryResolveRequest(BaseModel):
    actor: str = "system"
    reason: str | None = None


class InventoryRead(BaseModel):
    id: int
    inventory_uid: str
    warehouse_id: int | None
    warehouse_code: str | None
    location_id: int | None
    location_code: str | None
    current_location_id: int | None
    current_location_code: str | None
    status: InventoryStatus
    actor: str
    created_at: datetime
    completed_at: datetime | None
    expected_count: int
    scanned_count: int
    missing_count: int
    extra_count: int
    wrong_location_count: int


class InventoryLineRead(BaseModel):
    line_id: int
    pallet: PalletSummaryRead
    status: InventoryLineStatus
    expected_location_code: str | None
    actual_location_code: str | None
    scanned_at: datetime | None
    resolution_action: str | None = None
    resolution_actor: str | None = None
    resolved_at: datetime | None = None


class InventoryProgressLocationRead(BaseModel):
    location_id: int
    location_code: str
    status: str
    expected_count: int
    scanned_count: int
    problem_count: int


class InventoryProgressRead(BaseModel):
    inventory_uid: str
    warehouse_code: str | None
    total_locations: int
    checked_locations: int
    unchecked_locations: int
    progress_percent: float
    unchecked_locations_list: list[InventoryProgressLocationRead]
    unchecked_pallets: list[PalletSummaryRead]
    problem_lines: list[InventoryLineRead]
