from collections import defaultdict
from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import func, select
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
from app.models.enums import StockDocumentStatus


@dataclass(frozen=True)
class StockIdentity:
    product_id: int
    batch_id: int | None
    serial_number: str | None
    owner_id: int
    quality_status: str
    logistic_unit_id: int | None
    location_id: int | None


ACTIVE_LEDGER_STATUSES = {
    StockDocumentStatus.POSTED,
    StockDocumentStatus.REVERSED,
}


def _identity(
    movement: StockMovement,
    *,
    source: bool,
) -> StockIdentity | None:
    if source:
        logistic_unit_id = movement.source_logistic_unit_id
        location_id = movement.source_location_id
        quality_status = movement.source_quality_status
    else:
        logistic_unit_id = movement.destination_logistic_unit_id
        location_id = movement.destination_location_id
        quality_status = movement.destination_quality_status
    if logistic_unit_id is None and location_id is None:
        return None
    if not quality_status:
        return None
    return StockIdentity(
        product_id=movement.product_id,
        batch_id=movement.batch_id,
        serial_number=movement.serial_number,
        owner_id=movement.owner_id,
        quality_status=quality_status,
        logistic_unit_id=logistic_unit_id,
        location_id=location_id,
    )


def _position_identity(position: StockPosition) -> StockIdentity:
    return StockIdentity(
        product_id=position.product_id,
        batch_id=position.batch_id,
        serial_number=position.serial_number,
        owner_id=position.owner_id,
        quality_status=position.quality_status,
        logistic_unit_id=position.logistic_unit_id,
        location_id=position.location_id,
    )


def _identity_sort_key(identity: StockIdentity) -> tuple:
    return (
        identity.product_id,
        identity.batch_id or 0,
        identity.serial_number or "",
        identity.owner_id,
        identity.quality_status,
        identity.logistic_unit_id or 0,
        identity.location_id or 0,
    )


def _identity_payload(
    db: Session,
    identity: StockIdentity,
    *,
    expected_quantity: Decimal,
    actual_quantity: Decimal,
    position_id: int | None,
    ledger_base_uom_ids: set[int],
) -> dict:
    product = db.get(Product, identity.product_id)
    batch = db.get(Batch, identity.batch_id) if identity.batch_id is not None else None
    owner = db.get(StockOwner, identity.owner_id)
    unit = (
        db.get(LogisticUnit, identity.logistic_unit_id)
        if identity.logistic_unit_id is not None
        else None
    )
    location = (
        db.get(Location, identity.location_id)
        if identity.location_id is not None
        else None
    )
    base_uom = (
        db.get(UnitOfMeasure, product.base_uom_id)
        if product is not None and product.base_uom_id is not None
        else None
    )
    return {
        "position_id": position_id,
        "product_id": identity.product_id,
        "product_code": product.code if product else None,
        "product_name": product.name if product else None,
        "batch_id": identity.batch_id,
        "batch_number": batch.batch_number if batch else None,
        "serial_number": identity.serial_number,
        "owner_id": identity.owner_id,
        "owner_code": owner.code if owner else None,
        "quality_status": identity.quality_status,
        "holder_kind": "logistic_unit" if identity.logistic_unit_id is not None else "location",
        "logistic_unit_id": identity.logistic_unit_id,
        "logistic_unit_uid": unit.uid if unit else None,
        "location_id": identity.location_id,
        "location_code": location.code if location else None,
        "base_uom_id": product.base_uom_id if product else None,
        "base_uom_code": base_uom.code if base_uom else None,
        "ledger_base_uom_ids": sorted(ledger_base_uom_ids),
        "expected_quantity": expected_quantity,
        "actual_quantity": actual_quantity,
        "delta_quantity": actual_quantity - expected_quantity,
    }


def reconcile_stock_positions(db: Session) -> dict:
    expected: dict[StockIdentity, Decimal] = defaultdict(lambda: Decimal("0"))
    ledger_uoms: dict[StockIdentity, set[int]] = defaultdict(set)
    issues: list[dict] = []
    movement_rows = list(
        db.execute(
            select(StockMovement, StockDocument)
            .join(StockDocument, StockDocument.id == StockMovement.document_id)
            .where(StockDocument.status.in_(ACTIVE_LEDGER_STATUSES))
            .order_by(StockMovement.id)
        )
    )
    total_movement_count = db.scalar(select(func.count(StockMovement.id))) or 0

    for movement, document in movement_rows:
        for source, sign in ((True, Decimal("-1")), (False, Decimal("1"))):
            if source:
                has_holder = (
                    movement.source_logistic_unit_id is not None
                    or movement.source_location_id is not None
                )
            else:
                has_holder = (
                    movement.destination_logistic_unit_id is not None
                    or movement.destination_location_id is not None
                )
            if not has_holder:
                continue
            identity = _identity(movement, source=source)
            if identity is None:
                issues.append(
                    {
                        "kind": "invalid_movement",
                        "message": (
                            "У стороны движения отсутствует статус качества."
                        ),
                        "movement_id": movement.id,
                        "document_uid": document.uid,
                    }
                )
                continue
            expected[identity] += sign * movement.quantity
            ledger_uoms[identity].add(movement.base_uom_id)

    actual: dict[StockIdentity, StockPosition] = {}
    duplicate_identities: set[StockIdentity] = set()
    positions = list(db.scalars(select(StockPosition).order_by(StockPosition.id)))
    for position in positions:
        identity = _position_identity(position)
        if identity in actual:
            duplicate_identities.add(identity)
            continue
        actual[identity] = position

    matched_identity_count = 0
    zero_balance_identity_count = 0
    negative_ledger_count = 0
    all_identities = sorted(set(expected) | set(actual), key=_identity_sort_key)
    for identity in all_identities:
        expected_quantity = expected.get(identity, Decimal("0"))
        position = actual.get(identity)
        actual_quantity = position.quantity if position is not None else Decimal("0")
        payload = _identity_payload(
            db,
            identity,
            expected_quantity=expected_quantity,
            actual_quantity=actual_quantity,
            position_id=position.id if position is not None else None,
            ledger_base_uom_ids=ledger_uoms.get(identity, set()),
        )
        product = db.get(Product, identity.product_id)
        expected_uom_ids = ledger_uoms.get(identity, set())
        has_base_uom_mismatch = bool(expected_uom_ids) and (
            product is None
            or product.base_uom_id is None
            or expected_uom_ids != {product.base_uom_id}
        )
        if has_base_uom_mismatch:
            issues.append(
                {
                    **payload,
                    "kind": "base_uom_mismatch",
                    "message": (
                        "Движения позиции используют несовместимые базовые единицы."
                    ),
                }
            )
        if identity in duplicate_identities:
            issues.append(
                {
                    **payload,
                    "kind": "duplicate_position",
                    "message": (
                        "Для одной учётной идентичности найдено несколько позиций."
                    ),
                }
            )
        if expected_quantity < 0:
            negative_ledger_count += 1
            issues.append(
                {
                    **payload,
                    "kind": "negative_ledger_balance",
                    "message": (
                        "Журнал движений формирует отрицательный остаток."
                    ),
                }
            )
        elif expected_quantity == 0:
            zero_balance_identity_count += 1
            if actual_quantity > 0:
                issues.append(
                    {
                        **payload,
                        "kind": "unexpected_position",
                        "message": (
                            "Позиция существует без положительного остатка по журналу."
                        ),
                    }
                )
        elif actual_quantity == 0:
            issues.append(
                {
                    **payload,
                    "kind": "missing_position",
                    "message": (
                        "По журналу позиция должна существовать, но текущего остатка нет."
                    ),
                }
            )
        elif actual_quantity != expected_quantity:
            issues.append(
                {
                    **payload,
                    "kind": "quantity_mismatch",
                    "message": (
                        "Количество в текущей позиции не совпадает с журналом."
                    ),
                }
            )
        elif identity not in duplicate_identities and not has_base_uom_mismatch:
            matched_identity_count += 1

    issues.sort(
        key=lambda issue: (
            issue["kind"],
            issue.get("product_id") or 0,
            issue.get("logistic_unit_id") or 0,
            issue.get("location_id") or 0,
            issue.get("movement_id") or 0,
        )
    )
    return {
        "checked_at": utcnow(),
        "is_consistent": not issues,
        "movement_count": len(movement_rows),
        "ignored_movement_count": total_movement_count - len(movement_rows),
        "position_count": len(positions),
        "checked_identity_count": len(all_identities),
        "matched_identity_count": matched_identity_count,
        "zero_balance_identity_count": zero_balance_identity_count,
        "discrepancy_count": len(issues),
        "negative_ledger_count": negative_ledger_count,
        "issues": issues,
    }
