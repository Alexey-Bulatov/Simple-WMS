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
    StockReservationRequest,
    UnitOfMeasure,
    utcnow,
)
from app.models.enums import (
    LogisticUnitStatus,
    StockReservationKind,
    StockReservationResult,
    StockReservationStatus,
    TaskStatus,
)
from app.schemas import (
    StockDocumentPost,
    StockMovementPost,
    StockReservationConsumeRequest,
    StockReservationCreate,
    StockReservationLogisticUnitRequest,
    StockReservationQuantityRequest,
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
        | StockReservationQuantityRequest
        | StockReservationLogisticUnitRequest
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


def _request_command_hash(
    kind: StockReservationKind,
    payload: StockReservationQuantityRequest | StockReservationLogisticUnitRequest,
) -> str:
    serialized = json.dumps(
        {"kind": kind.value, "payload": payload.model_dump(mode="json")},
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

        _, input_uom, quantity, base_uom, conversion_factor = (
            _convert_reservation_quantity(
                db,
                position,
                payload.input_quantity,
                payload.input_uom_id,
            )
        )
        position_payload = stock_position_payload(db, position)
        available = position_payload["available_quantity"]
        if quantity > available:
            raise _conflict("insufficient available stock for reservation")

        task = _load_reservation_task(
            db,
            payload.task_uid,
            reference_type=payload.reference_type,
            reference_uid=payload.reference_uid,
            warehouse_id=position_payload["warehouse_id"],
        )
        reservation = _build_stock_reservation(
            db,
            position=position,
            quantity=quantity,
            base_uom=base_uom,
            input_quantity=payload.input_quantity,
            input_uom=input_uom,
            conversion_factor=conversion_factor,
            reference_type=payload.reference_type,
            reference_uid=payload.reference_uid,
            reference_line_uid=payload.reference_line_uid,
            task=task,
            idempotency_key=payload.idempotency_key,
            command_hash=command_hash,
            actor=payload.actor,
            reason=payload.reason,
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


def _convert_reservation_quantity(
    db: Session,
    position: StockPosition,
    input_quantity: Decimal,
    input_uom_id: int,
) -> tuple[Product, UnitOfMeasure, Decimal, UnitOfMeasure, Decimal]:
    product = db.get(Product, position.product_id)
    input_uom = db.get(UnitOfMeasure, input_uom_id)
    if product is None or not product.is_active:
        raise _bad_request("active product not found")
    if input_uom is None:
        raise _bad_request("input unit of measure not found")
    quantity, base_uom = convert_product_quantity_to_base(
        db,
        product,
        input_quantity,
        input_uom,
    )
    conversion_factor = (input_uom.factor_to_base / base_uom.factor_to_base).quantize(
        Decimal("0.00000001")
    )
    return product, input_uom, quantity, base_uom, conversion_factor


def _load_reservation_task(
    db: Session,
    task_uid: str | None,
    *,
    reference_type: str,
    reference_uid: str,
    warehouse_id: int | None,
) -> LogisticTask | None:
    if task_uid is None:
        return None
    task = db.scalar(
        select(LogisticTask)
        .where(LogisticTask.task_uid == task_uid)
        .execution_options(populate_existing=True)
        .with_for_update()
    )
    if task is None:
        raise _bad_request("logistic task not found")
    if task.status not in {TaskStatus.NEW, TaskStatus.IN_PROGRESS}:
        raise _conflict("stock reservation requires an active logistic task")
    if task.object_type != reference_type or task.object_uid != reference_uid.strip().upper():
        raise _conflict("logistic task does not match the reservation reference")
    if warehouse_id is None or task.warehouse_id != warehouse_id:
        raise _conflict("logistic task belongs to another warehouse")
    return task


def _build_stock_reservation(
    db: Session,
    *,
    position: StockPosition,
    quantity: Decimal,
    base_uom: UnitOfMeasure,
    input_quantity: Decimal,
    input_uom: UnitOfMeasure,
    conversion_factor: Decimal,
    reference_type: str,
    reference_uid: str,
    reference_line_uid: str | None,
    task: LogisticTask | None,
    idempotency_key: str,
    command_hash: str,
    actor: str,
    reason: str | None,
    request: StockReservationRequest | None = None,
) -> StockReservation:
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
    reservation = StockReservation(
        uid=f"RSV-{uuid4().hex[:20].upper()}",
        request_id=request.id if request else None,
        status=StockReservationStatus.ACTIVE,
        stock_position_id=position.id,
        product_id=position.product_id,
        batch_id=position.batch_id,
        serial_number=position.serial_number,
        owner_id=position.owner_id,
        quality_status=position.quality_status,
        quantity=quantity,
        base_uom_id=base_uom.id,
        input_quantity=input_quantity,
        input_uom_id=input_uom.id,
        conversion_factor=conversion_factor,
        logistic_unit_id=position.logistic_unit_id,
        location_id=position.location_id,
        logistic_unit_uid=logistic_unit.uid if logistic_unit else None,
        location_code=location.code if location else None,
        reference_type=reference_type,
        reference_uid=reference_uid,
        reference_line_uid=reference_line_uid,
        task_id=task.id if task else None,
        idempotency_key=idempotency_key,
        command_hash=command_hash,
        actor=actor,
        reason=reason,
    )
    db.add(reservation)
    db.flush()
    db.add(
        OperationEvent(
            operation="stock_reservation_created",
            object_type="stock_reservation",
            object_uid=reservation.uid,
            actor=actor,
            reason=reason,
            before=None,
            after={
                "request_uid": request.uid if request else None,
                "status": StockReservationStatus.ACTIVE.value,
                "stock_position_id": position.id,
                "quantity": str(quantity),
                "reference_type": reference_type,
                "reference_uid": reference_uid,
                "reference_line_uid": reference_line_uid,
                "task_uid": task.task_uid if task else None,
            },
        )
    )
    return reservation


def _idempotent_request(
    db: Session,
    idempotency_key: str,
    command_hash: str,
) -> StockReservationRequest | None:
    request = db.scalar(
        select(StockReservationRequest).where(
            StockReservationRequest.idempotency_key == idempotency_key
        )
    )
    if request is None:
        return None
    if request.command_hash != command_hash:
        raise _conflict("idempotency key belongs to another reservation request")
    return request


def _add_request_event(db: Session, request: StockReservationRequest) -> None:
    db.add(
        OperationEvent(
            operation="stock_reservation_request_created",
            object_type="stock_reservation_request",
            object_uid=request.uid,
            actor=request.actor,
            reason=request.reason,
            before=None,
            after={
                "kind": request.kind.value,
                "result": request.result.value,
                "reference_type": request.reference_type,
                "reference_uid": request.reference_uid,
                "reference_line_uid": request.reference_line_uid,
                "expected_position_count": request.expected_position_count,
                "allocation_count": request.allocation_count,
            },
        )
    )


def create_quantity_reservation_request(
    db: Session,
    payload: StockReservationQuantityRequest,
) -> StockReservationRequest:
    kind = StockReservationKind.QUANTITY
    command_hash = _request_command_hash(kind, payload)
    try:
        existing = _idempotent_request(db, payload.idempotency_key, command_hash)
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
        existing = _idempotent_request(db, payload.idempotency_key, command_hash)
        if existing is not None:
            return existing

        _, input_uom, requested_quantity, base_uom, conversion_factor = (
            _convert_reservation_quantity(
                db,
                position,
                payload.input_quantity,
                payload.input_uom_id,
            )
        )
        position_data = stock_position_payload(db, position)
        available_quantity = position_data["available_quantity"]
        if requested_quantity <= available_quantity:
            reserved_quantity = requested_quantity
            result = StockReservationResult.FULL
        elif payload.allow_partial and available_quantity > 0:
            reserved_quantity = available_quantity
            result = StockReservationResult.PARTIAL
        else:
            reserved_quantity = Decimal("0")
            result = StockReservationResult.NONE

        task = _load_reservation_task(
            db,
            payload.task_uid,
            reference_type=payload.reference_type,
            reference_uid=payload.reference_uid,
            warehouse_id=position_data["warehouse_id"],
        )
        request = StockReservationRequest(
            uid=f"RSQ-{uuid4().hex[:20].upper()}",
            kind=kind,
            result=result,
            requested_stock_position_id=position.id,
            requested_quantity=requested_quantity,
            reserved_quantity=reserved_quantity,
            base_uom_id=base_uom.id,
            input_quantity=payload.input_quantity,
            input_uom_id=input_uom.id,
            conversion_factor=conversion_factor,
            allow_partial=payload.allow_partial,
            expected_position_count=1,
            allocation_count=1 if reserved_quantity > 0 else 0,
            reference_type=payload.reference_type,
            reference_uid=payload.reference_uid,
            reference_line_uid=payload.reference_line_uid,
            task_id=task.id if task else None,
            idempotency_key=payload.idempotency_key,
            command_hash=command_hash,
            actor=payload.actor,
            reason=payload.reason,
        )
        db.add(request)
        db.flush()
        if reserved_quantity > 0:
            allocated_input_quantity = (
                payload.input_quantity
                if reserved_quantity == requested_quantity
                else (reserved_quantity / conversion_factor).quantize(Decimal("0.00000001"))
            )
            allocation_hash = hashlib.sha256(
                f"{request.uid}:{position.id}:{reserved_quantity}".encode("utf-8")
            ).hexdigest()
            _build_stock_reservation(
                db,
                position=position,
                quantity=reserved_quantity,
                base_uom=base_uom,
                input_quantity=allocated_input_quantity,
                input_uom=input_uom,
                conversion_factor=conversion_factor,
                reference_type=payload.reference_type,
                reference_uid=payload.reference_uid,
                reference_line_uid=payload.reference_line_uid,
                task=task,
                idempotency_key=f"{request.uid}:{position.id}",
                command_hash=allocation_hash,
                actor=payload.actor,
                reason=payload.reason,
                request=request,
            )
        _add_request_event(db, request)
        db.commit()
        db.refresh(request)
        return request
    except IntegrityError as exc:
        db.rollback()
        existing = _idempotent_request(db, payload.idempotency_key, command_hash)
        if existing is not None:
            return existing
        raise _conflict("stock reservation request conflicts with existing data") from exc
    except Exception:
        db.rollback()
        raise


def _logistic_unit_hierarchy_ids(db: Session, root_id: int) -> list[int]:
    unit_ids = [root_id]
    frontier = [root_id]
    while frontier:
        child_ids = list(
            db.scalars(
                select(LogisticUnit.id)
                .where(LogisticUnit.parent_unit_id.in_(frontier))
                .order_by(LogisticUnit.id)
                .with_for_update()
            )
        )
        frontier = [item for item in child_ids if item not in unit_ids]
        unit_ids.extend(frontier)
    return unit_ids


def create_logistic_unit_reservation_request(
    db: Session,
    payload: StockReservationLogisticUnitRequest,
) -> StockReservationRequest:
    kind = StockReservationKind.LOGISTIC_UNIT
    command_hash = _request_command_hash(kind, payload)
    try:
        existing = _idempotent_request(db, payload.idempotency_key, command_hash)
        if existing is not None:
            return existing
        unit = db.scalar(
            select(LogisticUnit)
            .where(LogisticUnit.uid == payload.logistic_unit_uid)
            .execution_options(populate_existing=True)
            .with_for_update()
        )
        if unit is None:
            raise _bad_request("logistic unit not found")
        if unit.parent_unit_id is not None:
            raise _conflict("nested logistic unit must be reserved with its root unit")
        existing = _idempotent_request(db, payload.idempotency_key, command_hash)
        if existing is not None:
            return existing

        unit_ids = _logistic_unit_hierarchy_ids(db, unit.id)
        positions = list(
            db.scalars(
                select(StockPosition)
                .where(StockPosition.logistic_unit_id.in_(unit_ids))
                .order_by(StockPosition.id)
                .execution_options(populate_existing=True)
                .with_for_update()
            )
        )
        position_data = [stock_position_payload(db, position) for position in positions]
        can_reserve_all = (
            unit.status == LogisticUnitStatus.AVAILABLE
            and bool(positions)
            and all(
                data["available_quantity"] == position.quantity and position.quantity > 0
                for position, data in zip(positions, position_data, strict=True)
            )
        )
        unit_location = (
            db.get(Location, unit.current_location_id)
            if unit.current_location_id is not None
            else None
        )
        if position_data:
            warehouse_id = position_data[0]["warehouse_id"]
        elif unit_location is not None:
            warehouse_id = unit_location.warehouse_id
        else:
            warehouse_id = None
        task = _load_reservation_task(
            db,
            payload.task_uid,
            reference_type=payload.reference_type,
            reference_uid=payload.reference_uid,
            warehouse_id=warehouse_id,
        )
        result = StockReservationResult.FULL if can_reserve_all else StockReservationResult.NONE
        request = StockReservationRequest(
            uid=f"RSQ-{uuid4().hex[:20].upper()}",
            kind=kind,
            result=result,
            requested_logistic_unit_id=unit.id,
            requested_logistic_unit_uid=unit.uid,
            allow_partial=False,
            expected_position_count=len(positions),
            allocation_count=len(positions) if can_reserve_all else 0,
            reference_type=payload.reference_type,
            reference_uid=payload.reference_uid,
            reference_line_uid=payload.reference_line_uid,
            task_id=task.id if task else None,
            idempotency_key=payload.idempotency_key,
            command_hash=command_hash,
            actor=payload.actor,
            reason=payload.reason,
        )
        db.add(request)
        db.flush()
        if can_reserve_all:
            for position in positions:
                product = db.get(Product, position.product_id)
                base_uom = (
                    db.get(UnitOfMeasure, product.base_uom_id)
                    if product is not None and product.base_uom_id is not None
                    else None
                )
                if product is None or not product.is_active or base_uom is None:
                    raise _conflict("logistic unit contains stock without a valid base unit")
                allocation_hash = hashlib.sha256(
                    f"{request.uid}:{position.id}:{position.quantity}".encode("utf-8")
                ).hexdigest()
                _build_stock_reservation(
                    db,
                    position=position,
                    quantity=position.quantity,
                    base_uom=base_uom,
                    input_quantity=position.quantity,
                    input_uom=base_uom,
                    conversion_factor=Decimal("1.00000000"),
                    reference_type=payload.reference_type,
                    reference_uid=payload.reference_uid,
                    reference_line_uid=payload.reference_line_uid,
                    task=task,
                    idempotency_key=f"{request.uid}:{position.id}",
                    command_hash=allocation_hash,
                    actor=payload.actor,
                    reason=payload.reason,
                    request=request,
                )
        _add_request_event(db, request)
        db.commit()
        db.refresh(request)
        return request
    except IntegrityError as exc:
        db.rollback()
        existing = _idempotent_request(db, payload.idempotency_key, command_hash)
        if existing is not None:
            return existing
        raise _conflict("stock reservation request conflicts with existing data") from exc
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
    position = (
        db.get(StockPosition, reservation.stock_position_id)
        if reservation.stock_position_id is not None
        else None
    )
    position_data = stock_position_payload(db, position) if position is not None else {}
    return {
        "id": reservation.id,
        "uid": reservation.uid,
        "request_id": reservation.request_id,
        "request_uid": reservation.request.uid if reservation.request else None,
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
        "warehouse_id": position_data.get("warehouse_id"),
        "warehouse_code": position_data.get("warehouse_code"),
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


def stock_reservation_request_payload(
    db: Session,
    request: StockReservationRequest,
) -> dict:
    base_uom = db.get(UnitOfMeasure, request.base_uom_id) if request.base_uom_id else None
    input_uom = db.get(UnitOfMeasure, request.input_uom_id) if request.input_uom_id else None
    task = db.get(LogisticTask, request.task_id) if request.task_id else None
    reservations = list(
        db.scalars(
            select(StockReservation)
            .where(StockReservation.request_id == request.id)
            .order_by(StockReservation.id)
        )
    )
    return {
        "id": request.id,
        "uid": request.uid,
        "kind": request.kind,
        "result": request.result,
        "requested_stock_position_id": request.requested_stock_position_id,
        "requested_logistic_unit_id": request.requested_logistic_unit_id,
        "requested_logistic_unit_uid": request.requested_logistic_unit_uid,
        "requested_quantity": request.requested_quantity,
        "reserved_quantity": request.reserved_quantity,
        "base_uom_id": request.base_uom_id,
        "base_uom_code": base_uom.code if base_uom else None,
        "input_quantity": request.input_quantity,
        "input_uom_id": request.input_uom_id,
        "input_uom_code": input_uom.code if input_uom else None,
        "conversion_factor": request.conversion_factor,
        "allow_partial": request.allow_partial,
        "expected_position_count": request.expected_position_count,
        "allocation_count": request.allocation_count,
        "active_allocation_count": sum(
            reservation.status == StockReservationStatus.ACTIVE
            for reservation in reservations
        ),
        "reference_type": request.reference_type,
        "reference_uid": request.reference_uid,
        "reference_line_uid": request.reference_line_uid,
        "task_id": request.task_id,
        "task_uid": task.task_uid if task else None,
        "idempotency_key": request.idempotency_key,
        "actor": request.actor,
        "reason": request.reason,
        "created_at": request.created_at,
        "reservations": [stock_reservation_payload(db, item) for item in reservations],
    }
