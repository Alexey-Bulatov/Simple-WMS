from sqlalchemy.orm import Session

from app.models.entities import (
    Batch,
    Location,
    LogisticUnit,
    Product,
    StockDocument,
    StockMovement,
    StockOwner,
    UnitOfMeasure,
)


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
        "attributes": document.attributes or {},
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
