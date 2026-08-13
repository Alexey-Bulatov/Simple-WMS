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
    LogisticUnit,
    ProductPackaging,
    StockDocument,
    StockMovement,
    StockPosition,
    StockRecipient,
    UnitOfMeasure,
    utcnow,
)
from app.schemas import (
    InternalAccountabilityWriteoffCreate,
    InternalIssueCreate,
    InternalReturnCreate,
    StockDocumentPost,
    StockDocumentReverseRequest,
    StockMovementPost,
)
from app.models.enums import StockDocumentStatus
from app.stock import (
    convert_product_quantity_to_base,
    effective_logistic_unit_holder,
    stock_position_payload,
)
from app.stock_ledger import (
    post_stock_document,
    reverse_stock_document,
    stock_document_payload,
    stock_movement_payload,
)


INTERNAL_ISSUE_DOCUMENT_TYPE = "internal_issue"
INTERNAL_RETURN_DOCUMENT_TYPE = "internal_return"
INTERNAL_ACCOUNTABILITY_WRITEOFF_DOCUMENT_TYPE = "internal_accountability_writeoff"


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


def _return_command_hash(payload: InternalReturnCreate) -> str:
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


def _existing_return(
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
        document.document_type != INTERNAL_RETURN_DOCUMENT_TYPE
        or (document.attributes or {}).get("return_command_hash") != command_hash
    ):
        raise _conflict("idempotency key belongs to another command")
    return document


def _existing_writeoff(
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
        document.document_type != INTERNAL_ACCOUNTABILITY_WRITEOFF_DOCUMENT_TYPE
        or (document.attributes or {}).get("writeoff_command_hash") != command_hash
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
                "issue_kind": payload.issue_kind,
                "accountability_policy": payload.accountability_policy,
                "planned_close_date": (
                    payload.planned_close_date.isoformat()
                    if payload.planned_close_date
                    else None
                ),
                "auto_writeoff": payload.auto_writeoff,
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
    _, _, return_uids, writeoff_uids = _accountability_settlements(db, issue)
    if return_uids or writeoff_uids:
        raise _conflict("internal issue has accountability settlements")
    reverse_stock_document(db, issue.uid, payload)
    return get_internal_issue(db, uid)


def _accountability_settlements(
    db: Session,
    issue: StockDocument,
) -> tuple[dict[int, Decimal], dict[int, Decimal], list[str], list[str]]:
    returned_quantities: dict[int, Decimal] = {}
    written_off_quantities: dict[int, Decimal] = {}
    return_uids: list[str] = []
    writeoff_uids: list[str] = []
    settlements = db.scalars(
        select(StockDocument)
        .where(
            StockDocument.document_type.in_(
                (
                    INTERNAL_RETURN_DOCUMENT_TYPE,
                    INTERNAL_ACCOUNTABILITY_WRITEOFF_DOCUMENT_TYPE,
                )
            ),
            StockDocument.reference_type == INTERNAL_ISSUE_DOCUMENT_TYPE,
            StockDocument.reference_uid == issue.uid,
            StockDocument.status == StockDocumentStatus.POSTED,
        )
        .order_by(StockDocument.created_at, StockDocument.id)
    )
    for document in settlements:
        is_return = document.document_type == INTERNAL_RETURN_DOCUMENT_TYPE
        if is_return:
            return_uids.append(document.uid)
        else:
            writeoff_uids.append(document.uid)
        line_inputs = (document.attributes or {}).get("line_inputs", [])
        for index, line_input in enumerate(line_inputs):
            issue_movement_id = line_input.get("issue_movement_id")
            if issue_movement_id is None:
                continue
            movement_id = int(issue_movement_id)
            quantity = (
                document.movements[index].quantity
                if is_return and index < len(document.movements)
                else Decimal(str(line_input.get("base_quantity", "0")))
            )
            target = returned_quantities if is_return else written_off_quantities
            target[movement_id] = target.get(movement_id, Decimal("0")) + quantity
    return returned_quantities, written_off_quantities, return_uids, writeoff_uids


def _validate_return_scans(
    db: Session,
    movement: StockMovement,
    *,
    destination_scan: str,
    item_scan: str,
) -> tuple[int | None, int | None, int]:
    data = stock_movement_payload(db, movement)
    location = db.scalar(select(Location).where(Location.code == destination_scan))
    unit = db.scalar(select(LogisticUnit).where(LogisticUnit.uid == destination_scan))
    if location is not None:
        if not location.is_active:
            raise _bad_request("return destination location is inactive")
        destination_logistic_unit_id = None
        destination_location_id = location.id
        destination_warehouse_id = location.warehouse_id
    elif unit is not None:
        root, effective_location = effective_logistic_unit_holder(db, unit)
        destination_logistic_unit_id = unit.id
        destination_location_id = None
        destination_warehouse_id = (
            effective_location.warehouse_id
            if effective_location is not None
            else root.warehouse_id
        )
        if destination_warehouse_id is None:
            raise _bad_request("return destination logistic unit has no warehouse")
    else:
        raise _bad_request("return destination scan is not a location or logistic unit")
    if destination_warehouse_id != movement.source_warehouse_id:
        raise _bad_request("return destination belongs to another warehouse")

    accepted_items = {data["product_code"].upper()}
    if movement.serial_number:
        accepted_items.add(movement.serial_number.upper())
    packagings = db.scalars(
        select(ProductPackaging).where(
            ProductPackaging.product_id == movement.product_id,
            ProductPackaging.is_active.is_(True),
        )
    )
    for packaging in packagings:
        accepted_items.add(packaging.code.upper())
        if packaging.barcode:
            accepted_items.add(packaging.barcode.upper())
    if item_scan not in accepted_items:
        raise _bad_request("item scan does not match the original issue product")
    return (
        destination_logistic_unit_id,
        destination_location_id,
        destination_warehouse_id,
    )


def create_internal_return(
    db: Session,
    issue_uid: str,
    payload: InternalReturnCreate,
    *,
    warehouse_scope: set[int] | None = None,
) -> StockDocument:
    command_hash = _return_command_hash(payload)
    existing = _existing_return(db, payload.idempotency_key, command_hash)
    if existing is not None:
        return existing

    issue = db.scalar(
        select(StockDocument)
        .where(
            StockDocument.uid == issue_uid.strip().upper(),
            StockDocument.document_type == INTERNAL_ISSUE_DOCUMENT_TYPE,
        )
        .with_for_update()
    )
    if issue is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="internal_issue not found")
    existing = _existing_return(db, payload.idempotency_key, command_hash)
    if existing is not None:
        return existing
    if issue.status != StockDocumentStatus.POSTED:
        raise _conflict("only a posted internal issue can be returned")
    issue_attributes = issue.attributes or {}
    if issue_attributes.get("issue_kind", "permanent") != "accountable":
        raise _conflict("only an accountable internal issue can be returned")

    returned_quantities, written_off_quantities, _, _ = _accountability_settlements(
        db,
        issue,
    )
    issue_movements = {movement.id: movement for movement in issue.movements}
    requested_movement_ids = [line.issue_movement_id for line in payload.lines]
    if len(set(requested_movement_ids)) != len(requested_movement_ids):
        raise _bad_request("return lines must reference different issue movements")

    movements: list[StockMovementPost] = []
    line_inputs: list[dict] = []
    warehouse_ids: set[int] = set()
    for line in payload.lines:
        issue_movement = issue_movements.get(line.issue_movement_id)
        if issue_movement is None:
            raise _bad_request("issue movement does not belong to the internal issue")
        if issue_movement.source_warehouse_id is None:
            raise _bad_request("original issue movement has no source warehouse")
        if (
            warehouse_scope is not None
            and issue_movement.source_warehouse_id not in warehouse_scope
        ):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="internal issue belongs to an unavailable warehouse",
            )
        (
            destination_logistic_unit_id,
            destination_location_id,
            destination_warehouse_id,
        ) = _validate_return_scans(
            db,
            issue_movement,
            destination_scan=line.destination_scan,
            item_scan=line.item_scan,
        )
        warehouse_ids.add(destination_warehouse_id)

        packaging = db.get(ProductPackaging, line.packaging_id) if line.packaging_id else None
        if packaging is not None and (
            not packaging.is_active or packaging.product_id != issue_movement.product_id
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
            issue_movement.product,
            input_quantity,
            input_uom,
        )
        returned_quantity = returned_quantities.get(issue_movement.id, Decimal("0"))
        written_off_quantity = written_off_quantities.get(
            issue_movement.id,
            Decimal("0"),
        )
        remaining_quantity = (
            issue_movement.quantity - returned_quantity - written_off_quantity
        )
        if base_quantity > remaining_quantity:
            raise _conflict("return quantity exceeds the outstanding accountable quantity")
        movements.append(
            StockMovementPost(
                product_id=issue_movement.product_id,
                batch_id=issue_movement.batch_id,
                serial_number=issue_movement.serial_number,
                owner_id=issue_movement.owner_id,
                destination_quality_status=line.quality_status,
                input_quantity=input_quantity,
                input_uom_id=input_uom.id,
                destination_logistic_unit_id=destination_logistic_unit_id,
                destination_location_id=destination_location_id,
            )
        )
        line_inputs.append(
            {
                "issue_movement_id": issue_movement.id,
                "entered_quantity": str(line.input_quantity),
                "input_uom_id": line.input_uom_id,
                "packaging_id": packaging.id if packaging else None,
                "packaging_code": packaging.code if packaging else None,
                "base_quantity": str(base_quantity),
                "quality_status": line.quality_status,
            }
        )

    if len(warehouse_ids) != 1:
        raise _bad_request("one internal return must use one warehouse")

    deterministic_uid = f"RET-{hashlib.sha256(payload.idempotency_key.encode()).hexdigest()[:20].upper()}"
    return post_stock_document(
        db,
        StockDocumentPost(
            uid=deterministic_uid,
            document_type=INTERNAL_RETURN_DOCUMENT_TYPE,
            reference_type=INTERNAL_ISSUE_DOCUMENT_TYPE,
            reference_uid=issue.uid,
            idempotency_key=payload.idempotency_key,
            actor=payload.actor,
            reason=payload.reason,
            attributes={
                "issue_uid": issue.uid,
                "recipient_code": issue_attributes["recipient_code"],
                "recipient_name": issue_attributes["recipient_name"],
                "return_command_hash": command_hash,
                "line_inputs": line_inputs,
            },
            movements=movements,
        ),
    )


def internal_return_payload(db: Session, document: StockDocument) -> dict:
    data = stock_document_payload(db, document, include_movements=True)
    attributes = document.attributes or {}
    return {
        "uid": document.uid,
        "status": document.status,
        "issue_uid": attributes["issue_uid"],
        "recipient_code": attributes["recipient_code"],
        "recipient_name": attributes["recipient_name"],
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


def create_accountability_writeoff(
    db: Session,
    issue_uid: str,
    payload: InternalAccountabilityWriteoffCreate,
    *,
    as_of_date: date | None = None,
) -> StockDocument:
    effective_date = as_of_date or date.today()
    command_hash = hashlib.sha256(
        json.dumps(
            {
                "issue_uid": issue_uid.strip().upper(),
                **payload.model_dump(mode="json"),
            },
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    ).hexdigest()
    existing = _existing_writeoff(db, payload.idempotency_key, command_hash)
    if existing is not None:
        return existing

    try:
        issue = db.scalar(
            select(StockDocument)
            .where(
                StockDocument.uid == issue_uid.strip().upper(),
                StockDocument.document_type == INTERNAL_ISSUE_DOCUMENT_TYPE,
            )
            .with_for_update()
        )
        if issue is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="internal_issue not found",
            )
        existing = _existing_writeoff(db, payload.idempotency_key, command_hash)
        if existing is not None:
            return existing
        if issue.status != StockDocumentStatus.POSTED:
            raise _conflict("only a posted internal issue can be written off")
        attributes = issue.attributes or {}
        if attributes.get("issue_kind", "permanent") != "accountable":
            raise _conflict("only an accountable internal issue can be written off")
        if attributes.get("accountability_policy") != "normative_writeoff":
            raise _conflict("internal issue does not use normative writeoff")
        planned_close_date = attributes.get("planned_close_date")
        if planned_close_date is None or date.fromisoformat(planned_close_date) > effective_date:
            raise _conflict("normative writeoff date has not been reached")

        returned, written_off, _, _ = _accountability_settlements(db, issue)
        line_inputs = []
        written_off_quantities = {}
        for movement in issue.movements:
            remaining = (
                movement.quantity
                - returned.get(movement.id, Decimal("0"))
                - written_off.get(movement.id, Decimal("0"))
            )
            if remaining <= 0:
                continue
            line_inputs.append(
                {
                    "issue_movement_id": movement.id,
                    "product_id": movement.product_id,
                    "base_uom_id": movement.base_uom_id,
                    "base_quantity": str(remaining),
                }
            )
            written_off_quantities[str(movement.id)] = remaining
        if not line_inputs:
            raise _conflict("accountable issue has no outstanding quantity")

        deterministic_uid = (
            "NWO-"
            f"{hashlib.sha256(payload.idempotency_key.encode()).hexdigest()[:20].upper()}"
        )
        document = StockDocument(
            uid=deterministic_uid,
            document_type=INTERNAL_ACCOUNTABILITY_WRITEOFF_DOCUMENT_TYPE,
            status=StockDocumentStatus.POSTED,
            reference_type=INTERNAL_ISSUE_DOCUMENT_TYPE,
            reference_uid=issue.uid,
            idempotency_key=payload.idempotency_key,
            actor=payload.actor,
            reason=payload.reason,
            attributes={
                "issue_uid": issue.uid,
                "recipient_code": attributes["recipient_code"],
                "recipient_name": attributes["recipient_name"],
                "effective_date": effective_date.isoformat(),
                "writeoff_command_hash": command_hash,
                "line_inputs": line_inputs,
            },
            posted_at=utcnow(),
        )
        db.add(document)
        db.commit()
        db.refresh(document)
        return document
    except IntegrityError as exc:
        db.rollback()
        existing = _existing_writeoff(db, payload.idempotency_key, command_hash)
        if existing is not None:
            return existing
        raise _conflict("accountability writeoff conflicts with existing data") from exc
    except Exception:
        db.rollback()
        raise


def accountability_writeoff_payload(
    db: Session,
    document: StockDocument,
) -> dict:
    attributes = document.attributes or {}
    return {
        "uid": document.uid,
        "status": document.status,
        "issue_uid": attributes["issue_uid"],
        "recipient_code": attributes["recipient_code"],
        "recipient_name": attributes["recipient_name"],
        "actor": document.actor,
        "reason": document.reason or "",
        "idempotency_key": document.idempotency_key,
        "written_off_quantities": {
            str(item["issue_movement_id"]): Decimal(item["base_quantity"])
            for item in attributes.get("line_inputs", [])
        },
        "created_at": document.created_at,
        "posted_at": document.posted_at,
    }


def process_due_accountability_writeoffs(
    db: Session,
    *,
    as_of_date: date | None = None,
) -> list[StockDocument]:
    effective_date = as_of_date or date.today()
    issues = list(
        db.scalars(
            select(StockDocument).where(
                StockDocument.document_type == INTERNAL_ISSUE_DOCUMENT_TYPE,
                StockDocument.status == StockDocumentStatus.POSTED,
            )
        )
    )
    processed = []
    for issue in issues:
        attributes = issue.attributes or {}
        planned_close_date = attributes.get("planned_close_date")
        if (
            attributes.get("issue_kind") != "accountable"
            or attributes.get("accountability_policy") != "normative_writeoff"
            or not attributes.get("auto_writeoff")
            or planned_close_date is None
            or date.fromisoformat(planned_close_date) > effective_date
        ):
            continue
        returned, written_off, _, _ = _accountability_settlements(db, issue)
        if all(
            returned.get(movement.id, Decimal("0"))
            + written_off.get(movement.id, Decimal("0"))
            >= movement.quantity
            for movement in issue.movements
        ):
            continue
        processed.append(
            create_accountability_writeoff(
                db,
                issue.uid,
                InternalAccountabilityWriteoffCreate(
                    reason=f"Автоматическое списание по нормативу на {effective_date.isoformat()}",
                    idempotency_key=(
                        f"accountability:auto:{issue.uid}:{effective_date.isoformat()}"
                    ),
                    actor="accountability-scheduler",
                ),
                as_of_date=effective_date,
            )
        )
    return processed


def internal_issue_payload(db: Session, document: StockDocument) -> dict:
    data = stock_document_payload(db, document, include_movements=True)
    attributes = document.attributes or {}
    issue_kind = attributes.get("issue_kind", "permanent")
    (
        returned_quantities,
        written_off_quantities,
        return_uids,
        writeoff_uids,
    ) = _accountability_settlements(db, document)
    movement_payloads = []
    any_returned = False
    any_written_off = False
    all_returned = True
    all_written_off = True
    for movement, movement_data in zip(document.movements, data["movements"], strict=True):
        returned_quantity = returned_quantities.get(movement.id, Decimal("0"))
        written_off_quantity = written_off_quantities.get(movement.id, Decimal("0"))
        remaining_quantity = max(
            Decimal("0"),
            movement.quantity - returned_quantity - written_off_quantity,
        )
        movement_payloads.append(
            {
                **movement_data,
                "returned_quantity": returned_quantity,
                "written_off_quantity": written_off_quantity,
                "remaining_quantity": remaining_quantity,
            }
        )
        any_returned = any_returned or returned_quantity > 0
        any_written_off = any_written_off or written_off_quantity > 0
        all_returned = all_returned and returned_quantity == movement.quantity
        all_written_off = all_written_off and written_off_quantity == movement.quantity
    all_closed = all(item["remaining_quantity"] == 0 for item in movement_payloads)
    if issue_kind != "accountable":
        accountability_status = "not_applicable"
    elif all_returned:
        accountability_status = "returned"
    elif all_written_off:
        accountability_status = "written_off"
    elif all_closed and any_returned and any_written_off:
        accountability_status = "closed_mixed"
    elif any_returned or any_written_off:
        accountability_status = "partial"
    else:
        accountability_status = "open"
    return {
        "uid": document.uid,
        "status": document.status,
        "recipient_id": attributes["recipient_id"],
        "recipient_code": attributes["recipient_code"],
        "recipient_name": attributes["recipient_name"],
        "recipient_kind": attributes["recipient_kind"],
        "issue_kind": issue_kind,
        "accountability_policy": attributes.get("accountability_policy"),
        "planned_close_date": attributes.get("planned_close_date"),
        "auto_writeoff": bool(attributes.get("auto_writeoff", False)),
        "accountability_status": accountability_status,
        "return_uids": return_uids,
        "writeoff_uids": writeoff_uids,
        "request_reference": attributes.get("request_reference"),
        "actor": document.actor,
        "reason": document.reason or "",
        "idempotency_key": document.idempotency_key,
        "warehouse_ids": data["warehouse_ids"],
        "warehouse_codes": data["warehouse_codes"],
        "created_at": document.created_at,
        "posted_at": document.posted_at,
        "reversed_at": document.reversed_at,
        "movements": movement_payloads,
    }
