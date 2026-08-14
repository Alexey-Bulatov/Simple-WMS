import hashlib
import json
from datetime import date
from decimal import Decimal

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.entities import (
    Batch,
    Location,
    LogisticShipment,
    LogisticShipmentAllocation,
    LogisticShipmentLine,
    LogisticShipmentReservationAttempt,
    LogisticUnitContent,
    OperationEvent,
    Product,
    ProductPackaging,
    StockDocument,
    StockOwner,
    StockPosition,
    StockReservation,
    UnitOfMeasure,
    utcnow,
)
from app.models.enums import (
    LocationKind,
    ShipmentStatus,
    StockReservationResult,
    StockReservationStatus,
)
from app.schemas import (
    LogisticShipmentLineCreate,
    LogisticShipmentLoadQuantityRequest,
    LogisticShipmentPickQuantityRequest,
    LogisticShipmentReserveQuantityRequest,
    StockDocumentPost,
    StockMovementPost,
)
from app.stock import convert_product_quantity_to_base, stock_position_payload
from app.stock_ledger import post_stock_document
from app.stock_reservations import _build_stock_reservation


REFERENCE_TYPE = "logistic_shipment"


def _bad_request(message: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=message)


def _conflict(message: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=message)


def _command_hash(operation: str, shipment_uid: str, payload) -> str:
    serialized = json.dumps(
        {
            "operation": operation,
            "shipment_uid": shipment_uid,
            "payload": payload.model_dump(mode="json"),
        },
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def _resolve_line(
    db: Session,
    payload: LogisticShipmentLineCreate,
) -> tuple[Product, StockOwner, UnitOfMeasure, ProductPackaging | None, Batch | None, Decimal, UnitOfMeasure]:
    product = db.get(Product, payload.product_id)
    if product is None or not product.is_active:
        raise _bad_request("active product not found")
    owner = db.get(StockOwner, payload.owner_id)
    if owner is None or not owner.is_active:
        raise _bad_request("active stock owner not found")
    packaging = db.get(ProductPackaging, payload.packaging_id) if payload.packaging_id else None
    if payload.packaging_id is not None and (
        packaging is None or not packaging.is_active or packaging.product_id != product.id
    ):
        raise _bad_request("active product packaging not found")
    input_uom_id = packaging.uom_id if packaging else payload.input_uom_id
    input_uom = db.get(UnitOfMeasure, input_uom_id)
    if input_uom is None or not input_uom.is_active:
        raise _bad_request("active input unit of measure not found")
    converted_input = (
        payload.input_quantity * packaging.quantity
        if packaging is not None
        else payload.input_quantity
    )
    base_quantity, base_uom = convert_product_quantity_to_base(
        db, product, converted_input, input_uom
    )
    batch = db.get(Batch, payload.batch_id) if payload.batch_id else None
    if payload.batch_id is not None and (
        batch is None
        or batch.product_id != product.id
        or batch.operation_status != "allowed"
    ):
        raise _bad_request("allowed product batch not found")
    if payload.serial_number is not None and base_quantity != Decimal("1"):
        raise _bad_request("a serialized shipment line must contain one base unit")
    return product, owner, input_uom, packaging, batch, base_quantity, base_uom


def add_quantity_lines(
    db: Session,
    shipment: LogisticShipment,
    payloads: list[LogisticShipmentLineCreate],
) -> None:
    seen_serials: set[tuple[int, str]] = set()
    for line_no, payload in enumerate(payloads, start=1):
        product, owner, input_uom, packaging, batch, base_quantity, base_uom = (
            _resolve_line(db, payload)
        )
        if payload.serial_number is not None:
            serial_key = (product.id, payload.serial_number)
            if serial_key in seen_serials:
                raise _bad_request("serial number is repeated in shipment")
            seen_serials.add(serial_key)
        db.add(
            LogisticShipmentLine(
                shipment_id=shipment.id,
                line_no=line_no,
                line_uid=f"{shipment.shipment_uid}-L{line_no:03d}",
                product_id=product.id,
                owner_id=owner.id,
                input_quantity=payload.input_quantity,
                input_uom_id=input_uom.id,
                packaging_id=packaging.id if packaging else None,
                requested_base_quantity=base_quantity,
                base_uom_id=base_uom.id,
                conversion_factor=(base_quantity / payload.input_quantity).quantize(
                    Decimal("0.00000001")
                ),
                batch_id=batch.id if batch else None,
                serial_number=payload.serial_number,
                quality_status=payload.quality_status,
                note=payload.note,
            )
        )
    db.flush()


def _allocation_payload(db: Session, allocation: LogisticShipmentAllocation) -> dict:
    reservation = allocation.reservation
    uom = allocation.base_uom
    expedition = allocation.expedition_location
    pick_document = allocation.picking_stock_document
    load_document = allocation.loading_stock_document
    return {
        "id": allocation.id,
        "reservation_uid": reservation.uid,
        "status": allocation.status,
        "quantity": allocation.quantity,
        "base_uom_code": uom.code,
        "source_holder": (
            reservation.logistic_unit_uid or reservation.location_code or ""
        ),
        "source_location_code": reservation.location_code,
        "source_logistic_unit_uid": reservation.logistic_unit_uid,
        "expedition_location_code": expedition.code if expedition else None,
        "picking_stock_document_uid": pick_document.uid if pick_document else None,
        "loading_stock_document_uid": load_document.uid if load_document else None,
        "picked_at": allocation.picked_at,
        "loaded_at": allocation.loaded_at,
    }


def quantity_lines_payload(db: Session, shipment: LogisticShipment) -> list[dict]:
    result = []
    for line in shipment.lines:
        result.append(
            {
                "id": line.id,
                "line_no": line.line_no,
                "line_uid": line.line_uid,
                "product_id": line.product_id,
                "product_code": line.product.code,
                "product_name": line.product.name,
                "owner_id": line.owner_id,
                "owner_code": line.owner.code,
                "input_quantity": line.input_quantity,
                "input_uom_id": line.input_uom_id,
                "input_uom_code": line.input_uom.code,
                "packaging_id": line.packaging_id,
                "packaging_code": line.packaging.code if line.packaging else None,
                "requested_base_quantity": line.requested_base_quantity,
                "base_uom_id": line.base_uom_id,
                "base_uom_code": line.base_uom.code,
                "conversion_factor": line.conversion_factor,
                "batch_id": line.batch_id,
                "batch_number": line.batch.batch_number if line.batch else None,
                "serial_number": line.serial_number,
                "quality_status": line.quality_status,
                "reservation_result": line.reservation_result,
                "reserved_base_quantity": line.reserved_base_quantity,
                "picked_base_quantity": line.picked_base_quantity,
                "loaded_base_quantity": line.loaded_base_quantity,
                "note": line.note,
                "allocations": [
                    _allocation_payload(db, allocation)
                    for allocation in line.allocations
                ],
            }
        )
    return result


def _candidate_positions(
    db: Session,
    shipment: LogisticShipment,
    line: LogisticShipmentLine,
) -> list[tuple[StockPosition, dict]]:
    query = (
        select(StockPosition)
        .where(
            StockPosition.product_id == line.product_id,
            StockPosition.owner_id == line.owner_id,
            StockPosition.quality_status == line.quality_status,
        )
        .order_by(StockPosition.id)
        .execution_options(populate_existing=True)
        .with_for_update()
    )
    if line.batch_id is not None:
        query = query.where(StockPosition.batch_id == line.batch_id)
    if line.serial_number is not None:
        query = query.where(StockPosition.serial_number == line.serial_number)
    positions = []
    for position in db.scalars(query):
        data = stock_position_payload(db, position)
        if (
            data["warehouse_id"] == shipment.warehouse_id
            and data["available_quantity"] > 0
        ):
            positions.append((position, data))
    positions.sort(
        key=lambda item: (
            item[0].batch.expiry_date if item[0].batch else date.max,
            item[0].created_at,
            item[0].id,
        )
    )
    return positions


def _reserve_shipment_quantities(
    db: Session,
    shipment_uid: str,
    payload: LogisticShipmentReserveQuantityRequest,
) -> LogisticShipment:
    from app.logistic_documents import get_logistic_shipment

    command_hash = _command_hash("reserve_quantities", shipment_uid, payload)
    existing_attempt = db.scalar(
        select(LogisticShipmentReservationAttempt).where(
            LogisticShipmentReservationAttempt.idempotency_key == payload.idempotency_key
        )
    )
    if existing_attempt is not None:
        if existing_attempt.command_hash != command_hash:
            raise _conflict("idempotency key belongs to another shipment reservation")
        return get_logistic_shipment(db, shipment_uid)

    shipment = get_logistic_shipment(db, shipment_uid, for_update=True)
    if shipment.status not in {ShipmentStatus.DRAFT, ShipmentStatus.RESERVED}:
        raise _conflict("shipment quantities cannot be reserved from its current status")
    if not shipment.lines:
        raise _bad_request("shipment has no quantity lines")

    for line in shipment.lines:
        remaining = line.requested_base_quantity - line.reserved_base_quantity
        if remaining <= 0:
            line.reservation_result = StockReservationResult.FULL
            continue
        candidates = _candidate_positions(db, shipment, line)
        total_available = sum(
            (data["available_quantity"] for _, data in candidates), Decimal("0")
        )
        target = (
            min(remaining, total_available)
            if payload.allow_partial or total_available >= remaining
            else Decimal("0")
        )
        to_allocate = target
        for position, data in candidates:
            if to_allocate <= 0:
                break
            quantity = min(to_allocate, data["available_quantity"])
            reservation_key = (
                "SHP-RSV-"
                + hashlib.sha256(
                    f"{payload.idempotency_key}:{line.line_uid}:{position.id}:{quantity}".encode()
                ).hexdigest()[:40]
            )
            reservation_hash = hashlib.sha256(reservation_key.encode()).hexdigest()
            reservation = _build_stock_reservation(
                db,
                position=position,
                quantity=quantity,
                base_uom=line.base_uom,
                input_quantity=quantity,
                input_uom=line.base_uom,
                conversion_factor=Decimal("1.00000000"),
                reference_type=REFERENCE_TYPE,
                reference_uid=shipment.shipment_uid,
                reference_line_uid=line.line_uid,
                task=None,
                idempotency_key=reservation_key,
                command_hash=reservation_hash,
                actor=payload.actor,
                reason=payload.reason,
            )
            db.add(
                LogisticShipmentAllocation(
                    shipment_line_id=line.id,
                    reservation_id=reservation.id,
                    quantity=quantity,
                    base_uom_id=line.base_uom_id,
                )
            )
            line.reserved_base_quantity += quantity
            to_allocate -= quantity
        if line.reserved_base_quantity >= line.requested_base_quantity:
            line.reservation_result = StockReservationResult.FULL
        elif line.reserved_base_quantity > 0:
            line.reservation_result = StockReservationResult.PARTIAL
        else:
            line.reservation_result = StockReservationResult.NONE

    result_counts = {
        result: sum(line.reservation_result == result for line in shipment.lines)
        for result in StockReservationResult
    }
    db.add(
        LogisticShipmentReservationAttempt(
            shipment_id=shipment.id,
            idempotency_key=payload.idempotency_key,
            command_hash=command_hash,
            full_line_count=result_counts[StockReservationResult.FULL],
            partial_line_count=result_counts[StockReservationResult.PARTIAL],
            missing_line_count=result_counts[StockReservationResult.NONE],
            actor=payload.actor,
            reason=payload.reason,
        )
    )
    if any(line.reserved_base_quantity > 0 for line in shipment.lines):
        shipment.status = ShipmentStatus.RESERVED
    db.add(
        OperationEvent(
            operation="logistic_shipment_quantities_reserved",
            object_type=REFERENCE_TYPE,
            object_uid=shipment.shipment_uid,
            actor=payload.actor,
            reason=payload.reason,
            after={
                "full_line_count": result_counts[StockReservationResult.FULL],
                "partial_line_count": result_counts[StockReservationResult.PARTIAL],
                "missing_line_count": result_counts[StockReservationResult.NONE],
            },
        )
    )
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        existing_attempt = db.scalar(
            select(LogisticShipmentReservationAttempt).where(
                LogisticShipmentReservationAttempt.idempotency_key
                == payload.idempotency_key
            )
        )
        if existing_attempt is not None and existing_attempt.command_hash == command_hash:
            return get_logistic_shipment(db, shipment_uid)
        raise _conflict("shipment reservation conflicts with existing data") from exc
    db.refresh(shipment)
    return shipment


def reserve_shipment_quantities(
    db: Session,
    shipment_uid: str,
    payload: LogisticShipmentReserveQuantityRequest,
) -> LogisticShipment:
    try:
        return _reserve_shipment_quantities(db, shipment_uid, payload)
    except Exception:
        db.rollback()
        raise


def _decrement_content_projection(db: Session, reservation: StockReservation) -> None:
    if reservation.logistic_unit_id is None:
        return
    query = select(LogisticUnitContent).where(
        LogisticUnitContent.logistic_unit_id == reservation.logistic_unit_id,
        LogisticUnitContent.product_id == reservation.product_id,
        LogisticUnitContent.uom_id == reservation.base_uom_id,
    )
    query = (
        query.where(LogisticUnitContent.batch_id.is_(None))
        if reservation.batch_id is None
        else query.where(LogisticUnitContent.batch_id == reservation.batch_id)
    )
    projection = db.scalar(query.with_for_update())
    if projection is None:
        return
    if projection.quantity < reservation.quantity:
        raise _conflict("logistic unit content projection is smaller than reserved stock")
    if projection.quantity == reservation.quantity:
        db.delete(projection)
    else:
        projection.quantity -= reservation.quantity


def pick_shipment_quantities(
    db: Session,
    shipment_uid: str,
    payload: LogisticShipmentPickQuantityRequest,
) -> LogisticShipment:
    from app.logistic_documents import get_logistic_shipment

    command_hash = _command_hash("pick_quantities", shipment_uid, payload)
    shipment = get_logistic_shipment(db, shipment_uid, for_update=True)
    if shipment.picking_stock_document_id is not None:
        if (
            shipment.picking_idempotency_key == payload.idempotency_key
            and shipment.picking_command_hash == command_hash
        ):
            return shipment
        raise _conflict("shipment quantities are already picked")
    if shipment.status not in {
        ShipmentStatus.RESERVED,
        ShipmentStatus.EXPEDITION,
        ShipmentStatus.LOADING,
    }:
        raise _conflict("shipment quantities cannot be picked from its current status")
    if not shipment.lines or any(
        line.reservation_result != StockReservationResult.FULL
        or line.reserved_base_quantity != line.requested_base_quantity
        for line in shipment.lines
    ):
        raise _conflict("all shipment quantity lines must be fully reserved")
    allocations = [allocation for line in shipment.lines for allocation in line.allocations]
    if not allocations or any(allocation.status != "reserved" for allocation in allocations):
        raise _conflict("shipment has no complete reserved allocation set")
    if any(
        sum((item.quantity for item in line.allocations), Decimal("0"))
        != line.requested_base_quantity
        for line in shipment.lines
    ):
        raise _conflict("shipment allocation quantities do not match its lines")
    expedition = db.scalar(
        select(Location).where(Location.code == payload.expedition_location_code)
    )
    if (
        expedition is None
        or not expedition.is_active
        or expedition.kind != LocationKind.EXPEDITION
        or expedition.warehouse_id != shipment.warehouse_id
    ):
        raise _bad_request("active expedition location must belong to shipment warehouse")

    reservations = [allocation.reservation for allocation in allocations]
    if any(reservation.status != StockReservationStatus.ACTIVE for reservation in reservations):
        raise _conflict("all shipment allocations must have active reservations")
    movements = [
        StockMovementPost(
            product_id=reservation.product_id,
            batch_id=reservation.batch_id,
            serial_number=reservation.serial_number,
            owner_id=reservation.owner_id,
            source_quality_status=reservation.quality_status,
            destination_quality_status=reservation.quality_status,
            input_quantity=reservation.quantity,
            input_uom_id=reservation.base_uom_id,
            source_logistic_unit_id=reservation.logistic_unit_id,
            source_location_id=reservation.location_id,
            destination_location_id=expedition.id,
        )
        for reservation in reservations
    ]
    command = StockDocumentPost(
        document_type="shipment_pick",
        reference_type=REFERENCE_TYPE,
        reference_uid=shipment.shipment_uid,
        idempotency_key=payload.idempotency_key,
        actor=payload.actor,
        reason=payload.reason,
        attributes={"operation": "shipment_quantity_pick", "shipment_id": shipment.id},
        movements=movements,
    )

    def finalize(document: StockDocument) -> None:
        picked_at = utcnow()
        for allocation, reservation in zip(allocations, reservations, strict=True):
            _decrement_content_projection(db, reservation)
            reservation.status = StockReservationStatus.CONSUMED
            reservation.consumed_at = picked_at
            reservation.consumed_by_document_id = document.id
            reservation.consume_idempotency_key = (
                "SHP-PICK-"
                + hashlib.sha256(
                    f"{payload.idempotency_key}:{reservation.uid}".encode()
                ).hexdigest()[:40]
            )
            reservation.consume_command_hash = command_hash
            reservation.consume_actor = payload.actor
            reservation.consume_reason = payload.reason
            db.add(
                OperationEvent(
                    operation="stock_reservation_consumed",
                    object_type="stock_reservation",
                    object_uid=reservation.uid,
                    actor=payload.actor,
                    reason=payload.reason,
                    before={"status": StockReservationStatus.ACTIVE.value},
                    after={
                        "status": StockReservationStatus.CONSUMED.value,
                        "stock_document_uid": document.uid,
                        "shipment_uid": shipment.shipment_uid,
                    },
                )
            )
            allocation.status = "picked"
            allocation.expedition_location_id = expedition.id
            allocation.picking_stock_document_id = document.id
            allocation.picked_at = picked_at
        for line in shipment.lines:
            line.picked_base_quantity = line.reserved_base_quantity
        if shipment.status != ShipmentStatus.LOADING:
            shipment.status = ShipmentStatus.EXPEDITION
        shipment.picking_stock_document_id = document.id
        shipment.picking_idempotency_key = payload.idempotency_key
        shipment.picking_command_hash = command_hash
        db.add(
            OperationEvent(
                operation="logistic_shipment_quantities_picked",
                object_type=REFERENCE_TYPE,
                object_uid=shipment.shipment_uid,
                actor=payload.actor,
                reason=payload.reason,
                after={
                    "stock_document_uid": document.uid,
                    "expedition_location_code": expedition.code,
                    "allocation_count": len(allocations),
                },
            )
        )

    post_stock_document(
        db,
        command,
        before_commit=finalize,
        consuming_reservation_ids={reservation.id for reservation in reservations},
    )
    db.refresh(shipment)
    return shipment


def load_shipment_quantities(
    db: Session,
    shipment_uid: str,
    payload: LogisticShipmentLoadQuantityRequest,
) -> LogisticShipment:
    from app.logistic_documents import get_logistic_shipment

    command_hash = _command_hash("load_quantities", shipment_uid, payload)
    shipment = get_logistic_shipment(db, shipment_uid, for_update=True)
    if shipment.loading_stock_document_id is not None:
        if (
            shipment.loading_idempotency_key == payload.idempotency_key
            and shipment.loading_command_hash == command_hash
        ):
            return shipment
        raise _conflict("shipment quantities are already loaded")
    if shipment.status not in {ShipmentStatus.EXPEDITION, ShipmentStatus.LOADING}:
        raise _conflict("shipment quantities cannot be loaded from its current status")
    allocations = [allocation for line in shipment.lines for allocation in line.allocations]
    if not allocations or any(
        allocation.status != "picked" or allocation.expedition_location_id is None
        for allocation in allocations
    ):
        raise _conflict("all shipment quantity allocations must be picked first")
    if any(
        sum((item.quantity for item in line.allocations), Decimal("0"))
        != line.picked_base_quantity
        for line in shipment.lines
    ):
        raise _conflict("picked allocation quantities do not match shipment lines")
    reservations = [allocation.reservation for allocation in allocations]
    movements = [
        StockMovementPost(
            product_id=reservation.product_id,
            batch_id=reservation.batch_id,
            serial_number=reservation.serial_number,
            owner_id=reservation.owner_id,
            source_quality_status=reservation.quality_status,
            input_quantity=allocation.quantity,
            input_uom_id=allocation.base_uom_id,
            source_location_id=allocation.expedition_location_id,
        )
        for allocation, reservation in zip(allocations, reservations, strict=True)
    ]
    command = StockDocumentPost(
        document_type="shipment_load",
        reference_type=REFERENCE_TYPE,
        reference_uid=shipment.shipment_uid,
        idempotency_key=payload.idempotency_key,
        actor=payload.actor,
        reason=payload.reason,
        attributes={"operation": "shipment_quantity_load", "shipment_id": shipment.id},
        movements=movements,
    )

    def finalize(document: StockDocument) -> None:
        loaded_at = utcnow()
        for allocation in allocations:
            allocation.status = "loaded"
            allocation.loading_stock_document_id = document.id
            allocation.loaded_at = loaded_at
        for line in shipment.lines:
            line.loaded_base_quantity = line.picked_base_quantity
        shipment.status = ShipmentStatus.LOADING
        shipment.loading_stock_document_id = document.id
        shipment.loading_idempotency_key = payload.idempotency_key
        shipment.loading_command_hash = command_hash
        db.add(
            OperationEvent(
                operation="logistic_shipment_quantities_loaded",
                object_type=REFERENCE_TYPE,
                object_uid=shipment.shipment_uid,
                actor=payload.actor,
                reason=payload.reason,
                after={
                    "stock_document_uid": document.uid,
                    "allocation_count": len(allocations),
                },
            )
        )

    post_stock_document(db, command, before_commit=finalize)
    db.refresh(shipment)
    return shipment


def validate_quantity_lines_loaded(shipment: LogisticShipment) -> None:
    if not shipment.lines:
        return
    if any(
        line.loaded_base_quantity != line.requested_base_quantity
        for line in shipment.lines
    ):
        raise _conflict("all shipment quantity lines must be loaded before closing")
