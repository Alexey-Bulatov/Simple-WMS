import hashlib
import json
from decimal import Decimal

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.constants import INBOUND_RECEIPT_CODE_PREFIX
from app.models.entities import (
    InboundReceipt,
    InboundReceiptLine,
    Product,
    ProductPackaging,
    StockOwner,
    UnitOfMeasure,
    Warehouse,
)
from app.schemas import InboundReceiptCreate, InboundReceiptLineCreate
from app.services import create_event
from app.stock import convert_product_quantity_to_base


def _bad_request(message: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=message)


def _conflict(message: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=message)


def _command_hash(payload: InboundReceiptCreate) -> str:
    serialized = json.dumps(
        payload.model_dump(mode="json"),
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def _existing_receipt(
    db: Session,
    idempotency_key: str,
    command_hash: str,
) -> InboundReceipt | None:
    receipt = db.scalar(
        select(InboundReceipt).where(
            InboundReceipt.idempotency_key == idempotency_key
        )
    )
    if receipt is None:
        return None
    if receipt.command_hash != command_hash:
        raise _conflict("idempotency key belongs to another inbound receipt")
    return receipt


def get_inbound_receipt(
    db: Session,
    receipt_uid: str,
    *,
    for_update: bool = False,
) -> InboundReceipt:
    query = select(InboundReceipt).where(
        InboundReceipt.uid == receipt_uid.strip().upper()
    )
    if for_update:
        query = query.with_for_update()
    receipt = db.scalar(query)
    if receipt is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="inbound_receipt not found",
        )
    return receipt


def _resolved_line(
    db: Session,
    line: InboundReceiptLineCreate,
) -> tuple[Product, StockOwner, UnitOfMeasure, ProductPackaging | None, Decimal, UnitOfMeasure]:
    product = db.get(Product, line.product_id)
    if product is None or not product.is_active:
        raise _bad_request("active product not found")
    owner = db.get(StockOwner, line.owner_id)
    if owner is None or not owner.is_active:
        raise _bad_request("active stock owner not found")

    packaging = db.get(ProductPackaging, line.packaging_id) if line.packaging_id else None
    if packaging is not None and (
        not packaging.is_active or packaging.product_id != product.id
    ):
        raise _bad_request("active product packaging not found")
    if line.packaging_id is not None and packaging is None:
        raise _bad_request("active product packaging not found")

    input_uom_id = packaging.uom_id if packaging else line.input_uom_id
    input_uom = db.get(UnitOfMeasure, input_uom_id)
    if input_uom is None or not input_uom.is_active:
        raise _bad_request("active input unit of measure not found")
    converted_input = (
        line.input_quantity * packaging.quantity
        if packaging is not None
        else line.input_quantity
    )
    base_quantity, base_uom = convert_product_quantity_to_base(
        db,
        product,
        converted_input,
        input_uom,
    )
    if line.serial_number is not None and base_quantity != Decimal("1"):
        raise _bad_request("a serialized receipt line must contain one base unit")
    return product, owner, input_uom, packaging, base_quantity, base_uom


def create_inbound_receipt(
    db: Session,
    payload: InboundReceiptCreate,
) -> InboundReceipt:
    command_hash = _command_hash(payload)
    existing = _existing_receipt(db, payload.idempotency_key, command_hash)
    if existing is not None:
        return existing

    warehouse = db.scalar(
        select(Warehouse).where(Warehouse.code == payload.warehouse_code)
    )
    if warehouse is None:
        raise _bad_request("warehouse not found")

    resolved_lines = []
    serial_keys: set[tuple[int, str]] = set()
    for line in payload.lines:
        resolved = _resolved_line(db, line)
        product, _, _, packaging, base_quantity, base_uom = resolved
        if line.serial_number is not None:
            serial_key = (product.id, line.serial_number)
            if serial_key in serial_keys:
                raise _bad_request("serial number is repeated in inbound receipt")
            serial_keys.add(serial_key)
        conversion_factor = (base_quantity / line.input_quantity).quantize(
            Decimal("0.00000001")
        )
        resolved_lines.append(
            (line, resolved, conversion_factor)
        )

    receipt_uid = (
        f"{INBOUND_RECEIPT_CODE_PREFIX}-"
        f"{hashlib.sha256(payload.idempotency_key.encode()).hexdigest()[:20].upper()}"
    )
    receipt = InboundReceipt(
        uid=receipt_uid,
        warehouse_id=warehouse.id,
        receipt_kind=payload.receipt_kind,
        source_name=payload.source_name,
        external_reference=payload.external_reference,
        planned_date=payload.planned_date,
        idempotency_key=payload.idempotency_key,
        command_hash=command_hash,
        actor=payload.actor,
        note=payload.note,
    )
    db.add(receipt)
    db.flush()
    for line_no, (line, resolved, conversion_factor) in enumerate(
        resolved_lines,
        start=1,
    ):
        product, owner, input_uom, packaging, base_quantity, base_uom = resolved
        db.add(
            InboundReceiptLine(
                receipt_id=receipt.id,
                line_no=line_no,
                product_id=product.id,
                owner_id=owner.id,
                input_quantity=line.input_quantity,
                input_uom_id=input_uom.id,
                packaging_id=packaging.id if packaging else None,
                expected_base_quantity=base_quantity,
                base_uom_id=base_uom.id,
                conversion_factor=conversion_factor,
                batch_number=line.batch_number,
                production_date=line.production_date,
                expiry_date=line.expiry_date,
                serial_number=line.serial_number,
                quality_status=line.quality_status,
                note=line.note,
            )
        )
    create_event(
        db,
        operation="inbound_receipt_created",
        object_type="inbound_receipt",
        object_uid=receipt.uid,
        actor=payload.actor,
        after={
            "warehouse_code": warehouse.code,
            "receipt_kind": payload.receipt_kind.value,
            "external_reference": payload.external_reference,
            "line_count": len(payload.lines),
        },
    )
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        existing = _existing_receipt(db, payload.idempotency_key, command_hash)
        if existing is not None:
            return existing
        raise _conflict("inbound receipt conflicts with existing data") from exc
    db.refresh(receipt)
    return receipt


def inbound_receipt_payload(db: Session, receipt: InboundReceipt) -> dict:
    warehouse = db.get(Warehouse, receipt.warehouse_id)
    posted_document = receipt.posted_stock_document
    lines = []
    for line in receipt.lines:
        product = line.product
        owner = line.owner
        input_uom = line.input_uom
        base_uom = line.base_uom
        packaging = line.packaging
        lines.append(
            {
                "id": line.id,
                "line_no": line.line_no,
                "product_id": line.product_id,
                "product_code": product.code,
                "product_name": product.name,
                "owner_id": line.owner_id,
                "owner_code": owner.code,
                "owner_name": owner.name,
                "input_quantity": line.input_quantity,
                "input_uom_id": line.input_uom_id,
                "input_uom_code": input_uom.code,
                "input_uom_symbol": input_uom.symbol,
                "packaging_id": line.packaging_id,
                "packaging_code": packaging.code if packaging else None,
                "packaging_name": packaging.name if packaging else None,
                "expected_base_quantity": line.expected_base_quantity,
                "base_uom_id": line.base_uom_id,
                "base_uom_code": base_uom.code,
                "base_uom_symbol": base_uom.symbol,
                "conversion_factor": line.conversion_factor,
                "batch_number": line.batch_number,
                "production_date": line.production_date,
                "expiry_date": line.expiry_date,
                "serial_number": line.serial_number,
                "quality_status": line.quality_status,
                "note": line.note,
            }
        )
    return {
        "id": receipt.id,
        "uid": receipt.uid,
        "warehouse_id": receipt.warehouse_id,
        "warehouse_code": warehouse.code,
        "warehouse_name": warehouse.name,
        "receipt_kind": receipt.receipt_kind,
        "status": receipt.status,
        "source_name": receipt.source_name,
        "external_reference": receipt.external_reference,
        "planned_date": receipt.planned_date,
        "idempotency_key": receipt.idempotency_key,
        "actor": receipt.actor,
        "note": receipt.note,
        "posted_stock_document_uid": posted_document.uid if posted_document else None,
        "line_count": len(lines),
        "created_at": receipt.created_at,
        "updated_at": receipt.updated_at,
        "posted_at": receipt.posted_at,
        "cancelled_at": receipt.cancelled_at,
        "lines": lines,
    }
