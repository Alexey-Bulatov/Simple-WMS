from fastapi import APIRouter, Depends, File, HTTPException, Query, Response, UploadFile
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.constants import (
    DEFAULT_WAREHOUSE_CODE,
    LOGISTIC_INVENTORY_CODE_PREFIX,
    LOGISTIC_TASK_CODE_PREFIX,
    SHIPMENT_CODE_PREFIX,
    TRANSFER_CODE_PREFIX,
)
from app.db.session import get_db
from app.demo import generate_demo_logistic_units
from app.labels import LabelItem, build_labels_pdf
from app.thermal_printing import ThermalPrintError, print_thermal_label
from app.imports import apply_import, parse_import_file, validate_import_rows
from app.models.entities import (
    Aisle,
    Batch,
    EquipmentProfile,
    LogisticInventory,
    LogisticTask,
    LogisticShipment,
    LogisticTransfer,
    LogisticUnit,
    LogisticUnitType,
    Location,
    OperationEvent,
    Product,
    Rack,
    RackLevel,
    RackSection,
    UnitOfMeasure,
    User,
    Warehouse,
    Zone,
)
from app.schemas import (
    AisleCreate,
    AisleRead,
    BatchCreate,
    BatchRead,
    DemoCatalogRequest,
    DemoGenerateRead,
    DemoLogisticUnitsRequest,
    EquipmentProfileCreate,
    EquipmentProfileRead,
    EquipmentProfileUpdate,
    EventRead,
    LogisticUnitAcceptRequest,
    LogisticUnitActionRequest,
    LogisticUnitChildRequest,
    LogisticUnitContentCreate,
    LogisticUnitContentRemoveRequest,
    LogisticUnitCreate,
    LogisticUnitHoldRequest,
    LogisticUnitLocationRequest,
    LogisticUnitRead,
    LogisticDocumentActionRequest,
    LogisticDocumentStageRequest,
    LogisticDocumentUnitRequest,
    LogisticInventoryLocationRequest,
    LogisticInventoryRead,
    LogisticInventoryResolveRequest,
    LogisticInventoryStartRequest,
    LogisticInventoryUnitRequest,
    LogisticTaskCreate,
    LogisticTaskRead,
    LogisticShipmentCreate,
    LogisticShipmentRead,
    LogisticTransferCreate,
    LogisticTransferRead,
    LogisticUnitTypeCreate,
    LogisticUnitTypeRead,
    LocationCreate,
    LocationRead,
    ProductCreate,
    ProductRead,
    RackCreate,
    RackLevelCreate,
    RackLevelRead,
    RackRead,
    RackSectionCreate,
    RackSectionRead,
    TaskActionRequest,
    TaskAssignRequest,
    TaskSyncRequest,
    UserCreate,
    UserRead,
    UnitOfMeasureCreate,
    UnitOfMeasureRead,
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
    accept_logistic_unit,
    add_logistic_unit_child,
    add_logistic_unit_content,
    close_logistic_unit,
    create_batch,
    create_aisle,
    create_equipment_profile,
    create_location,
    create_logistic_unit,
    create_logistic_unit_type,
    create_product,
    create_rack,
    create_rack_level,
    create_rack_section,
    create_user,
    create_unit_of_measure,
    create_warehouse,
    create_zone,
    ensure_demo_catalog,
    bad_request,
    not_found,
    update_equipment_profile,
    disassemble_logistic_unit,
    get_logistic_unit,
    hold_logistic_unit,
    logistic_unit_payload,
    location_address_payload,
    move_logistic_unit,
    place_logistic_unit,
    release_logistic_unit,
    remove_logistic_unit_child,
    remove_logistic_unit_content,
    reopen_logistic_unit,
)
from app.logistic_documents import (
    close_logistic_shipment,
    create_logistic_shipment,
    create_logistic_transfer,
    dispatch_logistic_transfer,
    get_logistic_shipment,
    get_logistic_transfer,
    load_logistic_shipment_unit,
    load_logistic_transfer_unit,
    logistic_shipment_payload,
    logistic_transfer_payload,
    receive_logistic_transfer_unit,
    reserve_unit_for_logistic_shipment,
    reserve_unit_for_logistic_transfer,
    stage_logistic_shipment,
    stage_logistic_transfer,
)
from app.logistic_inventory import (
    complete_logistic_inventory,
    confirm_logistic_inventory_location,
    confirm_logistic_inventory_missing,
    get_logistic_inventory,
    logistic_inventory_payload,
    move_logistic_inventory_unit_to_actual,
    place_logistic_inventory_found_unit,
    scan_logistic_inventory_location,
    scan_logistic_inventory_unit,
    start_logistic_inventory,
)
from app.logistic_tasks import (
    assign_logistic_task,
    cancel_logistic_task,
    complete_logistic_task,
    create_logistic_task,
    get_logistic_task,
    logistic_task_payload,
    reopen_logistic_task,
    start_logistic_task,
    sync_logistic_tasks,
)
from app.models.enums import (
    LocationKind,
    LogisticUnitStatus,
    TaskStatus,
    TaskType,
    TransferKind,
)
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
router = APIRouter(prefix="/api")

LOGISTIC_UNIT_STATUS_LABELS = {
    "open": "Открыта",
    "closed": "Закрыта",
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
        "shipment_code_prefix": SHIPMENT_CODE_PREFIX,
        "logistic_inventory_code_prefix": LOGISTIC_INVENTORY_CODE_PREFIX,
        "logistic_task_code_prefix": LOGISTIC_TASK_CODE_PREFIX,
        "transfer_code_prefix": TRANSFER_CODE_PREFIX,
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


def pdf_response(content: bytes, filename: str) -> Response:
    return Response(
        content=content,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{filename}"'},
    )


def thermal_print_response(item: LabelItem) -> dict:
    try:
        job = print_thermal_label(item)
    except ThermalPrintError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return {
        "status": "queued",
        "object_type": item.object_type,
        "code": item.code,
        **job,
    }


def logistic_unit_label_item(db: Session, unit: LogisticUnit) -> LabelItem:
    payload = logistic_unit_payload(db, unit)
    content = ", ".join(
        f"{row['product_code']} {row['quantity']} {row['uom_symbol']}"
        for row in payload["contents"][:2]
    )
    composition = (
        f"Содержимое: {content}"
        if content
        else f"Вложенных единиц: {len(payload['child_units'])}"
    )
    return LabelItem(
        object_type=payload["type_name"] or "Логистическая единица",
        code=unit.uid,
        title=payload["type_name"] or payload["type_code"],
        lines=(
            composition,
            f"Ячейка: {payload['current_location_code'] or '-'}",
            f"Статус: {label(LOGISTIC_UNIT_STATUS_LABELS, unit.status)}",
        ),
    )


def location_label_item(location: Location) -> LabelItem:
    return LabelItem(
        object_type="Ячейка",
        code=location.code,
        title=location.name or "Адрес хранения",
        lines=(
            f"Тип: {label(LOCATION_KIND_LABELS, location.kind)}",
            f"Вместимость, единиц: {location.capacity_units}",
        ),
    )


@router.get("/cards/resolve/{code}")
def api_resolve_universal_card(code: str, db: Session = Depends(get_db)) -> dict:
    normalized = code.strip().upper()
    if db.scalar(select(LogisticUnit.id).where(LogisticUnit.uid == normalized)):
        return {
            "kind": "unit",
            "code": normalized,
            "url": f"/cards?kind=unit&code={normalized}",
        }
    if db.scalar(select(Location.id).where(Location.code == normalized)):
        return {
            "kind": "location",
            "code": normalized,
            "url": f"/cards?kind=location&code={normalized}",
        }
    raise not_found("object")


@router.get("/cards/locations/{location_code}")
def api_universal_location_card(
    location_code: str,
    db: Session = Depends(get_db),
) -> dict:
    location = db.scalar(
        select(Location).where(
            func.upper(Location.code) == location_code.strip().upper()
        )
    )
    if location is None:
        raise not_found("location")
    warehouse = db.get(Warehouse, location.warehouse_id)
    zone = db.get(Zone, location.zone_id)
    units = list(
        db.scalars(
            select(LogisticUnit)
            .where(
                LogisticUnit.current_location_id == location.id,
                LogisticUnit.parent_unit_id.is_(None),
            )
            .order_by(LogisticUnit.uid)
        )
    )
    events = list(
        db.scalars(
            select(OperationEvent)
            .where(OperationEvent.object_type == "logistic_unit")
            .order_by(OperationEvent.created_at.desc())
            .limit(500)
        )
    )
    location_events = [
        event
        for event in events
        if location.code
        in {
            str((event.before or {}).get("location_code") or ""),
            str((event.after or {}).get("location_code") or ""),
        }
    ][:100]
    return {
        "location": {
            "id": location.id,
            "code": location.code,
            "name": location.name,
            "kind": location.kind,
            "kind_label": label(LOCATION_KIND_LABELS, location.kind),
            "capacity_units": location.capacity_units,
            "occupied_units": len(units),
            "free_unit_slots": max(location.capacity_units - len(units), 0),
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
            "address": location_address_payload(location),
        },
        "logistic_units": [logistic_unit_payload(db, unit) for unit in units],
        "events": [
            EventRead.model_validate(event).model_dump()
            for event in location_events
        ],
    }


@router.post("/users", response_model=UserRead)
def api_create_user(payload: UserCreate, db: Session = Depends(get_db)) -> User:
    return create_user(db, payload)


@router.get("/users", response_model=list[UserRead])
def api_list_users(db: Session = Depends(get_db)) -> list[User]:
    return list(db.scalars(select(User).order_by(User.username)))


@router.post("/equipment-profiles", response_model=EquipmentProfileRead)
def api_create_equipment_profile(
    payload: EquipmentProfileCreate,
    db: Session = Depends(get_db),
) -> EquipmentProfile:
    return create_equipment_profile(db, payload)


@router.get("/equipment-profiles", response_model=list[EquipmentProfileRead])
def api_list_equipment_profiles(
    warehouse_id: int | None = Query(default=None),
    device_kind: str | None = Query(default=None),
    db: Session = Depends(get_db),
) -> list[EquipmentProfile]:
    query = select(EquipmentProfile)
    if warehouse_id is not None:
        query = query.where(EquipmentProfile.warehouse_id == warehouse_id)
    if device_kind is not None:
        query = query.where(EquipmentProfile.device_kind == device_kind)
    return list(db.scalars(query.order_by(EquipmentProfile.device_kind, EquipmentProfile.code)))


@router.put("/equipment-profiles/{profile_id}", response_model=EquipmentProfileRead)
def api_update_equipment_profile(
    profile_id: int,
    payload: EquipmentProfileUpdate,
    db: Session = Depends(get_db),
) -> EquipmentProfile:
    return update_equipment_profile(db, profile_id, payload)


@router.post("/units-of-measure", response_model=UnitOfMeasureRead)
def api_create_unit_of_measure(payload: UnitOfMeasureCreate, db: Session = Depends(get_db)) -> UnitOfMeasure:
    return create_unit_of_measure(db, payload)


@router.get("/units-of-measure", response_model=list[UnitOfMeasureRead])
def api_list_units_of_measure(db: Session = Depends(get_db)) -> list[UnitOfMeasure]:
    return list(db.scalars(select(UnitOfMeasure).order_by(UnitOfMeasure.dimension, UnitOfMeasure.code)))


@router.post("/logistic-unit-types", response_model=LogisticUnitTypeRead)
def api_create_logistic_unit_type(
    payload: LogisticUnitTypeCreate,
    db: Session = Depends(get_db),
) -> LogisticUnitType:
    return create_logistic_unit_type(db, payload)


@router.get("/logistic-unit-types", response_model=list[LogisticUnitTypeRead])
def api_list_logistic_unit_types(db: Session = Depends(get_db)) -> list[LogisticUnitType]:
    return list(db.scalars(select(LogisticUnitType).order_by(LogisticUnitType.code)))


@router.post("/logistic-units", response_model=LogisticUnitRead)
def api_create_logistic_unit(
    payload: LogisticUnitCreate,
    db: Session = Depends(get_db),
) -> dict:
    return logistic_unit_payload(db, create_logistic_unit(db, payload))


@router.get("/logistic-units", response_model=list[LogisticUnitRead])
def api_list_logistic_units(
    type_id: int | None = Query(default=None),
    unit_status: LogisticUnitStatus | None = Query(default=None, alias="status"),
    parent_uid: str | None = Query(default=None),
    warehouse_code: str | None = Query(default=None),
    db: Session = Depends(get_db),
) -> list[dict]:
    query = select(LogisticUnit)
    if type_id is not None:
        query = query.where(LogisticUnit.type_id == type_id)
    if unit_status is not None:
        query = query.where(LogisticUnit.status == unit_status)
    if parent_uid is not None:
        parent = get_logistic_unit(db, parent_uid)
        query = query.where(LogisticUnit.parent_unit_id == parent.id)
    if warehouse_code is not None:
        warehouse = db.scalar(
            select(Warehouse).where(
                func.upper(Warehouse.code) == warehouse_code.strip().upper()
            )
        )
        if warehouse is None:
            raise not_found("warehouse")
        query = query.where(
            LogisticUnit.current_location_id.in_(
                select(Location.id).where(Location.warehouse_id == warehouse.id)
            )
        )
    return [
        logistic_unit_payload(db, item)
        for item in db.scalars(query.order_by(LogisticUnit.created_at.desc(), LogisticUnit.uid))
    ]


@router.get("/logistic-units/{uid}", response_model=LogisticUnitRead)
def api_get_logistic_unit(uid: str, db: Session = Depends(get_db)) -> dict:
    return logistic_unit_payload(db, get_logistic_unit(db, uid))


@router.get("/logistic-units/{uid}/label.pdf")
def api_logistic_unit_label(uid: str, db: Session = Depends(get_db)) -> Response:
    unit = get_logistic_unit(db, uid)
    content = build_labels_pdf(
        [logistic_unit_label_item(db, unit)],
        title=f"Этикетка {unit.uid}",
    )
    return pdf_response(content, f"logistic-unit-{unit.uid}.pdf")


@router.post("/logistic-units/{uid}/label.print")
def api_print_logistic_unit_label(uid: str, db: Session = Depends(get_db)) -> dict:
    return thermal_print_response(logistic_unit_label_item(db, get_logistic_unit(db, uid)))


@router.get("/logistic-units/{uid}/events", response_model=list[EventRead])
def api_logistic_unit_events(
    uid: str,
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
) -> list[OperationEvent]:
    unit = get_logistic_unit(db, uid)
    return list(
        db.scalars(
            select(OperationEvent)
            .where(
                OperationEvent.object_type == "logistic_unit",
                OperationEvent.object_uid == unit.uid,
            )
            .order_by(OperationEvent.created_at.desc())
            .limit(limit)
        )
    )


@router.post("/logistic-units/{uid}/accept", response_model=LogisticUnitRead)
def api_accept_logistic_unit(
    uid: str,
    payload: LogisticUnitAcceptRequest,
    db: Session = Depends(get_db),
) -> dict:
    return logistic_unit_payload(db, accept_logistic_unit(db, uid, payload))


@router.post("/logistic-units/{uid}/contents", response_model=LogisticUnitRead)
def api_add_logistic_unit_content(
    uid: str,
    payload: LogisticUnitContentCreate,
    db: Session = Depends(get_db),
) -> dict:
    return logistic_unit_payload(db, add_logistic_unit_content(db, uid, payload))


@router.post(
    "/logistic-units/{uid}/contents/{content_id}/remove",
    response_model=LogisticUnitRead,
)
def api_remove_logistic_unit_content(
    uid: str,
    content_id: int,
    payload: LogisticUnitContentRemoveRequest,
    db: Session = Depends(get_db),
) -> dict:
    return logistic_unit_payload(
        db,
        remove_logistic_unit_content(db, uid, content_id, payload),
    )


@router.post("/logistic-units/{uid}/children", response_model=LogisticUnitRead)
def api_add_logistic_unit_child(
    uid: str,
    payload: LogisticUnitChildRequest,
    db: Session = Depends(get_db),
) -> dict:
    return logistic_unit_payload(db, add_logistic_unit_child(db, uid, payload))


@router.post(
    "/logistic-units/{uid}/children/{child_uid}/remove",
    response_model=LogisticUnitRead,
)
def api_remove_logistic_unit_child(
    uid: str,
    child_uid: str,
    payload: LogisticUnitActionRequest,
    db: Session = Depends(get_db),
) -> dict:
    return logistic_unit_payload(
        db,
        remove_logistic_unit_child(db, uid, child_uid, payload),
    )


@router.post("/logistic-units/{uid}/close", response_model=LogisticUnitRead)
def api_close_logistic_unit(
    uid: str,
    payload: LogisticUnitActionRequest,
    db: Session = Depends(get_db),
) -> dict:
    return logistic_unit_payload(db, close_logistic_unit(db, uid, payload))


@router.post("/logistic-units/{uid}/reopen", response_model=LogisticUnitRead)
def api_reopen_logistic_unit(
    uid: str,
    payload: LogisticUnitActionRequest,
    db: Session = Depends(get_db),
) -> dict:
    return logistic_unit_payload(db, reopen_logistic_unit(db, uid, payload))


@router.post("/logistic-units/{uid}/block", response_model=LogisticUnitRead)
def api_block_logistic_unit(
    uid: str,
    payload: LogisticUnitHoldRequest,
    db: Session = Depends(get_db),
) -> dict:
    return logistic_unit_payload(
        db,
        hold_logistic_unit(db, uid, LogisticUnitStatus.BLOCKED, payload),
    )


@router.post("/logistic-units/{uid}/quarantine", response_model=LogisticUnitRead)
def api_quarantine_logistic_unit(
    uid: str,
    payload: LogisticUnitHoldRequest,
    db: Session = Depends(get_db),
) -> dict:
    return logistic_unit_payload(
        db,
        hold_logistic_unit(db, uid, LogisticUnitStatus.QUARANTINE, payload),
    )


@router.post("/logistic-units/{uid}/release", response_model=LogisticUnitRead)
def api_release_logistic_unit(
    uid: str,
    payload: LogisticUnitHoldRequest,
    db: Session = Depends(get_db),
) -> dict:
    return logistic_unit_payload(db, release_logistic_unit(db, uid, payload))


@router.post("/logistic-units/{uid}/place", response_model=LogisticUnitRead)
def api_place_logistic_unit(
    uid: str,
    payload: LogisticUnitLocationRequest,
    db: Session = Depends(get_db),
) -> dict:
    return logistic_unit_payload(db, place_logistic_unit(db, uid, payload))


@router.post("/logistic-units/{uid}/move", response_model=LogisticUnitRead)
def api_move_logistic_unit(
    uid: str,
    payload: LogisticUnitLocationRequest,
    db: Session = Depends(get_db),
) -> dict:
    return logistic_unit_payload(db, move_logistic_unit(db, uid, payload))


@router.post("/logistic-units/{uid}/disassemble", response_model=LogisticUnitRead)
def api_disassemble_logistic_unit(
    uid: str,
    payload: LogisticUnitActionRequest,
    db: Session = Depends(get_db),
) -> dict:
    return logistic_unit_payload(db, disassemble_logistic_unit(db, uid, payload))


@router.post("/logistic-shipments", response_model=LogisticShipmentRead)
def api_create_logistic_shipment(
    payload: LogisticShipmentCreate,
    db: Session = Depends(get_db),
) -> dict:
    return logistic_shipment_payload(db, create_logistic_shipment(db, payload))


@router.get("/logistic-shipments", response_model=list[LogisticShipmentRead])
def api_list_logistic_shipments(
    status_filter: list[str] | None = Query(default=None, alias="status"),
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
) -> list[dict]:
    query = select(LogisticShipment).order_by(LogisticShipment.created_at.desc()).limit(limit)
    if status_filter:
        query = query.where(LogisticShipment.status.in_(status_filter))
    return [logistic_shipment_payload(db, item) for item in db.scalars(query)]


@router.get(
    "/logistic-shipments/{shipment_uid}",
    response_model=LogisticShipmentRead,
)
def api_get_logistic_shipment(
    shipment_uid: str,
    db: Session = Depends(get_db),
) -> dict:
    return logistic_shipment_payload(db, get_logistic_shipment(db, shipment_uid))


@router.post(
    "/logistic-shipments/{shipment_uid}/units",
    response_model=LogisticShipmentRead,
)
def api_reserve_logistic_shipment_unit(
    shipment_uid: str,
    payload: LogisticDocumentUnitRequest,
    db: Session = Depends(get_db),
) -> dict:
    shipment = reserve_unit_for_logistic_shipment(db, shipment_uid, payload)
    return logistic_shipment_payload(db, shipment)


@router.post(
    "/logistic-shipments/{shipment_uid}/expedition",
    response_model=LogisticShipmentRead,
)
def api_stage_logistic_shipment(
    shipment_uid: str,
    payload: LogisticDocumentStageRequest,
    db: Session = Depends(get_db),
) -> dict:
    shipment = stage_logistic_shipment(db, shipment_uid, payload)
    return logistic_shipment_payload(db, shipment)


@router.post(
    "/logistic-shipments/{shipment_uid}/load",
    response_model=LogisticShipmentRead,
)
def api_load_logistic_shipment_unit(
    shipment_uid: str,
    payload: LogisticDocumentUnitRequest,
    db: Session = Depends(get_db),
) -> dict:
    shipment = load_logistic_shipment_unit(db, shipment_uid, payload)
    return logistic_shipment_payload(db, shipment)


@router.post(
    "/logistic-shipments/{shipment_uid}/close",
    response_model=LogisticShipmentRead,
)
def api_close_logistic_shipment(
    shipment_uid: str,
    payload: LogisticDocumentActionRequest,
    db: Session = Depends(get_db),
) -> dict:
    shipment = close_logistic_shipment(db, shipment_uid, payload)
    return logistic_shipment_payload(db, shipment)


@router.post("/logistic-transfers", response_model=LogisticTransferRead)
def api_create_logistic_transfer(
    payload: LogisticTransferCreate,
    db: Session = Depends(get_db),
) -> dict:
    return logistic_transfer_payload(db, create_logistic_transfer(db, payload))


@router.get("/logistic-transfers", response_model=list[LogisticTransferRead])
def api_list_logistic_transfers(
    status_filter: list[str] | None = Query(default=None, alias="status"),
    transfer_kind: TransferKind | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
) -> list[dict]:
    query = select(LogisticTransfer).order_by(LogisticTransfer.created_at.desc()).limit(limit)
    if status_filter:
        query = query.where(LogisticTransfer.status.in_(status_filter))
    if transfer_kind is not None:
        query = query.where(LogisticTransfer.transfer_kind == transfer_kind)
    return [logistic_transfer_payload(db, item) for item in db.scalars(query)]


@router.get(
    "/logistic-transfers/{transfer_uid}",
    response_model=LogisticTransferRead,
)
def api_get_logistic_transfer(
    transfer_uid: str,
    db: Session = Depends(get_db),
) -> dict:
    return logistic_transfer_payload(db, get_logistic_transfer(db, transfer_uid))


@router.post(
    "/logistic-transfers/{transfer_uid}/units",
    response_model=LogisticTransferRead,
)
def api_reserve_logistic_transfer_unit(
    transfer_uid: str,
    payload: LogisticDocumentUnitRequest,
    db: Session = Depends(get_db),
) -> dict:
    transfer = reserve_unit_for_logistic_transfer(db, transfer_uid, payload)
    return logistic_transfer_payload(db, transfer)


@router.post(
    "/logistic-transfers/{transfer_uid}/expedition",
    response_model=LogisticTransferRead,
)
def api_stage_logistic_transfer(
    transfer_uid: str,
    payload: LogisticDocumentStageRequest,
    db: Session = Depends(get_db),
) -> dict:
    transfer = stage_logistic_transfer(db, transfer_uid, payload)
    return logistic_transfer_payload(db, transfer)


@router.post(
    "/logistic-transfers/{transfer_uid}/load",
    response_model=LogisticTransferRead,
)
def api_load_logistic_transfer_unit(
    transfer_uid: str,
    payload: LogisticDocumentUnitRequest,
    db: Session = Depends(get_db),
) -> dict:
    transfer = load_logistic_transfer_unit(db, transfer_uid, payload)
    return logistic_transfer_payload(db, transfer)


@router.post(
    "/logistic-transfers/{transfer_uid}/dispatch",
    response_model=LogisticTransferRead,
)
def api_dispatch_logistic_transfer(
    transfer_uid: str,
    payload: LogisticDocumentActionRequest,
    db: Session = Depends(get_db),
) -> dict:
    transfer = dispatch_logistic_transfer(db, transfer_uid, payload)
    return logistic_transfer_payload(db, transfer)


@router.post(
    "/logistic-transfers/{transfer_uid}/receive/{unit_uid}",
    response_model=LogisticTransferRead,
)
def api_receive_logistic_transfer_unit(
    transfer_uid: str,
    unit_uid: str,
    payload: LogisticDocumentStageRequest,
    db: Session = Depends(get_db),
) -> dict:
    unit_request = LogisticDocumentUnitRequest(
        unit_uid=unit_uid,
        actor=payload.actor,
        reason=payload.reason,
    )
    transfer = receive_logistic_transfer_unit(
        db,
        transfer_uid,
        unit_request,
        payload.location_code,
    )
    return logistic_transfer_payload(db, transfer)


@router.post("/logistic-inventories", response_model=LogisticInventoryRead)
def api_start_logistic_inventory(
    payload: LogisticInventoryStartRequest,
    db: Session = Depends(get_db),
) -> dict:
    inventory = start_logistic_inventory(db, payload)
    return logistic_inventory_payload(db, inventory)


@router.get(
    "/logistic-inventories",
    response_model=list[LogisticInventoryRead],
)
def api_list_logistic_inventories(
    status_filter: list[str] | None = Query(default=None, alias="status"),
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
) -> list[dict]:
    query = (
        select(LogisticInventory)
        .order_by(LogisticInventory.created_at.desc())
        .limit(limit)
    )
    if status_filter:
        query = query.where(LogisticInventory.status.in_(status_filter))
    return [
        logistic_inventory_payload(db, inventory)
        for inventory in db.scalars(query)
    ]


@router.get(
    "/logistic-inventories/{inventory_uid}",
    response_model=LogisticInventoryRead,
)
def api_get_logistic_inventory(
    inventory_uid: str,
    db: Session = Depends(get_db),
) -> dict:
    return logistic_inventory_payload(
        db,
        get_logistic_inventory(db, inventory_uid),
    )


@router.post(
    "/logistic-inventories/{inventory_uid}/scan-location",
    response_model=LogisticInventoryRead,
)
def api_scan_logistic_inventory_location(
    inventory_uid: str,
    payload: LogisticInventoryLocationRequest,
    db: Session = Depends(get_db),
) -> dict:
    inventory = scan_logistic_inventory_location(db, inventory_uid, payload)
    return logistic_inventory_payload(db, inventory)


@router.post(
    "/logistic-inventories/{inventory_uid}/scan-unit",
    response_model=LogisticInventoryRead,
)
def api_scan_logistic_inventory_unit(
    inventory_uid: str,
    payload: LogisticInventoryUnitRequest,
    db: Session = Depends(get_db),
) -> dict:
    inventory = scan_logistic_inventory_unit(db, inventory_uid, payload)
    return logistic_inventory_payload(db, inventory)


@router.post(
    "/logistic-inventories/{inventory_uid}/confirm-location",
    response_model=LogisticInventoryRead,
)
def api_confirm_logistic_inventory_location(
    inventory_uid: str,
    payload: LogisticDocumentActionRequest,
    db: Session = Depends(get_db),
) -> dict:
    inventory = confirm_logistic_inventory_location(
        db,
        inventory_uid,
        actor=payload.actor,
    )
    return logistic_inventory_payload(db, inventory)


@router.post(
    "/logistic-inventories/{inventory_uid}/empty",
    response_model=LogisticInventoryRead,
)
def api_mark_logistic_inventory_location_empty(
    inventory_uid: str,
    payload: LogisticDocumentActionRequest,
    db: Session = Depends(get_db),
) -> dict:
    inventory = confirm_logistic_inventory_location(
        db,
        inventory_uid,
        actor=payload.actor,
        require_empty=True,
    )
    return logistic_inventory_payload(db, inventory)


@router.post(
    "/logistic-inventories/{inventory_uid}/complete",
    response_model=LogisticInventoryRead,
)
def api_complete_logistic_inventory(
    inventory_uid: str,
    payload: LogisticDocumentActionRequest,
    db: Session = Depends(get_db),
) -> dict:
    inventory = complete_logistic_inventory(
        db,
        inventory_uid,
        actor=payload.actor,
    )
    return logistic_inventory_payload(db, inventory)


@router.get(
    "/logistic-inventories/{inventory_uid}/events",
    response_model=list[EventRead],
)
def api_logistic_inventory_events(
    inventory_uid: str,
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
) -> list[OperationEvent]:
    inventory = get_logistic_inventory(db, inventory_uid)
    return list(
        db.scalars(
            select(OperationEvent)
            .where(
                OperationEvent.object_type == "logistic_inventory",
                OperationEvent.object_uid == inventory.inventory_uid,
            )
            .order_by(OperationEvent.created_at.desc())
            .limit(limit)
        )
    )


@router.post(
    "/logistic-inventories/{inventory_uid}/discrepancies/"
    "{unit_uid}/confirm-missing",
    response_model=LogisticInventoryRead,
)
def api_confirm_logistic_inventory_missing(
    inventory_uid: str,
    unit_uid: str,
    payload: LogisticInventoryResolveRequest,
    db: Session = Depends(get_db),
) -> dict:
    inventory = confirm_logistic_inventory_missing(
        db,
        inventory_uid,
        unit_uid,
        payload,
    )
    return logistic_inventory_payload(db, inventory)


@router.post(
    "/logistic-inventories/{inventory_uid}/discrepancies/"
    "{unit_uid}/place-found",
    response_model=LogisticInventoryRead,
)
def api_place_logistic_inventory_found_unit(
    inventory_uid: str,
    unit_uid: str,
    payload: LogisticInventoryResolveRequest,
    db: Session = Depends(get_db),
) -> dict:
    inventory = place_logistic_inventory_found_unit(
        db,
        inventory_uid,
        unit_uid,
        payload,
    )
    return logistic_inventory_payload(db, inventory)


@router.post(
    "/logistic-inventories/{inventory_uid}/discrepancies/"
    "{unit_uid}/move-to-actual",
    response_model=LogisticInventoryRead,
)
def api_move_logistic_inventory_unit_to_actual(
    inventory_uid: str,
    unit_uid: str,
    payload: LogisticInventoryResolveRequest,
    db: Session = Depends(get_db),
) -> dict:
    inventory = move_logistic_inventory_unit_to_actual(
        db,
        inventory_uid,
        unit_uid,
        payload,
    )
    return logistic_inventory_payload(db, inventory)


@router.post("/logistic-tasks", response_model=LogisticTaskRead)
def api_create_logistic_task(
    payload: LogisticTaskCreate,
    db: Session = Depends(get_db),
) -> dict:
    return logistic_task_payload(db, create_logistic_task(db, payload))


@router.get("/logistic-tasks", response_model=list[LogisticTaskRead])
def api_list_logistic_tasks(
    warehouse_code: str | None = Query(default=None),
    status_filter: list[str] | None = Query(default=None, alias="status"),
    task_type: TaskType | None = Query(default=None),
    assigned_to: str | None = Query(default=None, max_length=80),
    include_unassigned: bool = False,
    object_uid: str | None = Query(default=None, max_length=120),
    limit: int = Query(default=200, ge=1, le=500),
    db: Session = Depends(get_db),
) -> list[dict]:
    query = select(LogisticTask).order_by(LogisticTask.created_at).limit(limit)
    if warehouse_code:
        warehouse = db.scalar(
            select(Warehouse).where(
                Warehouse.code == warehouse_code.strip().upper()
            )
        )
        if warehouse is None:
            raise not_found("warehouse")
        query = query.where(LogisticTask.warehouse_id == warehouse.id)
    if status_filter:
        query = query.where(LogisticTask.status.in_(status_filter))
    if task_type is not None:
        query = query.where(LogisticTask.task_type == task_type)
    if assigned_to:
        assignment = LogisticTask.assigned_to == assigned_to
        if include_unassigned:
            assignment = or_(assignment, LogisticTask.assigned_to.is_(None))
        query = query.where(assignment)
    if object_uid:
        query = query.where(
            LogisticTask.object_uid == object_uid.strip().upper()
        )
    tasks = list(db.scalars(query))
    status_order = {
        TaskStatus.IN_PROGRESS: 0,
        TaskStatus.NEW: 1,
        TaskStatus.COMPLETED: 2,
        TaskStatus.CANCELLED: 3,
    }
    priority_order = {"urgent": 0, "high": 1, "normal": 2, "low": 3}
    tasks.sort(
        key=lambda task: (
            status_order.get(task.status, 9),
            priority_order.get(task.priority.value, 9),
            task.created_at,
        )
    )
    return [logistic_task_payload(db, task) for task in tasks]


@router.post(
    "/logistic-tasks/sync",
    response_model=list[LogisticTaskRead],
)
def api_sync_logistic_tasks(
    payload: TaskSyncRequest,
    db: Session = Depends(get_db),
) -> list[dict]:
    tasks = sync_logistic_tasks(
        db,
        warehouse_code=payload.warehouse_code,
        actor=payload.actor,
    )
    priority_order = {"urgent": 0, "high": 1, "normal": 2, "low": 3}
    tasks.sort(
        key=lambda task: (
            priority_order.get(task.priority.value, 9),
            task.created_at,
        )
    )
    return [logistic_task_payload(db, task) for task in tasks]


@router.get(
    "/logistic-tasks/{task_uid}",
    response_model=LogisticTaskRead,
)
def api_get_logistic_task(
    task_uid: str,
    db: Session = Depends(get_db),
) -> dict:
    return logistic_task_payload(db, get_logistic_task(db, task_uid))


@router.post(
    "/logistic-tasks/{task_uid}/start",
    response_model=LogisticTaskRead,
)
def api_start_logistic_task(
    task_uid: str,
    payload: TaskActionRequest,
    db: Session = Depends(get_db),
) -> dict:
    task = start_logistic_task(db, task_uid, actor=payload.actor)
    return logistic_task_payload(db, task)


@router.post(
    "/logistic-tasks/{task_uid}/assign",
    response_model=LogisticTaskRead,
)
def api_assign_logistic_task(
    task_uid: str,
    payload: TaskAssignRequest,
    db: Session = Depends(get_db),
) -> dict:
    task = assign_logistic_task(
        db,
        task_uid,
        assigned_to=payload.assigned_to,
        actor=payload.actor,
    )
    return logistic_task_payload(db, task)


@router.post(
    "/logistic-tasks/{task_uid}/complete",
    response_model=LogisticTaskRead,
)
def api_complete_logistic_task(
    task_uid: str,
    payload: TaskActionRequest,
    db: Session = Depends(get_db),
) -> dict:
    task = complete_logistic_task(db, task_uid, actor=payload.actor)
    return logistic_task_payload(db, task)


@router.post(
    "/logistic-tasks/{task_uid}/cancel",
    response_model=LogisticTaskRead,
)
def api_cancel_logistic_task(
    task_uid: str,
    payload: TaskActionRequest,
    db: Session = Depends(get_db),
) -> dict:
    task = cancel_logistic_task(db, task_uid, actor=payload.actor)
    return logistic_task_payload(db, task)


@router.post(
    "/logistic-tasks/{task_uid}/reopen",
    response_model=LogisticTaskRead,
)
def api_reopen_logistic_task(
    task_uid: str,
    payload: TaskActionRequest,
    db: Session = Depends(get_db),
) -> dict:
    task = reopen_logistic_task(db, task_uid, actor=payload.actor)
    return logistic_task_payload(db, task)


@router.get(
    "/logistic-tasks/{task_uid}/events",
    response_model=list[EventRead],
)
def api_logistic_task_events(
    task_uid: str,
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
) -> list[OperationEvent]:
    task = get_logistic_task(db, task_uid)
    return list(
        db.scalars(
            select(OperationEvent)
            .where(
                OperationEvent.object_type == "logistic_task",
                OperationEvent.object_uid == task.task_uid,
            )
            .order_by(OperationEvent.created_at.desc())
            .limit(limit)
        )
    )


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


@router.post("/aisles", response_model=AisleRead)
def api_create_aisle(payload: AisleCreate, db: Session = Depends(get_db)) -> Aisle:
    return create_aisle(db, payload)


@router.get("/aisles", response_model=list[AisleRead])
def api_list_aisles(db: Session = Depends(get_db)) -> list[Aisle]:
    return list(db.scalars(select(Aisle).order_by(Aisle.zone_id, Aisle.sort_order, Aisle.code)))


@router.post("/racks", response_model=RackRead)
def api_create_rack(payload: RackCreate, db: Session = Depends(get_db)) -> Rack:
    return create_rack(db, payload)


@router.get("/racks", response_model=list[RackRead])
def api_list_racks(db: Session = Depends(get_db)) -> list[Rack]:
    return list(db.scalars(select(Rack).order_by(Rack.aisle_id, Rack.sort_order, Rack.code)))


@router.post("/rack-sections", response_model=RackSectionRead)
def api_create_rack_section(
    payload: RackSectionCreate,
    db: Session = Depends(get_db),
) -> RackSection:
    return create_rack_section(db, payload)


@router.get("/rack-sections", response_model=list[RackSectionRead])
def api_list_rack_sections(db: Session = Depends(get_db)) -> list[RackSection]:
    return list(
        db.scalars(
            select(RackSection).order_by(
                RackSection.rack_id,
                RackSection.sort_order,
                RackSection.code,
            )
        )
    )


@router.post("/rack-levels", response_model=RackLevelRead)
def api_create_rack_level(
    payload: RackLevelCreate,
    db: Session = Depends(get_db),
) -> RackLevel:
    return create_rack_level(db, payload)


@router.get("/rack-levels", response_model=list[RackLevelRead])
def api_list_rack_levels(db: Session = Depends(get_db)) -> list[RackLevel]:
    return list(
        db.scalars(
            select(RackLevel).order_by(
                RackLevel.section_id,
                RackLevel.sort_order,
                RackLevel.code,
            )
        )
    )


@router.get("/warehouses/{warehouse_code}/address-tree")
def api_warehouse_address_tree(
    warehouse_code: str,
    db: Session = Depends(get_db),
) -> dict:
    warehouse = db.scalar(
        select(Warehouse).where(func.upper(Warehouse.code) == warehouse_code.strip().upper())
    )
    if warehouse is None:
        raise not_found("warehouse")
    zones = list(
        db.scalars(select(Zone).where(Zone.warehouse_id == warehouse.id).order_by(Zone.code))
    )
    zone_ids = [zone.id for zone in zones]
    aisles = list(
        db.scalars(
            select(Aisle)
            .where(Aisle.zone_id.in_(zone_ids))
            .order_by(Aisle.zone_id, Aisle.sort_order, Aisle.code)
        )
    ) if zone_ids else []
    aisle_ids = [aisle.id for aisle in aisles]
    racks = list(
        db.scalars(
            select(Rack)
            .where(Rack.aisle_id.in_(aisle_ids))
            .order_by(Rack.aisle_id, Rack.sort_order, Rack.code)
        )
    ) if aisle_ids else []
    rack_ids = [rack.id for rack in racks]
    sections = list(
        db.scalars(
            select(RackSection)
            .where(RackSection.rack_id.in_(rack_ids))
            .order_by(RackSection.rack_id, RackSection.sort_order, RackSection.code)
        )
    ) if rack_ids else []
    section_ids = [section.id for section in sections]
    levels = list(
        db.scalars(
            select(RackLevel)
            .where(RackLevel.section_id.in_(section_ids))
            .order_by(RackLevel.section_id, RackLevel.sort_order, RackLevel.code)
        )
    ) if section_ids else []
    locations = list(
        db.scalars(
            select(Location)
            .where(Location.zone_id.in_(zone_ids))
            .order_by(Location.zone_id, Location.level_id, Location.position_code, Location.code)
        )
    ) if zone_ids else []

    def group_by(rows: list, key: str) -> dict[int, list]:
        result: dict[int, list] = {}
        for row in rows:
            value = getattr(row, key)
            if value is not None:
                result.setdefault(value, []).append(row)
        return result

    aisles_by_zone = group_by(aisles, "zone_id")
    racks_by_aisle = group_by(racks, "aisle_id")
    sections_by_rack = group_by(sections, "rack_id")
    levels_by_section = group_by(levels, "section_id")
    positions_by_level = group_by(
        [location for location in locations if location.level_id is not None],
        "level_id",
    )
    zone_locations_by_zone = group_by(
        [location for location in locations if location.level_id is None],
        "zone_id",
    )
    result_zones = []
    for zone in zones:
        aisle_rows = []
        for aisle in aisles_by_zone.get(zone.id, []):
            rack_rows = []
            for rack in racks_by_aisle.get(aisle.id, []):
                section_rows = []
                for section in sections_by_rack.get(rack.id, []):
                    level_rows = []
                    for level in levels_by_section.get(section.id, []):
                        level_rows.append(
                            {
                                "id": level.id,
                                "code": level.code,
                                "name": level.name,
                                "elevation_mm": level.elevation_mm,
                                "positions": [
                                    {
                                        "id": location.id,
                                        "code": location.code,
                                        "position_code": location.position_code,
                                        "name": location.name,
                                        "capacity_units": location.capacity_units,
                                        "is_active": location.is_active,
                                    }
                                    for location in positions_by_level.get(level.id, [])
                                ],
                            }
                        )
                    section_rows.append(
                        {"id": section.id, "code": section.code, "name": section.name, "levels": level_rows}
                    )
                rack_rows.append(
                    {"id": rack.id, "code": rack.code, "name": rack.name, "sections": section_rows}
                )
            aisle_rows.append(
                {"id": aisle.id, "code": aisle.code, "name": aisle.name, "racks": rack_rows}
            )
        result_zones.append(
            {
                "id": zone.id,
                "code": zone.code,
                "name": zone.name,
                "kind": zone.kind,
                "zone_locations": [
                    {"id": location.id, "code": location.code, "name": location.name}
                    for location in zone_locations_by_zone.get(zone.id, [])
                ],
                "aisles": aisle_rows,
            }
        )
    return {
        "warehouse": {"id": warehouse.id, "code": warehouse.code, "name": warehouse.name},
        "zones": result_zones,
    }


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


@router.get("/labels/logistic-units.pdf")
def api_logistic_unit_labels(
    unit_uid_filter: list[str] | None = Query(default=None, alias="unit_uid"),
    type_code: str | None = Query(default=None),
    status_filter: list[str] | None = Query(default=None, alias="status"),
    warehouse_code: str | None = Query(default=None),
    limit: int = Query(default=200, ge=1, le=400),
    db: Session = Depends(get_db),
) -> Response:
    stmt = select(LogisticUnit).where(LogisticUnit.parent_unit_id.is_(None))
    unit_uids = query_values(unit_uid_filter)
    statuses = query_values(status_filter)
    if unit_uids:
        stmt = stmt.where(LogisticUnit.uid.in_(unit_uids))
    if type_code:
        unit_type = db.scalar(
            select(LogisticUnitType).where(
                func.upper(LogisticUnitType.code) == type_code.strip().upper()
            )
        )
        if unit_type is None:
            raise not_found("logistic_unit_type")
        stmt = stmt.where(LogisticUnit.type_id == unit_type.id)
    if statuses:
        try:
            status_values = [LogisticUnitStatus(value) for value in statuses]
        except ValueError as exc:
            raise bad_request("unknown logistic unit status") from exc
        stmt = stmt.where(LogisticUnit.status.in_(status_values))
    if warehouse_code:
        warehouse = db.scalar(
            select(Warehouse).where(
                func.upper(Warehouse.code) == warehouse_code.strip().upper()
            )
        )
        if warehouse is None:
            raise not_found("warehouse")
        stmt = stmt.where(
            LogisticUnit.current_location_id.in_(
                select(Location.id).where(Location.warehouse_id == warehouse.id)
            )
        )
    units = list(db.scalars(stmt.order_by(LogisticUnit.uid).limit(limit)))
    content = build_labels_pdf(
        [logistic_unit_label_item(db, unit) for unit in units],
        title="Этикетки логистических единиц",
    )
    return pdf_response(content, "logistic-unit-labels.pdf")


@router.get("/locations/{location_code}/label.pdf")
def api_location_label(location_code: str, db: Session = Depends(get_db)) -> Response:
    location = db.scalar(select(Location).where(Location.code == location_code))
    if location is None:
        raise not_found("location")
    content = build_labels_pdf([location_label_item(location)], title=f"Этикетка ячейки {location.code}")
    return pdf_response(content, f"location-{location.code}.pdf")


@router.post("/locations/{location_code}/label.print")
def api_print_location_label(location_code: str, db: Session = Depends(get_db)) -> dict:
    location = db.scalar(select(Location).where(Location.code == location_code))
    if location is None:
        raise not_found("location")
    return thermal_print_response(location_label_item(location))


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


@router.post("/demo/logistic-units", response_model=DemoGenerateRead)
def api_generate_demo_logistic_units(
    payload: DemoLogisticUnitsRequest,
    db: Session = Depends(get_db),
) -> dict:
    return generate_demo_logistic_units(db, payload)


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
