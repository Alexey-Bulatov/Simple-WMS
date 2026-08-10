from decimal import Decimal

from fastapi import HTTPException, status
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models.entities import (
    Batch,
    Location,
    LogisticUnit,
    LogisticUnitContent,
    Product,
    StockOwner,
    StockPosition,
    UnitOfMeasure,
    Warehouse,
)
from app.models.enums import LocationKind, LogisticUnitStatus


DEFAULT_STOCK_OWNER_CODE = "INTERNAL"
DEFAULT_STOCK_OWNER_NAME = "Собственная организация"
TERMINAL_UNIT_STATUSES = {
    LogisticUnitStatus.DISASSEMBLED,
    LogisticUnitStatus.WRITTEN_OFF,
    LogisticUnitStatus.SHIPPED,
}
RESERVED_UNIT_STATUSES = {
    LogisticUnitStatus.RESERVED,
    LogisticUnitStatus.PICKING,
    LogisticUnitStatus.EXPEDITION,
    LogisticUnitStatus.LOADED,
}


def ensure_default_stock_owner(db: Session) -> StockOwner:
    owner = db.scalar(select(StockOwner).where(StockOwner.code == DEFAULT_STOCK_OWNER_CODE))
    if owner is not None:
        return owner
    owner = StockOwner(
        code=DEFAULT_STOCK_OWNER_CODE,
        name=DEFAULT_STOCK_OWNER_NAME,
        is_internal=True,
    )
    db.add(owner)
    db.flush()
    return owner


def stock_position_identity_query(
    *,
    logistic_unit_id: int | None,
    location_id: int | None,
    product_id: int,
    batch_id: int | None,
    owner_id: int,
    quality_status: str,
    serial_number: str | None = None,
):
    query = select(StockPosition).where(
        StockPosition.product_id == product_id,
        StockPosition.owner_id == owner_id,
        StockPosition.quality_status == quality_status,
        StockPosition.serial_number == serial_number
        if serial_number is not None
        else StockPosition.serial_number.is_(None),
    )
    query = query.where(
        StockPosition.logistic_unit_id == logistic_unit_id
        if logistic_unit_id is not None
        else StockPosition.logistic_unit_id.is_(None),
        StockPosition.location_id == location_id
        if location_id is not None
        else StockPosition.location_id.is_(None),
        StockPosition.batch_id == batch_id
        if batch_id is not None
        else StockPosition.batch_id.is_(None),
    )
    return query


def convert_product_quantity_to_base(
    db: Session,
    product: Product,
    quantity: Decimal,
    uom: UnitOfMeasure,
) -> tuple[Decimal, UnitOfMeasure]:
    if product.base_uom_id is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="product base unit is required for quantity conversion",
        )
    base_uom = db.get(UnitOfMeasure, product.base_uom_id)
    if base_uom is None or not base_uom.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="product has an invalid base unit",
        )
    if not uom.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="unit of measure is not active",
        )
    if base_uom.dimension != uom.dimension:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="unit is incompatible with the product base unit",
        )

    converted = quantity * uom.factor_to_base / base_uom.factor_to_base
    quantum = Decimal("1").scaleb(-base_uom.decimal_precision)
    normalized = converted.quantize(quantum)
    if normalized != converted:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="converted quantity exceeds product base unit precision",
        )
    return normalized, base_uom


def sync_logistic_content_position(
    db: Session,
    line: LogisticUnitContent,
    quantity: Decimal,
) -> StockPosition | None:
    product = db.get(Product, line.product_id)
    if product is None or product.base_uom_id is None:
        raise ValueError("stock position requires a product base unit")
    if line.uom_id != product.base_uom_id:
        raise ValueError("stock position quantity must use the product base unit")

    batch = db.get(Batch, line.batch_id) if line.batch_id is not None else None
    quality_status = batch.quality_status if batch is not None else "released"
    owner = ensure_default_stock_owner(db)
    position = db.scalar(
        stock_position_identity_query(
            logistic_unit_id=line.logistic_unit_id,
            location_id=None,
            product_id=line.product_id,
            batch_id=line.batch_id,
            owner_id=owner.id,
            quality_status=quality_status,
        )
    )
    if quantity <= 0:
        if position is not None:
            db.delete(position)
        return None
    if position is None:
        position = StockPosition(
            logistic_unit_id=line.logistic_unit_id,
            product_id=line.product_id,
            batch_id=line.batch_id,
            owner_id=owner.id,
            quality_status=quality_status,
            quantity=quantity,
        )
        db.add(position)
    else:
        position.quantity = quantity
    return position


def remove_logistic_unit_stock_positions(db: Session, logistic_unit_id: int) -> None:
    unit_ids = {logistic_unit_id}
    frontier = {logistic_unit_id}
    while frontier:
        child_ids = set(
            db.scalars(select(LogisticUnit.id).where(LogisticUnit.parent_unit_id.in_(frontier)))
        )
        frontier = child_ids - unit_ids
        unit_ids.update(child_ids)
    db.execute(delete(StockPosition).where(StockPosition.logistic_unit_id.in_(unit_ids)))


def effective_logistic_unit_holder(
    db: Session,
    unit: LogisticUnit,
) -> tuple[LogisticUnit, Location | None]:
    current = unit
    visited = {unit.id}
    while current.parent_unit_id is not None:
        parent = db.get(LogisticUnit, current.parent_unit_id)
        if parent is None or parent.id in visited:
            break
        visited.add(parent.id)
        current = parent
    location = db.get(Location, current.current_location_id) if current.current_location_id else None
    return current, location


def stock_position_payload(db: Session, position: StockPosition) -> dict:
    product = db.get(Product, position.product_id)
    owner = db.get(StockOwner, position.owner_id)
    batch = db.get(Batch, position.batch_id) if position.batch_id is not None else None
    base_uom = (
        db.get(UnitOfMeasure, product.base_uom_id)
        if product is not None and product.base_uom_id is not None
        else None
    )
    unit = (
        db.get(LogisticUnit, position.logistic_unit_id)
        if position.logistic_unit_id is not None
        else None
    )
    root_unit, location = effective_logistic_unit_holder(db, unit) if unit is not None else (None, None)
    if location is None and position.location_id is not None:
        location = db.get(Location, position.location_id)
    warehouse = db.get(Warehouse, location.warehouse_id) if location is not None else None

    quantity = position.quantity
    operation_allowed = batch is None or batch.operation_status == "allowed"
    quality_allowed = position.quality_status == "released" and operation_allowed
    holder_status = root_unit.status if root_unit is not None else None
    available = Decimal("0")
    reserved = Decimal("0")
    in_transit = Decimal("0")
    blocked = Decimal("0")
    if not quality_allowed or holder_status in {
        LogisticUnitStatus.BLOCKED,
        LogisticUnitStatus.QUARANTINE,
    }:
        blocked = quantity
    elif holder_status in RESERVED_UNIT_STATUSES:
        reserved = quantity
    elif holder_status == LogisticUnitStatus.IN_TRANSIT:
        in_transit = quantity
    elif holder_status in TERMINAL_UNIT_STATUSES:
        quantity = Decimal("0")
    elif (
        location is not None
        and location.kind == LocationKind.STORAGE
        and (root_unit is None or holder_status == LogisticUnitStatus.AVAILABLE)
    ):
        available = quantity

    return {
        "id": position.id,
        "product_id": position.product_id,
        "product_code": product.code if product else None,
        "product_name": product.name if product else None,
        "batch_id": position.batch_id,
        "batch_number": batch.batch_number if batch else None,
        "owner_id": position.owner_id,
        "owner_code": owner.code if owner else None,
        "owner_name": owner.name if owner else None,
        "quality_status": position.quality_status,
        "serial_number": position.serial_number,
        "quantity": quantity,
        "available_quantity": available,
        "reserved_quantity": reserved,
        "in_transit_quantity": in_transit,
        "blocked_quantity": blocked,
        "base_uom_id": product.base_uom_id if product else None,
        "base_uom_code": base_uom.code if base_uom else None,
        "base_uom_symbol": base_uom.symbol if base_uom else None,
        "holder_kind": "logistic_unit" if unit is not None else "location",
        "logistic_unit_id": position.logistic_unit_id,
        "logistic_unit_uid": unit.uid if unit else None,
        "root_logistic_unit_uid": root_unit.uid if root_unit else None,
        "holder_status": holder_status,
        "location_id": location.id if location else None,
        "location_code": location.code if location else None,
        "warehouse_id": warehouse.id if warehouse else None,
        "warehouse_code": warehouse.code if warehouse else None,
        "created_at": position.created_at,
        "updated_at": position.updated_at,
    }
