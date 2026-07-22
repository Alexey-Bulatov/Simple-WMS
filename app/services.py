from __future__ import annotations

from datetime import date
from uuid import uuid4

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.constants import (
    BOX_CODE_PREFIX,
    CODE_SEPARATOR,
    DEFAULT_CITY,
    DEFAULT_UNIT,
    INVENTORY_CODE_PREFIX,
    PALLET_CODE_PREFIX,
    RECEIVING_LOCATION_SUFFIX,
    RECEIVING_ZONE_CODE,
    RECEIVING_ZONE_NAME,
    SHIPMENT_CODE_PREFIX,
    STORAGE_LOCATION_PATTERN,
    STORAGE_ZONE_CODE,
    STORAGE_ZONE_NAME,
)
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
    Zone,
    utcnow,
)
from app.models.enums import BoxStatus, InventoryLineStatus, InventoryStatus, LocationKind, PalletStatus, ShipmentStatus
from app.schemas import (
    BatchCreate,
    DemoCatalogRequest,
    DemoPalletsRequest,
    InventoryStartRequest,
    LocationCreate,
    ProductCreate,
    ShipmentCreate,
    UserCreate,
    WarehouseCreate,
    ZoneCreate,
)


def not_found(name: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"{name} not found")


def bad_request(message: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=message)


def create_event(
    db: Session,
    *,
    operation: str,
    object_type: str,
    object_uid: str,
    actor: str = "system",
    reason: str | None = None,
    before: dict | None = None,
    after: dict | None = None,
) -> OperationEvent:
    event = OperationEvent(
        operation=operation,
        object_type=object_type,
        object_uid=object_uid,
        actor=actor,
        reason=reason,
        before=before,
        after=after,
    )
    db.add(event)
    return event


def commit_or_409(db: Session, message: str) -> None:
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=message) from exc


def create_user(db: Session, payload: UserCreate) -> User:
    user = User(**payload.model_dump())
    db.add(user)
    commit_or_409(db, "user already exists")
    db.refresh(user)
    return user


def create_product(db: Session, payload: ProductCreate) -> Product:
    product = Product(**payload.model_dump())
    db.add(product)
    commit_or_409(db, "product already exists")
    db.refresh(product)
    return product


def create_batch(db: Session, payload: BatchCreate) -> Batch:
    product = db.get(Product, payload.product_id)
    if product is None:
        raise not_found("product")
    if payload.expiry_date <= payload.production_date:
        raise bad_request("expiry_date must be after production_date")
    batch = Batch(**payload.model_dump())
    db.add(batch)
    commit_or_409(db, "batch already exists for this product")
    db.refresh(batch)
    return batch


def create_warehouse(db: Session, payload: WarehouseCreate) -> Warehouse:
    warehouse = Warehouse(**payload.model_dump())
    db.add(warehouse)
    commit_or_409(db, "warehouse already exists")
    db.refresh(warehouse)
    return warehouse


def create_zone(db: Session, payload: ZoneCreate) -> Zone:
    warehouse = db.get(Warehouse, payload.warehouse_id)
    if warehouse is None:
        raise not_found("warehouse")
    zone = Zone(**payload.model_dump())
    db.add(zone)
    commit_or_409(db, "zone already exists in this warehouse")
    db.refresh(zone)
    return zone


def create_location(db: Session, payload: LocationCreate) -> Location:
    warehouse = db.get(Warehouse, payload.warehouse_id)
    if warehouse is None:
        raise not_found("warehouse")
    zone = db.get(Zone, payload.zone_id)
    if zone is None:
        raise not_found("zone")
    if zone.warehouse_id != warehouse.id:
        raise bad_request("zone belongs to another warehouse")
    location = Location(**payload.model_dump())
    db.add(location)
    commit_or_409(db, "location already exists")
    db.refresh(location)
    return location


def generate_box_uid(db: Session) -> str:
    while True:
        candidate = f"{BOX_CODE_PREFIX}{CODE_SEPARATOR}{uuid4().hex[:14].upper()}"
        exists = db.scalar(select(Box.id).where(Box.box_uid == candidate))
        if not exists:
            return candidate


def generate_pallet_uid(db: Session) -> str:
    while True:
        candidate = f"{PALLET_CODE_PREFIX}{CODE_SEPARATOR}{uuid4().hex[:12].upper()}"
        exists = db.scalar(select(Pallet.id).where(Pallet.pallet_uid == candidate))
        if not exists:
            return candidate


def generate_shipment_uid(db: Session) -> str:
    while True:
        candidate = f"{SHIPMENT_CODE_PREFIX}{CODE_SEPARATOR}{uuid4().hex[:10].upper()}"
        exists = db.scalar(select(Shipment.id).where(Shipment.shipment_uid == candidate))
        if not exists:
            return candidate


def generate_inventory_uid(db: Session) -> str:
    while True:
        candidate = f"{INVENTORY_CODE_PREFIX}{CODE_SEPARATOR}{uuid4().hex[:10].upper()}"
        exists = db.scalar(select(InventorySession.id).where(InventorySession.inventory_uid == candidate))
        if not exists:
            return candidate


def generate_boxes(db: Session, *, batch_id: int, quantity: int, actor: str = "system") -> list[Box]:
    batch = db.get(Batch, batch_id)
    if batch is None:
        raise not_found("batch")
    boxes: list[Box] = []
    for _ in range(quantity):
        box = Box(box_uid=generate_box_uid(db), product_id=batch.product_id, batch_id=batch.id)
        db.add(box)
        boxes.append(box)
    create_event(
        db,
        operation="boxes_generated",
        object_type="batch",
        object_uid=batch.batch_number,
        actor=actor,
        after={"quantity": quantity},
    )
    db.commit()
    for box in boxes:
        db.refresh(box)
    return boxes


def ensure_demo_catalog(db: Session, payload: DemoCatalogRequest) -> dict:
    created = {
        "created_products": 0,
        "created_batches": 0,
        "created_warehouses": 0,
        "created_zones": 0,
        "created_locations": 0,
        "product_ids": [],
        "batch_ids": [],
    }
    warehouse = db.scalar(select(Warehouse).where(Warehouse.code == payload.warehouse_code))
    if warehouse is None:
        warehouse = create_warehouse(
            db,
            WarehouseCreate(
                code=payload.warehouse_code,
                name=payload.warehouse_name,
                city=DEFAULT_CITY,
            ),
        )
        created["created_warehouses"] += 1

    storage = db.scalar(select(Zone).where(Zone.warehouse_id == warehouse.id, Zone.code == STORAGE_ZONE_CODE))
    if storage is None:
        storage = create_zone(
            db,
            ZoneCreate(
                warehouse_id=warehouse.id,
                code=STORAGE_ZONE_CODE,
                name=STORAGE_ZONE_NAME,
                kind=LocationKind.STORAGE,
            ),
        )
        created["created_zones"] += 1
    receiving = db.scalar(select(Zone).where(Zone.warehouse_id == warehouse.id, Zone.code == RECEIVING_ZONE_CODE))
    if receiving is None:
        receiving = create_zone(
            db,
            ZoneCreate(
                warehouse_id=warehouse.id,
                code=RECEIVING_ZONE_CODE,
                name=RECEIVING_ZONE_NAME,
                kind=LocationKind.RECEIVING,
            ),
        )
        created["created_zones"] += 1

    receiving_code = f"{warehouse.code}{CODE_SEPARATOR}{RECEIVING_ZONE_CODE}{CODE_SEPARATOR}{RECEIVING_LOCATION_SUFFIX}"
    if db.scalar(select(Location.id).where(Location.code == receiving_code)) is None:
        create_location(
            db,
            LocationCreate(
                warehouse_id=warehouse.id,
                zone_id=receiving.id,
                code=receiving_code,
                name="Приемка палет 1",
                kind=LocationKind.RECEIVING,
                capacity_pallets=4,
            ),
        )
        created["created_locations"] += 1

    for idx in range(1, payload.storage_locations + 1):
        code = f"{warehouse.code}{CODE_SEPARATOR}{STORAGE_ZONE_CODE}{CODE_SEPARATOR}{STORAGE_LOCATION_PATTERN.format(index=idx)}"
        if db.scalar(select(Location.id).where(Location.code == code)) is None:
            create_location(
                db,
                LocationCreate(
                    warehouse_id=warehouse.id,
                    zone_id=storage.id,
                    code=code,
                    name=f"Палетоместо {idx}",
                    kind=LocationKind.STORAGE,
                    capacity_pallets=1,
                ),
            )
            created["created_locations"] += 1

    demo_products = [
        ("ICE-VAN-100", "Мороженое ванильное 100 г", 24, 96, 365),
        ("ICE-CHO-100", "Мороженое шоколадное 100 г", 20, 96, 365),
        ("ICE-BER-80", "Пломбир ягодный 80 г", 30, 80, 300),
    ]
    production_date, expiry_date = seed_batch_dates()
    for code, name, quantity_per_box, boxes_per_pallet, shelf_life_days in demo_products:
        product = db.scalar(select(Product).where(Product.code == code))
        if product is None:
            product = create_product(
                db,
                ProductCreate(
                    code=code,
                    name=name,
                    unit=DEFAULT_UNIT,
                    quantity_per_box=quantity_per_box,
                    boxes_per_pallet=boxes_per_pallet,
                    shelf_life_days=shelf_life_days,
                ),
            )
            created["created_products"] += 1
        created["product_ids"].append(product.id)
        batch_number = f"DEMO-{code}-20260721"
        batch = db.scalar(select(Batch).where(Batch.product_id == product.id, Batch.batch_number == batch_number))
        if batch is None:
            batch = create_batch(
                db,
                BatchCreate(
                    product_id=product.id,
                    batch_number=batch_number,
                    production_date=production_date,
                    expiry_date=expiry_date,
                ),
            )
            created["created_batches"] += 1
        created["batch_ids"].append(batch.id)

    create_event(
        db,
        operation="demo_catalog_generated",
        object_type="warehouse",
        object_uid=warehouse.code,
        actor=payload.actor,
        after=created,
    )
    db.commit()
    return created


def empty_storage_locations(db: Session) -> list[Location]:
    locations = list(
        db.scalars(
            select(Location)
            .where(Location.kind == LocationKind.STORAGE, Location.is_active.is_(True))
            .order_by(Location.code)
        )
    )
    return [location for location in locations if location_occupied_count(db, location.id) < location.capacity_pallets]


def generate_demo_pallets(db: Session, payload: DemoPalletsRequest) -> dict:
    batch = db.get(Batch, payload.batch_id) if payload.batch_id else None
    if batch is None:
        batch = db.scalar(select(Batch).order_by(Batch.id))
    if batch is None:
        raise bad_request("create demo catalog first")
    product = db.get(Product, batch.product_id)
    if product is None:
        raise not_found("product")
    if payload.boxes_per_pallet > product.boxes_per_pallet:
        raise bad_request("boxes_per_pallet exceeds product capacity")

    result = {
        "created_products": 0,
        "created_batches": 0,
        "created_warehouses": 0,
        "created_zones": 0,
        "created_locations": 0,
        "created_boxes": 0,
        "created_pallets": 0,
        "placed_pallets": 0,
        "waiting_pallets": 0,
        "product_ids": [product.id],
        "batch_ids": [batch.id],
        "pallet_uids": [],
    }
    for _ in range(payload.quantity):
        boxes = generate_boxes(db, batch_id=batch.id, quantity=payload.boxes_per_pallet, actor=payload.actor)
        result["created_boxes"] += len(boxes)
        pallet = open_pallet(db, actor=payload.actor)
        for box in boxes:
            accept_box(db, box_uid=box.box_uid, actor=payload.actor)
            add_box_to_pallet(db, pallet_uid=pallet.pallet_uid, box_uid=box.box_uid, actor=payload.actor)
        close_pallet(db, pallet_uid=pallet.pallet_uid, actor=payload.actor, reason="demo")
        result["created_pallets"] += 1
        if payload.place_to_empty_locations:
            free_locations = empty_storage_locations(db)
            if free_locations:
                place_pallet(
                    db,
                    pallet_uid=pallet.pallet_uid,
                    location_code=free_locations[0].code,
                    actor=payload.actor,
                    reason="demo auto placement",
                )
                result["placed_pallets"] += 1
            else:
                result["waiting_pallets"] += 1
        else:
            result["waiting_pallets"] += 1
        result["pallet_uids"].append(pallet.pallet_uid)

    create_event(
        db,
        operation="demo_pallets_generated",
        object_type="batch",
        object_uid=batch.batch_number,
        actor=payload.actor,
        after=result,
    )
    db.commit()
    return result


def accept_box(db: Session, *, box_uid: str, actor: str = "system") -> Box:
    box = db.scalar(select(Box).where(Box.box_uid == box_uid))
    if box is None:
        raise not_found("box")
    if box.status != BoxStatus.LABEL_CREATED:
        raise bad_request(f"box cannot be accepted from status {box.status}")
    before = {"status": box.status}
    box.status = BoxStatus.ACCEPTED_FROM_PRODUCTION
    box.accepted_at = utcnow()
    create_event(
        db,
        operation="box_accepted",
        object_type="box",
        object_uid=box.box_uid,
        actor=actor,
        before=before,
        after={"status": box.status},
    )
    db.commit()
    db.refresh(box)
    return box


def open_pallet(db: Session, *, actor: str = "system") -> Pallet:
    pallet = Pallet(pallet_uid=generate_pallet_uid(db))
    db.add(pallet)
    create_event(
        db,
        operation="pallet_opened",
        object_type="pallet",
        object_uid=pallet.pallet_uid,
        actor=actor,
        after={"status": PalletStatus.OPEN},
    )
    db.commit()
    db.refresh(pallet)
    return pallet


def add_box_to_pallet(db: Session, *, pallet_uid: str, box_uid: str, actor: str = "system") -> Pallet:
    pallet = db.scalar(select(Pallet).where(Pallet.pallet_uid == pallet_uid))
    if pallet is None:
        raise not_found("pallet")
    box = db.scalar(select(Box).where(Box.box_uid == box_uid))
    if box is None:
        raise not_found("box")
    if pallet.status != PalletStatus.OPEN:
        raise bad_request("only open pallet can accept boxes")
    if box.status != BoxStatus.ACCEPTED_FROM_PRODUCTION:
        raise bad_request(f"box cannot be added from status {box.status}")
    if box.current_pallet_id is not None:
        raise bad_request("box already belongs to a pallet")
    if pallet.product_id is not None and pallet.product_id != box.product_id:
        raise bad_request("box product does not match pallet product")
    if pallet.batch_id is not None and pallet.batch_id != box.batch_id:
        raise bad_request("box batch does not match pallet batch")
    if pallet.product_id is None:
        pallet.product_id = box.product_id
        pallet.batch_id = box.batch_id
    product = db.get(Product, box.product_id)
    current_count = db.scalar(select(func.count(PalletBox.id)).where(PalletBox.pallet_id == pallet.id)) or 0
    if product and current_count >= product.boxes_per_pallet:
        raise bad_request("pallet capacity for this product is already reached")

    box.current_pallet_id = pallet.id
    box.status = BoxStatus.IN_OPEN_PALLET
    db.add(PalletBox(pallet_id=pallet.id, box_id=box.id))
    create_event(
        db,
        operation="box_added_to_pallet",
        object_type="pallet",
        object_uid=pallet.pallet_uid,
        actor=actor,
        after={"box_uid": box.box_uid, "box_count": current_count + 1},
    )
    commit_or_409(db, "box already belongs to a pallet")
    db.refresh(pallet)
    return pallet


def close_pallet(db: Session, *, pallet_uid: str, actor: str = "system", reason: str | None = None) -> Pallet:
    pallet = db.scalar(select(Pallet).where(Pallet.pallet_uid == pallet_uid))
    if pallet is None:
        raise not_found("pallet")
    if pallet.status != PalletStatus.OPEN:
        raise bad_request("only open pallet can be closed")
    box_count = db.scalar(select(func.count(PalletBox.id)).where(PalletBox.pallet_id == pallet.id)) or 0
    if box_count == 0:
        raise bad_request("empty pallet cannot be closed")
    before = {"status": pallet.status}
    pallet.status = PalletStatus.AVAILABLE if pallet.current_location_id else PalletStatus.WAITING_PLACEMENT
    pallet.closed_at = utcnow()
    db.query(Box).filter(Box.current_pallet_id == pallet.id).update({"status": BoxStatus.IN_CLOSED_PALLET})
    create_event(
        db,
        operation="pallet_closed",
        object_type="pallet",
        object_uid=pallet.pallet_uid,
        actor=actor,
        reason=reason,
        before=before,
        after={"status": pallet.status, "box_count": box_count},
    )
    db.commit()
    db.refresh(pallet)
    return pallet


def reopen_pallet(db: Session, *, pallet_uid: str, actor: str = "system", reason: str) -> Pallet:
    pallet = db.scalar(select(Pallet).where(Pallet.pallet_uid == pallet_uid))
    if pallet is None:
        raise not_found("pallet")
    if pallet.status not in {PalletStatus.CLOSED, PalletStatus.WAITING_PLACEMENT, PalletStatus.AVAILABLE}:
        raise bad_request(f"pallet cannot be reopened from status {pallet.status}")
    box_count = db.scalar(select(func.count(PalletBox.id)).where(PalletBox.pallet_id == pallet.id)) or 0
    if box_count == 0:
        raise bad_request("empty pallet does not need reopening")
    before = {"status": pallet.status, "location_id": pallet.current_location_id, "box_count": box_count}
    pallet.status = PalletStatus.OPEN
    pallet.closed_at = None
    db.query(Box).filter(Box.current_pallet_id == pallet.id).update({"status": BoxStatus.IN_OPEN_PALLET})
    create_event(
        db,
        operation="pallet_reopened",
        object_type="pallet",
        object_uid=pallet.pallet_uid,
        actor=actor,
        reason=reason,
        before=before,
        after={"status": pallet.status, "box_count": box_count},
    )
    db.commit()
    db.refresh(pallet)
    return pallet


def set_pallet_problem_status(
    db: Session,
    *,
    pallet_uid: str,
    target_status: PalletStatus,
    actor: str = "system",
    reason: str,
) -> Pallet:
    pallet = db.scalar(select(Pallet).where(Pallet.pallet_uid == pallet_uid))
    if pallet is None:
        raise not_found("pallet")
    if target_status not in {PalletStatus.BLOCKED, PalletStatus.QUARANTINE}:
        raise bad_request("target status must be blocked or quarantine")
    if pallet.status in {PalletStatus.SHIPPED, PalletStatus.WRITTEN_OFF, PalletStatus.DISASSEMBLED}:
        raise bad_request(f"pallet cannot be changed from status {pallet.status}")
    before = {"status": pallet.status}
    pallet.status = target_status
    create_event(
        db,
        operation=f"pallet_{target_status.value}",
        object_type="pallet",
        object_uid=pallet.pallet_uid,
        actor=actor,
        reason=reason,
        before=before,
        after={"status": pallet.status},
    )
    db.commit()
    db.refresh(pallet)
    return pallet


def release_pallet(db: Session, *, pallet_uid: str, actor: str = "system", reason: str) -> Pallet:
    pallet = db.scalar(select(Pallet).where(Pallet.pallet_uid == pallet_uid))
    if pallet is None:
        raise not_found("pallet")
    if pallet.status not in {PalletStatus.BLOCKED, PalletStatus.QUARANTINE}:
        raise bad_request("only blocked or quarantine pallet can be released")
    box_count = db.scalar(select(func.count(PalletBox.id)).where(PalletBox.pallet_id == pallet.id)) or 0
    before = {"status": pallet.status}
    if box_count == 0:
        pallet.status = PalletStatus.OPEN
    elif pallet.current_location_id:
        pallet.status = PalletStatus.AVAILABLE
    else:
        pallet.status = PalletStatus.WAITING_PLACEMENT
    create_event(
        db,
        operation="pallet_released",
        object_type="pallet",
        object_uid=pallet.pallet_uid,
        actor=actor,
        reason=reason,
        before=before,
        after={"status": pallet.status},
    )
    db.commit()
    db.refresh(pallet)
    return pallet


def location_occupied_count(db: Session, location_id: int) -> int:
    return db.scalar(select(func.count(Pallet.id)).where(Pallet.current_location_id == location_id)) or 0


def place_pallet(db: Session, *, pallet_uid: str, location_code: str, actor: str = "system", reason: str | None = None) -> Pallet:
    pallet = db.scalar(select(Pallet).where(Pallet.pallet_uid == pallet_uid))
    if pallet is None:
        raise not_found("pallet")
    location = db.scalar(select(Location).where(Location.code == location_code))
    if location is None:
        raise not_found("location")
    if not location.is_active:
        raise bad_request("location is not active")
    if location.kind != LocationKind.STORAGE:
        raise bad_request("pallet can be placed only in a storage location")
    if pallet.status not in {PalletStatus.CLOSED, PalletStatus.WAITING_PLACEMENT}:
        raise bad_request(f"pallet cannot be placed from status {pallet.status}")
    current_location = db.get(Location, pallet.current_location_id) if pallet.current_location_id else None
    if (
        current_location is not None
        and current_location.kind == LocationKind.TRANSFER_IN
        and current_location.warehouse_id != location.warehouse_id
    ):
        raise bad_request("received pallet can be placed only at the destination warehouse")
    if location_occupied_count(db, location.id) >= location.capacity_pallets:
        raise bad_request("location capacity is already reached")
    before = {"status": pallet.status, "location_id": pallet.current_location_id}
    pallet.current_location_id = location.id
    pallet.status = PalletStatus.AVAILABLE
    create_event(
        db,
        operation="pallet_placed",
        object_type="pallet",
        object_uid=pallet.pallet_uid,
        actor=actor,
        reason=reason,
        before=before,
        after={"status": pallet.status, "location_code": location.code},
    )
    db.commit()
    db.refresh(pallet)
    return pallet


def move_pallet(db: Session, *, pallet_uid: str, location_code: str, actor: str = "system", reason: str | None = None) -> Pallet:
    pallet = db.scalar(select(Pallet).where(Pallet.pallet_uid == pallet_uid))
    if pallet is None:
        raise not_found("pallet")
    location = db.scalar(select(Location).where(Location.code == location_code))
    if location is None:
        raise not_found("location")
    if not location.is_active or location.kind != LocationKind.STORAGE:
        raise bad_request("pallet can be moved only to an active storage location")
    if pallet.status != PalletStatus.AVAILABLE:
        raise bad_request(f"pallet cannot be moved from status {pallet.status}")
    if pallet.current_location_id == location.id:
        raise bad_request("pallet is already in this location")
    if location_occupied_count(db, location.id) >= location.capacity_pallets:
        raise bad_request("location capacity is already reached")
    before = {"location_id": pallet.current_location_id}
    pallet.current_location_id = location.id
    create_event(
        db,
        operation="pallet_moved",
        object_type="pallet",
        object_uid=pallet.pallet_uid,
        actor=actor,
        reason=reason,
        before=before,
        after={"location_code": location.code},
    )
    db.commit()
    db.refresh(pallet)
    return pallet


def seed_batch_dates() -> tuple[date, date]:
    production_date = date(2026, 7, 21)
    expiry_date = date(2027, 7, 21)
    return production_date, expiry_date


def create_shipment(db: Session, payload: ShipmentCreate) -> Shipment:
    shipment = Shipment(
        shipment_uid=generate_shipment_uid(db),
        customer_name=payload.customer_name,
        destination=payload.destination,
        planned_date=payload.planned_date,
    )
    db.add(shipment)
    create_event(
        db,
        operation="shipment_created",
        object_type="shipment",
        object_uid=shipment.shipment_uid,
        actor=payload.actor,
        after={"customer_name": shipment.customer_name, "destination": shipment.destination},
    )
    db.commit()
    db.refresh(shipment)
    return shipment


def get_shipment(db: Session, shipment_uid: str) -> Shipment:
    shipment = db.scalar(select(Shipment).where(Shipment.shipment_uid == shipment_uid))
    if shipment is None:
        raise not_found("shipment")
    return shipment


def reserve_pallet_for_shipment(
    db: Session,
    *,
    shipment_uid: str,
    pallet_uid: str,
    actor: str = "system",
) -> Shipment:
    shipment = get_shipment(db, shipment_uid)
    if shipment.status not in {ShipmentStatus.DRAFT, ShipmentStatus.RESERVED}:
        raise bad_request(f"shipment cannot accept pallets from status {shipment.status}")
    pallet = db.scalar(select(Pallet).where(Pallet.pallet_uid == pallet_uid))
    if pallet is None:
        raise not_found("pallet")
    if pallet.status != PalletStatus.AVAILABLE:
        raise bad_request(f"only available pallet can be reserved, got {pallet.status}")
    already_reserved = db.scalar(select(ShipmentPallet.id).where(ShipmentPallet.pallet_id == pallet.id))
    if already_reserved:
        raise bad_request("pallet already belongs to a shipment")

    before = {"pallet_status": pallet.status, "shipment_status": shipment.status}
    pallet.status = PalletStatus.RESERVED
    shipment.status = ShipmentStatus.RESERVED
    db.add(ShipmentPallet(shipment_id=shipment.id, pallet_id=pallet.id, status="reserved"))
    create_event(
        db,
        operation="shipment_pallet_reserved",
        object_type="shipment",
        object_uid=shipment.shipment_uid,
        actor=actor,
        before=before,
        after={"pallet_uid": pallet.pallet_uid, "shipment_status": shipment.status},
    )
    create_event(
        db,
        operation="pallet_reserved_for_shipment",
        object_type="pallet",
        object_uid=pallet.pallet_uid,
        actor=actor,
        before={"status": before["pallet_status"]},
        after={"status": pallet.status, "shipment_uid": shipment.shipment_uid},
    )
    commit_or_409(db, "pallet already belongs to a shipment")
    db.refresh(shipment)
    return shipment


def move_shipment_to_expedition(db: Session, *, shipment_uid: str, actor: str = "system") -> Shipment:
    shipment = get_shipment(db, shipment_uid)
    if shipment.status != ShipmentStatus.RESERVED:
        raise bad_request("only reserved shipment can be moved to expedition")
    links = list(db.scalars(select(ShipmentPallet).where(ShipmentPallet.shipment_id == shipment.id)))
    if not links:
        raise bad_request("shipment has no reserved pallets")
    now = utcnow()
    for link in links:
        pallet = db.get(Pallet, link.pallet_id)
        if not pallet or pallet.status != PalletStatus.RESERVED:
            raise bad_request("all shipment pallets must be reserved")
        pallet.status = PalletStatus.EXPEDITION
        link.status = "expedition"
        link.moved_to_expedition_at = now
        create_event(
            db,
            operation="pallet_moved_to_expedition",
            object_type="pallet",
            object_uid=pallet.pallet_uid,
            actor=actor,
            after={"shipment_uid": shipment.shipment_uid, "status": pallet.status},
        )
    before = {"status": shipment.status}
    shipment.status = ShipmentStatus.EXPEDITION
    create_event(
        db,
        operation="shipment_moved_to_expedition",
        object_type="shipment",
        object_uid=shipment.shipment_uid,
        actor=actor,
        before=before,
        after={"status": shipment.status, "pallet_count": len(links)},
    )
    db.commit()
    db.refresh(shipment)
    return shipment


def load_shipment_pallet(
    db: Session,
    *,
    shipment_uid: str,
    pallet_uid: str,
    actor: str = "system",
) -> Shipment:
    shipment = get_shipment(db, shipment_uid)
    if shipment.status not in {ShipmentStatus.EXPEDITION, ShipmentStatus.LOADING}:
        raise bad_request("shipment must be in expedition or loading status")
    pallet = db.scalar(select(Pallet).where(Pallet.pallet_uid == pallet_uid))
    if pallet is None:
        raise not_found("pallet")
    link = db.scalar(
        select(ShipmentPallet).where(ShipmentPallet.shipment_id == shipment.id, ShipmentPallet.pallet_id == pallet.id)
    )
    if link is None:
        raise bad_request("pallet does not belong to this shipment")
    if link.status == "loaded":
        raise bad_request("pallet already loaded")
    if pallet.status != PalletStatus.EXPEDITION:
        raise bad_request(f"pallet cannot be loaded from status {pallet.status}")

    before = {"shipment_status": shipment.status, "pallet_status": pallet.status}
    shipment.status = ShipmentStatus.LOADING
    pallet.status = PalletStatus.LOADED
    link.status = "loaded"
    link.loaded_at = utcnow()
    create_event(
        db,
        operation="shipment_pallet_loaded",
        object_type="shipment",
        object_uid=shipment.shipment_uid,
        actor=actor,
        before=before,
        after={"pallet_uid": pallet.pallet_uid, "shipment_status": shipment.status},
    )
    create_event(
        db,
        operation="pallet_loaded",
        object_type="pallet",
        object_uid=pallet.pallet_uid,
        actor=actor,
        before={"status": before["pallet_status"]},
        after={"status": pallet.status, "shipment_uid": shipment.shipment_uid},
    )
    db.commit()
    db.refresh(shipment)
    return shipment


def close_shipment(db: Session, *, shipment_uid: str, actor: str = "system", reason: str | None = None) -> Shipment:
    shipment = get_shipment(db, shipment_uid)
    if shipment.status != ShipmentStatus.LOADING:
        raise bad_request("shipment can be closed only after loading has started")
    links = list(db.scalars(select(ShipmentPallet).where(ShipmentPallet.shipment_id == shipment.id)))
    if not links:
        raise bad_request("shipment has no pallets")
    not_loaded = [link for link in links if link.status != "loaded"]
    if not_loaded:
        raise bad_request("all shipment pallets must be loaded before close")

    before = {"status": shipment.status}
    shipment.status = ShipmentStatus.COMPLETED
    shipment.closed_at = utcnow()
    for link in links:
        pallet = db.get(Pallet, link.pallet_id)
        if pallet:
            previous_location_id = pallet.current_location_id
            previous_location_code = None
            if previous_location_id:
                previous_location_code = db.scalar(select(Location.code).where(Location.id == previous_location_id))
            pallet.status = PalletStatus.SHIPPED
            pallet.current_location_id = None
            db.query(Box).filter(Box.current_pallet_id == pallet.id).update({"status": BoxStatus.SHIPPED})
            create_event(
                db,
                operation="pallet_shipped",
                object_type="pallet",
                object_uid=pallet.pallet_uid,
                actor=actor,
                reason=reason,
                before={"location_id": previous_location_id, "location_code": previous_location_code},
                after={"shipment_uid": shipment.shipment_uid, "status": pallet.status, "location_id": None},
            )
    create_event(
        db,
        operation="shipment_closed",
        object_type="shipment",
        object_uid=shipment.shipment_uid,
        actor=actor,
        reason=reason,
        before=before,
        after={"status": shipment.status, "pallet_count": len(links)},
    )
    db.commit()
    db.refresh(shipment)
    return shipment


def start_inventory(db: Session, payload: InventoryStartRequest) -> InventorySession:
    warehouse = None
    initial_location = None
    if payload.warehouse_code:
        warehouse = db.scalar(select(Warehouse).where(Warehouse.code == payload.warehouse_code))
        if warehouse is None:
            raise not_found("warehouse")
    if payload.location_code:
        initial_location = db.scalar(select(Location).where(Location.code == payload.location_code))
        if initial_location is None:
            raise not_found("location")
        if initial_location.kind != LocationKind.STORAGE:
            raise bad_request("only storage locations are included in this inventory")
        warehouse = db.get(Warehouse, initial_location.warehouse_id)
    if warehouse is None:
        warehouse = db.scalar(select(Warehouse).order_by(Warehouse.code))
    if warehouse is None:
        raise not_found("warehouse")
    existing_open = db.scalar(
        select(InventorySession.id).where(
            InventorySession.warehouse_id == warehouse.id,
            InventorySession.status == InventoryStatus.OPEN,
        )
    )
    if existing_open:
        raise bad_request("warehouse already has open inventory")

    inventory = InventorySession(
        inventory_uid=generate_inventory_uid(db),
        warehouse_id=warehouse.id,
        location_id=initial_location.id if initial_location else None,
        current_location_id=initial_location.id if initial_location else None,
        actor=payload.actor,
    )
    db.add(inventory)
    db.flush()
    expected_stmt = select(Pallet).join(Location, Pallet.current_location_id == Location.id).where(
        Location.warehouse_id == warehouse.id,
        Location.kind == LocationKind.STORAGE,
        Location.is_active.is_(True),
    )
    if initial_location:
        expected_stmt = expected_stmt.where(Pallet.current_location_id == initial_location.id)
    expected_pallets = list(db.scalars(expected_stmt))
    for pallet in expected_pallets:
        db.add(
            InventoryLine(
                inventory_id=inventory.id,
                pallet_id=pallet.id,
                expected_location_id=pallet.current_location_id,
                status=InventoryLineStatus.EXPECTED,
            )
        )
    create_event(
        db,
        operation="inventory_started",
        object_type="inventory",
        object_uid=inventory.inventory_uid,
        actor=payload.actor,
        after={
            "warehouse_code": warehouse.code,
            "location_code": initial_location.code if initial_location else None,
            "expected_count": len(expected_pallets),
        },
    )
    db.commit()
    db.refresh(inventory)
    return inventory


def get_inventory(db: Session, inventory_uid: str) -> InventorySession:
    inventory = db.scalar(select(InventorySession).where(InventorySession.inventory_uid == inventory_uid))
    if inventory is None:
        raise not_found("inventory")
    return inventory


def inventory_scope_locations(db: Session, inventory: InventorySession) -> list[Location]:
    warehouse_id = inventory.warehouse_id
    if warehouse_id is None and inventory.location_id:
        warehouse_id = db.scalar(select(Location.warehouse_id).where(Location.id == inventory.location_id))
    if warehouse_id is None:
        return []
    stmt = select(Location).where(
        Location.warehouse_id == warehouse_id,
        Location.kind == LocationKind.STORAGE,
        Location.is_active.is_(True),
    )
    start_event = db.scalar(
        select(OperationEvent)
        .where(
            OperationEvent.object_type == "inventory",
            OperationEvent.object_uid == inventory.inventory_uid,
            OperationEvent.operation == "inventory_started",
        )
        .order_by(OperationEvent.created_at)
    )
    initial_location_code = (start_event.after or {}).get("location_code") if start_event else None
    if initial_location_code:
        stmt = stmt.where(Location.code == initial_location_code)
    return list(db.scalars(stmt.order_by(Location.code)))


def confirmed_inventory_location_codes(db: Session, inventory: InventorySession) -> set[str]:
    events = db.scalars(
        select(OperationEvent).where(
            OperationEvent.object_type == "inventory",
            OperationEvent.object_uid == inventory.inventory_uid,
            OperationEvent.operation == "inventory_location_confirmed",
        )
    )
    confirmed = set()
    for event in events:
        event_after = event.after or {}
        code = event_after.get("location_code")
        if code:
            confirmed.add(code)
    return confirmed


def unchecked_inventory_locations(db: Session, inventory: InventorySession) -> list[Location]:
    lines = list(db.scalars(select(InventoryLine).where(InventoryLine.inventory_id == inventory.id)))
    confirmed_codes = confirmed_inventory_location_codes(db, inventory)
    unchecked = []
    for location in inventory_scope_locations(db, inventory):
        expected = [line for line in lines if line.expected_location_id == location.id]
        actual = [line for line in lines if line.actual_location_id == location.id]
        checked = (
            location.code in confirmed_codes
            or bool(actual)
            or any(line.status in {InventoryLineStatus.SCANNED, InventoryLineStatus.MISSING} for line in expected)
        )
        if not checked:
            unchecked.append(location)
    return unchecked


def resolved_inventory_line_ids(db: Session, inventory: InventorySession) -> set[int]:
    events = db.scalars(
        select(OperationEvent).where(
            OperationEvent.object_type == "inventory",
            OperationEvent.object_uid == inventory.inventory_uid,
            OperationEvent.operation == "inventory_discrepancy_resolved",
        )
    )
    resolved = set()
    for event in events:
        event_after = event.after or {}
        line_id = event_after.get("line_id")
        if line_id:
            resolved.add(int(line_id))
    return resolved


def inventory_line_resolution_event(db: Session, inventory: InventorySession, line: InventoryLine) -> OperationEvent | None:
    events = db.scalars(
        select(OperationEvent)
        .where(
            OperationEvent.object_type == "inventory",
            OperationEvent.object_uid == inventory.inventory_uid,
            OperationEvent.operation == "inventory_discrepancy_resolved",
        )
        .order_by(OperationEvent.created_at.desc())
    )
    for event in events:
        event_after = event.after or {}
        if event_after.get("line_id") == line.id:
            return event
    return None


def scan_inventory_location(
    db: Session,
    *,
    inventory_uid: str,
    location_code: str,
    actor: str = "system",
) -> InventorySession:
    inventory = get_inventory(db, inventory_uid)
    if inventory.status != InventoryStatus.OPEN:
        raise bad_request("inventory is already completed")
    location = db.scalar(select(Location).where(Location.code == location_code))
    if location is None:
        raise not_found("location")
    if location.kind != LocationKind.STORAGE:
        raise bad_request("only storage locations are included in this inventory")
    if inventory.warehouse_id and location.warehouse_id != inventory.warehouse_id:
        raise bad_request("location belongs to another warehouse")
    inventory.current_location_id = location.id
    existing_expected_ids = set(
        db.scalars(
            select(InventoryLine.pallet_id).where(
                InventoryLine.inventory_id == inventory.id,
                InventoryLine.expected_location_id == location.id,
            )
        )
    )
    expected_pallets = list(db.scalars(select(Pallet).where(Pallet.current_location_id == location.id)))
    for pallet in expected_pallets:
        if pallet.id not in existing_expected_ids:
            db.add(
                InventoryLine(
                    inventory_id=inventory.id,
                    pallet_id=pallet.id,
                    expected_location_id=location.id,
                    status=InventoryLineStatus.EXPECTED,
                )
            )
    create_event(
        db,
        operation="inventory_location_scanned",
        object_type="inventory",
        object_uid=inventory.inventory_uid,
        actor=actor,
        after={"location_code": location.code, "expected_count": len(expected_pallets)},
    )
    db.commit()
    db.refresh(inventory)
    return inventory


def confirm_inventory_location(
    db: Session,
    *,
    inventory_uid: str,
    location_code: str | None = None,
    actor: str = "system",
) -> InventorySession:
    inventory = get_inventory(db, inventory_uid)
    if inventory.status != InventoryStatus.OPEN:
        raise bad_request("inventory is already completed")
    location = None
    if location_code:
        location = db.scalar(select(Location).where(Location.code == location_code))
        if location is None:
            raise not_found("location")
        if location.kind != LocationKind.STORAGE:
            raise bad_request("only storage locations are included in this inventory")
        if inventory.warehouse_id and location.warehouse_id != inventory.warehouse_id:
            raise bad_request("location belongs to another warehouse")
        inventory.current_location_id = location.id
    elif inventory.current_location_id:
        location = db.get(Location, inventory.current_location_id)
    if location is None:
        raise bad_request("scan location first")

    now = utcnow()
    missing_lines = list(
        db.scalars(
            select(InventoryLine).where(
                InventoryLine.inventory_id == inventory.id,
                InventoryLine.expected_location_id == location.id,
                InventoryLine.status == InventoryLineStatus.EXPECTED,
                InventoryLine.scanned_at.is_(None),
            )
        )
    )
    for line in missing_lines:
        line.status = InventoryLineStatus.MISSING
        line.scanned_at = now
    create_event(
        db,
        operation="inventory_location_confirmed",
        object_type="inventory",
        object_uid=inventory.inventory_uid,
        actor=actor,
        after={"location_code": location.code, "missing_count": len(missing_lines)},
    )
    inventory.current_location_id = None
    db.commit()
    db.refresh(inventory)
    return inventory


def scan_inventory_pallet(
    db: Session,
    *,
    inventory_uid: str,
    pallet_uid: str,
    actor: str = "system",
) -> InventorySession:
    inventory = get_inventory(db, inventory_uid)
    if inventory.status != InventoryStatus.OPEN:
        raise bad_request("inventory is already completed")
    if inventory.current_location_id is None:
        raise bad_request("scan location first")
    pallet = db.scalar(select(Pallet).where(Pallet.pallet_uid == pallet_uid))
    if pallet is None:
        raise not_found("pallet")
    line = db.scalar(select(InventoryLine).where(InventoryLine.inventory_id == inventory.id, InventoryLine.pallet_id == pallet.id))
    if line is None:
        line = InventoryLine(
            inventory_id=inventory.id,
            pallet_id=pallet.id,
            expected_location_id=pallet.current_location_id,
        )
        db.add(line)
    if line.scanned_at:
        raise bad_request("pallet already scanned in this inventory")
    line.actual_location_id = inventory.current_location_id
    line.scanned_at = utcnow()
    if line.expected_location_id == inventory.current_location_id:
        line.status = InventoryLineStatus.SCANNED
    elif line.expected_location_id is None:
        line.status = InventoryLineStatus.EXTRA
    else:
        line.status = InventoryLineStatus.WRONG_LOCATION
    create_event(
        db,
        operation="inventory_pallet_scanned",
        object_type="inventory",
        object_uid=inventory.inventory_uid,
        actor=actor,
        after={"pallet_uid": pallet.pallet_uid, "status": line.status, "location_id": inventory.current_location_id},
    )
    inventory.current_location_id = None
    db.commit()
    db.refresh(inventory)
    return inventory


def inventory_problem_line_by_pallet(db: Session, inventory: InventorySession, pallet_uid: str) -> tuple[InventoryLine, Pallet]:
    pallet = db.scalar(select(Pallet).where(Pallet.pallet_uid == pallet_uid))
    if pallet is None:
        raise not_found("pallet")
    line = db.scalar(
        select(InventoryLine).where(
            InventoryLine.inventory_id == inventory.id,
            InventoryLine.pallet_id == pallet.id,
            InventoryLine.status.in_(
                {
                    InventoryLineStatus.MISSING,
                    InventoryLineStatus.EXTRA,
                    InventoryLineStatus.WRONG_LOCATION,
                }
            ),
        )
    )
    if line is None:
        raise bad_request("inventory discrepancy line not found")
    if inventory_line_resolution_event(db, inventory, line):
        raise bad_request("inventory discrepancy is already resolved")
    return line, pallet


def ensure_location_capacity_for_resolution(db: Session, pallet: Pallet, location: Location) -> None:
    occupied = (
        db.scalar(
            select(func.count(Pallet.id)).where(
                Pallet.current_location_id == location.id,
                Pallet.id != pallet.id,
            )
        )
        or 0
    )
    if occupied >= location.capacity_pallets:
        raise bad_request("location capacity is already reached")


def create_inventory_resolution_events(
    db: Session,
    *,
    inventory: InventorySession,
    line: InventoryLine,
    pallet: Pallet,
    action: str,
    actor: str,
    reason: str | None,
    before: dict | None = None,
    after: dict | None = None,
) -> None:
    expected_location = db.get(Location, line.expected_location_id) if line.expected_location_id else None
    actual_location = db.get(Location, line.actual_location_id) if line.actual_location_id else None
    payload = {
        "line_id": line.id,
        "pallet_id": pallet.id,
        "pallet_uid": pallet.pallet_uid,
        "line_status": line.status,
        "action": action,
        "expected_location_code": expected_location.code if expected_location else None,
        "actual_location_code": actual_location.code if actual_location else None,
    }
    if after:
        payload.update(after)
    create_event(
        db,
        operation="inventory_discrepancy_resolved",
        object_type="inventory",
        object_uid=inventory.inventory_uid,
        actor=actor,
        reason=reason,
        before=before,
        after=payload,
    )
    create_event(
        db,
        operation=f"pallet_inventory_{action}",
        object_type="pallet",
        object_uid=pallet.pallet_uid,
        actor=actor,
        reason=reason,
        before=before,
        after={
            "inventory_uid": inventory.inventory_uid,
            "line_id": line.id,
            "line_status": line.status,
            **(after or {}),
        },
    )


def confirm_inventory_missing(
    db: Session,
    *,
    inventory_uid: str,
    pallet_uid: str,
    actor: str = "system",
    reason: str | None = None,
) -> InventoryLine:
    inventory = get_inventory(db, inventory_uid)
    line, pallet = inventory_problem_line_by_pallet(db, inventory, pallet_uid)
    if line.status != InventoryLineStatus.MISSING:
        raise bad_request("only missing discrepancy can be confirmed as shortage")
    create_inventory_resolution_events(
        db,
        inventory=inventory,
        line=line,
        pallet=pallet,
        action="missing_confirmed",
        actor=actor,
        reason=reason,
        before={"pallet_status": pallet.status, "location_id": pallet.current_location_id},
    )
    db.commit()
    db.refresh(line)
    return line


def place_inventory_found_pallet(
    db: Session,
    *,
    inventory_uid: str,
    pallet_uid: str,
    actor: str = "system",
    reason: str | None = None,
) -> InventoryLine:
    inventory = get_inventory(db, inventory_uid)
    line, pallet = inventory_problem_line_by_pallet(db, inventory, pallet_uid)
    if line.status != InventoryLineStatus.EXTRA:
        raise bad_request("only extra pallet can be placed as found")
    if line.actual_location_id is None:
        raise bad_request("actual location is missing")
    if pallet.status in {
        PalletStatus.RESERVED,
        PalletStatus.EXPEDITION,
        PalletStatus.LOADED,
        PalletStatus.IN_TRANSIT,
        PalletStatus.SHIPPED,
        PalletStatus.WRITTEN_OFF,
        PalletStatus.DISASSEMBLED,
    }:
        raise bad_request(f"pallet cannot be placed from status {pallet.status}")
    location = db.get(Location, line.actual_location_id)
    if location is None:
        raise not_found("location")
    ensure_location_capacity_for_resolution(db, pallet, location)
    before = {"status": pallet.status, "location_id": pallet.current_location_id}
    pallet.current_location_id = location.id
    if pallet.status in {PalletStatus.CLOSED, PalletStatus.WAITING_PLACEMENT}:
        pallet.status = PalletStatus.AVAILABLE
    create_inventory_resolution_events(
        db,
        inventory=inventory,
        line=line,
        pallet=pallet,
        action="found_placed",
        actor=actor,
        reason=reason,
        before=before,
        after={"status": pallet.status, "location_code": location.code},
    )
    db.commit()
    db.refresh(line)
    return line


def move_inventory_pallet_to_actual(
    db: Session,
    *,
    inventory_uid: str,
    pallet_uid: str,
    actor: str = "system",
    reason: str | None = None,
) -> InventoryLine:
    inventory = get_inventory(db, inventory_uid)
    line, pallet = inventory_problem_line_by_pallet(db, inventory, pallet_uid)
    if line.status != InventoryLineStatus.WRONG_LOCATION:
        raise bad_request("only wrong-location discrepancy can be moved to actual location")
    if line.actual_location_id is None:
        raise bad_request("actual location is missing")
    if pallet.status in {
        PalletStatus.RESERVED,
        PalletStatus.EXPEDITION,
        PalletStatus.LOADED,
        PalletStatus.IN_TRANSIT,
        PalletStatus.SHIPPED,
        PalletStatus.WRITTEN_OFF,
        PalletStatus.DISASSEMBLED,
    }:
        raise bad_request(f"pallet cannot be moved from status {pallet.status}")
    location = db.get(Location, line.actual_location_id)
    if location is None:
        raise not_found("location")
    ensure_location_capacity_for_resolution(db, pallet, location)
    before = {"status": pallet.status, "location_id": pallet.current_location_id}
    pallet.current_location_id = location.id
    create_inventory_resolution_events(
        db,
        inventory=inventory,
        line=line,
        pallet=pallet,
        action="moved_to_actual",
        actor=actor,
        reason=reason,
        before=before,
        after={"status": pallet.status, "location_code": location.code},
    )
    db.commit()
    db.refresh(line)
    return line


def complete_inventory(db: Session, *, inventory_uid: str, actor: str = "system") -> InventorySession:
    inventory = get_inventory(db, inventory_uid)
    if inventory.status != InventoryStatus.OPEN:
        raise bad_request("inventory is already completed")
    unchecked_locations = unchecked_inventory_locations(db, inventory)
    if unchecked_locations:
        preview = ", ".join(location.code for location in unchecked_locations[:5])
        suffix = "" if len(unchecked_locations) <= 5 else f" and {len(unchecked_locations) - 5} more"
        raise bad_request(f"inventory has unchecked locations: {preview}{suffix}")
    lines = list(db.scalars(select(InventoryLine).where(InventoryLine.inventory_id == inventory.id)))
    for line in lines:
        if line.status == InventoryLineStatus.EXPECTED and line.scanned_at is None:
            line.status = InventoryLineStatus.MISSING
    inventory.status = InventoryStatus.COMPLETED
    inventory.completed_at = utcnow()
    create_event(
        db,
        operation="inventory_completed",
        object_type="inventory",
        object_uid=inventory.inventory_uid,
        actor=actor,
        after={"line_count": len(lines)},
    )
    db.commit()
    db.refresh(inventory)
    return inventory
