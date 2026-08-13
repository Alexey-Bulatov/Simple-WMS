import hashlib
import json
from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.entities import (
    ProductPackaging,
    StockDocument,
    StockPosition,
    StockRecipient,
    UnitOfMeasure,
)
from app.schemas import (
    InternalIssueCreate,
    StockDocumentPost,
    StockDocumentReverseRequest,
    StockMovementPost,
)
from app.stock import convert_product_quantity_to_base, stock_position_payload
from app.stock_ledger import (
    post_stock_document,
    reverse_stock_document,
    stock_document_payload,
)


INTERNAL_ISSUE_DOCUMENT_TYPE = "internal_issue"


def _bad_request(message: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=message)


def _conflict(message: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=message)


def _issue_command_hash(payload: InternalIssueCreate) -> str:
    serialized = json.dumps(
        payload.model_dump(mode="json"),
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def _existing_issue(
    db: Session,
    idempotency_key: str,
    command_hash: str,
) -> StockDocument | None:
    document = db.scalar(
        select(StockDocument).where(StockDocument.idempotency_key == idempotency_key)
    )
    if document is None:
        return None
    if (
        document.document_type != INTERNAL_ISSUE_DOCUMENT_TYPE
        or (document.attributes or {}).get("issue_command_hash") != command_hash
    ):
        raise _conflict("idempotency key belongs to another command")
    return document


def _validate_scans(
    db: Session,
    position: StockPosition,
    *,
    source_scan: str | None,
    item_scan: str | None,
) -> None:
    data = stock_position_payload(db, position)
    if source_scan:
        accepted_sources = {
            value.upper()
            for value in (
                data["location_code"],
                data["logistic_unit_uid"],
                data["root_logistic_unit_uid"],
            )
            if value
        }
        if source_scan not in accepted_sources:
            raise _bad_request("source scan does not match the selected stock position")
    if item_scan:
        accepted_items = {data["product_code"].upper()}
        if position.serial_number:
            accepted_items.add(position.serial_number.upper())
        packagings = db.scalars(
            select(ProductPackaging).where(
                ProductPackaging.product_id == position.product_id,
                ProductPackaging.is_active.is_(True),
            )
        )
        for packaging in packagings:
            accepted_items.add(packaging.code.upper())
            if packaging.barcode:
                accepted_items.add(packaging.barcode.upper())
        if item_scan not in accepted_items:
            raise _bad_request("item scan does not match the selected product")


def create_internal_issue(
    db: Session,
    payload: InternalIssueCreate,
    *,
    warehouse_scope: set[int] | None = None,
) -> StockDocument:
    command_hash = _issue_command_hash(payload)
    existing = _existing_issue(db, payload.idempotency_key, command_hash)
    if existing is not None:
        return existing

    recipient = db.get(StockRecipient, payload.recipient_id)
    if recipient is None or not recipient.is_active:
        raise _bad_request("active stock recipient not found")

    movements: list[StockMovementPost] = []
    line_inputs: list[dict] = []
    warehouse_ids: set[int] = set()
    for line in payload.lines:
        position = db.get(StockPosition, line.stock_position_id)
        if position is None:
            raise _bad_request("stock position not found")
        data = stock_position_payload(db, position)
        if data["warehouse_id"] is None:
            raise _bad_request("stock position is not assigned to a warehouse")
        if warehouse_scope is not None and data["warehouse_id"] not in warehouse_scope:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="stock position belongs to an unavailable warehouse",
            )
        warehouse_ids.add(data["warehouse_id"])
        _validate_scans(
            db,
            position,
            source_scan=line.source_scan,
            item_scan=line.item_scan,
        )
        product = position.product
        packaging = db.get(ProductPackaging, line.packaging_id) if line.packaging_id else None
        if packaging is not None and (
            not packaging.is_active or packaging.product_id != position.product_id
        ):
            raise _bad_request("active product packaging not found")
        if line.packaging_id is not None and packaging is None:
            raise _bad_request("active product packaging not found")
        input_uom_id = packaging.uom_id if packaging else line.input_uom_id
        input_quantity = line.input_quantity * packaging.quantity if packaging else line.input_quantity
        input_uom = db.get(UnitOfMeasure, input_uom_id)
        if input_uom is None:
            raise _bad_request("input unit of measure not found")
        base_quantity, _ = convert_product_quantity_to_base(
            db,
            product,
            input_quantity,
            input_uom,
        )
        if data["available_quantity"] < base_quantity:
            raise _conflict("insufficient available stock for internal issue")
        movements.append(
            StockMovementPost(
                product_id=position.product_id,
                batch_id=position.batch_id,
                serial_number=position.serial_number,
                owner_id=position.owner_id,
                source_quality_status=position.quality_status,
                input_quantity=input_quantity,
                input_uom_id=input_uom.id,
                source_logistic_unit_id=position.logistic_unit_id,
                source_location_id=position.location_id,
            )
        )
        line_inputs.append(
            {
                "stock_position_id": position.id,
                "entered_quantity": str(line.input_quantity),
                "input_uom_id": line.input_uom_id,
                "packaging_id": packaging.id if packaging else None,
                "packaging_code": packaging.code if packaging else None,
                "packaging_name": packaging.name if packaging else None,
            }
        )
    if len(warehouse_ids) != 1:
        raise _bad_request("one internal issue must use stock from one warehouse")

    deterministic_uid = f"ISS-{hashlib.sha256(payload.idempotency_key.encode()).hexdigest()[:20].upper()}"
    document = post_stock_document(
        db,
        StockDocumentPost(
            uid=deterministic_uid,
            document_type=INTERNAL_ISSUE_DOCUMENT_TYPE,
            reference_type="stock_recipient",
            reference_uid=recipient.code,
            idempotency_key=payload.idempotency_key,
            actor=payload.actor,
            reason=payload.reason,
            attributes={
                "recipient_id": recipient.id,
                "recipient_code": recipient.code,
                "recipient_name": recipient.name,
                "recipient_kind": recipient.kind.value,
                "request_reference": payload.request_reference,
                "issue_command_hash": command_hash,
                "line_inputs": line_inputs,
            },
            movements=movements,
        ),
    )
    return document


def get_internal_issue(db: Session, uid: str) -> StockDocument:
    document = db.scalar(
        select(StockDocument).where(
            StockDocument.uid == uid.strip().upper(),
            StockDocument.document_type == INTERNAL_ISSUE_DOCUMENT_TYPE,
        )
    )
    if document is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="internal_issue not found")
    return document


def reverse_internal_issue(
    db: Session,
    uid: str,
    payload: StockDocumentReverseRequest,
) -> StockDocument:
    issue = get_internal_issue(db, uid)
    reverse_stock_document(db, issue.uid, payload)
    return get_internal_issue(db, uid)


def internal_issue_payload(db: Session, document: StockDocument) -> dict:
    data = stock_document_payload(db, document, include_movements=True)
    attributes = document.attributes or {}
    return {
        "uid": document.uid,
        "status": document.status,
        "recipient_id": attributes["recipient_id"],
        "recipient_code": attributes["recipient_code"],
        "recipient_name": attributes["recipient_name"],
        "recipient_kind": attributes["recipient_kind"],
        "request_reference": attributes.get("request_reference"),
        "actor": document.actor,
        "reason": document.reason or "",
        "idempotency_key": document.idempotency_key,
        "warehouse_ids": data["warehouse_ids"],
        "warehouse_codes": data["warehouse_codes"],
        "created_at": document.created_at,
        "posted_at": document.posted_at,
        "reversed_at": document.reversed_at,
        "movements": data["movements"],
    }
