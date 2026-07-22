from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.constants import (
    CODE_SEPARATOR,
    TRANSFER_CODE_PREFIX,
    TRANSFER_IN_LOCATION_SUFFIX,
    TRANSFER_IN_ZONE_CODE,
    TRANSFER_IN_ZONE_NAME,
)
from app.models.entities import (
    Location,
    Pallet,
    Warehouse,
    WarehouseTransfer,
    WarehouseTransferPallet,
    Zone,
    utcnow,
)
from app.models.enums import LocationKind, PalletStatus, TransferStatus
from app.schemas import TransferCreate
from app.services import bad_request, commit_or_409, create_event, not_found


def generate_transfer_uid(db: Session) -> str:
    while True:
        candidate = f"{TRANSFER_CODE_PREFIX}{CODE_SEPARATOR}{uuid4().hex[:10].upper()}"
        if db.scalar(select(WarehouseTransfer.id).where(WarehouseTransfer.transfer_uid == candidate)) is None:
            return candidate


def get_transfer(db: Session, transfer_uid: str) -> WarehouseTransfer:
    transfer = db.scalar(select(WarehouseTransfer).where(WarehouseTransfer.transfer_uid == transfer_uid))
    if transfer is None:
        raise not_found("transfer")
    return transfer


def transfer_links(db: Session, transfer_id: int) -> list[WarehouseTransferPallet]:
    return list(
        db.scalars(
            select(WarehouseTransferPallet)
            .where(WarehouseTransferPallet.transfer_id == transfer_id)
            .order_by(WarehouseTransferPallet.id)
        )
    )


def create_transfer(db: Session, payload: TransferCreate) -> WarehouseTransfer:
    source = db.scalar(select(Warehouse).where(Warehouse.code == payload.source_warehouse_code))
    destination = db.scalar(select(Warehouse).where(Warehouse.code == payload.destination_warehouse_code))
    if source is None:
        raise not_found("source warehouse")
    if destination is None:
        raise not_found("destination warehouse")
    if source.id == destination.id:
        raise bad_request("source and destination warehouses must be different")

    transfer = WarehouseTransfer(
        transfer_uid=generate_transfer_uid(db),
        source_warehouse_id=source.id,
        destination_warehouse_id=destination.id,
        planned_date=payload.planned_date,
        vehicle_number=(payload.vehicle_number or "").strip() or None,
    )
    db.add(transfer)
    create_event(
        db,
        operation="transfer_created",
        object_type="transfer",
        object_uid=transfer.transfer_uid,
        actor=payload.actor,
        after={
            "source_warehouse": source.code,
            "destination_warehouse": destination.code,
            "vehicle_number": transfer.vehicle_number,
        },
    )
    db.commit()
    db.refresh(transfer)
    return transfer


def reserve_pallet_for_transfer(
    db: Session,
    *,
    transfer_uid: str,
    pallet_uid: str,
    actor: str = "system",
) -> WarehouseTransfer:
    transfer = get_transfer(db, transfer_uid)
    if transfer.status not in {TransferStatus.DRAFT, TransferStatus.RESERVED}:
        raise bad_request(f"transfer cannot accept pallets from status {transfer.status}")
    pallet = db.scalar(select(Pallet).where(Pallet.pallet_uid == pallet_uid))
    if pallet is None:
        raise not_found("pallet")
    if pallet.status != PalletStatus.AVAILABLE:
        raise bad_request(f"only available pallet can be reserved, got {pallet.status}")
    location = db.get(Location, pallet.current_location_id) if pallet.current_location_id else None
    if location is None or location.warehouse_id != transfer.source_warehouse_id:
        raise bad_request("pallet is not located at the source warehouse")
    active_link = db.scalar(
        select(WarehouseTransferPallet.id)
        .join(WarehouseTransfer, WarehouseTransfer.id == WarehouseTransferPallet.transfer_id)
        .where(
            WarehouseTransferPallet.pallet_id == pallet.id,
            WarehouseTransfer.status.not_in({TransferStatus.COMPLETED, TransferStatus.CANCELLED}),
        )
    )
    if active_link is not None:
        raise bad_request("pallet already belongs to an active transfer")

    before = {"transfer_status": transfer.status, "pallet_status": pallet.status, "location_code": location.code}
    transfer.status = TransferStatus.RESERVED
    pallet.status = PalletStatus.RESERVED
    db.add(
        WarehouseTransferPallet(
            transfer_id=transfer.id,
            pallet_id=pallet.id,
            source_location_id=location.id,
            status="reserved",
        )
    )
    create_event(
        db,
        operation="transfer_pallet_reserved",
        object_type="transfer",
        object_uid=transfer.transfer_uid,
        actor=actor,
        before=before,
        after={"pallet_uid": pallet.pallet_uid, "status": transfer.status},
    )
    create_event(
        db,
        operation="pallet_reserved_for_transfer",
        object_type="pallet",
        object_uid=pallet.pallet_uid,
        actor=actor,
        before={"status": before["pallet_status"], "location_code": location.code},
        after={"status": pallet.status, "transfer_uid": transfer.transfer_uid},
    )
    commit_or_409(db, "pallet already belongs to this transfer")
    db.refresh(transfer)
    return transfer


def move_transfer_to_expedition(db: Session, *, transfer_uid: str, actor: str = "system") -> WarehouseTransfer:
    transfer = get_transfer(db, transfer_uid)
    if transfer.status != TransferStatus.RESERVED:
        raise bad_request("only reserved transfer can be moved to expedition")
    links = transfer_links(db, transfer.id)
    if not links:
        raise bad_request("transfer has no reserved pallets")
    now = utcnow()
    for link in links:
        pallet = db.get(Pallet, link.pallet_id)
        if pallet is None or pallet.status != PalletStatus.RESERVED or link.status != "reserved":
            raise bad_request("all transfer pallets must be reserved")
        source_location = db.get(Location, link.source_location_id) if link.source_location_id else None
        pallet.status = PalletStatus.EXPEDITION
        pallet.current_location_id = None
        link.status = "expedition"
        link.moved_to_expedition_at = now
        create_event(
            db,
            operation="pallet_moved_to_transfer_expedition",
            object_type="pallet",
            object_uid=pallet.pallet_uid,
            actor=actor,
            before={"status": PalletStatus.RESERVED, "location_code": source_location.code if source_location else None},
            after={"status": pallet.status, "transfer_uid": transfer.transfer_uid, "location_id": None},
        )
    transfer.status = TransferStatus.EXPEDITION
    create_event(
        db,
        operation="transfer_moved_to_expedition",
        object_type="transfer",
        object_uid=transfer.transfer_uid,
        actor=actor,
        before={"status": TransferStatus.RESERVED},
        after={"status": transfer.status, "pallet_count": len(links)},
    )
    db.commit()
    db.refresh(transfer)
    return transfer


def load_transfer_pallet(
    db: Session,
    *,
    transfer_uid: str,
    pallet_uid: str,
    actor: str = "system",
) -> WarehouseTransfer:
    transfer = get_transfer(db, transfer_uid)
    if transfer.status not in {TransferStatus.EXPEDITION, TransferStatus.LOADING}:
        raise bad_request("transfer must be in expedition or loading status")
    pallet = db.scalar(select(Pallet).where(Pallet.pallet_uid == pallet_uid))
    if pallet is None:
        raise not_found("pallet")
    link = db.scalar(
        select(WarehouseTransferPallet).where(
            WarehouseTransferPallet.transfer_id == transfer.id,
            WarehouseTransferPallet.pallet_id == pallet.id,
        )
    )
    if link is None:
        raise bad_request("pallet does not belong to this transfer")
    if link.status == "loaded":
        raise bad_request("pallet already loaded")
    if link.status != "expedition" or pallet.status != PalletStatus.EXPEDITION:
        raise bad_request(f"pallet cannot be loaded from status {pallet.status}")

    transfer.status = TransferStatus.LOADING
    pallet.status = PalletStatus.LOADED
    link.status = "loaded"
    link.loaded_at = utcnow()
    create_event(
        db,
        operation="transfer_pallet_loaded",
        object_type="transfer",
        object_uid=transfer.transfer_uid,
        actor=actor,
        after={"pallet_uid": pallet.pallet_uid, "status": transfer.status},
    )
    create_event(
        db,
        operation="pallet_loaded_for_transfer",
        object_type="pallet",
        object_uid=pallet.pallet_uid,
        actor=actor,
        before={"status": PalletStatus.EXPEDITION},
        after={"status": pallet.status, "transfer_uid": transfer.transfer_uid},
    )
    db.commit()
    db.refresh(transfer)
    return transfer


def dispatch_transfer(
    db: Session,
    *,
    transfer_uid: str,
    actor: str = "system",
    reason: str | None = None,
) -> WarehouseTransfer:
    transfer = get_transfer(db, transfer_uid)
    if transfer.status != TransferStatus.LOADING:
        raise bad_request("transfer can be dispatched only after loading has started")
    links = transfer_links(db, transfer.id)
    if not links or any(link.status != "loaded" for link in links):
        raise bad_request("all transfer pallets must be loaded before dispatch")
    transfer.status = TransferStatus.IN_TRANSIT
    transfer.dispatched_at = utcnow()
    for link in links:
        pallet = db.get(Pallet, link.pallet_id)
        if pallet is None or pallet.status != PalletStatus.LOADED:
            raise bad_request("all transfer pallets must have loaded status")
        pallet.status = PalletStatus.IN_TRANSIT
        link.status = "in_transit"
        create_event(
            db,
            operation="pallet_dispatched_between_warehouses",
            object_type="pallet",
            object_uid=pallet.pallet_uid,
            actor=actor,
            reason=reason,
            before={"status": PalletStatus.LOADED},
            after={"status": pallet.status, "transfer_uid": transfer.transfer_uid},
        )
    create_event(
        db,
        operation="transfer_dispatched",
        object_type="transfer",
        object_uid=transfer.transfer_uid,
        actor=actor,
        reason=reason,
        before={"status": TransferStatus.LOADING},
        after={"status": transfer.status, "pallet_count": len(links)},
    )
    db.commit()
    db.refresh(transfer)
    return transfer


def ensure_transfer_in_location(db: Session, warehouse_id: int) -> Location:
    warehouse = db.get(Warehouse, warehouse_id)
    if warehouse is None:
        raise not_found("destination warehouse")
    zone = db.scalar(
        select(Zone).where(Zone.warehouse_id == warehouse.id, Zone.code == TRANSFER_IN_ZONE_CODE)
    )
    if zone is None:
        zone = Zone(
            warehouse_id=warehouse.id,
            code=TRANSFER_IN_ZONE_CODE,
            name=TRANSFER_IN_ZONE_NAME,
            kind=LocationKind.TRANSFER_IN,
        )
        db.add(zone)
        db.flush()
    location_code = (
        f"{warehouse.code}{CODE_SEPARATOR}{TRANSFER_IN_ZONE_CODE}{CODE_SEPARATOR}{TRANSFER_IN_LOCATION_SUFFIX}"
    )
    location = db.scalar(select(Location).where(Location.code == location_code))
    if location is None:
        location = Location(
            warehouse_id=warehouse.id,
            zone_id=zone.id,
            code=location_code,
            name="Межскладская приемка",
            kind=LocationKind.TRANSFER_IN,
            capacity_pallets=999,
        )
        db.add(location)
        db.flush()
    return location


def receive_transfer_pallet(
    db: Session,
    *,
    transfer_uid: str,
    pallet_uid: str,
    actor: str = "system",
) -> WarehouseTransfer:
    transfer = get_transfer(db, transfer_uid)
    if transfer.status not in {TransferStatus.IN_TRANSIT, TransferStatus.RECEIVING}:
        raise bad_request("transfer must be in transit or receiving status")
    pallet = db.scalar(select(Pallet).where(Pallet.pallet_uid == pallet_uid))
    if pallet is None:
        raise not_found("pallet")
    link = db.scalar(
        select(WarehouseTransferPallet).where(
            WarehouseTransferPallet.transfer_id == transfer.id,
            WarehouseTransferPallet.pallet_id == pallet.id,
        )
    )
    if link is None:
        raise bad_request("pallet was not sent in this transfer")
    if link.status == "received":
        raise bad_request("pallet already received")
    if link.status != "in_transit" or pallet.status != PalletStatus.IN_TRANSIT:
        raise bad_request(f"pallet cannot be received from status {pallet.status}")

    receiving_location = ensure_transfer_in_location(db, transfer.destination_warehouse_id)
    previous_transfer_status = transfer.status
    pallet.status = PalletStatus.WAITING_PLACEMENT
    pallet.current_location_id = receiving_location.id
    link.status = "received"
    link.received_at = utcnow()
    links = transfer_links(db, transfer.id)
    all_received = all(item.status == "received" for item in links)
    transfer.status = TransferStatus.COMPLETED if all_received else TransferStatus.RECEIVING
    if all_received:
        transfer.completed_at = utcnow()
    create_event(
        db,
        operation="transfer_pallet_received",
        object_type="transfer",
        object_uid=transfer.transfer_uid,
        actor=actor,
        after={
            "pallet_uid": pallet.pallet_uid,
            "location_code": receiving_location.code,
            "status": transfer.status,
        },
    )
    create_event(
        db,
        operation="pallet_received_between_warehouses",
        object_type="pallet",
        object_uid=pallet.pallet_uid,
        actor=actor,
        before={"status": PalletStatus.IN_TRANSIT, "location_id": None},
        after={
            "status": pallet.status,
            "location_code": receiving_location.code,
            "transfer_uid": transfer.transfer_uid,
        },
    )
    if all_received:
        create_event(
            db,
            operation="transfer_completed",
            object_type="transfer",
            object_uid=transfer.transfer_uid,
            actor=actor,
            before={"status": previous_transfer_status},
            after={"status": transfer.status, "pallet_count": len(links)},
        )
    db.commit()
    db.refresh(transfer)
    return transfer
