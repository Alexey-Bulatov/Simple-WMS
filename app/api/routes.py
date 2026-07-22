from fastapi import APIRouter, Depends, File, Query, Response, UploadFile
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.constants import (
    BOX_CODE_PREFIX,
    DEFAULT_WAREHOUSE_CODE,
    INVENTORY_CODE_PREFIX,
    PALLET_CODE_PREFIX,
    SHIPMENT_CODE_PREFIX,
)
from app.db.session import get_db
from app.labels import LabelItem, build_labels_pdf
from app.imports import apply_import, parse_import_file, validate_import_rows
from app.models.entities import (
    Batch,
    Box,
    InventoryLine,
    InventorySession,
    Location,
    OperationEvent,
    Pallet,
    PalletBox,
    Product,
    Shipment,
    ShipmentPallet,
    User,
    Warehouse,
    WarehouseTransfer,
    WarehouseTransferPallet,
    Zone,
)
from app.schemas import (
    BatchCreate,
    BatchRead,
    BoxRead,
    BoxTraceRead,
    DemoCatalogRequest,
    DemoGenerateRead,
    DemoPalletsRequest,
    EventRead,
    GenerateBoxesRequest,
    InventoryLineRead,
    InventoryProgressRead,
    InventoryLocationScanRequest,
    InventoryRead,
    InventoryResolveRequest,
    InventoryScanRequest,
    InventoryStartRequest,
    LocationCreate,
    LocationRead,
    PalletActionRequest,
    PalletRead,
    PalletSummaryRead,
    PalletStatusRequest,
    PlacePalletRequest,
    ProductCreate,
    ProductRead,
    ShipmentActionRequest,
    ShipmentCreate,
    ShipmentPalletRead,
    ShipmentRead,
    ShipmentSummaryRead,
    TransferActionRequest,
    TransferCreate,
    TransferPalletRead,
    TransferRead,
    UserCreate,
    UserRead,
    WarehouseCreate,
    WarehouseMapActionRequest,
    WarehouseMapItemUpdate,
    WarehouseMapLabelCreate,
    WarehouseMapLocationCreate,
    WarehouseMapRowCreate,
    WarehouseRead,
    ZoneCreate,
    ZoneRead,
)
from app.services import (
    accept_box,
    add_box_to_pallet,
    close_pallet,
    close_shipment,
    complete_inventory,
    confirm_inventory_missing,
    confirm_inventory_location,
    confirmed_inventory_location_codes,
    create_batch,
    create_location,
    create_product,
    create_shipment,
    create_user,
    create_warehouse,
    create_zone,
    ensure_demo_catalog,
    generate_boxes,
    generate_demo_pallets,
    load_shipment_pallet,
    move_pallet,
    move_inventory_pallet_to_actual,
    move_shipment_to_expedition,
    not_found,
    open_pallet,
    place_pallet,
    place_inventory_found_pallet,
    release_pallet,
    reopen_pallet,
    reserve_pallet_for_shipment,
    scan_inventory_pallet,
    scan_inventory_location,
    set_pallet_problem_status,
    start_inventory,
    inventory_scope_locations,
    inventory_line_resolution_event,
    resolved_inventory_line_ids,
)
from app.models.enums import InventoryLineStatus, LocationKind, PalletStatus
from app.warehouse_map import (
    create_map_label,
    create_map_location,
    create_map_row,
    delete_map_item,
    ensure_demo_maps,
    reset_sandbox_map,
    update_map_item,
    warehouse_map_payload,
)
from app.transfers import (
    create_transfer,
    dispatch_transfer,
    get_transfer,
    load_transfer_pallet,
    move_transfer_to_expedition,
    receive_transfer_pallet,
    reserve_pallet_for_transfer,
    transfer_links,
)

router = APIRouter(prefix="/api")

PALLET_STATUS_LABELS = {
    "open": "Открыта",
    "closed": "Закрыта",
    "waiting_placement": "Ожидает размещения",
    "available": "Доступна",
    "reserved": "В резерве",
    "picking": "Отбор",
    "expedition": "В экспедиции",
    "loaded": "Погружена",
    "in_transit": "В пути",
    "quarantine": "Карантин",
    "blocked": "Заблокирована",
    "disassembled": "Расформирована",
    "written_off": "Списана",
    "shipped": "Отгружена",
}
BOX_STATUS_LABELS = {
    "label_created": "Этикетка создана",
    "accepted_from_production": "Принята от производства",
    "in_open_pallet": "В открытой палете",
    "in_closed_pallet": "В закрытой палете",
    "blocked": "Заблокирована",
    "quarantine": "Карантин",
    "damaged": "Повреждена",
    "written_off": "Списана",
    "shipped": "Отгружена",
}
LOCATION_KIND_LABELS = {
    "receiving": "Приемка",
    "storage": "Хранение",
    "quarantine": "Карантин",
    "discrepancy": "Расхождения",
    "expedition": "Экспедиция",
    "transfer_out": "Перемещение исходящее",
    "transfer_in": "Перемещение входящее",
    "scrap": "Списание",
}


def label(mapping: dict[str, str], value: object) -> str:
    return mapping.get(str(value), str(value))


def query_values(values: list[str] | None) -> list[str]:
    if not values:
        return []
    result = []
    for value in values:
        result.extend(part.strip() for part in value.replace(",", " ").split() if part.strip())
    return result


@router.get("/meta/constants")
def api_constants() -> dict:
    return {
        "box_code_prefix": BOX_CODE_PREFIX,
        "pallet_code_prefix": PALLET_CODE_PREFIX,
        "shipment_code_prefix": SHIPMENT_CODE_PREFIX,
        "inventory_code_prefix": INVENTORY_CODE_PREFIX,
        "default_warehouse_code": DEFAULT_WAREHOUSE_CODE,
    }


@router.post("/maps/setup")
def api_setup_maps(payload: WarehouseMapActionRequest, db: Session = Depends(get_db)) -> list[dict]:
    return ensure_demo_maps(db, actor=payload.actor)


@router.get("/maps/{warehouse_code}")
def api_warehouse_map(warehouse_code: str, db: Session = Depends(get_db)) -> dict:
    return warehouse_map_payload(db, warehouse_code)


@router.post("/maps/{warehouse_code}/rows")
def api_create_map_row(
    warehouse_code: str,
    payload: WarehouseMapRowCreate,
    db: Session = Depends(get_db),
) -> dict:
    return create_map_row(db, warehouse_code, payload)


@router.post("/maps/{warehouse_code}/locations")
def api_create_map_location(
    warehouse_code: str,
    payload: WarehouseMapLocationCreate,
    db: Session = Depends(get_db),
) -> dict:
    return create_map_location(db, warehouse_code, payload)


@router.post("/maps/{warehouse_code}/labels")
def api_create_map_label(
    warehouse_code: str,
    payload: WarehouseMapLabelCreate,
    db: Session = Depends(get_db),
) -> dict:
    return create_map_label(db, warehouse_code, payload)


@router.post("/maps/{warehouse_code}/items/{item_id}")
def api_update_map_item(
    warehouse_code: str,
    item_id: int,
    payload: WarehouseMapItemUpdate,
    db: Session = Depends(get_db),
) -> dict:
    return update_map_item(db, warehouse_code, item_id, payload)


@router.post("/maps/{warehouse_code}/items/{item_id}/delete")
def api_delete_map_item(
    warehouse_code: str,
    item_id: int,
    payload: WarehouseMapActionRequest,
    db: Session = Depends(get_db),
) -> dict:
    return delete_map_item(db, warehouse_code, item_id, actor=payload.actor)


@router.post("/maps/{warehouse_code}/reset")
def api_reset_map(
    warehouse_code: str,
    payload: WarehouseMapActionRequest,
    db: Session = Depends(get_db),
) -> dict:
    return reset_sandbox_map(db, warehouse_code, actor=payload.actor)


def pallet_summary(db: Session, pallet: Pallet) -> dict:
    location_code = None
    if pallet.current_location_id:
        location_code = db.scalar(select(Location.code).where(Location.id == pallet.current_location_id))
    box_count = db.scalar(select(func.count(Box.id)).where(Box.current_pallet_id == pallet.id)) or 0
    return {
        "id": pallet.id,
        "pallet_uid": pallet.pallet_uid,
        "product_id": pallet.product_id,
        "batch_id": pallet.batch_id,
        "status": pallet.status,
        "current_location_id": pallet.current_location_id,
        "current_location_code": location_code,
        "box_count": box_count,
        "created_at": pallet.created_at,
        "closed_at": pallet.closed_at,
    }


def product_payload(product: Product | None) -> dict | None:
    if product is None:
        return None
    return {
        "id": product.id,
        "code": product.code,
        "name": product.name,
        "unit": product.unit,
        "quantity_per_box": product.quantity_per_box,
        "boxes_per_pallet": product.boxes_per_pallet,
        "shelf_life_days": product.shelf_life_days,
        "is_active": product.is_active,
    }


def batch_payload(db: Session, batch: Batch | None) -> dict | None:
    if batch is None:
        return None
    return {
        "id": batch.id,
        "batch_number": batch.batch_number,
        "product_id": batch.product_id,
        "product_code": db.scalar(select(Product.code).where(Product.id == batch.product_id)),
        "production_date": batch.production_date,
        "expiry_date": batch.expiry_date,
        "quality_status": batch.quality_status,
        "operation_status": batch.operation_status,
    }


def location_payload(db: Session, location: Location | None) -> dict | None:
    if location is None:
        return None
    warehouse = db.get(Warehouse, location.warehouse_id)
    zone = db.get(Zone, location.zone_id)
    occupied = db.scalar(select(func.count(Pallet.id)).where(Pallet.current_location_id == location.id)) or 0
    return {
        "id": location.id,
        "code": location.code,
        "name": location.name,
        "kind": location.kind,
        "kind_label": label(LOCATION_KIND_LABELS, location.kind),
        "capacity_pallets": location.capacity_pallets,
        "occupied_pallets": occupied,
        "free_pallet_slots": max(location.capacity_pallets - occupied, 0),
        "is_active": location.is_active,
        "warehouse": {
            "id": warehouse.id,
            "code": warehouse.code,
            "name": warehouse.name,
        } if warehouse else None,
        "zone": {
            "id": zone.id,
            "code": zone.code,
            "name": zone.name,
            "kind": zone.kind,
        } if zone else None,
    }


def event_payload(event: OperationEvent) -> dict:
    return {
        "id": event.id,
        "operation": event.operation,
        "object_type": event.object_type,
        "object_uid": event.object_uid,
        "actor": event.actor,
        "reason": event.reason,
        "before": event.before,
        "after": event.after,
        "created_at": event.created_at,
    }


def object_events(db: Session, *, object_type: str, object_uid: str, limit: int = 100) -> list[dict]:
    events = db.scalars(
        select(OperationEvent)
        .where(OperationEvent.object_type == object_type, OperationEvent.object_uid == object_uid)
        .order_by(OperationEvent.created_at.desc())
        .limit(limit)
    )
    return [event_payload(event) for event in events]


def shipment_summary(db: Session, shipment: Shipment) -> dict:
    pallet_count = db.scalar(select(func.count(ShipmentPallet.id)).where(ShipmentPallet.shipment_id == shipment.id)) or 0
    loaded_count = (
        db.scalar(
            select(func.count(ShipmentPallet.id)).where(
                ShipmentPallet.shipment_id == shipment.id,
                ShipmentPallet.status == "loaded",
            )
        )
        or 0
    )
    return {
        "id": shipment.id,
        "shipment_uid": shipment.shipment_uid,
        "customer_name": shipment.customer_name,
        "destination": shipment.destination,
        "status": shipment.status,
        "planned_date": shipment.planned_date,
        "created_at": shipment.created_at,
        "closed_at": shipment.closed_at,
        "pallet_count": pallet_count,
        "loaded_count": loaded_count,
    }


def transfer_summary(db: Session, transfer: WarehouseTransfer) -> dict:
    source = db.get(Warehouse, transfer.source_warehouse_id)
    destination = db.get(Warehouse, transfer.destination_warehouse_id)
    links = transfer_links(db, transfer.id)
    return {
        "id": transfer.id,
        "transfer_uid": transfer.transfer_uid,
        "source_warehouse_id": transfer.source_warehouse_id,
        "source_warehouse_code": source.code if source else "-",
        "source_warehouse_name": source.name if source else "-",
        "destination_warehouse_id": transfer.destination_warehouse_id,
        "destination_warehouse_code": destination.code if destination else "-",
        "destination_warehouse_name": destination.name if destination else "-",
        "status": transfer.status,
        "planned_date": transfer.planned_date,
        "vehicle_number": transfer.vehicle_number,
        "created_at": transfer.created_at,
        "dispatched_at": transfer.dispatched_at,
        "completed_at": transfer.completed_at,
        "pallet_count": len(links),
        "loaded_count": sum(1 for link in links if link.status in {"loaded", "in_transit", "received"}),
        "received_count": sum(1 for link in links if link.status == "received"),
    }


def location_code(db: Session, location_id: int | None) -> str | None:
    if location_id is None:
        return None
    return db.scalar(select(Location.code).where(Location.id == location_id))


def warehouse_code(db: Session, warehouse_id: int | None) -> str | None:
    if warehouse_id is None:
        return None
    return db.scalar(select(Warehouse.code).where(Warehouse.id == warehouse_id))


def product_name(db: Session, product_id: int | None) -> str:
    if product_id is None:
        return "-"
    product = db.get(Product, product_id)
    return product.name if product else "-"


def batch_number(db: Session, batch_id: int | None) -> str:
    if batch_id is None:
        return "-"
    batch = db.get(Batch, batch_id)
    return batch.batch_number if batch else "-"


def pdf_response(content: bytes, filename: str) -> Response:
    return Response(
        content=content,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{filename}"'},
    )


def box_label_item(db: Session, box: Box) -> LabelItem:
    batch = db.get(Batch, box.batch_id)
    expiry = batch.expiry_date.isoformat() if batch else "-"
    return LabelItem(
        object_type="Коробка",
        code=box.box_uid,
        title=product_name(db, box.product_id),
        lines=(
            f"Партия: {batch_number(db, box.batch_id)}",
            f"Срок годности: {expiry}",
            f"Статус: {label(BOX_STATUS_LABELS, box.status)}",
        ),
    )


def pallet_label_item(db: Session, pallet: Pallet) -> LabelItem:
    box_count = db.scalar(select(func.count(Box.id)).where(Box.current_pallet_id == pallet.id)) or 0
    return LabelItem(
        object_type="Палета",
        code=pallet.pallet_uid,
        title=product_name(db, pallet.product_id),
        lines=(
            f"Партия: {batch_number(db, pallet.batch_id)}",
            f"Коробок: {box_count}",
            f"Ячейка: {location_code(db, pallet.current_location_id) or '-'}",
            f"Статус: {label(PALLET_STATUS_LABELS, pallet.status)}",
        ),
    )


def location_label_item(location: Location) -> LabelItem:
    return LabelItem(
        object_type="Ячейка",
        code=location.code,
        title=location.name or "Адрес хранения",
        lines=(
            f"Тип: {label(LOCATION_KIND_LABELS, location.kind)}",
            f"Вместимость, палет: {location.capacity_pallets}",
        ),
    )


def inventory_summary(db: Session, inventory: InventorySession) -> dict:
    lines = list(db.scalars(select(InventoryLine).where(InventoryLine.inventory_id == inventory.id)))
    return {
        "id": inventory.id,
        "inventory_uid": inventory.inventory_uid,
        "warehouse_id": inventory.warehouse_id,
        "warehouse_code": warehouse_code(db, inventory.warehouse_id),
        "location_id": inventory.location_id,
        "location_code": location_code(db, inventory.location_id),
        "current_location_id": inventory.current_location_id,
        "current_location_code": location_code(db, inventory.current_location_id),
        "status": inventory.status,
        "actor": inventory.actor,
        "created_at": inventory.created_at,
        "completed_at": inventory.completed_at,
        "expected_count": sum(1 for line in lines if line.expected_location_id is not None),
        "scanned_count": sum(1 for line in lines if line.status == InventoryLineStatus.SCANNED),
        "missing_count": sum(1 for line in lines if line.status == InventoryLineStatus.MISSING),
        "extra_count": sum(1 for line in lines if line.status == InventoryLineStatus.EXTRA),
        "wrong_location_count": sum(1 for line in lines if line.status == InventoryLineStatus.WRONG_LOCATION),
    }


def inventory_line_payload(db: Session, line: InventoryLine) -> dict | None:
    pallet = db.get(Pallet, line.pallet_id)
    if pallet is None:
        return None
    inventory = db.get(InventorySession, line.inventory_id)
    resolution_event = inventory_line_resolution_event(db, inventory, line) if inventory else None
    resolution_after = resolution_event.after if resolution_event else {}
    return {
        "line_id": line.id,
        "pallet": pallet_summary(db, pallet),
        "status": line.status,
        "expected_location_code": location_code(db, line.expected_location_id),
        "actual_location_code": location_code(db, line.actual_location_id),
        "scanned_at": line.scanned_at,
        "resolution_action": resolution_after.get("action") if resolution_after else None,
        "resolution_actor": resolution_event.actor if resolution_event else None,
        "resolved_at": resolution_event.created_at if resolution_event else None,
    }


def inventory_progress(db: Session, inventory: InventorySession) -> dict:
    warehouse_id = inventory.warehouse_id
    if warehouse_id is None and inventory.location_id:
        warehouse_id = db.scalar(select(Location.warehouse_id).where(Location.id == inventory.location_id))
    locations = inventory_scope_locations(db, inventory)
    lines = list(db.scalars(select(InventoryLine).where(InventoryLine.inventory_id == inventory.id)))
    confirmed_locations = confirmed_inventory_location_codes(db, inventory)
    resolved_line_ids = resolved_inventory_line_ids(db, inventory)
    location_rows = []
    checked_count = 0
    problem_statuses = {
        InventoryLineStatus.MISSING,
        InventoryLineStatus.EXTRA,
        InventoryLineStatus.WRONG_LOCATION,
    }
    for location in locations:
        expected = [line for line in lines if line.expected_location_id == location.id]
        actual = [line for line in lines if line.actual_location_id == location.id]
        problems = [
            line
            for line in lines
            if line.id not in resolved_line_ids
            and (line.expected_location_id == location.id or line.actual_location_id == location.id)
            and line.status in problem_statuses
        ]
        checked = (
            location.code in confirmed_locations
            or bool(actual)
            or any(line.status in {InventoryLineStatus.SCANNED, InventoryLineStatus.MISSING} for line in expected)
        )
        if checked:
            checked_count += 1
        status_text = "problem" if problems else ("checked" if checked else "unchecked")
        location_rows.append(
            {
                "location_id": location.id,
                "location_code": location.code,
                "status": status_text,
                "expected_count": len(expected),
                "scanned_count": sum(1 for line in actual if line.status == InventoryLineStatus.SCANNED),
                "problem_count": len(problems),
            }
        )
    unchecked_pallets = []
    for line in lines:
        if line.expected_location_id is not None and line.status == InventoryLineStatus.EXPECTED:
            pallet = db.get(Pallet, line.pallet_id)
            if pallet:
                unchecked_pallets.append(pallet_summary(db, pallet))
    problem_lines = []
    for line in lines:
        if line.status in problem_statuses and line.id not in resolved_line_ids:
            payload = inventory_line_payload(db, line)
            if payload:
                problem_lines.append(payload)
    total = len(locations)
    return {
        "inventory_uid": inventory.inventory_uid,
        "warehouse_code": warehouse_code(db, warehouse_id),
        "total_locations": total,
        "checked_locations": checked_count,
        "unchecked_locations": max(total - checked_count, 0),
        "progress_percent": round((checked_count / total * 100) if total else 0, 1),
        "unchecked_locations_list": [row for row in location_rows if row["status"] == "unchecked"],
        "unchecked_pallets": unchecked_pallets,
        "problem_lines": problem_lines,
    }


@router.post("/users", response_model=UserRead)
def api_create_user(payload: UserCreate, db: Session = Depends(get_db)) -> User:
    return create_user(db, payload)


@router.get("/users", response_model=list[UserRead])
def api_list_users(db: Session = Depends(get_db)) -> list[User]:
    return list(db.scalars(select(User).order_by(User.username)))


@router.post("/products", response_model=ProductRead)
def api_create_product(payload: ProductCreate, db: Session = Depends(get_db)) -> Product:
    return create_product(db, payload)


@router.get("/products", response_model=list[ProductRead])
def api_list_products(db: Session = Depends(get_db)) -> list[Product]:
    return list(db.scalars(select(Product).order_by(Product.code)))


@router.post("/batches", response_model=BatchRead)
def api_create_batch(payload: BatchCreate, db: Session = Depends(get_db)) -> Batch:
    return create_batch(db, payload)


@router.get("/batches", response_model=list[BatchRead])
def api_list_batches(db: Session = Depends(get_db)) -> list[Batch]:
    return list(db.scalars(select(Batch).order_by(Batch.batch_number)))


@router.post("/warehouses", response_model=WarehouseRead)
def api_create_warehouse(payload: WarehouseCreate, db: Session = Depends(get_db)) -> Warehouse:
    return create_warehouse(db, payload)


@router.get("/warehouses", response_model=list[WarehouseRead])
def api_list_warehouses(db: Session = Depends(get_db)) -> list[Warehouse]:
    return list(db.scalars(select(Warehouse).order_by(Warehouse.code)))


@router.post("/zones", response_model=ZoneRead)
def api_create_zone(payload: ZoneCreate, db: Session = Depends(get_db)) -> Zone:
    return create_zone(db, payload)


@router.get("/zones", response_model=list[ZoneRead])
def api_list_zones(db: Session = Depends(get_db)) -> list[Zone]:
    return list(db.scalars(select(Zone).order_by(Zone.code)))


@router.post("/locations", response_model=LocationRead)
def api_create_location(payload: LocationCreate, db: Session = Depends(get_db)) -> Location:
    return create_location(db, payload)


@router.get("/locations", response_model=list[LocationRead])
def api_list_locations(db: Session = Depends(get_db)) -> list[Location]:
    return list(db.scalars(select(Location).order_by(Location.code)))


@router.get("/inventory-locations", response_model=list[LocationRead])
def api_list_inventory_locations(db: Session = Depends(get_db)) -> list[Location]:
    return list(
        db.scalars(
            select(Location)
            .where(Location.kind == LocationKind.STORAGE, Location.is_active.is_(True))
            .order_by(Location.code)
        )
    )


@router.get("/locations/{location_code}/label.pdf")
def api_location_label(location_code: str, db: Session = Depends(get_db)) -> Response:
    location = db.scalar(select(Location).where(Location.code == location_code))
    if location is None:
        raise not_found("location")
    content = build_labels_pdf([location_label_item(location)], title=f"Этикетка ячейки {location.code}")
    return pdf_response(content, f"location-{location.code}.pdf")


@router.get("/labels/locations.pdf")
def api_location_labels(
    warehouse_code_filter: str | None = Query(default=None, alias="warehouse_code"),
    location_code_filter: list[str] | None = Query(default=None, alias="location_code"),
    kind_filter: list[str] | None = Query(default=None, alias="kind"),
    storage_only: bool = True,
    limit: int = Query(default=200, ge=1, le=400),
    db: Session = Depends(get_db),
) -> Response:
    stmt = select(Location).order_by(Location.code).limit(limit)
    location_codes = query_values(location_code_filter)
    kind_values = query_values(kind_filter)
    if location_codes:
        stmt = stmt.where(Location.code.in_(location_codes))
    if warehouse_code_filter:
        warehouse = db.scalar(select(Warehouse).where(Warehouse.code == warehouse_code_filter))
        if warehouse is None:
            raise not_found("warehouse")
        stmt = stmt.where(Location.warehouse_id == warehouse.id)
    if kind_values:
        try:
            kinds = [LocationKind(value) for value in kind_values]
        except ValueError as exc:
            raise bad_request("unknown location kind") from exc
        stmt = stmt.where(Location.kind.in_(kinds))
    if storage_only:
        stmt = stmt.where(Location.kind == LocationKind.STORAGE, Location.is_active.is_(True))
    locations = list(db.scalars(stmt))
    content = build_labels_pdf([location_label_item(location) for location in locations], title="Этикетки ячеек")
    return pdf_response(content, "location-labels.pdf")


@router.post("/demo/catalog", response_model=DemoGenerateRead)
def api_generate_demo_catalog(payload: DemoCatalogRequest, db: Session = Depends(get_db)) -> dict:
    return ensure_demo_catalog(db, payload)


@router.post("/demo/pallets", response_model=DemoGenerateRead)
def api_generate_demo_pallets(payload: DemoPalletsRequest, db: Session = Depends(get_db)) -> dict:
    return generate_demo_pallets(db, payload)


@router.post("/import/preview/{kind}")
async def api_import_preview(kind: str, file: UploadFile = File(...), db: Session = Depends(get_db)) -> dict:
    rows = parse_import_file(file.filename or "import.csv", await file.read())
    preview = validate_import_rows(kind, rows, db)
    return {**preview, "rows": preview["rows"][:50]}


@router.post("/import/apply/{kind}")
async def api_import_apply(kind: str, file: UploadFile = File(...), db: Session = Depends(get_db)) -> dict:
    rows = parse_import_file(file.filename or "import.csv", await file.read())
    result = apply_import(kind, rows, db)
    return {**result, "rows": result["rows"][:50]}


@router.post("/boxes/generate", response_model=list[BoxRead])
def api_generate_boxes(payload: GenerateBoxesRequest, db: Session = Depends(get_db)) -> list[Box]:
    return generate_boxes(db, batch_id=payload.batch_id, quantity=payload.quantity, actor=payload.actor)


@router.get("/boxes/{box_uid}", response_model=BoxRead)
def api_get_box(box_uid: str, db: Session = Depends(get_db)) -> Box:
    box = db.scalar(select(Box).where(Box.box_uid == box_uid))
    if box is None:
        raise not_found("box")
    return box


@router.get("/boxes/{box_uid}/trace", response_model=BoxTraceRead)
def api_trace_box(box_uid: str, db: Session = Depends(get_db)) -> dict:
    box = db.scalar(select(Box).where(Box.box_uid == box_uid))
    if box is None:
        raise not_found("box")
    pallet_data = None
    location_code = None
    if box.current_pallet_id:
        pallet = db.get(Pallet, box.current_pallet_id)
        if pallet:
            pallet_data = pallet_summary(db, pallet)
            location_code = pallet_data["current_location_code"]
    return {"box": box, "pallet": pallet_data, "location_code": location_code}


@router.get("/boxes/{box_uid}/label.pdf")
def api_box_label(box_uid: str, db: Session = Depends(get_db)) -> Response:
    box = db.scalar(select(Box).where(Box.box_uid == box_uid))
    if box is None:
        raise not_found("box")
    content = build_labels_pdf([box_label_item(db, box)], title=f"Этикетка коробки {box.box_uid}")
    return pdf_response(content, f"box-{box.box_uid}.pdf")


@router.get("/labels/boxes.pdf")
def api_box_labels(
    box_uid_filter: list[str] | None = Query(default=None, alias="box_uid"),
    status_filter: list[str] | None = Query(default=None, alias="status"),
    batch_id: int | None = None,
    product_id: int | None = None,
    limit: int = Query(default=80, ge=1, le=400),
    db: Session = Depends(get_db),
) -> Response:
    box_uids = query_values(box_uid_filter)
    statuses = query_values(status_filter)
    stmt = select(Box).order_by(Box.created_at.desc()).limit(limit)
    if box_uids:
        stmt = stmt.where(Box.box_uid.in_(box_uids))
    if statuses:
        stmt = stmt.where(Box.status.in_(statuses))
    if batch_id:
        stmt = stmt.where(Box.batch_id == batch_id)
    if product_id:
        stmt = stmt.where(Box.product_id == product_id)
    boxes = list(db.scalars(stmt))
    content = build_labels_pdf([box_label_item(db, box) for box in boxes], title="Этикетки коробок")
    return pdf_response(content, "box-labels.pdf")


@router.post("/boxes/{box_uid}/accept", response_model=BoxRead)
def api_accept_box(box_uid: str, payload: PalletActionRequest, db: Session = Depends(get_db)) -> Box:
    return accept_box(db, box_uid=box_uid, actor=payload.actor)


@router.post("/pallets", response_model=PalletRead)
def api_open_pallet(payload: PalletActionRequest, db: Session = Depends(get_db)) -> Pallet:
    return open_pallet(db, actor=payload.actor)


@router.get("/pallets", response_model=list[PalletSummaryRead])
def api_list_pallets(
    status_filter: list[str] | None = Query(default=None, alias="status"),
    warehouse_code_filter: str | None = Query(default=None, alias="warehouse_code"),
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
) -> list[dict]:
    stmt = (
        select(Pallet, Location.code, func.count(Box.id).label("box_count"))
        .outerjoin(Location, Pallet.current_location_id == Location.id)
        .outerjoin(Box, Box.current_pallet_id == Pallet.id)
        .group_by(Pallet.id, Location.code)
        .order_by(Pallet.created_at.desc())
        .limit(limit)
    )
    if status_filter:
        stmt = stmt.where(Pallet.status.in_(status_filter))
    if warehouse_code_filter:
        warehouse = db.scalar(select(Warehouse).where(Warehouse.code == warehouse_code_filter))
        if warehouse is None:
            raise not_found("warehouse")
        stmt = stmt.where(Location.warehouse_id == warehouse.id)
    rows = db.execute(stmt).all()
    return [
        {
            "id": pallet.id,
            "pallet_uid": pallet.pallet_uid,
            "product_id": pallet.product_id,
            "batch_id": pallet.batch_id,
            "status": pallet.status,
            "current_location_id": pallet.current_location_id,
            "current_location_code": location_code,
            "box_count": box_count,
            "created_at": pallet.created_at,
            "closed_at": pallet.closed_at,
        }
        for pallet, location_code, box_count in rows
    ]


@router.get("/pallets/{pallet_uid}", response_model=PalletRead)
def api_get_pallet(pallet_uid: str, db: Session = Depends(get_db)) -> Pallet:
    pallet = db.scalar(select(Pallet).where(Pallet.pallet_uid == pallet_uid))
    if pallet is None:
        raise not_found("pallet")
    return pallet


@router.get("/pallets/{pallet_uid}/boxes", response_model=list[BoxRead])
def api_get_pallet_boxes(pallet_uid: str, db: Session = Depends(get_db)) -> list[Box]:
    pallet = db.scalar(select(Pallet).where(Pallet.pallet_uid == pallet_uid))
    if pallet is None:
        raise not_found("pallet")
    return list(db.scalars(select(Box).where(Box.current_pallet_id == pallet.id).order_by(Box.box_uid)))


@router.get("/pallets/{pallet_uid}/label.pdf")
def api_pallet_label(pallet_uid: str, db: Session = Depends(get_db)) -> Response:
    pallet = db.scalar(select(Pallet).where(Pallet.pallet_uid == pallet_uid))
    if pallet is None:
        raise not_found("pallet")
    content = build_labels_pdf([pallet_label_item(db, pallet)], title=f"Этикетка палеты {pallet.pallet_uid}")
    return pdf_response(content, f"pallet-{pallet.pallet_uid}.pdf")


@router.get("/labels/pallets.pdf")
def api_pallet_labels(
    pallet_uid_filter: list[str] | None = Query(default=None, alias="pallet_uid"),
    status_filter: list[str] | None = Query(default=None, alias="status"),
    batch_id: int | None = None,
    product_id: int | None = None,
    location_code_filter: str | None = Query(default=None, alias="location_code"),
    limit: int = Query(default=80, ge=1, le=400),
    db: Session = Depends(get_db),
) -> Response:
    pallet_uids = query_values(pallet_uid_filter)
    statuses = query_values(status_filter)
    stmt = select(Pallet).order_by(Pallet.created_at.desc()).limit(limit)
    if pallet_uids:
        stmt = stmt.where(Pallet.pallet_uid.in_(pallet_uids))
    if statuses:
        stmt = stmt.where(Pallet.status.in_(statuses))
    if batch_id:
        stmt = stmt.where(Pallet.batch_id == batch_id)
    if product_id:
        stmt = stmt.where(Pallet.product_id == product_id)
    if location_code_filter:
        location = db.scalar(select(Location).where(Location.code == location_code_filter))
        if location is None:
            raise not_found("location")
        stmt = stmt.where(Pallet.current_location_id == location.id)
    pallets = list(db.scalars(stmt))
    content = build_labels_pdf([pallet_label_item(db, pallet) for pallet in pallets], title="Этикетки палет")
    return pdf_response(content, "pallet-labels.pdf")


@router.post("/pallets/{pallet_uid}/boxes/{box_uid}", response_model=PalletRead)
def api_add_box_to_pallet(
    pallet_uid: str,
    box_uid: str,
    payload: PalletActionRequest,
    db: Session = Depends(get_db),
) -> Pallet:
    return add_box_to_pallet(db, pallet_uid=pallet_uid, box_uid=box_uid, actor=payload.actor)


@router.post("/pallets/{pallet_uid}/close", response_model=PalletRead)
def api_close_pallet(pallet_uid: str, payload: PalletActionRequest, db: Session = Depends(get_db)) -> Pallet:
    return close_pallet(db, pallet_uid=pallet_uid, actor=payload.actor, reason=payload.reason)


@router.post("/pallets/{pallet_uid}/reopen", response_model=PalletRead)
def api_reopen_pallet(pallet_uid: str, payload: PalletStatusRequest, db: Session = Depends(get_db)) -> Pallet:
    return reopen_pallet(db, pallet_uid=pallet_uid, actor=payload.actor, reason=payload.reason)


@router.post("/pallets/{pallet_uid}/block", response_model=PalletRead)
def api_block_pallet(pallet_uid: str, payload: PalletStatusRequest, db: Session = Depends(get_db)) -> Pallet:
    return set_pallet_problem_status(
        db,
        pallet_uid=pallet_uid,
        target_status=PalletStatus.BLOCKED,
        actor=payload.actor,
        reason=payload.reason,
    )


@router.post("/pallets/{pallet_uid}/quarantine", response_model=PalletRead)
def api_quarantine_pallet(pallet_uid: str, payload: PalletStatusRequest, db: Session = Depends(get_db)) -> Pallet:
    return set_pallet_problem_status(
        db,
        pallet_uid=pallet_uid,
        target_status=PalletStatus.QUARANTINE,
        actor=payload.actor,
        reason=payload.reason,
    )


@router.post("/pallets/{pallet_uid}/release", response_model=PalletRead)
def api_release_pallet(pallet_uid: str, payload: PalletStatusRequest, db: Session = Depends(get_db)) -> Pallet:
    return release_pallet(db, pallet_uid=pallet_uid, actor=payload.actor, reason=payload.reason)


@router.post("/pallets/{pallet_uid}/place", response_model=PalletRead)
def api_place_pallet(pallet_uid: str, payload: PlacePalletRequest, db: Session = Depends(get_db)) -> Pallet:
    return place_pallet(
        db,
        pallet_uid=pallet_uid,
        location_code=payload.location_code,
        actor=payload.actor,
        reason=payload.reason,
    )


@router.post("/pallets/{pallet_uid}/move", response_model=PalletRead)
def api_move_pallet(pallet_uid: str, payload: PlacePalletRequest, db: Session = Depends(get_db)) -> Pallet:
    return move_pallet(
        db,
        pallet_uid=pallet_uid,
        location_code=payload.location_code,
        actor=payload.actor,
        reason=payload.reason,
    )


@router.get("/pallets/{pallet_uid}/events", response_model=list[EventRead])
def api_pallet_events(
    pallet_uid: str,
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
) -> list[OperationEvent]:
    pallet = db.scalar(select(Pallet).where(Pallet.pallet_uid == pallet_uid))
    if pallet is None:
        raise not_found("pallet")
    return list(
        db.scalars(
            select(OperationEvent)
            .where(OperationEvent.object_type == "pallet", OperationEvent.object_uid == pallet_uid)
            .order_by(OperationEvent.created_at.desc())
            .limit(limit)
        )
    )


@router.get("/events", response_model=list[EventRead])
def api_list_events(
    object_uid: str | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
) -> list[OperationEvent]:
    stmt = select(OperationEvent).order_by(OperationEvent.created_at.desc()).limit(limit)
    if object_uid:
        stmt = select(OperationEvent).where(OperationEvent.object_uid == object_uid).order_by(OperationEvent.created_at.desc()).limit(limit)
    return list(db.scalars(stmt))


@router.get("/cards/resolve/{code}")
def api_resolve_card(code: str, db: Session = Depends(get_db)) -> dict:
    normalized = code.strip()
    if db.scalar(select(Pallet.id).where(Pallet.pallet_uid == normalized)):
        return {"kind": "pallet", "code": normalized, "url": f"/cards?kind=pallet&code={normalized}"}
    if db.scalar(select(Box.id).where(Box.box_uid == normalized)):
        return {"kind": "box", "code": normalized, "url": f"/cards?kind=box&code={normalized}"}
    if db.scalar(select(Location.id).where(Location.code == normalized)):
        return {"kind": "location", "code": normalized, "url": f"/cards?kind=location&code={normalized}"}
    raise not_found("object")


@router.get("/cards/pallets/{pallet_uid}")
def api_pallet_card(pallet_uid: str, db: Session = Depends(get_db)) -> dict:
    pallet = db.scalar(select(Pallet).where(Pallet.pallet_uid == pallet_uid))
    if pallet is None:
        raise not_found("pallet")
    product = db.get(Product, pallet.product_id) if pallet.product_id else None
    batch = db.get(Batch, pallet.batch_id) if pallet.batch_id else None
    location = db.get(Location, pallet.current_location_id) if pallet.current_location_id else None
    box_rows = db.execute(
        select(Box, PalletBox.added_at)
        .join(PalletBox, PalletBox.box_id == Box.id)
        .where(PalletBox.pallet_id == pallet.id)
        .order_by(PalletBox.added_at.desc(), Box.box_uid)
    ).all()
    shipment_link = db.scalar(select(ShipmentPallet).where(ShipmentPallet.pallet_id == pallet.id))
    shipment = db.get(Shipment, shipment_link.shipment_id) if shipment_link else None
    return {
        "kind": "pallet",
        "pallet": {
            **pallet_summary(db, pallet),
            "status_label": label(PALLET_STATUS_LABELS, pallet.status),
            "product_code": product.code if product else None,
            "product_name": product.name if product else None,
            "batch_number": batch.batch_number if batch else None,
        },
        "product": product_payload(product),
        "batch": batch_payload(db, batch),
        "location": location_payload(db, location),
        "shipment": shipment_summary(db, shipment) if shipment else None,
        "boxes": [
            {
                "id": box.id,
                "box_uid": box.box_uid,
                "status": box.status,
                "status_label": label(BOX_STATUS_LABELS, box.status),
                "product_id": box.product_id,
                "batch_id": box.batch_id,
                "added_at": added_at,
                "accepted_at": box.accepted_at,
                "created_at": box.created_at,
            }
            for box, added_at in box_rows
        ],
        "events": object_events(db, object_type="pallet", object_uid=pallet.pallet_uid),
        "pdf_url": f"/api/pallets/{pallet.pallet_uid}/label.pdf",
    }


@router.get("/cards/boxes/{box_uid}")
def api_box_card(box_uid: str, db: Session = Depends(get_db)) -> dict:
    box = db.scalar(select(Box).where(Box.box_uid == box_uid))
    if box is None:
        raise not_found("box")
    product = db.get(Product, box.product_id)
    batch = db.get(Batch, box.batch_id)
    pallet = db.get(Pallet, box.current_pallet_id) if box.current_pallet_id else None
    pallet_data = pallet_summary(db, pallet) if pallet else None
    location = db.get(Location, pallet.current_location_id) if pallet and pallet.current_location_id else None
    events = object_events(db, object_type="box", object_uid=box.box_uid)
    if pallet:
        pallet_events = db.scalars(
            select(OperationEvent)
            .where(OperationEvent.object_type == "pallet", OperationEvent.object_uid == pallet.pallet_uid)
            .order_by(OperationEvent.created_at.desc())
            .limit(200)
        )
        for event in pallet_events:
            event_after = event.after or {}
            if event_after.get("box_uid") == box.box_uid:
                events.append(event_payload(event))
    events.sort(key=lambda event: event["created_at"], reverse=True)
    return {
        "kind": "box",
        "box": {
            "id": box.id,
            "box_uid": box.box_uid,
            "status": box.status,
            "status_label": label(BOX_STATUS_LABELS, box.status),
            "product_id": box.product_id,
            "batch_id": box.batch_id,
            "current_pallet_id": box.current_pallet_id,
            "created_at": box.created_at,
            "accepted_at": box.accepted_at,
        },
        "product": product_payload(product),
        "batch": batch_payload(db, batch),
        "pallet": {
            **pallet_data,
            "status_label": label(PALLET_STATUS_LABELS, pallet.status),
        } if pallet and pallet_data else None,
        "location": location_payload(db, location),
        "events": events[:100],
        "pdf_url": f"/api/boxes/{box.box_uid}/label.pdf",
    }


@router.get("/cards/locations/{location_code}")
def api_location_card(location_code: str, db: Session = Depends(get_db)) -> dict:
    location = db.scalar(select(Location).where(Location.code == location_code))
    if location is None:
        raise not_found("location")
    pallets = list(
        db.scalars(
            select(Pallet)
            .where(Pallet.current_location_id == location.id)
            .order_by(Pallet.created_at.desc())
        )
    )
    recent_events = db.scalars(select(OperationEvent).order_by(OperationEvent.created_at.desc()).limit(500))
    events = []
    for event in recent_events:
        before = event.before or {}
        after = event.after or {}
        if before.get("location_code") == location.code or after.get("location_code") == location.code:
            events.append(event_payload(event))
        if len(events) >= 100:
            break
    return {
        "kind": "location",
        "location": location_payload(db, location),
        "pallets": [
            {
                **pallet_summary(db, pallet),
                "status_label": label(PALLET_STATUS_LABELS, pallet.status),
                "product_name": product_name(db, pallet.product_id),
                "batch_number": batch_number(db, pallet.batch_id),
            }
            for pallet in pallets
        ],
        "events": events,
        "pdf_url": f"/api/locations/{location.code}/label.pdf",
    }


@router.post("/shipments", response_model=ShipmentRead)
def api_create_shipment(payload: ShipmentCreate, db: Session = Depends(get_db)) -> Shipment:
    return create_shipment(db, payload)


@router.get("/shipments", response_model=list[ShipmentSummaryRead])
def api_list_shipments(
    status_filter: list[str] | None = Query(default=None, alias="status"),
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
) -> list[dict]:
    stmt = select(Shipment).order_by(Shipment.created_at.desc()).limit(limit)
    if status_filter:
        stmt = stmt.where(Shipment.status.in_(status_filter))
    return [shipment_summary(db, shipment) for shipment in db.scalars(stmt)]


@router.get("/shipments/{shipment_uid}", response_model=ShipmentSummaryRead)
def api_get_shipment(shipment_uid: str, db: Session = Depends(get_db)) -> dict:
    shipment = db.scalar(select(Shipment).where(Shipment.shipment_uid == shipment_uid))
    if shipment is None:
        raise not_found("shipment")
    return shipment_summary(db, shipment)


@router.get("/shipments/{shipment_uid}/pallets", response_model=list[ShipmentPalletRead])
def api_get_shipment_pallets(shipment_uid: str, db: Session = Depends(get_db)) -> list[dict]:
    shipment = db.scalar(select(Shipment).where(Shipment.shipment_uid == shipment_uid))
    if shipment is None:
        raise not_found("shipment")
    links = list(db.scalars(select(ShipmentPallet).where(ShipmentPallet.shipment_id == shipment.id).order_by(ShipmentPallet.id)))
    result = []
    for link in links:
        pallet = db.get(Pallet, link.pallet_id)
        if pallet is None:
            continue
        result.append(
            {
                "pallet": pallet_summary(db, pallet),
                "shipment_pallet_status": link.status,
                "reserved_at": link.reserved_at,
                "moved_to_expedition_at": link.moved_to_expedition_at,
                "loaded_at": link.loaded_at,
            }
        )
    return result


@router.post("/shipments/{shipment_uid}/pallets/{pallet_uid}", response_model=ShipmentRead)
def api_reserve_shipment_pallet(
    shipment_uid: str,
    pallet_uid: str,
    payload: ShipmentActionRequest,
    db: Session = Depends(get_db),
) -> Shipment:
    return reserve_pallet_for_shipment(db, shipment_uid=shipment_uid, pallet_uid=pallet_uid, actor=payload.actor)


@router.post("/shipments/{shipment_uid}/expedition", response_model=ShipmentRead)
def api_move_shipment_to_expedition(
    shipment_uid: str,
    payload: ShipmentActionRequest,
    db: Session = Depends(get_db),
) -> Shipment:
    return move_shipment_to_expedition(db, shipment_uid=shipment_uid, actor=payload.actor)


@router.post("/shipments/{shipment_uid}/load/{pallet_uid}", response_model=ShipmentRead)
def api_load_shipment_pallet(
    shipment_uid: str,
    pallet_uid: str,
    payload: ShipmentActionRequest,
    db: Session = Depends(get_db),
) -> Shipment:
    return load_shipment_pallet(db, shipment_uid=shipment_uid, pallet_uid=pallet_uid, actor=payload.actor)


@router.post("/shipments/{shipment_uid}/close", response_model=ShipmentRead)
def api_close_shipment(
    shipment_uid: str,
    payload: ShipmentActionRequest,
    db: Session = Depends(get_db),
) -> Shipment:
    return close_shipment(db, shipment_uid=shipment_uid, actor=payload.actor, reason=payload.reason)


@router.get("/shipments/{shipment_uid}/events", response_model=list[EventRead])
def api_shipment_events(
    shipment_uid: str,
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
) -> list[OperationEvent]:
    shipment = db.scalar(select(Shipment).where(Shipment.shipment_uid == shipment_uid))
    if shipment is None:
        raise not_found("shipment")
    return list(
        db.scalars(
            select(OperationEvent)
            .where(OperationEvent.object_type == "shipment", OperationEvent.object_uid == shipment_uid)
            .order_by(OperationEvent.created_at.desc())
            .limit(limit)
        )
    )


@router.post("/transfers", response_model=TransferRead)
def api_create_transfer(payload: TransferCreate, db: Session = Depends(get_db)) -> dict:
    return transfer_summary(db, create_transfer(db, payload))


@router.get("/transfers", response_model=list[TransferRead])
def api_list_transfers(
    status_filter: list[str] | None = Query(default=None, alias="status"),
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
) -> list[dict]:
    stmt = select(WarehouseTransfer).order_by(WarehouseTransfer.created_at.desc()).limit(limit)
    if status_filter:
        stmt = stmt.where(WarehouseTransfer.status.in_(status_filter))
    return [transfer_summary(db, transfer) for transfer in db.scalars(stmt)]


@router.get("/transfers/{transfer_uid}", response_model=TransferRead)
def api_get_transfer(transfer_uid: str, db: Session = Depends(get_db)) -> dict:
    return transfer_summary(db, get_transfer(db, transfer_uid))


@router.get("/transfers/{transfer_uid}/pallets", response_model=list[TransferPalletRead])
def api_get_transfer_pallets(transfer_uid: str, db: Session = Depends(get_db)) -> list[dict]:
    transfer = get_transfer(db, transfer_uid)
    result = []
    for link in transfer_links(db, transfer.id):
        pallet = db.get(Pallet, link.pallet_id)
        if pallet is None:
            continue
        result.append(
            {
                "pallet": pallet_summary(db, pallet),
                "transfer_pallet_status": link.status,
                "source_location_code": location_code(db, link.source_location_id),
                "reserved_at": link.reserved_at,
                "moved_to_expedition_at": link.moved_to_expedition_at,
                "loaded_at": link.loaded_at,
                "received_at": link.received_at,
            }
        )
    return result


@router.post("/transfers/{transfer_uid}/pallets/{pallet_uid}", response_model=TransferRead)
def api_reserve_transfer_pallet(
    transfer_uid: str,
    pallet_uid: str,
    payload: TransferActionRequest,
    db: Session = Depends(get_db),
) -> dict:
    transfer = reserve_pallet_for_transfer(db, transfer_uid=transfer_uid, pallet_uid=pallet_uid, actor=payload.actor)
    return transfer_summary(db, transfer)


@router.post("/transfers/{transfer_uid}/expedition", response_model=TransferRead)
def api_transfer_to_expedition(
    transfer_uid: str,
    payload: TransferActionRequest,
    db: Session = Depends(get_db),
) -> dict:
    return transfer_summary(db, move_transfer_to_expedition(db, transfer_uid=transfer_uid, actor=payload.actor))


@router.post("/transfers/{transfer_uid}/load/{pallet_uid}", response_model=TransferRead)
def api_load_transfer_pallet(
    transfer_uid: str,
    pallet_uid: str,
    payload: TransferActionRequest,
    db: Session = Depends(get_db),
) -> dict:
    transfer = load_transfer_pallet(db, transfer_uid=transfer_uid, pallet_uid=pallet_uid, actor=payload.actor)
    return transfer_summary(db, transfer)


@router.post("/transfers/{transfer_uid}/dispatch", response_model=TransferRead)
def api_dispatch_transfer(
    transfer_uid: str,
    payload: TransferActionRequest,
    db: Session = Depends(get_db),
) -> dict:
    transfer = dispatch_transfer(
        db,
        transfer_uid=transfer_uid,
        actor=payload.actor,
        reason=payload.reason,
    )
    return transfer_summary(db, transfer)


@router.post("/transfers/{transfer_uid}/receive/{pallet_uid}", response_model=TransferRead)
def api_receive_transfer_pallet(
    transfer_uid: str,
    pallet_uid: str,
    payload: TransferActionRequest,
    db: Session = Depends(get_db),
) -> dict:
    transfer = receive_transfer_pallet(db, transfer_uid=transfer_uid, pallet_uid=pallet_uid, actor=payload.actor)
    return transfer_summary(db, transfer)


@router.get("/transfers/{transfer_uid}/events", response_model=list[EventRead])
def api_transfer_events(
    transfer_uid: str,
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
) -> list[OperationEvent]:
    get_transfer(db, transfer_uid)
    return list(
        db.scalars(
            select(OperationEvent)
            .where(OperationEvent.object_type == "transfer", OperationEvent.object_uid == transfer_uid)
            .order_by(OperationEvent.created_at.desc())
            .limit(limit)
        )
    )


@router.post("/inventories", response_model=InventoryRead)
def api_start_inventory(payload: InventoryStartRequest, db: Session = Depends(get_db)) -> dict:
    inventory = start_inventory(db, payload)
    return inventory_summary(db, inventory)


@router.get("/inventories", response_model=list[InventoryRead])
def api_list_inventories(
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
) -> list[dict]:
    inventories = db.scalars(select(InventorySession).order_by(InventorySession.created_at.desc()).limit(limit))
    return [inventory_summary(db, inventory) for inventory in inventories]


@router.get("/inventories/{inventory_uid}", response_model=InventoryRead)
def api_get_inventory(inventory_uid: str, db: Session = Depends(get_db)) -> dict:
    inventory = db.scalar(select(InventorySession).where(InventorySession.inventory_uid == inventory_uid))
    if inventory is None:
        raise not_found("inventory")
    return inventory_summary(db, inventory)


@router.get("/inventories/{inventory_uid}/lines", response_model=list[InventoryLineRead])
def api_inventory_lines(inventory_uid: str, db: Session = Depends(get_db)) -> list[dict]:
    inventory = db.scalar(select(InventorySession).where(InventorySession.inventory_uid == inventory_uid))
    if inventory is None:
        raise not_found("inventory")
    lines = list(db.scalars(select(InventoryLine).where(InventoryLine.inventory_id == inventory.id).order_by(InventoryLine.id)))
    result = []
    for line in lines:
        payload = inventory_line_payload(db, line)
        if payload:
            result.append(payload)
    return result


@router.get("/inventories/{inventory_uid}/progress", response_model=InventoryProgressRead)
def api_inventory_progress(inventory_uid: str, db: Session = Depends(get_db)) -> dict:
    inventory = db.scalar(select(InventorySession).where(InventorySession.inventory_uid == inventory_uid))
    if inventory is None:
        raise not_found("inventory")
    return inventory_progress(db, inventory)


@router.post("/inventories/{inventory_uid}/scan", response_model=InventoryRead)
def api_scan_inventory_pallet(
    inventory_uid: str,
    payload: InventoryScanRequest,
    db: Session = Depends(get_db),
) -> dict:
    inventory = scan_inventory_pallet(db, inventory_uid=inventory_uid, pallet_uid=payload.pallet_uid, actor=payload.actor)
    return inventory_summary(db, inventory)


@router.post("/inventories/{inventory_uid}/scan-location", response_model=InventoryRead)
def api_scan_inventory_location(
    inventory_uid: str,
    payload: InventoryLocationScanRequest,
    db: Session = Depends(get_db),
) -> dict:
    inventory = scan_inventory_location(
        db,
        inventory_uid=inventory_uid,
        location_code=payload.location_code,
        actor=payload.actor,
    )
    return inventory_summary(db, inventory)


@router.post("/inventories/{inventory_uid}/confirm-location", response_model=InventoryRead)
def api_confirm_inventory_location(
    inventory_uid: str,
    payload: InventoryLocationScanRequest,
    db: Session = Depends(get_db),
) -> dict:
    inventory = confirm_inventory_location(
        db,
        inventory_uid=inventory_uid,
        location_code=payload.location_code,
        actor=payload.actor,
    )
    return inventory_summary(db, inventory)


@router.post("/inventories/{inventory_uid}/discrepancies/{pallet_uid}/confirm-missing", response_model=InventoryLineRead)
def api_confirm_inventory_missing(
    inventory_uid: str,
    pallet_uid: str,
    payload: InventoryResolveRequest,
    db: Session = Depends(get_db),
) -> dict:
    line = confirm_inventory_missing(
        db,
        inventory_uid=inventory_uid,
        pallet_uid=pallet_uid,
        actor=payload.actor,
        reason=payload.reason,
    )
    result = inventory_line_payload(db, line)
    if result is None:
        raise not_found("inventory line")
    return result


@router.post("/inventories/{inventory_uid}/discrepancies/{pallet_uid}/place-found", response_model=InventoryLineRead)
def api_place_inventory_found_pallet(
    inventory_uid: str,
    pallet_uid: str,
    payload: InventoryResolveRequest,
    db: Session = Depends(get_db),
) -> dict:
    line = place_inventory_found_pallet(
        db,
        inventory_uid=inventory_uid,
        pallet_uid=pallet_uid,
        actor=payload.actor,
        reason=payload.reason,
    )
    result = inventory_line_payload(db, line)
    if result is None:
        raise not_found("inventory line")
    return result


@router.post("/inventories/{inventory_uid}/discrepancies/{pallet_uid}/move-to-actual", response_model=InventoryLineRead)
def api_move_inventory_pallet_to_actual(
    inventory_uid: str,
    pallet_uid: str,
    payload: InventoryResolveRequest,
    db: Session = Depends(get_db),
) -> dict:
    line = move_inventory_pallet_to_actual(
        db,
        inventory_uid=inventory_uid,
        pallet_uid=pallet_uid,
        actor=payload.actor,
        reason=payload.reason,
    )
    result = inventory_line_payload(db, line)
    if result is None:
        raise not_found("inventory line")
    return result


@router.post("/inventories/{inventory_uid}/complete", response_model=InventoryRead)
def api_complete_inventory(
    inventory_uid: str,
    payload: ShipmentActionRequest,
    db: Session = Depends(get_db),
) -> dict:
    inventory = complete_inventory(db, inventory_uid=inventory_uid, actor=payload.actor)
    return inventory_summary(db, inventory)


@router.get("/inventories/{inventory_uid}/events", response_model=list[EventRead])
def api_inventory_events(
    inventory_uid: str,
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
) -> list[OperationEvent]:
    inventory = db.scalar(select(InventorySession).where(InventorySession.inventory_uid == inventory_uid))
    if inventory is None:
        raise not_found("inventory")
    return list(
        db.scalars(
            select(OperationEvent)
            .where(OperationEvent.object_type == "inventory", OperationEvent.object_uid == inventory_uid)
            .order_by(OperationEvent.created_at.desc())
            .limit(limit)
        )
    )
