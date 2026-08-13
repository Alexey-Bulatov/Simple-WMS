import hashlib
import json
from datetime import date, timedelta
from decimal import Decimal

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.constants import INBOUND_RECEIPT_CODE_PREFIX
from app.models.entities import (
    InboundReceipt,
    InboundReceiptLine,
    InboundReceiptResult,
    Batch,
    Location,
    LogisticUnit,
    LogisticUnitContent,
    LogisticUnitType,
    Product,
    ProductPackaging,
    StockDocument,
    StockMovement,
    StockOwner,
    UnitOfMeasure,
    Warehouse,
    utcnow,
)
from app.models.enums import InboundReceiptStatus, LocationKind, LogisticUnitStatus
from app.schemas import (
    InboundReceiptActualLineCreate,
    InboundReceiptCreate,
    InboundReceiptLineCreate,
    InboundReceiptPost,
    StockDocumentPost,
    StockMovementPost,
)
from app.services import create_event
from app.stock import convert_product_quantity_to_base, effective_logistic_unit_holder
from app.stock_ledger import post_stock_document


INBOUND_RECEIPT_DOCUMENT_TYPE = "inbound_receipt"


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


def _posting_command_hash(receipt_uid: str, payload: InboundReceiptPost) -> str:
    serialized = json.dumps(
        {
            "receipt_uid": receipt_uid.strip().upper(),
            **payload.model_dump(mode="json"),
        },
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def _validate_item_scan(
    db: Session,
    product: Product,
    item_scan: str,
) -> None:
    accepted = {product.code.upper()}
    for packaging in db.scalars(
        select(ProductPackaging).where(
            ProductPackaging.product_id == product.id,
            ProductPackaging.is_active.is_(True),
        )
    ):
        accepted.add(packaging.code.upper())
        if packaging.barcode:
            accepted.add(packaging.barcode.upper())
    if item_scan not in accepted:
        raise _bad_request("item scan does not match the expected receipt product")


def _resolve_receiving_destination(
    db: Session,
    receipt: InboundReceipt,
    destination_scan: str,
) -> tuple[int | None, int | None]:
    location = db.scalar(select(Location).where(Location.code == destination_scan))
    if location is not None:
        if not location.is_active:
            raise _bad_request("receipt destination location is inactive")
        if location.warehouse_id != receipt.warehouse_id:
            raise _bad_request("receipt destination belongs to another warehouse")
        if location.kind not in {LocationKind.RECEIVING, LocationKind.QUARANTINE}:
            raise _bad_request("receipt destination must be a receiving or quarantine location")
        return None, location.id

    unit = db.scalar(select(LogisticUnit).where(LogisticUnit.uid == destination_scan))
    if unit is None:
        raise _bad_request("receipt destination scan is not a location or logistic unit")
    if unit.status != LogisticUnitStatus.OPEN:
        raise _bad_request("receipt logistic unit must be open")
    unit_type = db.get(LogisticUnitType, unit.type_id)
    if unit_type is None or not unit_type.is_active or not unit_type.can_contain_goods:
        raise _bad_request("receipt logistic unit type cannot contain goods")
    root, effective_location = effective_logistic_unit_holder(db, unit)
    warehouse_id = effective_location.warehouse_id if effective_location else root.warehouse_id
    if warehouse_id != receipt.warehouse_id:
        raise _bad_request("receipt logistic unit belongs to another warehouse")
    if effective_location is None or effective_location.kind not in {
        LocationKind.RECEIVING,
        LocationKind.QUARANTINE,
    }:
        raise _bad_request("receipt logistic unit must be in a receiving or quarantine location")
    return unit.id, None


def _resolve_actual_quantity(
    db: Session,
    expected: InboundReceiptLine,
    actual: InboundReceiptActualLineCreate,
) -> tuple[UnitOfMeasure, ProductPackaging | None, Decimal, UnitOfMeasure, Decimal]:
    packaging = db.get(ProductPackaging, actual.packaging_id) if actual.packaging_id else None
    if packaging is not None and (
        not packaging.is_active or packaging.product_id != expected.product_id
    ):
        raise _bad_request("active product packaging not found")
    if actual.packaging_id is not None and packaging is None:
        raise _bad_request("active product packaging not found")
    input_uom_id = packaging.uom_id if packaging else actual.input_uom_id
    input_uom = db.get(UnitOfMeasure, input_uom_id)
    if input_uom is None or not input_uom.is_active:
        raise _bad_request("active input unit of measure not found")
    converted_input = (
        actual.input_quantity * packaging.quantity
        if packaging is not None
        else actual.input_quantity
    )
    base_quantity, base_uom = convert_product_quantity_to_base(
        db,
        expected.product,
        converted_input,
        input_uom,
    )
    conversion_factor = (base_quantity / actual.input_quantity).quantize(
        Decimal("0.00000001")
    )
    return input_uom, packaging, base_quantity, base_uom, conversion_factor


def _resolve_batch(
    db: Session,
    expected: InboundReceiptLine,
    actual: InboundReceiptActualLineCreate,
    quality_status: str,
) -> Batch | None:
    batch_number = actual.batch_number or expected.batch_number
    same_expected_batch = (
        actual.batch_number is None or actual.batch_number == expected.batch_number
    )
    production_date = actual.production_date or (
        expected.production_date if same_expected_batch else None
    )
    expiry_date = actual.expiry_date or (
        expected.expiry_date if same_expected_batch else None
    )
    product = expected.product
    if batch_number is None:
        if production_date is not None or expiry_date is not None:
            raise _bad_request("batch dates require a batch number")
        if product.shelf_life_days is not None:
            raise _bad_request("batch number is required for shelf-life product")
        return None

    existing = db.scalar(
        select(Batch).where(
            Batch.product_id == product.id,
            Batch.batch_number == batch_number,
        )
    )
    if existing is not None:
        if production_date is not None and existing.production_date != production_date:
            raise _conflict("batch production date differs from the existing batch")
        if expiry_date is not None and existing.expiry_date != expiry_date:
            raise _conflict("batch expiry date differs from the existing batch")
        if existing.operation_status != "allowed":
            raise _conflict("batch is not allowed for warehouse operations")
        if existing.expiry_date < date.today() and quality_status == "released":
            raise _bad_request("expired batch must be received into quarantine")
        return existing

    if product.shelf_life_days is not None:
        if production_date is not None and expiry_date is None:
            expiry_date = production_date + timedelta(days=product.shelf_life_days)
        elif expiry_date is not None and production_date is None:
            production_date = expiry_date - timedelta(days=product.shelf_life_days)
    if production_date is None or expiry_date is None:
        raise _bad_request("new batch requires production_date and expiry_date")
    if expiry_date < production_date:
        raise _bad_request("batch expiry date must not precede production date")
    if expiry_date < date.today() and quality_status == "released":
        raise _bad_request("expired batch must be received into quarantine")
    batch = Batch(
        batch_number=batch_number,
        product_id=product.id,
        production_date=production_date,
        expiry_date=expiry_date,
        quality_status=quality_status,
        operation_status="allowed",
    )
    db.add(batch)
    db.flush()
    return batch


def _add_logistic_unit_content_projection(
    db: Session,
    movement: StockMovement,
) -> None:
    if movement.destination_logistic_unit_id is None:
        return
    query = select(LogisticUnitContent).where(
        LogisticUnitContent.logistic_unit_id == movement.destination_logistic_unit_id,
        LogisticUnitContent.product_id == movement.product_id,
        LogisticUnitContent.uom_id == movement.base_uom_id,
    )
    query = (
        query.where(LogisticUnitContent.batch_id.is_(None))
        if movement.batch_id is None
        else query.where(LogisticUnitContent.batch_id == movement.batch_id)
    )
    projection = db.scalar(
        query.execution_options(populate_existing=True).with_for_update()
    )
    if projection is None:
        projection = LogisticUnitContent(
            logistic_unit_id=movement.destination_logistic_unit_id,
            product_id=movement.product_id,
            batch_id=movement.batch_id,
            quantity=movement.quantity,
            uom_id=movement.base_uom_id,
        )
        db.add(projection)
    else:
        projection.quantity += movement.quantity


def _post_inbound_receipt(
    db: Session,
    receipt_uid: str,
    payload: InboundReceiptPost,
) -> InboundReceipt:
    command_hash = _posting_command_hash(receipt_uid, payload)
    receipt = get_inbound_receipt(db, receipt_uid, for_update=True)
    if receipt.status == InboundReceiptStatus.POSTED:
        if receipt.posting_command_hash == command_hash:
            return receipt
        raise _conflict("inbound receipt is already posted by another command")
    if receipt.status != InboundReceiptStatus.DRAFT:
        raise _conflict("only a draft inbound receipt can be posted")

    expected_lines = {line.id: line for line in receipt.lines}
    actual_rows = []
    movements = []
    serial_keys: set[tuple[int, str]] = set()
    for actual in payload.lines:
        expected = expected_lines.get(actual.receipt_line_id)
        if expected is None:
            raise _bad_request("actual line does not belong to the inbound receipt")
        _validate_item_scan(db, expected.product, actual.item_scan)
        destination_unit_id, destination_location_id = _resolve_receiving_destination(
            db,
            receipt,
            actual.destination_scan,
        )
        input_uom, packaging, base_quantity, base_uom, conversion_factor = (
            _resolve_actual_quantity(db, expected, actual)
        )
        serial_number = actual.serial_number or expected.serial_number
        if serial_number is not None:
            if base_quantity != Decimal("1"):
                raise _bad_request("a serialized receipt line must contain one base unit")
            serial_key = (expected.product_id, serial_number)
            if serial_key in serial_keys:
                raise _bad_request("serial number is repeated in actual receipt")
            serial_keys.add(serial_key)
        quality_status = actual.quality_status or expected.quality_status
        batch = _resolve_batch(db, expected, actual, quality_status)
        converted_input = (
            actual.input_quantity * packaging.quantity
            if packaging is not None
            else actual.input_quantity
        )
        movements.append(
            StockMovementPost(
                product_id=expected.product_id,
                batch_id=batch.id if batch else None,
                serial_number=serial_number,
                owner_id=expected.owner_id,
                destination_quality_status=quality_status,
                input_quantity=converted_input,
                input_uom_id=input_uom.id,
                destination_logistic_unit_id=destination_unit_id,
                destination_location_id=destination_location_id,
            )
        )
        actual_rows.append(
            {
                "expected": expected,
                "actual": actual,
                "input_uom": input_uom,
                "packaging": packaging,
                "base_quantity": base_quantity,
                "base_uom": base_uom,
                "conversion_factor": conversion_factor,
                "batch": batch,
                "serial_number": serial_number,
                "quality_status": quality_status,
                "destination_unit_id": destination_unit_id,
                "destination_location_id": destination_location_id,
            }
        )

    received_by_line = {
        line_id: sum(
            (
                row["base_quantity"]
                for row in actual_rows
                if row["expected"].id == line_id
            ),
            Decimal("0"),
        )
        for line_id in expected_lines
    }
    discrepancy_count = sum(
        received_by_line[line.id] != line.expected_base_quantity
        for line in receipt.lines
    )
    stock_payload = StockDocumentPost(
        uid=(
            "RCVMOV-"
            f"{hashlib.sha256(payload.idempotency_key.encode()).hexdigest()[:20].upper()}"
        ),
        document_type=INBOUND_RECEIPT_DOCUMENT_TYPE,
        reference_type="inbound_receipt",
        reference_uid=receipt.uid,
        idempotency_key=payload.idempotency_key,
        actor=payload.actor,
        reason=payload.reason,
        attributes={
            "receipt_id": receipt.id,
            "receipt_uid": receipt.uid,
            "receipt_kind": receipt.receipt_kind.value,
            "warehouse_id": receipt.warehouse_id,
            "posting_command_hash": command_hash,
            "expected_line_count": len(receipt.lines),
            "actual_line_count": len(actual_rows),
            "quantity_discrepancy_count": discrepancy_count,
            "line_inputs": [
                {
                    "receipt_line_id": row["expected"].id,
                    "entered_quantity": str(row["actual"].input_quantity),
                    "input_uom_id": row["actual"].input_uom_id,
                    "packaging_id": row["packaging"].id if row["packaging"] else None,
                    "packaging_code": row["packaging"].code if row["packaging"] else None,
                    "base_quantity": str(row["base_quantity"]),
                    "destination_scan": row["actual"].destination_scan,
                    "item_scan": row["actual"].item_scan,
                }
                for row in actual_rows
            ],
        },
        movements=movements,
    )

    def finalize(document: StockDocument) -> None:
        posted_movements = list(
            db.scalars(
                select(StockMovement)
                .where(StockMovement.document_id == document.id)
                .order_by(StockMovement.sequence_no)
            )
        )
        if len(posted_movements) != len(actual_rows):
            raise _conflict("posted receipt movement count differs from actual lines")
        for movement, row in zip(posted_movements, actual_rows, strict=True):
            db.add(
                InboundReceiptResult(
                    receipt_line_id=row["expected"].id,
                    sequence_no=movement.sequence_no,
                    stock_movement_id=movement.id,
                    input_quantity=row["actual"].input_quantity,
                    input_uom_id=row["input_uom"].id,
                    packaging_id=row["packaging"].id if row["packaging"] else None,
                    received_base_quantity=row["base_quantity"],
                    base_uom_id=row["base_uom"].id,
                    conversion_factor=row["conversion_factor"],
                    batch_id=row["batch"].id if row["batch"] else None,
                    serial_number=row["serial_number"],
                    quality_status=row["quality_status"],
                    destination_logistic_unit_id=row["destination_unit_id"],
                    destination_location_id=row["destination_location_id"],
                    destination_scan=row["actual"].destination_scan,
                    item_scan=row["actual"].item_scan,
                    note=row["actual"].note,
                )
            )
            _add_logistic_unit_content_projection(db, movement)
        receipt.status = InboundReceiptStatus.POSTED
        receipt.posted_stock_document_id = document.id
        receipt.posting_idempotency_key = payload.idempotency_key
        receipt.posting_command_hash = command_hash
        receipt.posted_at = utcnow()
        create_event(
            db,
            operation="inbound_receipt_posted",
            object_type="inbound_receipt",
            object_uid=receipt.uid,
            actor=payload.actor,
            reason=payload.reason,
            before={"status": InboundReceiptStatus.DRAFT.value},
            after={
                "status": InboundReceiptStatus.POSTED.value,
                "stock_document_uid": document.uid,
                "actual_line_count": len(actual_rows),
                "quantity_discrepancy_count": discrepancy_count,
            },
        )

    try:
        post_stock_document(db, stock_payload, before_commit=finalize)
    except Exception:
        db.rollback()
        receipt = get_inbound_receipt(db, receipt_uid)
        if (
            receipt.status == InboundReceiptStatus.POSTED
            and receipt.posting_command_hash == command_hash
        ):
            return receipt
        raise
    db.refresh(receipt)
    return receipt


def post_inbound_receipt(
    db: Session,
    receipt_uid: str,
    payload: InboundReceiptPost,
) -> InboundReceipt:
    command_hash = _posting_command_hash(receipt_uid, payload)
    try:
        return _post_inbound_receipt(db, receipt_uid, payload)
    except Exception:
        db.rollback()
        receipt = db.scalar(
            select(InboundReceipt).where(
                InboundReceipt.uid == receipt_uid.strip().upper()
            )
        )
        if (
            receipt is not None
            and receipt.status == InboundReceiptStatus.POSTED
            and receipt.posting_command_hash == command_hash
        ):
            return receipt
        raise


def inbound_receipt_payload(db: Session, receipt: InboundReceipt) -> dict:
    warehouse = db.get(Warehouse, receipt.warehouse_id)
    posted_document = receipt.posted_stock_document
    lines = []
    exact_line_count = 0
    shortage_line_count = 0
    excess_line_count = 0
    discrepancy_count = 0
    has_results = receipt.status in {
        InboundReceiptStatus.POSTED,
        InboundReceiptStatus.REVERSED,
    }
    for line in receipt.lines:
        product = line.product
        owner = line.owner
        input_uom = line.input_uom
        base_uom = line.base_uom
        packaging = line.packaging
        results = []
        for result in line.results:
            result_input_uom = result.input_uom
            result_base_uom = result.base_uom
            result_packaging = result.packaging
            result_batch = result.batch
            destination_unit = result.destination_logistic_unit
            destination_location = result.destination_location
            results.append(
                {
                    "id": result.id,
                    "sequence_no": result.sequence_no,
                    "stock_movement_id": result.stock_movement_id,
                    "input_quantity": result.input_quantity,
                    "input_uom_id": result.input_uom_id,
                    "input_uom_code": result_input_uom.code,
                    "input_uom_symbol": result_input_uom.symbol,
                    "packaging_id": result.packaging_id,
                    "packaging_code": result_packaging.code if result_packaging else None,
                    "packaging_name": result_packaging.name if result_packaging else None,
                    "received_base_quantity": result.received_base_quantity,
                    "base_uom_id": result.base_uom_id,
                    "base_uom_code": result_base_uom.code,
                    "base_uom_symbol": result_base_uom.symbol,
                    "conversion_factor": result.conversion_factor,
                    "batch_id": result.batch_id,
                    "batch_number": result_batch.batch_number if result_batch else None,
                    "production_date": result_batch.production_date if result_batch else None,
                    "expiry_date": result_batch.expiry_date if result_batch else None,
                    "serial_number": result.serial_number,
                    "quality_status": result.quality_status,
                    "destination_logistic_unit_id": result.destination_logistic_unit_id,
                    "destination_logistic_unit_uid": destination_unit.uid if destination_unit else None,
                    "destination_location_id": result.destination_location_id,
                    "destination_location_code": (
                        destination_location.code if destination_location else None
                    ),
                    "destination_scan": result.destination_scan,
                    "item_scan": result.item_scan,
                    "note": result.note,
                }
            )
        received_quantity = (
            sum(
                (result.received_base_quantity for result in line.results),
                Decimal("0"),
            )
            if has_results
            else None
        )
        variance = (
            received_quantity - line.expected_base_quantity
            if received_quantity is not None
            else None
        )
        if variance is None:
            quantity_result = "pending"
        elif variance == 0:
            quantity_result = "exact"
            exact_line_count += 1
        elif variance < 0:
            quantity_result = "shortage"
            shortage_line_count += 1
        else:
            quantity_result = "excess"
            excess_line_count += 1

        actual_batch_numbers = {
            result.batch.batch_number if result.batch else None
            for result in line.results
        }
        actual_serial_numbers = {result.serial_number for result in line.results}
        actual_quality_statuses = {result.quality_status for result in line.results}
        if not has_results:
            batch_result = serial_result = quality_result = "pending"
        else:
            batch_result = (
                "not_expected"
                if line.batch_number is None
                else "exact"
                if actual_batch_numbers == {line.batch_number}
                else "mismatch"
            )
            serial_result = (
                "not_expected"
                if line.serial_number is None
                else "exact"
                if actual_serial_numbers == {line.serial_number}
                else "mismatch"
            )
            quality_result = (
                "exact"
                if actual_quality_statuses == {line.quality_status}
                else "mismatch"
            )
            if (
                quantity_result != "exact"
                or batch_result == "mismatch"
                or serial_result == "mismatch"
                or quality_result == "mismatch"
            ):
                discrepancy_count += 1
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
                "received_base_quantity": received_quantity,
                "variance_base_quantity": variance,
                "quantity_result": quantity_result,
                "batch_result": batch_result,
                "serial_result": serial_result,
                "quality_result": quality_result,
                "results": results,
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
        "exact_line_count": exact_line_count,
        "shortage_line_count": shortage_line_count,
        "excess_line_count": excess_line_count,
        "discrepancy_count": discrepancy_count,
        "has_discrepancies": discrepancy_count > 0,
        "created_at": receipt.created_at,
        "updated_at": receipt.updated_at,
        "posted_at": receipt.posted_at,
        "reversed_at": receipt.reversed_at,
        "cancelled_at": receipt.cancelled_at,
        "lines": lines,
    }
