import hashlib
import json
from datetime import datetime
from decimal import Decimal
from uuid import uuid4

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.entities import (
    Batch,
    LogisticUnit,
    Location,
    LogisticTask,
    OperationEvent,
    Product,
    StockDocument,
    StockOwner,
    StockPosition,
    StockReservation,
    UnitOfMeasure,
    utcnow,
)
from app.models.enums import StockReservationStatus, TaskStatus
from app.schemas import (
    StockDocumentPost,
    StockMovementPost,
    StockReservationConsumeRequest,
    StockReservationCreate,
    StockReservationReleaseRequest,
)
from app.stock import convert_product_quantity_to_base, stock_position_payload
from app.stock_ledger import post_stock_document


def _bad_request(message: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=message)


def _conflict(message: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=message)


def _not_found() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="stock reservation not found",
    )


def _command_hash(
    payload: (
        StockReservationCreate
        | StockReservationReleaseRequest
        | StockReservationConsumeRequest
    ),
) -> str:
    serialized = json.dumps(
        payload.model_dump(mode="json"),
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def _idempotent_create(
    db: Session,
    idempotency_key: str,
    command_hash: str,
) -> StockReservation | None:
    reservation = db.scalar(
        select(StockReservation).where(
            StockReservation.idempotency_key == idempotency_key
        )
    )
    if reservation is None:
        return None
    if reservation.command_hash != command_hash:
        raise _conflict("idempotency key belongs to another reservation command")
    return reservation


def create_stock_reservation(
    db: Session,
    payload: StockReservationCreate,
) -> StockReservation:
    command_hash = _command_hash(payload)
    try:
        existing = _idempotent_create(db, payload.idempotency_key, command_hash)
        if existing is not None:
            return existing

        position = db.scalar(
            select(StockPosition)
            .where(StockPosition.id == payload.stock_position_id)
            .execution_options(populate_existing=True)
            .with_for_update()
        )
        if position is None:
            raise _bad_request("stock position not found")

        existing = _idempotent_create(db, payload.idempotency_key, command_hash)
        if existing is not None:
            return existing

        product = db.get(Product, position.product_id)
        input_uom = db.get(UnitOfMeasure, payload.input_uom_id)
        if product is None or not product.is_active:
            raise _bad_request("active product not found")
        if input_uom is None:
            raise _bad_request("input unit of measure not found")
        quantity, base_uom = convert_product_quantity_to_base(
            db,
            product,
            payload.input_quantity,
            input_uom,
        )
        position_payload = stock_position_payload(db, position)
        available = position_payload["available_quantity"]
        if quantity > available:
            raise _conflict("insufficient available stock for reservation")

        task = None
        if payload.task_uid is not None:
            task = db.scalar(
                select(LogisticTask)
                .where(LogisticTask.task_uid == payload.task_uid)
                .execution_options(populate_existing=True)
                .with_for_update()
            )
            if task is None:
                raise _bad_request("logistic task not found")
            if task.status not in {TaskStatus.NEW, TaskStatus.IN_PROGRESS}:
                raise _conflict("stock reservation requires an active logistic task")
            if (
                task.object_type != payload.reference_type
                or task.object_uid != payload.reference_uid.strip().upper()
            ):
                raise _conflict("logistic task does not match the reservation reference")
            if task.warehouse_id != position_payload["warehouse_id"]:
                raise _conflict("logistic task belongs to another warehouse")

        logistic_unit = (
            db.get(LogisticUnit, position.logistic_unit_id)
            if position.logistic_unit_id is not None
            else None
        )
        location = (
            db.get(Location, position.location_id)
            if position.location_id is not None
            else None
        )
        if logistic_unit is None and location is None:
            raise _conflict("stock position has no valid holder")

        conversion_factor = (input_uom.factor_to_base / base_uom.factor_to_base).quantize(
            Decimal("0.00000001")
        )
        reservation = StockReservation(
            uid=f"RSV-{uuid4().hex[:20].upper()}",
            status=StockReservationStatus.ACTIVE,
            stock_position_id=position.id,
            product_id=position.product_id,
            batch_id=position.batch_id,
            serial_number=position.serial_number,
            owner_id=position.owner_id,
            quality_status=position.quality_status,
            quantity=quantity,
            base_uom_id=base_uom.id,
            input_quantity=payload.input_quantity,
            input_uom_id=input_uom.id,
            conversion_factor=conversion_factor,
            logistic_unit_id=position.logistic_unit_id,
            location_id=position.location_id,
            logistic_unit_uid=logistic_unit.uid if logistic_unit else None,
            location_code=location.code if location else None,
            reference_type=payload.reference_type,
            reference_uid=payload.reference_uid,
            reference_line_uid=payload.reference_line_uid,
            task_id=task.id if task else None,
            idempotency_key=payload.idempotency_key,
            command_hash=command_hash,
            actor=payload.actor,
            reason=payload.reason,
        )
        db.add(reservation)
        db.flush()
        db.add(
            OperationEvent(
                operation="stock_reservation_created",
                object_type="stock_reservation",
                object_uid=reservation.uid,
                actor=payload.actor,
                reason=payload.reason,
                before=None,
                after={
                    "status": StockReservationStatus.ACTIVE.value,
                    "stock_position_id": position.id,
                    "quantity": str(quantity),
                    "reference_type": payload.reference_type,
                    "reference_uid": payload.reference_uid,
                    "reference_line_uid": payload.reference_line_uid,
                    "task_uid": task.task_uid if task else None,
                },
            )
        )
        db.commit()
        db.refresh(reservation)
        return reservation
    except IntegrityError as exc:
        db.rollback()
        existing = _idempotent_create(db, payload.idempotency_key, command_hash)
        if existing is not None:
            return existing
        raise _conflict("stock reservation conflicts with existing data") from exc
    except Exception:
        db.rollback()
        raise


def _idempotent_release(
    db: Session,
    reservation_uid: str,
    idempotency_key: str,
    command_hash: str,
) -> StockReservation | None:
    reservation = db.scalar(
        select(StockReservation).where(
            StockReservation.release_idempotency_key == idempotency_key
        )
    )
    if reservation is None:
        return None
    if reservation.uid != reservation_uid or reservation.release_command_hash != command_hash:
        raise _conflict("idempotency key belongs to another reservation release")
    return reservation


def release_stock_reservation(
    db: Session,
    reservation_uid: str,
    payload: StockReservationReleaseRequest,
) -> StockReservation:
    normalized_uid = reservation_uid.strip().upper()
    command_hash = _command_hash(payload)
    try:
        existing = _idempotent_release(
            db,
            normalized_uid,
            payload.idempotency_key,
            command_hash,
        )
        if existing is not None:
            return existing

        reservation = db.scalar(
            select(StockReservation)
            .where(StockReservation.uid == normalized_uid)
            .execution_options(populate_existing=True)
            .with_for_update()
        )
        if reservation is None:
            raise _not_found()

        existing = _idempotent_release(
            db,
            normalized_uid,
            payload.idempotency_key,
            command_hash,
        )
        if existing is not None:
            return existing
        if reservation.status == StockReservationStatus.RELEASED:
            raise _conflict("stock reservation is already released")
        if reservation.status == StockReservationStatus.CONSUMED:
            raise _conflict("consumed stock reservation cannot be released")

        released_at = utcnow()
        reservation.status = StockReservationStatus.RELEASED
        reservation.released_at = released_at
        reservation.release_idempotency_key = payload.idempotency_key
        reservation.release_command_hash = command_hash
        reservation.release_actor = payload.actor
        reservation.release_reason = payload.reason
        db.add(
            OperationEvent(
                operation="stock_reservation_released",
                object_type="stock_reservation",
                object_uid=reservation.uid,
                actor=payload.actor,
                reason=payload.reason,
                before={"status": StockReservationStatus.ACTIVE.value},
                after={
                    "status": StockReservationStatus.RELEASED.value,
                    "released_at": released_at.isoformat(),
                },
            )
        )
        db.commit()
        db.refresh(reservation)
        return reservation
    except IntegrityError as exc:
        db.rollback()
        existing = _idempotent_release(
            db,
            normalized_uid,
            payload.idempotency_key,
            command_hash,
        )
        if existing is not None:
            return existing
        raise _conflict("stock reservation release conflicts with existing data") from exc
    except Exception:
        db.rollback()
        raise


def _idempotent_consume(
    db: Session,
    reservation_uid: str,
    idempotency_key: str,
    command_hash: str,
) -> StockReservation | None:
    reservation = db.scalar(
        select(StockReservation).where(
            StockReservation.consume_idempotency_key == idempotency_key
        )
    )
    if reservation is None:
        return None
    if reservation.uid != reservation_uid or reservation.consume_command_hash != command_hash:
        raise _conflict("idempotency key belongs to another reservation consumption")
    if reservation.status != StockReservationStatus.CONSUMED:
        raise _conflict(
            "reservation consumption was reversed; use a new idempotency key"
        )
    return reservation


def _complete_linked_task(
    db: Session,
    reservation: StockReservation,
    document: StockDocument,
    *,
    actor: str,
    reason: str,
    completed_at: datetime,
) -> LogisticTask | None:
    if reservation.task_id is None:
        return None
    task = db.scalar(
        select(LogisticTask)
        .where(LogisticTask.id == reservation.task_id)
        .execution_options(populate_existing=True)
        .with_for_update()
    )
    if task is None:
        raise _conflict("linked logistic task no longer exists")
    if task.status not in {TaskStatus.NEW, TaskStatus.IN_PROGRESS}:
        raise _conflict("linked logistic task is not active")
    if task.assigned_to and task.assigned_to != actor:
        raise _conflict("linked logistic task is assigned to another operator")
    before = {
        "status": task.status.value,
        "assigned_to": task.assigned_to,
    }
    task.assigned_to = task.assigned_to or actor
    task.started_at = task.started_at or completed_at
    remaining_reservations = db.scalar(
        select(func.count(StockReservation.id)).where(
            StockReservation.task_id == task.id,
            StockReservation.status == StockReservationStatus.ACTIVE,
        )
    ) or 0
    if remaining_reservations:
        task.status = TaskStatus.IN_PROGRESS
        task.parameters = {
            **(task.parameters or {}),
            "last_consumed_reservation_uid": reservation.uid,
            "last_stock_document_uid": document.uid,
            "remaining_reservation_count": remaining_reservations,
        }
        db.add(
            OperationEvent(
                operation="logistic_task_progressed_by_stock_reservation",
                object_type="logistic_task",
                object_uid=task.task_uid,
                actor=actor,
                reason=reason,
                before=before,
                after={
                    "status": TaskStatus.IN_PROGRESS.value,
                    "assigned_to": task.assigned_to,
                    "reservation_uid": reservation.uid,
                    "stock_document_uid": document.uid,
                    "remaining_reservation_count": remaining_reservations,
                },
            )
        )
        return task

    task.status = TaskStatus.COMPLETED
    task.completed_at = completed_at
    task.parameters = {
        **(task.parameters or {}),
        "completed_by_reservation_uid": reservation.uid,
        "stock_document_uid": document.uid,
    }
    db.add(
        OperationEvent(
            operation="logistic_task_completed_by_stock_reservation",
            object_type="logistic_task",
            object_uid=task.task_uid,
            actor=actor,
            reason=reason,
            before=before,
            after={
                "status": TaskStatus.COMPLETED.value,
                "assigned_to": task.assigned_to,
                "reservation_uid": reservation.uid,
                "stock_document_uid": document.uid,
            },
        )
    )
    return task


def _consume_stock_reservation(
    db: Session,
    reservation_uid: str,
    payload: StockReservationConsumeRequest,
) -> StockReservation:
    normalized_uid = reservation_uid.strip().upper()
    command_hash = _command_hash(payload)
    existing = _idempotent_consume(
        db,
        normalized_uid,
        payload.idempotency_key,
        command_hash,
    )
    if existing is not None:
        return existing

    reservation = db.scalar(
        select(StockReservation)
        .where(StockReservation.uid == normalized_uid)
        .execution_options(populate_existing=True)
        .with_for_update()
    )
    if reservation is None:
        raise _not_found()

    existing = _idempotent_consume(
        db,
        normalized_uid,
        payload.idempotency_key,
        command_hash,
    )
    if existing is not None:
        return existing
    if reservation.status == StockReservationStatus.RELEASED:
        raise _conflict("released stock reservation cannot be consumed")
    if reservation.status == StockReservationStatus.CONSUMED:
        raise _conflict("stock reservation is already consumed")

    position = db.scalar(
        select(StockPosition)
        .where(StockPosition.id == reservation.stock_position_id)
        .execution_options(populate_existing=True)
    )
    if position is None:
        raise _conflict("reserved stock position no longer exists")
    if (
        position.product_id != reservation.product_id
        or position.batch_id != reservation.batch_id
        or position.serial_number != reservation.serial_number
        or position.owner_id != reservation.owner_id
        or position.quality_status != reservation.quality_status
        or position.logistic_unit_id != reservation.logistic_unit_id
        or position.location_id != reservation.location_id
    ):
        raise _conflict("reserved stock position identity has changed")
    product = db.get(Product, reservation.product_id)
    if product is None or product.base_uom_id != reservation.base_uom_id:
        raise _conflict("product base unit changed after reservation")
    if position.quantity < reservation.quantity:
        raise _conflict("reserved stock quantity is no longer available")

    task = None
    if reservation.task_id is not None:
        task = db.get(LogisticTask, reservation.task_id)
        if task is None:
            raise _conflict("linked logistic task no longer exists")
        if task.status not in {TaskStatus.NEW, TaskStatus.IN_PROGRESS}:
            raise _conflict("linked logistic task is not active")
        if task.assigned_to and task.assigned_to != payload.actor:
            raise _conflict("linked logistic task is assigned to another operator")

    has_destination = (
        payload.destination_logistic_unit_id is not None
        or payload.destination_location_id is not None
    )
    command = StockDocumentPost(
        document_type="stock_pick" if has_destination else "stock_issue",
        reference_type=reservation.reference_type,
        reference_uid=reservation.reference_uid,
        idempotency_key=payload.idempotency_key,
        actor=payload.actor,
        reason=payload.reason,
        attributes={
            "operation": "stock_reservation_consumption",
            "reservation_uid": reservation.uid,
            "reference_line_uid": reservation.reference_line_uid,
            "task_uid": task.task_uid if task else None,
            "reserved_input_quantity": str(reservation.input_quantity),
            "reserved_input_uom_id": reservation.input_uom_id,
        },
        movements=[
            StockMovementPost(
                product_id=reservation.product_id,
                batch_id=reservation.batch_id,
                serial_number=reservation.serial_number,
                owner_id=reservation.owner_id,
                source_quality_status=reservation.quality_status,
                destination_quality_status=(
                    payload.destination_quality_status or reservation.quality_status
                    if has_destination
                    else None
                ),
                input_quantity=reservation.quantity,
                input_uom_id=reservation.base_uom_id,
                source_logistic_unit_id=reservation.logistic_unit_id,
                source_location_id=reservation.location_id,
                destination_logistic_unit_id=payload.destination_logistic_unit_id,
                destination_location_id=payload.destination_location_id,
            )
        ],
    )

    def mark_consumed(document: StockDocument) -> None:
        consumed_at = utcnow()
        reservation.status = StockReservationStatus.CONSUMED
        reservation.consumed_at = consumed_at
        reservation.consumed_by_document_id = document.id
        reservation.consume_idempotency_key = payload.idempotency_key
        reservation.consume_command_hash = command_hash
        reservation.consume_actor = payload.actor
        reservation.consume_reason = payload.reason
        db.flush()
        completed_task = _complete_linked_task(
            db,
            reservation,
            document,
            actor=payload.actor,
            reason=payload.reason,
            completed_at=consumed_at,
        )
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
                    "task_uid": completed_task.task_uid if completed_task else None,
                    "consumed_at": consumed_at.isoformat(),
                },
            )
        )

    document = post_stock_document(
        db,
        command,
        before_commit=mark_consumed,
        consuming_reservation_ids={reservation.id},
    )
    db.refresh(reservation)
    if (
        reservation.status != StockReservationStatus.CONSUMED
        or reservation.consumed_by_document_id != document.id
    ):
        raise _conflict("stock document exists without reservation consumption")
    return reservation


def consume_stock_reservation(
    db: Session,
    reservation_uid: str,
    payload: StockReservationConsumeRequest,
) -> StockReservation:
    try:
        return _consume_stock_reservation(db, reservation_uid, payload)
    except Exception:
        db.rollback()
        raise


def stock_reservation_payload(db: Session, reservation: StockReservation) -> dict:
    product = db.get(Product, reservation.product_id)
    batch = db.get(Batch, reservation.batch_id) if reservation.batch_id is not None else None
    owner = db.get(StockOwner, reservation.owner_id)
    base_uom = db.get(UnitOfMeasure, reservation.base_uom_id)
    input_uom = db.get(UnitOfMeasure, reservation.input_uom_id)
    consumed_document = (
        db.get(StockDocument, reservation.consumed_by_document_id)
        if reservation.consumed_by_document_id is not None
        else None
    )
    task = db.get(LogisticTask, reservation.task_id) if reservation.task_id else None
    return {
        "id": reservation.id,
        "uid": reservation.uid,
        "status": reservation.status,
        "stock_position_id": reservation.stock_position_id,
        "product_id": reservation.product_id,
        "product_code": product.code if product else "",
        "product_name": product.name if product else "",
        "batch_id": reservation.batch_id,
        "batch_number": batch.batch_number if batch else None,
        "serial_number": reservation.serial_number,
        "owner_id": reservation.owner_id,
        "owner_code": owner.code if owner else "",
        "quality_status": reservation.quality_status,
        "quantity": reservation.quantity,
        "base_uom_id": reservation.base_uom_id,
        "base_uom_code": base_uom.code if base_uom else "",
        "input_quantity": reservation.input_quantity,
        "input_uom_id": reservation.input_uom_id,
        "input_uom_code": input_uom.code if input_uom else "",
        "conversion_factor": reservation.conversion_factor,
        "holder_kind": (
            "logistic_unit" if reservation.logistic_unit_uid is not None else "location"
        ),
        "logistic_unit_id": reservation.logistic_unit_id,
        "logistic_unit_uid": reservation.logistic_unit_uid,
        "location_id": reservation.location_id,
        "location_code": reservation.location_code,
        "reference_type": reservation.reference_type,
        "reference_uid": reservation.reference_uid,
        "reference_line_uid": reservation.reference_line_uid,
        "task_id": reservation.task_id,
        "task_uid": task.task_uid if task else None,
        "task_status": task.status if task else None,
        "idempotency_key": reservation.idempotency_key,
        "actor": reservation.actor,
        "reason": reservation.reason,
        "created_at": reservation.created_at,
        "released_at": reservation.released_at,
        "release_actor": reservation.release_actor,
        "release_reason": reservation.release_reason,
        "consumed_at": reservation.consumed_at,
        "consumed_by_document_id": reservation.consumed_by_document_id,
        "consumed_by_document_uid": consumed_document.uid if consumed_document else None,
        "consume_actor": reservation.consume_actor,
        "consume_reason": reservation.consume_reason,
    }
