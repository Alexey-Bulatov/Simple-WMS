from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.constants import (
    CODE_SEPARATOR,
    SHIPMENT_CODE_PREFIX,
    TRANSFER_CODE_PREFIX,
)
from app.models.entities import (
    Location,
    LogisticShipment,
    LogisticShipmentUnit,
    LogisticTransfer,
    LogisticTransferUnit,
    LogisticUnit,
    LogisticUnitType,
    Warehouse,
    utcnow,
)
from app.models.enums import (
    LocationKind,
    LogisticUnitStatus,
    ShipmentStatus,
    TransferKind,
    TransferStatus,
)
from app.schemas import (
    LogisticDocumentActionRequest,
    LogisticDocumentStageRequest,
    LogisticDocumentUnitRequest,
    LogisticShipmentCreate,
    LogisticTransferCreate,
)
from app.services import (
    bad_request,
    commit_or_409,
    create_event,
    get_active_location,
    get_logistic_unit,
    logistic_location_occupied_count,
    not_found,
)


ACTIVE_SHIPMENT_STATUSES = {
    ShipmentStatus.DRAFT,
    ShipmentStatus.RESERVED,
    ShipmentStatus.EXPEDITION,
    ShipmentStatus.LOADING,
}
ACTIVE_TRANSFER_STATUSES = {
    TransferStatus.DRAFT,
    TransferStatus.RESERVED,
    TransferStatus.EXPEDITION,
    TransferStatus.LOADING,
    TransferStatus.IN_TRANSIT,
    TransferStatus.RECEIVING,
}


def get_warehouse(db: Session, code: str, label: str = "warehouse") -> Warehouse:
    warehouse = db.scalar(
        select(Warehouse).where(Warehouse.code == code.strip().upper())
    )
    if warehouse is None:
        raise not_found(label)
    return warehouse


def get_logistic_shipment(
    db: Session,
    shipment_uid: str,
    *,
    for_update: bool = False,
) -> LogisticShipment:
    query = select(LogisticShipment).where(
        LogisticShipment.shipment_uid == shipment_uid.strip().upper()
    )
    if for_update:
        query = query.with_for_update()
    shipment = db.scalar(query)
    if shipment is None:
        raise not_found("logistic_shipment")
    return shipment


def get_logistic_transfer(
    db: Session,
    transfer_uid: str,
    *,
    for_update: bool = False,
) -> LogisticTransfer:
    query = select(LogisticTransfer).where(
        LogisticTransfer.transfer_uid == transfer_uid.strip().upper()
    )
    if for_update:
        query = query.with_for_update()
    transfer = db.scalar(query)
    if transfer is None:
        raise not_found("logistic_transfer")
    return transfer


def generate_logistic_shipment_uid(db: Session) -> str:
    while True:
        candidate = f"{SHIPMENT_CODE_PREFIX}{CODE_SEPARATOR}{uuid4().hex[:12].upper()}"
        if (
            db.scalar(
                select(LogisticShipment.id).where(
                    LogisticShipment.shipment_uid == candidate
                )
            )
            is None
        ):
            return candidate


def generate_logistic_transfer_uid(db: Session) -> str:
    while True:
        candidate = f"{TRANSFER_CODE_PREFIX}{CODE_SEPARATOR}{uuid4().hex[:12].upper()}"
        if (
            db.scalar(
                select(LogisticTransfer.id).where(
                    LogisticTransfer.transfer_uid == candidate
                )
            )
            is None
        ):
            return candidate


def logistic_shipment_links(
    db: Session,
    shipment_id: int,
) -> list[LogisticShipmentUnit]:
    return list(
        db.scalars(
            select(LogisticShipmentUnit)
            .where(LogisticShipmentUnit.shipment_id == shipment_id)
            .order_by(LogisticShipmentUnit.id)
        )
    )


def logistic_transfer_links(
    db: Session,
    transfer_id: int,
) -> list[LogisticTransferUnit]:
    return list(
        db.scalars(
            select(LogisticTransferUnit)
            .where(LogisticTransferUnit.transfer_id == transfer_id)
            .order_by(LogisticTransferUnit.id)
        )
    )


def document_unit_payload(
    db: Session,
    link: LogisticShipmentUnit | LogisticTransferUnit,
) -> dict:
    unit = db.get(LogisticUnit, link.logistic_unit_id)
    unit_type = db.get(LogisticUnitType, unit.type_id) if unit else None
    source = db.get(Location, link.source_location_id)
    current = (
        db.get(Location, unit.current_location_id)
        if unit is not None and unit.current_location_id is not None
        else None
    )
    return {
        "id": link.id,
        "unit_uid": unit.uid if unit else "",
        "type_code": unit_type.code if unit_type else "",
        "unit_status": unit.status if unit else LogisticUnitStatus.WRITTEN_OFF,
        "item_status": link.status,
        "source_location_code": source.code if source else "",
        "current_location_code": current.code if current else None,
        "reserved_at": link.reserved_at,
        "moved_to_expedition_at": link.moved_to_expedition_at,
        "loaded_at": link.loaded_at,
        "received_at": getattr(link, "received_at", None),
    }


def logistic_shipment_payload(db: Session, shipment: LogisticShipment) -> dict:
    warehouse = db.get(Warehouse, shipment.warehouse_id)
    links = logistic_shipment_links(db, shipment.id)
    return {
        "id": shipment.id,
        "shipment_uid": shipment.shipment_uid,
        "warehouse_id": shipment.warehouse_id,
        "warehouse_code": warehouse.code if warehouse else "",
        "customer_name": shipment.customer_name,
        "destination": shipment.destination,
        "status": shipment.status,
        "planned_date": shipment.planned_date,
        "created_at": shipment.created_at,
        "closed_at": shipment.closed_at,
        "unit_count": len(links),
        "loaded_count": sum(
            1 for link in links if link.status in {"loaded", "shipped"}
        ),
        "units": [document_unit_payload(db, link) for link in links],
    }


def logistic_transfer_payload(db: Session, transfer: LogisticTransfer) -> dict:
    source = db.get(Warehouse, transfer.source_warehouse_id)
    destination = db.get(Warehouse, transfer.destination_warehouse_id)
    links = logistic_transfer_links(db, transfer.id)
    return {
        "id": transfer.id,
        "transfer_uid": transfer.transfer_uid,
        "source_warehouse_id": transfer.source_warehouse_id,
        "source_warehouse_code": source.code if source else "",
        "destination_warehouse_id": transfer.destination_warehouse_id,
        "destination_warehouse_code": destination.code if destination else "",
        "transfer_kind": transfer.transfer_kind,
        "status": transfer.status,
        "planned_date": transfer.planned_date,
        "vehicle_number": transfer.vehicle_number,
        "created_at": transfer.created_at,
        "dispatched_at": transfer.dispatched_at,
        "completed_at": transfer.completed_at,
        "unit_count": len(links),
        "loaded_count": sum(
            1
            for link in links
            if link.status in {"loaded", "in_transit", "received"}
        ),
        "received_count": sum(1 for link in links if link.status == "received"),
        "units": [document_unit_payload(db, link) for link in links],
    }


def ensure_unit_has_no_active_document(db: Session, unit_id: int) -> None:
    shipment_link = db.scalar(
        select(LogisticShipmentUnit.id)
        .join(
            LogisticShipment,
            LogisticShipment.id == LogisticShipmentUnit.shipment_id,
        )
        .where(
            LogisticShipmentUnit.logistic_unit_id == unit_id,
            LogisticShipment.status.in_(ACTIVE_SHIPMENT_STATUSES),
        )
    )
    if shipment_link is not None:
        raise bad_request("logistic unit already belongs to an active shipment")
    transfer_link = db.scalar(
        select(LogisticTransferUnit.id)
        .join(
            LogisticTransfer,
            LogisticTransfer.id == LogisticTransferUnit.transfer_id,
        )
        .where(
            LogisticTransferUnit.logistic_unit_id == unit_id,
            LogisticTransfer.status.in_(ACTIVE_TRANSFER_STATUSES),
        )
    )
    if transfer_link is not None:
        raise bad_request("logistic unit already belongs to an active transfer")


def require_available_top_level_unit(
    db: Session,
    unit_uid: str,
    warehouse_id: int,
) -> tuple[LogisticUnit, Location]:
    unit = db.scalar(
        select(LogisticUnit)
        .where(func.upper(LogisticUnit.uid) == unit_uid.strip().upper())
        .with_for_update()
    )
    if unit is None:
        raise not_found("logistic_unit")
    if unit.parent_unit_id is not None:
        raise bad_request("nested logistic unit cannot be reserved separately")
    if unit.status != LogisticUnitStatus.AVAILABLE:
        raise bad_request("only an available logistic unit can be reserved")
    location = (
        db.get(Location, unit.current_location_id)
        if unit.current_location_id is not None
        else None
    )
    if (
        location is None
        or location.kind != LocationKind.STORAGE
        or location.warehouse_id != warehouse_id
    ):
        raise bad_request("logistic unit is not stored at the required warehouse")
    ensure_unit_has_no_active_document(db, unit.id)
    return unit, location


def create_logistic_shipment(
    db: Session,
    payload: LogisticShipmentCreate,
) -> LogisticShipment:
    warehouse = get_warehouse(db, payload.warehouse_code)
    shipment = LogisticShipment(
        shipment_uid=generate_logistic_shipment_uid(db),
        warehouse_id=warehouse.id,
        customer_name=payload.customer_name.strip(),
        destination=payload.destination.strip(),
        planned_date=payload.planned_date,
    )
    db.add(shipment)
    create_event(
        db,
        operation="logistic_shipment_created",
        object_type="logistic_shipment",
        object_uid=shipment.shipment_uid,
        actor=payload.actor,
        after={
            "warehouse_code": warehouse.code,
            "customer_name": shipment.customer_name,
            "destination": shipment.destination,
        },
    )
    from app.logistic_tasks import sync_logistic_shipment_tasks

    sync_logistic_shipment_tasks(db, shipment, actor=payload.actor)
    db.commit()
    db.refresh(shipment)
    return shipment


def reserve_unit_for_logistic_shipment(
    db: Session,
    shipment_uid: str,
    payload: LogisticDocumentUnitRequest,
) -> LogisticShipment:
    shipment = get_logistic_shipment(db, shipment_uid, for_update=True)
    if shipment.status not in {ShipmentStatus.DRAFT, ShipmentStatus.RESERVED}:
        raise bad_request("shipment cannot accept units from its current status")
    unit, location = require_available_top_level_unit(
        db,
        payload.unit_uid,
        shipment.warehouse_id,
    )
    unit.status = LogisticUnitStatus.RESERVED
    shipment.status = ShipmentStatus.RESERVED
    db.add(
        LogisticShipmentUnit(
            shipment_id=shipment.id,
            logistic_unit_id=unit.id,
            source_location_id=location.id,
        )
    )
    create_event(
        db,
        operation="logistic_unit_reserved_for_shipment",
        object_type="logistic_unit",
        object_uid=unit.uid,
        actor=payload.actor,
        reason=payload.reason,
        before={"status": LogisticUnitStatus.AVAILABLE.value},
        after={
            "status": unit.status.value,
            "shipment_uid": shipment.shipment_uid,
        },
    )
    commit_or_409(db, "logistic unit already belongs to this shipment")
    db.refresh(shipment)
    return shipment


def stage_logistic_shipment(
    db: Session,
    shipment_uid: str,
    payload: LogisticDocumentStageRequest,
) -> LogisticShipment:
    shipment = get_logistic_shipment(db, shipment_uid, for_update=True)
    if shipment.status != ShipmentStatus.RESERVED:
        raise bad_request("only a reserved shipment can be moved to expedition")
    links = logistic_shipment_links(db, shipment.id)
    if not links:
        raise bad_request("shipment has no reserved logistic units")
    location = get_active_location(db, payload.location_code)
    if (
        location.kind != LocationKind.EXPEDITION
        or location.warehouse_id != shipment.warehouse_id
    ):
        raise bad_request("expedition location must belong to the shipment warehouse")
    occupied = logistic_location_occupied_count(db, location.id)
    if occupied + len(links) > location.capacity_units:
        raise bad_request("expedition location capacity is already reached")
    now = utcnow()
    for link in links:
        unit = db.get(LogisticUnit, link.logistic_unit_id)
        if (
            unit is None
            or unit.status != LogisticUnitStatus.RESERVED
            or link.status != "reserved"
        ):
            raise bad_request("all shipment units must be reserved")
        unit.status = LogisticUnitStatus.EXPEDITION
        unit.current_location_id = location.id
        link.status = "expedition"
        link.moved_to_expedition_at = now
        create_event(
            db,
            operation="logistic_unit_moved_to_shipment_expedition",
            object_type="logistic_unit",
            object_uid=unit.uid,
            actor=payload.actor,
            reason=payload.reason,
            after={
                "status": unit.status.value,
                "location_code": location.code,
                "shipment_uid": shipment.shipment_uid,
            },
        )
    shipment.status = ShipmentStatus.EXPEDITION
    db.commit()
    db.refresh(shipment)
    return shipment


def load_logistic_shipment_unit(
    db: Session,
    shipment_uid: str,
    payload: LogisticDocumentUnitRequest,
) -> LogisticShipment:
    shipment = get_logistic_shipment(db, shipment_uid, for_update=True)
    if shipment.status not in {ShipmentStatus.EXPEDITION, ShipmentStatus.LOADING}:
        raise bad_request("shipment must be in expedition or loading")
    unit = get_logistic_unit(db, payload.unit_uid)
    link = db.scalar(
        select(LogisticShipmentUnit).where(
            LogisticShipmentUnit.shipment_id == shipment.id,
            LogisticShipmentUnit.logistic_unit_id == unit.id,
        )
    )
    if link is None:
        raise bad_request("logistic unit does not belong to this shipment")
    if link.status != "expedition" or unit.status != LogisticUnitStatus.EXPEDITION:
        raise bad_request("logistic unit cannot be loaded from its current status")
    unit.status = LogisticUnitStatus.LOADED
    unit.current_location_id = None
    link.status = "loaded"
    link.loaded_at = utcnow()
    shipment.status = ShipmentStatus.LOADING
    create_event(
        db,
        operation="logistic_unit_loaded_for_shipment",
        object_type="logistic_unit",
        object_uid=unit.uid,
        actor=payload.actor,
        reason=payload.reason,
        after={
            "status": unit.status.value,
            "shipment_uid": shipment.shipment_uid,
        },
    )
    db.commit()
    db.refresh(shipment)
    return shipment


def close_logistic_shipment(
    db: Session,
    shipment_uid: str,
    payload: LogisticDocumentActionRequest,
) -> LogisticShipment:
    shipment = get_logistic_shipment(db, shipment_uid, for_update=True)
    if shipment.status != ShipmentStatus.LOADING:
        raise bad_request("shipment can be closed only after loading has started")
    links = logistic_shipment_links(db, shipment.id)
    if not links or any(link.status != "loaded" for link in links):
        raise bad_request("all shipment units must be loaded before closing")
    for link in links:
        unit = db.get(LogisticUnit, link.logistic_unit_id)
        if unit is None or unit.status != LogisticUnitStatus.LOADED:
            raise bad_request("all shipment units must have loaded status")
        unit.status = LogisticUnitStatus.SHIPPED
        link.status = "shipped"
        create_event(
            db,
            operation="logistic_unit_shipped",
            object_type="logistic_unit",
            object_uid=unit.uid,
            actor=payload.actor,
            reason=payload.reason,
            after={
                "status": unit.status.value,
                "shipment_uid": shipment.shipment_uid,
            },
        )
    shipment.status = ShipmentStatus.COMPLETED
    shipment.closed_at = utcnow()
    create_event(
        db,
        operation="logistic_shipment_completed",
        object_type="logistic_shipment",
        object_uid=shipment.shipment_uid,
        actor=payload.actor,
        reason=payload.reason,
        after={"status": shipment.status.value, "unit_count": len(links)},
    )
    from app.logistic_tasks import sync_logistic_shipment_tasks

    sync_logistic_shipment_tasks(db, shipment, actor=payload.actor)
    db.commit()
    db.refresh(shipment)
    return shipment


def create_logistic_transfer(
    db: Session,
    payload: LogisticTransferCreate,
) -> LogisticTransfer:
    source = get_warehouse(db, payload.source_warehouse_code, "source_warehouse")
    destination = get_warehouse(
        db,
        payload.destination_warehouse_code,
        "destination_warehouse",
    )
    if source.id == destination.id:
        raise bad_request("source and destination warehouses must be different")
    transfer = LogisticTransfer(
        transfer_uid=generate_logistic_transfer_uid(db),
        source_warehouse_id=source.id,
        destination_warehouse_id=destination.id,
        transfer_kind=payload.transfer_kind,
        planned_date=payload.planned_date,
        vehicle_number=(
            (payload.vehicle_number or "").strip() or None
            if payload.transfer_kind == TransferKind.TRANSPORT
            else None
        ),
    )
    db.add(transfer)
    create_event(
        db,
        operation="logistic_transfer_created",
        object_type="logistic_transfer",
        object_uid=transfer.transfer_uid,
        actor=payload.actor,
        after={
            "source_warehouse_code": source.code,
            "destination_warehouse_code": destination.code,
            "transfer_kind": transfer.transfer_kind.value,
            "vehicle_number": transfer.vehicle_number,
        },
    )
    from app.logistic_tasks import sync_logistic_transfer_tasks

    sync_logistic_transfer_tasks(db, transfer, actor=payload.actor)
    db.commit()
    db.refresh(transfer)
    return transfer


def reserve_unit_for_logistic_transfer(
    db: Session,
    transfer_uid: str,
    payload: LogisticDocumentUnitRequest,
) -> LogisticTransfer:
    transfer = get_logistic_transfer(db, transfer_uid, for_update=True)
    if transfer.status not in {TransferStatus.DRAFT, TransferStatus.RESERVED}:
        raise bad_request("transfer cannot accept units from its current status")
    unit, location = require_available_top_level_unit(
        db,
        payload.unit_uid,
        transfer.source_warehouse_id,
    )
    unit.status = LogisticUnitStatus.RESERVED
    transfer.status = TransferStatus.RESERVED
    db.add(
        LogisticTransferUnit(
            transfer_id=transfer.id,
            logistic_unit_id=unit.id,
            source_location_id=location.id,
        )
    )
    create_event(
        db,
        operation="logistic_unit_reserved_for_transfer",
        object_type="logistic_unit",
        object_uid=unit.uid,
        actor=payload.actor,
        reason=payload.reason,
        before={"status": LogisticUnitStatus.AVAILABLE.value},
        after={
            "status": unit.status.value,
            "transfer_uid": transfer.transfer_uid,
        },
    )
    commit_or_409(db, "logistic unit already belongs to this transfer")
    db.refresh(transfer)
    return transfer


def stage_logistic_transfer(
    db: Session,
    transfer_uid: str,
    payload: LogisticDocumentStageRequest,
) -> LogisticTransfer:
    transfer = get_logistic_transfer(db, transfer_uid, for_update=True)
    if transfer.status != TransferStatus.RESERVED:
        raise bad_request("only a reserved transfer can be moved to expedition")
    links = logistic_transfer_links(db, transfer.id)
    if not links:
        raise bad_request("transfer has no reserved logistic units")
    location = get_active_location(db, payload.location_code)
    if (
        location.kind != LocationKind.TRANSFER_OUT
        or location.warehouse_id != transfer.source_warehouse_id
    ):
        raise bad_request("transfer-out location must belong to the source warehouse")
    occupied = logistic_location_occupied_count(db, location.id)
    if occupied + len(links) > location.capacity_units:
        raise bad_request("transfer-out location capacity is already reached")
    now = utcnow()
    for link in links:
        unit = db.get(LogisticUnit, link.logistic_unit_id)
        if (
            unit is None
            or unit.status != LogisticUnitStatus.RESERVED
            or link.status != "reserved"
        ):
            raise bad_request("all transfer units must be reserved")
        unit.status = LogisticUnitStatus.EXPEDITION
        unit.current_location_id = location.id
        link.status = "expedition"
        link.moved_to_expedition_at = now
        create_event(
            db,
            operation=(
                "logistic_unit_prepared_for_local_transfer"
                if transfer.transfer_kind == TransferKind.LOCAL
                else "logistic_unit_moved_to_transfer_expedition"
            ),
            object_type="logistic_unit",
            object_uid=unit.uid,
            actor=payload.actor,
            reason=payload.reason,
            after={
                "status": unit.status.value,
                "location_code": location.code,
                "transfer_uid": transfer.transfer_uid,
            },
        )
    transfer.status = TransferStatus.EXPEDITION
    create_event(
        db,
        operation=(
            "logistic_local_transfer_prepared"
            if transfer.transfer_kind == TransferKind.LOCAL
            else "logistic_transfer_moved_to_expedition"
        ),
        object_type="logistic_transfer",
        object_uid=transfer.transfer_uid,
        actor=payload.actor,
        reason=payload.reason,
        after={"location_code": location.code, "unit_count": len(links)},
    )
    db.commit()
    db.refresh(transfer)
    return transfer


def load_logistic_transfer_unit(
    db: Session,
    transfer_uid: str,
    payload: LogisticDocumentUnitRequest,
) -> LogisticTransfer:
    transfer = get_logistic_transfer(db, transfer_uid, for_update=True)
    if transfer.status not in {TransferStatus.EXPEDITION, TransferStatus.LOADING}:
        raise bad_request("transfer must be in expedition or loading")
    unit = get_logistic_unit(db, payload.unit_uid)
    link = db.scalar(
        select(LogisticTransferUnit).where(
            LogisticTransferUnit.transfer_id == transfer.id,
            LogisticTransferUnit.logistic_unit_id == unit.id,
        )
    )
    if link is None:
        raise bad_request("logistic unit does not belong to this transfer")
    if link.status != "expedition" or unit.status != LogisticUnitStatus.EXPEDITION:
        raise bad_request("logistic unit cannot be loaded from its current status")
    is_local = transfer.transfer_kind == TransferKind.LOCAL
    unit.status = (
        LogisticUnitStatus.IN_TRANSIT
        if is_local
        else LogisticUnitStatus.LOADED
    )
    unit.current_location_id = None
    link.status = "in_transit" if is_local else "loaded"
    link.loaded_at = utcnow()
    transfer.status = TransferStatus.LOADING
    create_event(
        db,
        operation=(
            "logistic_unit_handed_over_for_local_transfer"
            if is_local
            else "logistic_unit_loaded_for_transfer"
        ),
        object_type="logistic_unit",
        object_uid=unit.uid,
        actor=payload.actor,
        reason=payload.reason,
        after={
            "status": unit.status.value,
            "transfer_uid": transfer.transfer_uid,
        },
    )
    if is_local:
        links = logistic_transfer_links(db, transfer.id)
        if all(item.status == "in_transit" for item in links):
            transfer.status = TransferStatus.IN_TRANSIT
            transfer.dispatched_at = utcnow()
            create_event(
                db,
                operation="logistic_local_transfer_started",
                object_type="logistic_transfer",
                object_uid=transfer.transfer_uid,
                actor=payload.actor,
                reason=payload.reason,
                after={
                    "status": transfer.status.value,
                    "unit_count": len(links),
                },
            )
    from app.logistic_tasks import sync_logistic_transfer_tasks

    sync_logistic_transfer_tasks(db, transfer, actor=payload.actor)
    db.commit()
    db.refresh(transfer)
    return transfer


def dispatch_logistic_transfer(
    db: Session,
    transfer_uid: str,
    payload: LogisticDocumentActionRequest,
) -> LogisticTransfer:
    transfer = get_logistic_transfer(db, transfer_uid, for_update=True)
    if transfer.transfer_kind == TransferKind.LOCAL:
        raise bad_request(
            "local transfer starts automatically after all units are handed over"
        )
    if transfer.status != TransferStatus.LOADING:
        raise bad_request("transfer can be dispatched only after loading has started")
    links = logistic_transfer_links(db, transfer.id)
    if not links or any(link.status != "loaded" for link in links):
        raise bad_request("all transfer units must be loaded before dispatch")
    for link in links:
        unit = db.get(LogisticUnit, link.logistic_unit_id)
        if unit is None or unit.status != LogisticUnitStatus.LOADED:
            raise bad_request("all transfer units must have loaded status")
        unit.status = LogisticUnitStatus.IN_TRANSIT
        link.status = "in_transit"
        create_event(
            db,
            operation="logistic_unit_dispatched_between_warehouses",
            object_type="logistic_unit",
            object_uid=unit.uid,
            actor=payload.actor,
            reason=payload.reason,
            after={
                "status": unit.status.value,
                "transfer_uid": transfer.transfer_uid,
            },
        )
    transfer.status = TransferStatus.IN_TRANSIT
    transfer.dispatched_at = utcnow()
    create_event(
        db,
        operation="logistic_transfer_dispatched",
        object_type="logistic_transfer",
        object_uid=transfer.transfer_uid,
        actor=payload.actor,
        reason=payload.reason,
        after={"status": transfer.status.value, "unit_count": len(links)},
    )
    from app.logistic_tasks import sync_logistic_transfer_tasks

    sync_logistic_transfer_tasks(db, transfer, actor=payload.actor)
    db.commit()
    db.refresh(transfer)
    return transfer


def receive_logistic_transfer_unit(
    db: Session,
    transfer_uid: str,
    payload: LogisticDocumentUnitRequest,
    location_code: str,
) -> LogisticTransfer:
    transfer = get_logistic_transfer(db, transfer_uid, for_update=True)
    if transfer.status not in {TransferStatus.IN_TRANSIT, TransferStatus.RECEIVING}:
        raise bad_request("transfer must be in transit or receiving")
    unit = get_logistic_unit(db, payload.unit_uid)
    link = db.scalar(
        select(LogisticTransferUnit).where(
            LogisticTransferUnit.transfer_id == transfer.id,
            LogisticTransferUnit.logistic_unit_id == unit.id,
        )
    )
    if link is None:
        raise bad_request("logistic unit does not belong to this transfer")
    if link.status != "in_transit" or unit.status != LogisticUnitStatus.IN_TRANSIT:
        raise bad_request("logistic unit cannot be received from its current status")
    location = get_active_location(db, location_code)
    if (
        location.kind != LocationKind.TRANSFER_IN
        or location.warehouse_id != transfer.destination_warehouse_id
    ):
        raise bad_request("transfer-in location must belong to the destination warehouse")
    if logistic_location_occupied_count(db, location.id) >= location.capacity_units:
        raise bad_request("transfer-in location capacity is already reached")
    unit.status = LogisticUnitStatus.CLOSED
    unit.current_location_id = location.id
    link.status = "received"
    link.received_at = utcnow()
    transfer.status = TransferStatus.RECEIVING
    db.flush()
    remaining = db.scalar(
        select(LogisticTransferUnit.id).where(
            LogisticTransferUnit.transfer_id == transfer.id,
            LogisticTransferUnit.status != "received",
        )
    )
    if remaining is None:
        transfer.status = TransferStatus.COMPLETED
        transfer.completed_at = utcnow()
        create_event(
            db,
            operation="logistic_transfer_completed",
            object_type="logistic_transfer",
            object_uid=transfer.transfer_uid,
            actor=payload.actor,
            reason=payload.reason,
            after={
                "status": transfer.status.value,
                "unit_count": len(logistic_transfer_links(db, transfer.id)),
            },
        )
    create_event(
        db,
        operation="logistic_unit_received_from_transfer",
        object_type="logistic_unit",
        object_uid=unit.uid,
        actor=payload.actor,
        reason=payload.reason,
        after={
            "status": unit.status.value,
            "location_code": location.code,
            "transfer_uid": transfer.transfer_uid,
        },
    )
    from app.logistic_tasks import sync_logistic_transfer_tasks

    sync_logistic_transfer_tasks(db, transfer, actor=payload.actor)
    db.commit()
    db.refresh(transfer)
    return transfer
