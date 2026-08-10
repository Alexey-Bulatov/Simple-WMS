import hashlib
import json
from collections.abc import Callable
from decimal import Decimal
from uuid import uuid4

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.entities import (
    Batch,
    Location,
    LogisticUnit,
    Product,
    StockDocument,
    StockMovement,
    StockOwner,
    StockPosition,
    UnitOfMeasure,
    utcnow,
)
from app.models.enums import MeasurementDimension, StockDocumentStatus
from app.schemas import StockDocumentPost, StockMovementPost
from app.stock import (
    TERMINAL_UNIT_STATUSES,
    convert_product_quantity_to_base,
    stock_position_identity_query,
)


COMMAND_HASH_ATTRIBUTE = "_command_hash"


def _bad_request(message: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=message)


def _conflict(message: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=message)


def _command_hash(payload: StockDocumentPost) -> str:
    serialized = json.dumps(
        payload.model_dump(mode="json"),
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def _idempotent_document(
    db: Session,
    idempotency_key: str,
    command_hash: str,
) -> StockDocument | None:
    document = db.scalar(
        select(StockDocument).where(StockDocument.idempotency_key == idempotency_key)
    )
    if document is None:
        return None
    if (document.attributes or {}).get(COMMAND_HASH_ATTRIBUTE) != command_hash:
        raise _conflict("idempotency key belongs to another stock command")
    return document


def _holder_identity(
    movement: StockMovementPost,
    *,
    source: bool,
) -> tuple[int | None, int | None, str | None]:
    if source:
        return (
            movement.source_logistic_unit_id,
            movement.source_location_id,
            movement.source_quality_status.strip() if movement.source_quality_status else None,
        )
    return (
        movement.destination_logistic_unit_id,
        movement.destination_location_id,
        movement.destination_quality_status.strip()
        if movement.destination_quality_status
        else None,
    )


def _locked_position(
    db: Session,
    *,
    logistic_unit_id: int | None,
    location_id: int | None,
    product_id: int,
    batch_id: int | None,
    owner_id: int,
    quality_status: str,
    serial_number: str | None,
) -> StockPosition | None:
    return db.scalar(
        stock_position_identity_query(
            logistic_unit_id=logistic_unit_id,
            location_id=location_id,
            product_id=product_id,
            batch_id=batch_id,
            owner_id=owner_id,
            quality_status=quality_status,
            serial_number=serial_number,
        )
        .execution_options(populate_existing=True)
        .with_for_update()
    )


def _validate_holder(
    db: Session,
    *,
    logistic_unit_id: int | None,
    location_id: int | None,
    destination: bool,
) -> None:
    if logistic_unit_id is not None:
        unit = db.get(LogisticUnit, logistic_unit_id)
        if unit is None:
            raise _bad_request("logistic unit not found")
        if destination and unit.status in TERMINAL_UNIT_STATUSES:
            raise _bad_request("destination logistic unit has a terminal status")
    if location_id is not None:
        location = db.get(Location, location_id)
        if location is None or not location.is_active:
            raise _bad_request("active location not found")


def _apply_movement(
    db: Session,
    document: StockDocument,
    sequence_no: int,
    command: StockMovementPost,
    product: Product,
) -> None:
    owner = db.get(StockOwner, command.owner_id)
    if owner is None or not owner.is_active:
        raise _bad_request("active stock owner not found")
    input_uom = db.get(UnitOfMeasure, command.input_uom_id)
    if input_uom is None:
        raise _bad_request("input unit of measure not found")
    quantity, base_uom = convert_product_quantity_to_base(
        db,
        product,
        command.input_quantity,
        input_uom,
    )

    if command.batch_id is not None:
        batch = db.get(Batch, command.batch_id)
        if batch is None or batch.product_id != product.id:
            raise _bad_request("batch does not belong to the product")

    serial_number = command.serial_number
    if serial_number:
        if quantity != Decimal("1"):
            raise _bad_request("serialized stock movement quantity must equal one")
        if base_uom.dimension != MeasurementDimension.QUANTITY.value:
            raise _bad_request("serialized stock requires a quantity base unit")

    source_unit_id, source_location_id, source_quality = _holder_identity(command, source=True)
    destination_unit_id, destination_location_id, destination_quality = _holder_identity(
        command,
        source=False,
    )
    _validate_holder(
        db,
        logistic_unit_id=source_unit_id,
        location_id=source_location_id,
        destination=False,
    )
    _validate_holder(
        db,
        logistic_unit_id=destination_unit_id,
        location_id=destination_location_id,
        destination=True,
    )
    if (
        source_unit_id,
        source_location_id,
        source_quality,
    ) == (
        destination_unit_id,
        destination_location_id,
        destination_quality,
    ):
        raise _bad_request("source and destination stock identities are equal")

    source_position = None
    if source_quality is not None:
        source_position = _locked_position(
            db,
            logistic_unit_id=source_unit_id,
            location_id=source_location_id,
            product_id=product.id,
            batch_id=command.batch_id,
            owner_id=owner.id,
            quality_status=source_quality,
            serial_number=serial_number,
        )
        if source_position is None:
            raise _bad_request("source stock position not found")
        if source_position.quantity < quantity:
            raise _bad_request("insufficient source stock")

    if serial_number and source_position is not None and destination_quality is not None:
        source_position.logistic_unit_id = destination_unit_id
        source_position.location_id = destination_location_id
        source_position.quality_status = destination_quality
    else:
        if source_position is not None:
            if source_position.quantity == quantity:
                db.delete(source_position)
            else:
                source_position.quantity -= quantity

        if destination_quality is not None:
            if serial_number:
                existing_serial = db.scalar(
                    select(StockPosition)
                    .where(
                        StockPosition.product_id == product.id,
                        StockPosition.serial_number == serial_number,
                        StockPosition.owner_id == owner.id,
                    )
                    .execution_options(populate_existing=True)
                    .with_for_update()
                )
                if existing_serial is not None:
                    raise _bad_request("serialized stock already exists")
                destination_position = None
            else:
                destination_position = _locked_position(
                    db,
                    logistic_unit_id=destination_unit_id,
                    location_id=destination_location_id,
                    product_id=product.id,
                    batch_id=command.batch_id,
                    owner_id=owner.id,
                    quality_status=destination_quality,
                    serial_number=None,
                )
            if destination_position is None:
                destination_position = StockPosition(
                    product_id=product.id,
                    batch_id=command.batch_id,
                    serial_number=serial_number,
                    owner_id=owner.id,
                    quality_status=destination_quality,
                    quantity=quantity,
                    logistic_unit_id=destination_unit_id,
                    location_id=destination_location_id,
                )
                db.add(destination_position)
            else:
                destination_position.quantity += quantity

    conversion_factor = (input_uom.factor_to_base / base_uom.factor_to_base).quantize(
        Decimal("0.00000001")
    )
    db.add(
        StockMovement(
            document_id=document.id,
            sequence_no=sequence_no,
            product_id=product.id,
            batch_id=command.batch_id,
            serial_number=serial_number,
            owner_id=owner.id,
            source_quality_status=source_quality,
            destination_quality_status=destination_quality,
            quantity=quantity,
            base_uom_id=base_uom.id,
            input_quantity=command.input_quantity,
            input_uom_id=input_uom.id,
            conversion_factor=conversion_factor,
            source_logistic_unit_id=source_unit_id,
            source_location_id=source_location_id,
            destination_logistic_unit_id=destination_unit_id,
            destination_location_id=destination_location_id,
        )
    )


def post_stock_document(
    db: Session,
    payload: StockDocumentPost,
    *,
    before_commit: Callable[[StockDocument], None] | None = None,
) -> StockDocument:
    idempotency_key = payload.idempotency_key.strip()
    command_hash = _command_hash(payload)
    try:
        existing = _idempotent_document(db, idempotency_key, command_hash)
        if existing is not None:
            return existing
        if any(key.startswith("_") for key in payload.attributes):
            raise _bad_request("stock document attributes cannot use reserved keys")

        product_ids = sorted({movement.product_id for movement in payload.movements})
        products = {
            product.id: product
            for product in db.scalars(
                select(Product)
                .where(Product.id.in_(product_ids))
                .order_by(Product.id)
                .with_for_update()
            )
        }
        if len(products) != len(product_ids) or any(
            not product.is_active for product in products.values()
        ):
            raise _bad_request("active product not found")

        existing = _idempotent_document(db, idempotency_key, command_hash)
        if existing is not None:
            return existing

        attributes = dict(payload.attributes)
        attributes[COMMAND_HASH_ATTRIBUTE] = command_hash
        document = StockDocument(
            uid=(
                payload.uid.strip().upper()
                if payload.uid
                else f"MOV-{uuid4().hex[:20].upper()}"
            ),
            document_type=payload.document_type.strip().lower(),
            status=StockDocumentStatus.DRAFT,
            reference_type=payload.reference_type.strip() if payload.reference_type else None,
            reference_uid=payload.reference_uid.strip() if payload.reference_uid else None,
            idempotency_key=idempotency_key,
            actor=payload.actor.strip(),
            reason=payload.reason.strip() if payload.reason else None,
            attributes=attributes,
        )
        db.add(document)
        db.flush()

        for sequence_no, movement in enumerate(payload.movements, start=1):
            _apply_movement(db, document, sequence_no, movement, products[movement.product_id])
            db.flush()

        if before_commit is not None:
            before_commit(document)
            db.flush()

        document.status = StockDocumentStatus.POSTED
        document.posted_at = utcnow()
        db.commit()
        db.refresh(document)
        return document
    except IntegrityError as exc:
        db.rollback()
        existing = _idempotent_document(db, idempotency_key, command_hash)
        if existing is not None:
            return existing
        raise _conflict("stock document conflicts with existing data") from exc
    except Exception:
        db.rollback()
        raise


def stock_movement_payload(db: Session, movement: StockMovement) -> dict:
    document = db.get(StockDocument, movement.document_id)
    product = db.get(Product, movement.product_id)
    batch = db.get(Batch, movement.batch_id) if movement.batch_id is not None else None
    owner = db.get(StockOwner, movement.owner_id)
    base_uom = db.get(UnitOfMeasure, movement.base_uom_id)
    input_uom = db.get(UnitOfMeasure, movement.input_uom_id)
    source_unit = (
        db.get(LogisticUnit, movement.source_logistic_unit_id)
        if movement.source_logistic_unit_id is not None
        else None
    )
    source_location = (
        db.get(Location, movement.source_location_id)
        if movement.source_location_id is not None
        else None
    )
    destination_unit = (
        db.get(LogisticUnit, movement.destination_logistic_unit_id)
        if movement.destination_logistic_unit_id is not None
        else None
    )
    destination_location = (
        db.get(Location, movement.destination_location_id)
        if movement.destination_location_id is not None
        else None
    )
    return {
        "id": movement.id,
        "document_id": movement.document_id,
        "document_uid": document.uid if document else None,
        "sequence_no": movement.sequence_no,
        "product_id": movement.product_id,
        "product_code": product.code if product else None,
        "batch_id": movement.batch_id,
        "batch_number": batch.batch_number if batch else None,
        "serial_number": movement.serial_number,
        "owner_id": movement.owner_id,
        "owner_code": owner.code if owner else None,
        "source_quality_status": movement.source_quality_status,
        "destination_quality_status": movement.destination_quality_status,
        "quantity": movement.quantity,
        "base_uom_id": movement.base_uom_id,
        "base_uom_code": base_uom.code if base_uom else None,
        "input_quantity": movement.input_quantity,
        "input_uom_id": movement.input_uom_id,
        "input_uom_code": input_uom.code if input_uom else None,
        "conversion_factor": movement.conversion_factor,
        "source_logistic_unit_id": movement.source_logistic_unit_id,
        "source_logistic_unit_uid": source_unit.uid if source_unit else None,
        "source_location_id": movement.source_location_id,
        "source_location_code": source_location.code if source_location else None,
        "destination_logistic_unit_id": movement.destination_logistic_unit_id,
        "destination_logistic_unit_uid": destination_unit.uid if destination_unit else None,
        "destination_location_id": movement.destination_location_id,
        "destination_location_code": destination_location.code if destination_location else None,
        "occurred_at": movement.occurred_at,
    }


def stock_document_payload(
    db: Session,
    document: StockDocument,
    *,
    include_movements: bool = False,
) -> dict:
    reversal = (
        db.get(StockDocument, document.reversal_of_id)
        if document.reversal_of_id is not None
        else None
    )
    payload = {
        "id": document.id,
        "uid": document.uid,
        "document_type": document.document_type,
        "status": document.status,
        "reference_type": document.reference_type,
        "reference_uid": document.reference_uid,
        "idempotency_key": document.idempotency_key,
        "reversal_of_id": document.reversal_of_id,
        "reversal_of_uid": reversal.uid if reversal else None,
        "actor": document.actor,
        "reason": document.reason,
        "attributes": {
            key: value
            for key, value in (document.attributes or {}).items()
            if not key.startswith("_")
        },
        "movement_count": len(document.movements),
        "created_at": document.created_at,
        "posted_at": document.posted_at,
        "reversed_at": document.reversed_at,
    }
    if include_movements:
        payload["movements"] = [
            stock_movement_payload(db, movement) for movement in document.movements
        ]
    return payload
