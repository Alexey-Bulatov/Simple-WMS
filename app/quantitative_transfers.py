import hashlib
import json
from datetime import date
from decimal import Decimal

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.entities import (
    Location,
    LogisticTransfer,
    LogisticTransferAllocation,
    LogisticTransferLine,
    LogisticTransferReservationAttempt,
    LogisticUnitContent,
    OperationEvent,
    StockDocument,
    StockPosition,
    StockReservation,
    utcnow,
)
from app.models.enums import (
    LocationKind,
    StockReservationResult,
    StockReservationStatus,
    TransferKind,
    TransferStatus,
)
from app.quantitative_shipments import _resolve_line
from app.schemas import (
    LogisticTransferDispatchQuantityRequest,
    LogisticTransferLineCreate,
    LogisticTransferPickQuantityRequest,
    LogisticTransferReceiveQuantityRequest,
    LogisticTransferReserveQuantityRequest,
    StockDocumentPost,
    StockMovementPost,
)
from app.stock import stock_position_payload
from app.stock_ledger import post_stock_document
from app.stock_reservations import _build_stock_reservation


REFERENCE_TYPE = "logistic_transfer"


def _bad_request(message: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=message)


def _conflict(message: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=message)


def _command_hash(operation: str, transfer_uid: str, payload) -> str:
    serialized = json.dumps(
        {
            "operation": operation,
            "transfer_uid": transfer_uid,
            "payload": payload.model_dump(mode="json"),
        },
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def _require_quantity_only_transport(transfer: LogisticTransfer) -> None:
    if transfer.transfer_kind != TransferKind.TRANSPORT:
        raise _conflict("quantity lines currently require a transport transfer")
    if transfer.units:
        raise _conflict("quantity transfer cannot be mixed with logistic units yet")


def add_quantity_lines(
    db: Session,
    transfer: LogisticTransfer,
    payloads: list[LogisticTransferLineCreate],
) -> None:
    seen_serials: set[tuple[int, str]] = set()
    for line_no, payload in enumerate(payloads, start=1):
        product, owner, input_uom, packaging, batch, base_quantity, base_uom = (
            _resolve_line(db, payload)
        )
        if payload.serial_number is not None:
            serial_key = (product.id, payload.serial_number)
            if serial_key in seen_serials:
                raise _bad_request("serial number is repeated in transfer")
            seen_serials.add(serial_key)
        db.add(
            LogisticTransferLine(
                transfer_id=transfer.id,
                line_no=line_no,
                line_uid=f"{transfer.transfer_uid}-L{line_no:03d}",
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


def _allocation_payload(allocation: LogisticTransferAllocation) -> dict:
    reservation = allocation.reservation
    return {
        "id": allocation.id,
        "reservation_uid": reservation.uid,
        "status": allocation.status,
        "quantity": allocation.quantity,
        "base_uom_code": allocation.base_uom.code,
        "source_holder": reservation.logistic_unit_uid or reservation.location_code or "",
        "source_location_code": reservation.location_code,
        "source_logistic_unit_uid": reservation.logistic_unit_uid,
        "transfer_out_location_code": (
            allocation.transfer_out_location.code
            if allocation.transfer_out_location
            else None
        ),
        "transfer_in_location_code": (
            allocation.transfer_in_location.code
            if allocation.transfer_in_location
            else None
        ),
        "picking_stock_document_uid": (
            allocation.picking_stock_document.uid
            if allocation.picking_stock_document
            else None
        ),
        "dispatch_stock_document_uid": (
            allocation.dispatch_stock_document.uid
            if allocation.dispatch_stock_document
            else None
        ),
        "receiving_stock_document_uid": (
            allocation.receiving_stock_document.uid
            if allocation.receiving_stock_document
            else None
        ),
        "picked_at": allocation.picked_at,
        "dispatched_at": allocation.dispatched_at,
        "received_at": allocation.received_at,
    }


def quantity_lines_payload(transfer: LogisticTransfer) -> list[dict]:
    return [
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
            "dispatched_base_quantity": line.dispatched_base_quantity,
            "received_base_quantity": line.received_base_quantity,
            "note": line.note,
            "allocations": [_allocation_payload(item) for item in line.allocations],
        }
        for line in transfer.lines
    ]


def _candidate_positions(
    db: Session,
    transfer: LogisticTransfer,
    line: LogisticTransferLine,
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
            data["warehouse_id"] == transfer.source_warehouse_id
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


def _reserve_transfer_quantities(
    db: Session,
    transfer_uid: str,
    payload: LogisticTransferReserveQuantityRequest,
) -> LogisticTransfer:
    from app.logistic_documents import get_logistic_transfer

    command_hash = _command_hash("reserve_quantities", transfer_uid, payload)
    existing_attempt = db.scalar(
        select(LogisticTransferReservationAttempt).where(
            LogisticTransferReservationAttempt.idempotency_key == payload.idempotency_key
        )
    )
    if existing_attempt is not None:
        if existing_attempt.command_hash != command_hash:
            raise _conflict("idempotency key belongs to another transfer reservation")
        return get_logistic_transfer(db, transfer_uid)

    transfer = get_logistic_transfer(db, transfer_uid, for_update=True)
    _require_quantity_only_transport(transfer)
    if transfer.status not in {TransferStatus.DRAFT, TransferStatus.RESERVED}:
        raise _conflict("transfer quantities cannot be reserved from its current status")
    if not transfer.lines:
        raise _bad_request("transfer has no quantity lines")

    for line in transfer.lines:
        remaining = line.requested_base_quantity - line.reserved_base_quantity
        if remaining <= 0:
            line.reservation_result = StockReservationResult.FULL
            continue
        candidates = _candidate_positions(db, transfer, line)
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
                "TRF-RSV-"
                + hashlib.sha256(
                    f"{payload.idempotency_key}:{line.line_uid}:{position.id}:{quantity}".encode()
                ).hexdigest()[:40]
            )
            reservation = _build_stock_reservation(
                db,
                position=position,
                quantity=quantity,
                base_uom=line.base_uom,
                input_quantity=quantity,
                input_uom=line.base_uom,
                conversion_factor=Decimal("1.00000000"),
                reference_type=REFERENCE_TYPE,
                reference_uid=transfer.transfer_uid,
                reference_line_uid=line.line_uid,
                task=None,
                idempotency_key=reservation_key,
                command_hash=hashlib.sha256(reservation_key.encode()).hexdigest(),
                actor=payload.actor,
                reason=payload.reason,
            )
            db.add(
                LogisticTransferAllocation(
                    transfer_line_id=line.id,
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
        result: sum(line.reservation_result == result for line in transfer.lines)
        for result in StockReservationResult
    }
    db.add(
        LogisticTransferReservationAttempt(
            transfer_id=transfer.id,
            idempotency_key=payload.idempotency_key,
            command_hash=command_hash,
            full_line_count=result_counts[StockReservationResult.FULL],
            partial_line_count=result_counts[StockReservationResult.PARTIAL],
            missing_line_count=result_counts[StockReservationResult.NONE],
            actor=payload.actor,
            reason=payload.reason,
        )
    )
    if any(line.reserved_base_quantity > 0 for line in transfer.lines):
        transfer.status = TransferStatus.RESERVED
    db.add(
        OperationEvent(
            operation="logistic_transfer_quantities_reserved",
            object_type=REFERENCE_TYPE,
            object_uid=transfer.transfer_uid,
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
            select(LogisticTransferReservationAttempt).where(
                LogisticTransferReservationAttempt.idempotency_key
                == payload.idempotency_key
            )
        )
        if existing_attempt is not None and existing_attempt.command_hash == command_hash:
            return get_logistic_transfer(db, transfer_uid)
        raise _conflict("transfer reservation conflicts with existing data") from exc
    db.refresh(transfer)
    return transfer


def reserve_transfer_quantities(
    db: Session,
    transfer_uid: str,
    payload: LogisticTransferReserveQuantityRequest,
) -> LogisticTransfer:
    try:
        return _reserve_transfer_quantities(db, transfer_uid, payload)
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


def _allocations(transfer: LogisticTransfer) -> list[LogisticTransferAllocation]:
    return [allocation for line in transfer.lines for allocation in line.allocations]


def pick_transfer_quantities(
    db: Session,
    transfer_uid: str,
    payload: LogisticTransferPickQuantityRequest,
) -> LogisticTransfer:
    from app.logistic_documents import get_logistic_transfer

    command_hash = _command_hash("pick_quantities", transfer_uid, payload)
    transfer = get_logistic_transfer(db, transfer_uid, for_update=True)
    _require_quantity_only_transport(transfer)
    if transfer.picking_stock_document_id is not None:
        if (
            transfer.picking_idempotency_key == payload.idempotency_key
            and transfer.picking_command_hash == command_hash
        ):
            return transfer
        raise _conflict("transfer quantities are already picked")
    if transfer.status not in {TransferStatus.RESERVED, TransferStatus.EXPEDITION}:
        raise _conflict("transfer quantities cannot be picked from its current status")
    if not transfer.lines or any(
        line.reservation_result != StockReservationResult.FULL
        or line.reserved_base_quantity != line.requested_base_quantity
        for line in transfer.lines
    ):
        raise _conflict("all transfer quantity lines must be fully reserved")
    allocations = _allocations(transfer)
    if not allocations or any(allocation.status != "reserved" for allocation in allocations):
        raise _conflict("transfer has no complete reserved allocation set")
    if any(
        sum((item.quantity for item in line.allocations), Decimal("0"))
        != line.requested_base_quantity
        for line in transfer.lines
    ):
        raise _conflict("transfer allocation quantities do not match its lines")
    transfer_out = db.scalar(
        select(Location).where(Location.code == payload.transfer_out_location_code)
    )
    if (
        transfer_out is None
        or not transfer_out.is_active
        or transfer_out.kind != LocationKind.TRANSFER_OUT
        or transfer_out.warehouse_id != transfer.source_warehouse_id
    ):
        raise _bad_request("active transfer-out location must belong to source warehouse")
    reservations = [allocation.reservation for allocation in allocations]
    if any(reservation.status != StockReservationStatus.ACTIVE for reservation in reservations):
        raise _conflict("all transfer allocations must have active reservations")
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
            destination_location_id=transfer_out.id,
        )
        for reservation in reservations
    ]
    command = StockDocumentPost(
        document_type="transfer_pick",
        reference_type=REFERENCE_TYPE,
        reference_uid=transfer.transfer_uid,
        idempotency_key=payload.idempotency_key,
        actor=payload.actor,
        reason=payload.reason,
        attributes={"operation": "transfer_quantity_pick", "transfer_id": transfer.id},
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
                "TRF-PICK-"
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
                        "transfer_uid": transfer.transfer_uid,
                    },
                )
            )
            allocation.status = "picked"
            allocation.transfer_out_location_id = transfer_out.id
            allocation.picking_stock_document_id = document.id
            allocation.picked_at = picked_at
        for line in transfer.lines:
            line.picked_base_quantity = line.reserved_base_quantity
        transfer.status = TransferStatus.EXPEDITION
        transfer.picking_stock_document_id = document.id
        transfer.picking_idempotency_key = payload.idempotency_key
        transfer.picking_command_hash = command_hash
        db.add(
            OperationEvent(
                operation="logistic_transfer_quantities_picked",
                object_type=REFERENCE_TYPE,
                object_uid=transfer.transfer_uid,
                actor=payload.actor,
                reason=payload.reason,
                after={
                    "stock_document_uid": document.uid,
                    "transfer_out_location_code": transfer_out.code,
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
    db.refresh(transfer)
    return transfer


def dispatch_transfer_quantities(
    db: Session,
    transfer_uid: str,
    payload: LogisticTransferDispatchQuantityRequest,
) -> LogisticTransfer:
    from app.logistic_documents import get_logistic_transfer

    command_hash = _command_hash("dispatch_quantities", transfer_uid, payload)
    transfer = get_logistic_transfer(db, transfer_uid, for_update=True)
    _require_quantity_only_transport(transfer)
    if transfer.dispatch_stock_document_id is not None:
        if (
            transfer.dispatch_idempotency_key == payload.idempotency_key
            and transfer.dispatch_command_hash == command_hash
        ):
            return transfer
        raise _conflict("transfer quantities are already dispatched")
    if transfer.status != TransferStatus.EXPEDITION:
        raise _conflict("transfer quantities must be picked before dispatch")
    allocations = _allocations(transfer)
    if not allocations or any(
        allocation.status != "picked" or allocation.transfer_out_location_id is None
        for allocation in allocations
    ):
        raise _conflict("all transfer quantity allocations must be picked first")
    if any(
        sum((item.quantity for item in line.allocations), Decimal("0"))
        != line.picked_base_quantity
        for line in transfer.lines
    ):
        raise _conflict("picked allocation quantities do not match transfer lines")
    movements = [
        StockMovementPost(
            product_id=allocation.reservation.product_id,
            batch_id=allocation.reservation.batch_id,
            serial_number=allocation.reservation.serial_number,
            owner_id=allocation.reservation.owner_id,
            source_quality_status=allocation.reservation.quality_status,
            input_quantity=allocation.quantity,
            input_uom_id=allocation.base_uom_id,
            source_location_id=allocation.transfer_out_location_id,
        )
        for allocation in allocations
    ]
    command = StockDocumentPost(
        document_type="transfer_dispatch",
        reference_type=REFERENCE_TYPE,
        reference_uid=transfer.transfer_uid,
        idempotency_key=payload.idempotency_key,
        actor=payload.actor,
        reason=payload.reason,
        attributes={"operation": "transfer_quantity_dispatch", "transfer_id": transfer.id},
        movements=movements,
    )

    def finalize(document: StockDocument) -> None:
        dispatched_at = utcnow()
        for allocation in allocations:
            allocation.status = "in_transit"
            allocation.dispatch_stock_document_id = document.id
            allocation.dispatched_at = dispatched_at
        for line in transfer.lines:
            line.dispatched_base_quantity = line.picked_base_quantity
        transfer.status = TransferStatus.IN_TRANSIT
        transfer.dispatched_at = dispatched_at
        transfer.dispatch_stock_document_id = document.id
        transfer.dispatch_idempotency_key = payload.idempotency_key
        transfer.dispatch_command_hash = command_hash
        db.add(
            OperationEvent(
                operation="logistic_transfer_quantities_dispatched",
                object_type=REFERENCE_TYPE,
                object_uid=transfer.transfer_uid,
                actor=payload.actor,
                reason=payload.reason,
                after={
                    "stock_document_uid": document.uid,
                    "allocation_count": len(allocations),
                    "status": transfer.status.value,
                },
            )
        )
        from app.logistic_tasks import sync_logistic_transfer_tasks

        sync_logistic_transfer_tasks(db, transfer, actor=payload.actor)

    post_stock_document(db, command, before_commit=finalize)
    db.refresh(transfer)
    return transfer


def receive_transfer_quantities(
    db: Session,
    transfer_uid: str,
    payload: LogisticTransferReceiveQuantityRequest,
) -> LogisticTransfer:
    from app.logistic_documents import get_logistic_transfer

    command_hash = _command_hash("receive_quantities", transfer_uid, payload)
    transfer = get_logistic_transfer(db, transfer_uid, for_update=True)
    _require_quantity_only_transport(transfer)
    if transfer.receiving_stock_document_id is not None:
        if (
            transfer.receiving_idempotency_key == payload.idempotency_key
            and transfer.receiving_command_hash == command_hash
        ):
            return transfer
        raise _conflict("transfer quantities are already received")
    if transfer.status not in {TransferStatus.IN_TRANSIT, TransferStatus.RECEIVING}:
        raise _conflict("transfer quantities must be in transit before receiving")
    allocations = _allocations(transfer)
    if not allocations or any(allocation.status != "in_transit" for allocation in allocations):
        raise _conflict("all transfer quantity allocations must be in transit")
    if any(
        sum((item.quantity for item in line.allocations), Decimal("0"))
        != line.dispatched_base_quantity
        for line in transfer.lines
    ):
        raise _conflict("dispatched allocation quantities do not match transfer lines")
    transfer_in = db.scalar(
        select(Location).where(Location.code == payload.transfer_in_location_code)
    )
    if (
        transfer_in is None
        or not transfer_in.is_active
        or transfer_in.kind != LocationKind.TRANSFER_IN
        or transfer_in.warehouse_id != transfer.destination_warehouse_id
    ):
        raise _bad_request("active transfer-in location must belong to destination warehouse")
    movements = [
        StockMovementPost(
            product_id=allocation.reservation.product_id,
            batch_id=allocation.reservation.batch_id,
            serial_number=allocation.reservation.serial_number,
            owner_id=allocation.reservation.owner_id,
            destination_quality_status=allocation.reservation.quality_status,
            input_quantity=allocation.quantity,
            input_uom_id=allocation.base_uom_id,
            destination_location_id=transfer_in.id,
        )
        for allocation in allocations
    ]
    command = StockDocumentPost(
        document_type="transfer_receive",
        reference_type=REFERENCE_TYPE,
        reference_uid=transfer.transfer_uid,
        idempotency_key=payload.idempotency_key,
        actor=payload.actor,
        reason=payload.reason,
        attributes={"operation": "transfer_quantity_receive", "transfer_id": transfer.id},
        movements=movements,
    )

    def finalize(document: StockDocument) -> None:
        received_at = utcnow()
        for allocation in allocations:
            allocation.status = "received"
            allocation.transfer_in_location_id = transfer_in.id
            allocation.receiving_stock_document_id = document.id
            allocation.received_at = received_at
        for line in transfer.lines:
            line.received_base_quantity = line.dispatched_base_quantity
        transfer.status = TransferStatus.COMPLETED
        transfer.completed_at = received_at
        transfer.receiving_stock_document_id = document.id
        transfer.receiving_idempotency_key = payload.idempotency_key
        transfer.receiving_command_hash = command_hash
        db.add(
            OperationEvent(
                operation="logistic_transfer_quantities_received",
                object_type=REFERENCE_TYPE,
                object_uid=transfer.transfer_uid,
                actor=payload.actor,
                reason=payload.reason,
                after={
                    "stock_document_uid": document.uid,
                    "transfer_in_location_code": transfer_in.code,
                    "allocation_count": len(allocations),
                    "status": transfer.status.value,
                },
            )
        )
        from app.logistic_tasks import sync_logistic_transfer_tasks

        sync_logistic_transfer_tasks(db, transfer, actor=payload.actor)

    post_stock_document(db, command, before_commit=finalize)
    db.refresh(transfer)
    return transfer
