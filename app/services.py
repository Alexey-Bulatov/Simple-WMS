from __future__ import annotations

from datetime import date
from decimal import Decimal
from uuid import uuid4

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.constants import (
    BOX_CODE_PREFIX,
    CODE_SEPARATOR,
    DEFAULT_CITY,
    DEFAULT_UNIT,
    INVENTORY_CODE_PREFIX,
    PALLET_CODE_PREFIX,
    RECEIVING_LOCATION_SUFFIX,
    RECEIVING_ZONE_CODE,
    RECEIVING_ZONE_NAME,
    SHIPMENT_CODE_PREFIX,
    STORAGE_LOCATION_PATTERN,
    STORAGE_ZONE_CODE,
    STORAGE_ZONE_NAME,
)
from app.models.entities import (
    Batch,
    Box,
    EquipmentProfile,
    InventoryLine,
    InventorySession,
    LogisticUnit,
    LogisticUnitContent,
    LogisticUnitType,
    LogisticUnitTypeAllowedChild,
    Location,
    OperationEvent,
    Pallet,
    PalletBox,
    Product,
    Shipment,
    ShipmentPallet,
    UnitOfMeasure,
    User,
    Warehouse,
    Zone,
    utcnow,
)
from app.models.enums import (
    BoxStatus,
    InventoryLineStatus,
    InventoryStatus,
    LocationKind,
    LogisticUnitStatus,
    MeasurementDimension,
    PalletStatus,
    ShipmentStatus,
)
from app.schemas import (
    BatchCreate,
    DemoCatalogRequest,
    DemoPalletsRequest,
    EquipmentProfileCreate,
    EquipmentProfileUpdate,
    InventoryStartRequest,
    LogisticUnitAcceptRequest,
    LogisticUnitActionRequest,
    LogisticUnitChildRequest,
    LogisticUnitContentCreate,
    LogisticUnitContentRemoveRequest,
    LogisticUnitCreate,
    LogisticUnitHoldRequest,
    LogisticUnitLocationRequest,
    LogisticUnitTypeCreate,
    LocationCreate,
    ProductCreate,
    ShipmentCreate,
    UserCreate,
    UnitOfMeasureCreate,
    WarehouseCreate,
    ZoneCreate,
)


DEFAULT_UNITS_OF_MEASURE = (
    ("PCS", "Штука", "шт", MeasurementDimension.QUANTITY, 0, Decimal("1"), True),
    ("KG", "Килограмм", "кг", MeasurementDimension.MASS, 3, Decimal("1"), True),
    ("G", "Грамм", "г", MeasurementDimension.MASS, 3, Decimal("0.001"), False),
    ("L", "Литр", "л", MeasurementDimension.VOLUME, 3, Decimal("1"), True),
    ("ML", "Миллилитр", "мл", MeasurementDimension.VOLUME, 3, Decimal("0.001"), False),
    ("M3", "Кубический метр", "м³", MeasurementDimension.VOLUME, 6, Decimal("1000"), False),
    ("M", "Метр", "м", MeasurementDimension.LENGTH, 3, Decimal("1"), True),
    ("M2", "Квадратный метр", "м²", MeasurementDimension.AREA, 3, Decimal("1"), True),
)

DEFAULT_LOGISTIC_UNIT_TYPES = (
    ("BOX", "Коробка", BOX_CODE_PREFIX, True, False, False),
    ("PALLET", "Палета", PALLET_CODE_PREFIX, False, True, True),
    ("CRATE", "Ящик", "CRT", True, False, True),
    ("DRUM", "Бочка", "DRM", True, False, True),
    ("CANISTER", "Канистра", "CAN", True, False, True),
    ("IBC", "Еврокуб", "IBC", True, False, True),
    ("ROLL", "Рулон", "ROL", True, False, False),
    ("CONTAINER", "Контейнер", "CNT", True, True, True),
)

DEFAULT_ALLOWED_CHILD_TYPES = {
    "PALLET": ("BOX", "CRATE", "DRUM", "CANISTER"),
    "CONTAINER": ("BOX", "PALLET", "CRATE", "DRUM", "CANISTER", "IBC", "ROLL"),
}


def not_found(name: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"{name} not found")


def bad_request(message: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=message)


def create_event(
    db: Session,
    *,
    operation: str,
    object_type: str,
    object_uid: str,
    actor: str = "system",
    reason: str | None = None,
    before: dict | None = None,
    after: dict | None = None,
) -> OperationEvent:
    event = OperationEvent(
        operation=operation,
        object_type=object_type,
        object_uid=object_uid,
        actor=actor,
        reason=reason,
        before=before,
        after=after,
    )
    db.add(event)
    return event


def commit_or_409(db: Session, message: str) -> None:
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=message) from exc


def create_user(db: Session, payload: UserCreate) -> User:
    user = User(**payload.model_dump())
    db.add(user)
    commit_or_409(db, "user already exists")
    db.refresh(user)
    return user


def ensure_reference_catalogs(db: Session) -> dict[str, int]:
    changed = False
    units: dict[str, UnitOfMeasure] = {
        unit.code: unit for unit in db.scalars(select(UnitOfMeasure).order_by(UnitOfMeasure.id))
    }
    for code, name, symbol, dimension, precision, factor, is_base in DEFAULT_UNITS_OF_MEASURE:
        if code in units:
            continue
        unit = UnitOfMeasure(
            code=code,
            name=name,
            symbol=symbol,
            dimension=dimension.value,
            decimal_precision=precision,
            factor_to_base=factor,
            is_base=is_base,
        )
        db.add(unit)
        units[code] = unit
        changed = True
    if changed:
        db.flush()

    unit_types: dict[str, LogisticUnitType] = {
        item.code: item for item in db.scalars(select(LogisticUnitType).order_by(LogisticUnitType.id))
    }
    for code, name, prefix, can_contain_goods, can_contain_units, is_returnable in DEFAULT_LOGISTIC_UNIT_TYPES:
        if code in unit_types:
            continue
        item = LogisticUnitType(
            code=code,
            name=name,
            identifier_prefix=prefix,
            can_contain_goods=can_contain_goods,
            can_contain_units=can_contain_units,
            is_returnable=is_returnable,
        )
        db.add(item)
        unit_types[code] = item
        changed = True
    if changed:
        db.flush()

    for parent_code, child_codes in DEFAULT_ALLOWED_CHILD_TYPES.items():
        parent = unit_types[parent_code]
        existing_child_ids = {
            child_id
            for child_id in db.scalars(
                select(LogisticUnitTypeAllowedChild.child_type_id).where(
                    LogisticUnitTypeAllowedChild.parent_type_id == parent.id
                )
            )
        }
        for child_code in child_codes:
            child = unit_types[child_code]
            if child.id in existing_child_ids:
                continue
            db.add(LogisticUnitTypeAllowedChild(parent_type_id=parent.id, child_type_id=child.id))
            changed = True

    if changed:
        commit_or_409(db, "reference catalog initialization conflict")
    return {
        "units_of_measure": len(units),
        "logistic_unit_types": len(unit_types),
    }


def create_unit_of_measure(db: Session, payload: UnitOfMeasureCreate) -> UnitOfMeasure:
    ensure_reference_catalogs(db)
    code = payload.code.strip().upper()
    if payload.is_base:
        existing_base = db.scalar(
            select(UnitOfMeasure).where(
                UnitOfMeasure.dimension == payload.dimension.value,
                UnitOfMeasure.is_base.is_(True),
            )
        )
        if existing_base is not None:
            raise bad_request(f"base unit already exists for dimension {payload.dimension.value}")
    unit = UnitOfMeasure(
        code=code,
        name=payload.name.strip(),
        symbol=payload.symbol.strip(),
        dimension=payload.dimension.value,
        decimal_precision=payload.decimal_precision,
        factor_to_base=payload.factor_to_base,
        is_base=payload.is_base,
    )
    db.add(unit)
    create_event(
        db,
        operation="unit_of_measure_created",
        object_type="unit_of_measure",
        object_uid=code,
        after={
            "name": unit.name,
            "symbol": unit.symbol,
            "dimension": unit.dimension,
            "factor_to_base": str(unit.factor_to_base),
            "is_base": unit.is_base,
        },
    )
    commit_or_409(db, "unit of measure already exists")
    db.refresh(unit)
    return unit


def validate_weight_uom(db: Session, uom_id: int | None, field_name: str) -> None:
    if uom_id is None:
        return
    unit = db.get(UnitOfMeasure, uom_id)
    if unit is None:
        raise not_found(field_name)
    if unit.dimension != MeasurementDimension.MASS.value:
        raise bad_request(f"{field_name} must reference a mass unit")


def create_logistic_unit_type(db: Session, payload: LogisticUnitTypeCreate) -> LogisticUnitType:
    ensure_reference_catalogs(db)
    validate_weight_uom(db, payload.tare_weight_uom_id, "tare_weight_uom")
    validate_weight_uom(db, payload.max_weight_uom_id, "max_weight_uom")

    code = payload.code.strip().upper()
    prefix = payload.identifier_prefix.strip().upper()
    duplicate = db.scalar(
        select(LogisticUnitType).where(
            (LogisticUnitType.code == code) | (LogisticUnitType.identifier_prefix == prefix)
        )
    )
    if duplicate is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="logistic unit type code or prefix already exists",
        )

    child_ids = sorted(set(payload.allowed_child_type_ids))
    if child_ids:
        existing_child_ids = set(
            db.scalars(select(LogisticUnitType.id).where(LogisticUnitType.id.in_(child_ids)))
        )
        missing_ids = set(child_ids) - existing_child_ids
        if missing_ids:
            raise bad_request(f"unknown allowed child type ids: {sorted(missing_ids)}")

    data = payload.model_dump(exclude={"allowed_child_type_ids"})
    data["code"] = code
    data["identifier_prefix"] = prefix
    data["name"] = payload.name.strip()
    item = LogisticUnitType(**data)
    db.add(item)
    db.flush()
    if item.id in child_ids:
        db.rollback()
        raise bad_request("logistic unit type cannot contain itself")
    for child_id in child_ids:
        db.add(LogisticUnitTypeAllowedChild(parent_type_id=item.id, child_type_id=child_id))
    create_event(
        db,
        operation="logistic_unit_type_created",
        object_type="logistic_unit_type",
        object_uid=item.code,
        after={
            "name": item.name,
            "identifier_prefix": item.identifier_prefix,
            "allowed_child_type_ids": child_ids,
        },
    )
    commit_or_409(db, "logistic unit type code or prefix already exists")
    db.refresh(item)
    return item


def get_logistic_unit(db: Session, uid: str) -> LogisticUnit:
    item = db.scalar(select(LogisticUnit).where(func.upper(LogisticUnit.uid) == uid.strip().upper()))
    if item is None:
        raise not_found("logistic_unit")
    return item


def generate_logistic_unit_uid(db: Session, unit_type: LogisticUnitType) -> str:
    while True:
        candidate = f"{unit_type.identifier_prefix}{CODE_SEPARATOR}{uuid4().hex[:14].upper()}"
        if db.scalar(select(LogisticUnit.id).where(LogisticUnit.uid == candidate)) is None:
            return candidate


def logistic_unit_payload(db: Session, item: LogisticUnit) -> dict:
    unit_type = db.get(LogisticUnitType, item.type_id)
    parent = db.get(LogisticUnit, item.parent_unit_id) if item.parent_unit_id is not None else None
    current_location = (
        db.get(Location, item.current_location_id)
        if item.current_location_id is not None
        else None
    )
    weight_uom = db.get(UnitOfMeasure, item.weight_uom_id) if item.weight_uom_id is not None else None
    content_rows = list(
        db.scalars(
            select(LogisticUnitContent)
            .where(LogisticUnitContent.logistic_unit_id == item.id)
            .order_by(LogisticUnitContent.id)
        )
    )
    contents = []
    for row in content_rows:
        product = db.get(Product, row.product_id)
        batch = db.get(Batch, row.batch_id) if row.batch_id is not None else None
        uom = db.get(UnitOfMeasure, row.uom_id)
        contents.append(
            {
                "id": row.id,
                "product_id": row.product_id,
                "product_code": product.code if product else "",
                "batch_id": row.batch_id,
                "batch_number": batch.batch_number if batch else None,
                "quantity": row.quantity,
                "uom_id": row.uom_id,
                "uom_code": uom.code if uom else "",
                "uom_symbol": uom.symbol if uom else "",
                "added_at": row.added_at,
            }
        )
    child_rows = list(
        db.scalars(
            select(LogisticUnit)
            .where(LogisticUnit.parent_unit_id == item.id)
            .order_by(LogisticUnit.uid)
        )
    )
    children = []
    for child in child_rows:
        child_type = db.get(LogisticUnitType, child.type_id)
        children.append(
            {
                "id": child.id,
                "uid": child.uid,
                "type_id": child.type_id,
                "type_code": child_type.code if child_type else "",
                "type_name": child_type.name if child_type else "",
                "status": child.status,
            }
        )
    return {
        "id": item.id,
        "uid": item.uid,
        "type_id": item.type_id,
        "type_code": unit_type.code if unit_type else "",
        "type_name": unit_type.name if unit_type else "",
        "status": item.status,
        "parent_uid": parent.uid if parent else None,
        "current_location_id": item.current_location_id,
        "current_location_code": current_location.code if current_location else None,
        "measured_gross_weight": item.measured_gross_weight,
        "weight_uom_id": item.weight_uom_id,
        "weight_uom_code": weight_uom.code if weight_uom else None,
        "length_mm": item.length_mm,
        "width_mm": item.width_mm,
        "height_mm": item.height_mm,
        "status_before_hold": item.status_before_hold,
        "created_at": item.created_at,
        "accepted_at": item.accepted_at,
        "closed_at": item.closed_at,
        "contents": contents,
        "child_units": children,
    }


def validate_logistic_unit_weight(
    db: Session,
    unit_type: LogisticUnitType,
    measured_weight: Decimal | None,
    weight_uom_id: int | None,
) -> None:
    if measured_weight is None:
        return
    weight_uom = db.get(UnitOfMeasure, weight_uom_id)
    if weight_uom is None:
        raise not_found("weight_uom")
    if weight_uom.dimension != MeasurementDimension.MASS.value:
        raise bad_request("weight_uom must reference a mass unit")
    if unit_type.max_weight is None or unit_type.max_weight_uom_id is None:
        return
    max_weight_uom = db.get(UnitOfMeasure, unit_type.max_weight_uom_id)
    if max_weight_uom is None:
        raise bad_request("logistic unit type has an invalid max weight unit")
    measured_base = measured_weight * weight_uom.factor_to_base
    max_base = unit_type.max_weight * max_weight_uom.factor_to_base
    if measured_base > max_base:
        raise bad_request("measured gross weight exceeds the logistic unit type limit")


def create_logistic_unit(db: Session, payload: LogisticUnitCreate) -> LogisticUnit:
    ensure_reference_catalogs(db)
    unit_type = db.get(LogisticUnitType, payload.type_id)
    if unit_type is None or not unit_type.is_active:
        raise not_found("logistic_unit_type")
    validate_logistic_unit_weight(
        db,
        unit_type,
        payload.measured_gross_weight,
        payload.weight_uom_id,
    )
    uid = payload.uid.strip().upper() if payload.uid else generate_logistic_unit_uid(db, unit_type)
    item = LogisticUnit(
        uid=uid,
        type_id=unit_type.id,
        measured_gross_weight=payload.measured_gross_weight,
        weight_uom_id=payload.weight_uom_id,
        length_mm=payload.length_mm or unit_type.length_mm,
        width_mm=payload.width_mm or unit_type.width_mm,
        height_mm=payload.height_mm or unit_type.height_mm,
    )
    db.add(item)
    create_event(
        db,
        operation="logistic_unit_created",
        object_type="logistic_unit",
        object_uid=uid,
        actor=payload.actor,
        after={
            "type_code": unit_type.code,
            "status": LogisticUnitStatus.OPEN.value,
            "measured_gross_weight": (
                str(payload.measured_gross_weight)
                if payload.measured_gross_weight is not None
                else None
            ),
            "weight_uom_id": payload.weight_uom_id,
        },
    )
    commit_or_409(db, "logistic unit identifier already exists")
    db.refresh(item)
    return item


def logistic_location_occupied_count(db: Session, location_id: int) -> int:
    return (
        db.scalar(
            select(func.count(LogisticUnit.id)).where(
                LogisticUnit.current_location_id == location_id,
                LogisticUnit.parent_unit_id.is_(None),
            )
        )
        or 0
    )


def get_active_location(db: Session, location_code: str) -> Location:
    location = db.scalar(
        select(Location).where(func.upper(Location.code) == location_code.strip().upper())
    )
    if location is None:
        raise not_found("location")
    if not location.is_active:
        raise bad_request("location is not active")
    return location


def accept_logistic_unit(
    db: Session,
    uid: str,
    payload: LogisticUnitAcceptRequest,
) -> LogisticUnit:
    item = get_logistic_unit(db, uid)
    if item.parent_unit_id is not None:
        raise bad_request("nested logistic unit cannot be accepted separately")
    if item.accepted_at is not None:
        raise bad_request("logistic unit is already accepted")
    if item.status not in {LogisticUnitStatus.OPEN, LogisticUnitStatus.CLOSED}:
        raise bad_request(f"logistic unit cannot be accepted from status {item.status.value}")
    if item.current_location_id is not None:
        raise bad_request("logistic unit already has a current location")
    location = get_active_location(db, payload.location_code)
    if location.kind != LocationKind.RECEIVING:
        raise bad_request("logistic unit can be accepted only at a receiving location")
    if logistic_location_occupied_count(db, location.id) >= location.capacity_pallets:
        raise bad_request("location capacity is already reached")
    item.current_location_id = location.id
    item.accepted_at = utcnow()
    create_event(
        db,
        operation="logistic_unit_accepted",
        object_type="logistic_unit",
        object_uid=item.uid,
        actor=payload.actor,
        reason=payload.reason,
        before={"location_id": None, "accepted_at": None},
        after={
            "location_id": location.id,
            "location_code": location.code,
            "accepted_at": item.accepted_at.isoformat(),
        },
    )
    db.commit()
    db.refresh(item)
    return item


def require_open_logistic_unit(item: LogisticUnit) -> None:
    if item.status != LogisticUnitStatus.OPEN:
        raise bad_request("logistic unit must be open for composition changes")


def add_logistic_unit_content(
    db: Session,
    uid: str,
    payload: LogisticUnitContentCreate,
) -> LogisticUnit:
    item = get_logistic_unit(db, uid)
    require_open_logistic_unit(item)
    unit_type = db.get(LogisticUnitType, item.type_id)
    if unit_type is None or not unit_type.can_contain_goods:
        raise bad_request("logistic unit type cannot contain goods directly")
    product = db.get(Product, payload.product_id)
    if product is None:
        raise not_found("product")
    batch = db.get(Batch, payload.batch_id) if payload.batch_id is not None else None
    if payload.batch_id is not None and batch is None:
        raise not_found("batch")
    if batch is not None and batch.product_id != product.id:
        raise bad_request("batch belongs to another product")
    uom = db.get(UnitOfMeasure, payload.uom_id)
    if uom is None:
        raise not_found("unit_of_measure")
    if product.base_uom_id is not None:
        base_uom = db.get(UnitOfMeasure, product.base_uom_id)
        if base_uom is None:
            raise bad_request("product has an invalid base unit")
        if base_uom.dimension != uom.dimension:
            raise bad_request("content unit is incompatible with the product base unit")

    line_query = select(LogisticUnitContent).where(
        LogisticUnitContent.logistic_unit_id == item.id,
        LogisticUnitContent.product_id == product.id,
        LogisticUnitContent.uom_id == uom.id,
    )
    if batch is None:
        line_query = line_query.where(LogisticUnitContent.batch_id.is_(None))
    else:
        line_query = line_query.where(LogisticUnitContent.batch_id == batch.id)
    line = db.scalar(line_query)
    before_quantity = line.quantity if line else Decimal("0")
    if line is None:
        line = LogisticUnitContent(
            logistic_unit_id=item.id,
            product_id=product.id,
            batch_id=batch.id if batch else None,
            quantity=payload.quantity,
            uom_id=uom.id,
        )
        db.add(line)
    else:
        line.quantity += payload.quantity
    create_event(
        db,
        operation="logistic_unit_content_added",
        object_type="logistic_unit",
        object_uid=item.uid,
        actor=payload.actor,
        before={"quantity": str(before_quantity)},
        after={
            "product_code": product.code,
            "batch_number": batch.batch_number if batch else None,
            "quantity": str(before_quantity + payload.quantity),
            "uom_code": uom.code,
        },
    )
    commit_or_409(db, "logistic unit content conflicts with an existing line")
    db.refresh(item)
    return item


def remove_logistic_unit_content(
    db: Session,
    uid: str,
    content_id: int,
    payload: LogisticUnitContentRemoveRequest,
) -> LogisticUnit:
    item = get_logistic_unit(db, uid)
    require_open_logistic_unit(item)
    line = db.get(LogisticUnitContent, content_id)
    if line is None or line.logistic_unit_id != item.id:
        raise not_found("logistic_unit_content")
    if payload.quantity > line.quantity:
        raise bad_request("removed quantity exceeds the content line quantity")
    before_quantity = line.quantity
    remaining = line.quantity - payload.quantity
    if remaining == 0:
        db.delete(line)
    else:
        line.quantity = remaining
    create_event(
        db,
        operation="logistic_unit_content_removed",
        object_type="logistic_unit",
        object_uid=item.uid,
        actor=payload.actor,
        reason=payload.reason,
        before={"content_id": content_id, "quantity": str(before_quantity)},
        after={"content_id": content_id, "quantity": str(remaining)},
    )
    db.commit()
    db.refresh(item)
    return item


def add_logistic_unit_child(
    db: Session,
    parent_uid: str,
    payload: LogisticUnitChildRequest,
) -> LogisticUnit:
    parent = get_logistic_unit(db, parent_uid)
    child = get_logistic_unit(db, payload.child_uid)
    require_open_logistic_unit(parent)
    if parent.id == child.id:
        raise bad_request("logistic unit cannot contain itself")
    parent_type = db.get(LogisticUnitType, parent.type_id)
    if parent_type is None or not parent_type.can_contain_units:
        raise bad_request("logistic unit type cannot contain other units")
    allowed = db.scalar(
        select(LogisticUnitTypeAllowedChild.id).where(
            LogisticUnitTypeAllowedChild.parent_type_id == parent.type_id,
            LogisticUnitTypeAllowedChild.child_type_id == child.type_id,
        )
    )
    if allowed is None:
        raise bad_request("child logistic unit type is not allowed for this parent")
    if child.parent_unit_id is not None:
        raise bad_request("child logistic unit already belongs to another parent")
    if child.current_location_id is not None:
        raise bad_request("placed logistic unit must be removed from its location before nesting")
    if child.status not in {LogisticUnitStatus.CLOSED, LogisticUnitStatus.AVAILABLE}:
        raise bad_request("child logistic unit must be closed before nesting")

    ancestor = parent
    while ancestor.parent_unit_id is not None:
        ancestor = db.get(LogisticUnit, ancestor.parent_unit_id)
        if ancestor is None:
            break
        if ancestor.id == child.id:
            raise bad_request("logistic unit nesting cycle is not allowed")

    child.parent_unit_id = parent.id
    create_event(
        db,
        operation="logistic_unit_child_added",
        object_type="logistic_unit",
        object_uid=parent.uid,
        actor=payload.actor,
        after={"child_uid": child.uid},
    )
    commit_or_409(db, "logistic unit cannot be attached to this parent")
    db.refresh(parent)
    return parent


def remove_logistic_unit_child(
    db: Session,
    parent_uid: str,
    child_uid: str,
    payload: LogisticUnitActionRequest,
) -> LogisticUnit:
    parent = get_logistic_unit(db, parent_uid)
    child = get_logistic_unit(db, child_uid)
    require_open_logistic_unit(parent)
    if child.parent_unit_id != parent.id:
        raise bad_request("logistic unit is not a direct child of this parent")
    child.parent_unit_id = None
    create_event(
        db,
        operation="logistic_unit_child_removed",
        object_type="logistic_unit",
        object_uid=parent.uid,
        actor=payload.actor,
        reason=payload.reason,
        before={"child_uid": child.uid},
    )
    db.commit()
    db.refresh(parent)
    return parent


def close_logistic_unit(
    db: Session,
    uid: str,
    payload: LogisticUnitActionRequest,
) -> LogisticUnit:
    item = get_logistic_unit(db, uid)
    require_open_logistic_unit(item)
    open_child = db.scalar(
        select(LogisticUnit.id).where(
            LogisticUnit.parent_unit_id == item.id,
            LogisticUnit.status == LogisticUnitStatus.OPEN,
        )
    )
    if open_child is not None:
        raise bad_request("all child logistic units must be closed first")
    item.status = LogisticUnitStatus.CLOSED
    item.closed_at = utcnow()
    create_event(
        db,
        operation="logistic_unit_closed",
        object_type="logistic_unit",
        object_uid=item.uid,
        actor=payload.actor,
        reason=payload.reason,
        before={"status": LogisticUnitStatus.OPEN.value},
        after={"status": LogisticUnitStatus.CLOSED.value},
    )
    db.commit()
    db.refresh(item)
    return item


def reopen_logistic_unit(
    db: Session,
    uid: str,
    payload: LogisticUnitActionRequest,
) -> LogisticUnit:
    item = get_logistic_unit(db, uid)
    if item.status != LogisticUnitStatus.CLOSED:
        raise bad_request("only a closed logistic unit can be reopened")
    if item.parent_unit_id is not None:
        parent = db.get(LogisticUnit, item.parent_unit_id)
        if parent is not None and parent.status != LogisticUnitStatus.OPEN:
            raise bad_request("parent logistic unit must be reopened first")
    item.status = LogisticUnitStatus.OPEN
    item.closed_at = None
    create_event(
        db,
        operation="logistic_unit_reopened",
        object_type="logistic_unit",
        object_uid=item.uid,
        actor=payload.actor,
        reason=payload.reason,
        before={"status": LogisticUnitStatus.CLOSED.value},
        after={"status": LogisticUnitStatus.OPEN.value},
    )
    db.commit()
    db.refresh(item)
    return item


def hold_logistic_unit(
    db: Session,
    uid: str,
    target_status: LogisticUnitStatus,
    payload: LogisticUnitHoldRequest,
) -> LogisticUnit:
    if target_status not in {LogisticUnitStatus.BLOCKED, LogisticUnitStatus.QUARANTINE}:
        raise bad_request("target status must be blocked or quarantine")
    item = get_logistic_unit(db, uid)
    if item.parent_unit_id is not None:
        raise bad_request("nested logistic unit must be removed from its parent before a hold")
    allowed_statuses = {
        LogisticUnitStatus.OPEN,
        LogisticUnitStatus.CLOSED,
        LogisticUnitStatus.AVAILABLE,
        LogisticUnitStatus.BLOCKED,
        LogisticUnitStatus.QUARANTINE,
    }
    if item.status not in allowed_statuses:
        raise bad_request(f"logistic unit cannot be held from status {item.status.value}")
    if item.status == target_status:
        raise bad_request(f"logistic unit is already {target_status.value}")
    before_status = item.status
    if item.status not in {LogisticUnitStatus.BLOCKED, LogisticUnitStatus.QUARANTINE}:
        item.status_before_hold = item.status.value
    item.status = target_status
    create_event(
        db,
        operation=f"logistic_unit_{target_status.value}",
        object_type="logistic_unit",
        object_uid=item.uid,
        actor=payload.actor,
        reason=payload.reason,
        before={"status": before_status.value},
        after={
            "status": target_status.value,
            "status_before_hold": item.status_before_hold,
        },
    )
    db.commit()
    db.refresh(item)
    return item


def release_logistic_unit(
    db: Session,
    uid: str,
    payload: LogisticUnitHoldRequest,
) -> LogisticUnit:
    item = get_logistic_unit(db, uid)
    if item.status not in {LogisticUnitStatus.BLOCKED, LogisticUnitStatus.QUARANTINE}:
        raise bad_request("only blocked or quarantine logistic unit can be released")
    try:
        restored_status = LogisticUnitStatus(item.status_before_hold or "")
    except ValueError:
        if item.current_location_id is not None and item.closed_at is not None:
            restored_status = LogisticUnitStatus.AVAILABLE
        elif item.closed_at is not None:
            restored_status = LogisticUnitStatus.CLOSED
        else:
            restored_status = LogisticUnitStatus.OPEN
    if restored_status not in {
        LogisticUnitStatus.OPEN,
        LogisticUnitStatus.CLOSED,
        LogisticUnitStatus.AVAILABLE,
    }:
        raise bad_request("stored status cannot be restored after hold")
    before_status = item.status
    item.status = restored_status
    item.status_before_hold = None
    create_event(
        db,
        operation="logistic_unit_released",
        object_type="logistic_unit",
        object_uid=item.uid,
        actor=payload.actor,
        reason=payload.reason,
        before={"status": before_status.value},
        after={"status": restored_status.value},
    )
    db.commit()
    db.refresh(item)
    return item


def place_logistic_unit(
    db: Session,
    uid: str,
    payload: LogisticUnitLocationRequest,
) -> LogisticUnit:
    item = get_logistic_unit(db, uid)
    if item.parent_unit_id is not None:
        raise bad_request("nested logistic unit is placed together with its parent")
    if item.status != LogisticUnitStatus.CLOSED:
        raise bad_request("only a closed logistic unit can be placed")
    location = get_active_location(db, payload.location_code)
    if location.kind != LocationKind.STORAGE:
        raise bad_request("logistic unit can be placed only in a storage location")
    current_location = (
        db.get(Location, item.current_location_id)
        if item.current_location_id is not None
        else None
    )
    if current_location is not None and current_location.kind == LocationKind.STORAGE:
        raise bad_request("placed logistic unit must be moved instead")
    if current_location is not None and current_location.warehouse_id != location.warehouse_id:
        raise bad_request("logistic unit cannot be placed in another warehouse")
    if logistic_location_occupied_count(db, location.id) >= location.capacity_pallets:
        raise bad_request("location capacity is already reached")
    before = {
        "status": item.status.value,
        "location_id": item.current_location_id,
        "location_code": current_location.code if current_location else None,
    }
    item.current_location_id = location.id
    item.status = LogisticUnitStatus.AVAILABLE
    create_event(
        db,
        operation="logistic_unit_placed",
        object_type="logistic_unit",
        object_uid=item.uid,
        actor=payload.actor,
        reason=payload.reason,
        before=before,
        after={
            "status": item.status.value,
            "location_id": location.id,
            "location_code": location.code,
        },
    )
    db.commit()
    db.refresh(item)
    return item


def move_logistic_unit(
    db: Session,
    uid: str,
    payload: LogisticUnitLocationRequest,
) -> LogisticUnit:
    item = get_logistic_unit(db, uid)
    if item.parent_unit_id is not None:
        raise bad_request("nested logistic unit is moved together with its parent")
    if item.status != LogisticUnitStatus.AVAILABLE:
        raise bad_request("only an available logistic unit can be moved")
    current_location = (
        db.get(Location, item.current_location_id)
        if item.current_location_id is not None
        else None
    )
    if current_location is None or current_location.kind != LocationKind.STORAGE:
        raise bad_request("available logistic unit must have a storage location")
    location = get_active_location(db, payload.location_code)
    if location.kind != LocationKind.STORAGE:
        raise bad_request("logistic unit can be moved only to a storage location")
    if current_location.id == location.id:
        raise bad_request("logistic unit is already in this location")
    if current_location.warehouse_id != location.warehouse_id:
        raise bad_request("logistic unit cannot be moved between warehouses without a transfer")
    if logistic_location_occupied_count(db, location.id) >= location.capacity_pallets:
        raise bad_request("location capacity is already reached")
    item.current_location_id = location.id
    create_event(
        db,
        operation="logistic_unit_moved",
        object_type="logistic_unit",
        object_uid=item.uid,
        actor=payload.actor,
        reason=payload.reason,
        before={
            "location_id": current_location.id,
            "location_code": current_location.code,
        },
        after={"location_id": location.id, "location_code": location.code},
    )
    db.commit()
    db.refresh(item)
    return item


def disassemble_logistic_unit(
    db: Session,
    uid: str,
    payload: LogisticUnitActionRequest,
) -> LogisticUnit:
    item = get_logistic_unit(db, uid)
    require_open_logistic_unit(item)
    if item.parent_unit_id is not None:
        raise bad_request("nested logistic unit must be removed from its parent first")
    has_content = db.scalar(
        select(LogisticUnitContent.id).where(LogisticUnitContent.logistic_unit_id == item.id)
    )
    has_children = db.scalar(
        select(LogisticUnit.id).where(LogisticUnit.parent_unit_id == item.id)
    )
    if has_content is not None or has_children is not None:
        raise bad_request("logistic unit must be empty before disassembly")
    item.status = LogisticUnitStatus.DISASSEMBLED
    create_event(
        db,
        operation="logistic_unit_disassembled",
        object_type="logistic_unit",
        object_uid=item.uid,
        actor=payload.actor,
        reason=payload.reason,
        before={"status": LogisticUnitStatus.OPEN.value},
        after={"status": LogisticUnitStatus.DISASSEMBLED.value},
    )
    db.commit()
    db.refresh(item)
    return item


def create_equipment_profile(db: Session, payload: EquipmentProfileCreate) -> EquipmentProfile:
    if payload.warehouse_id is not None and db.get(Warehouse, payload.warehouse_id) is None:
        raise not_found("warehouse")

    code = payload.code.strip().upper()
    if payload.is_default:
        default_query = select(EquipmentProfile).where(
            EquipmentProfile.device_kind == payload.device_kind.value,
            EquipmentProfile.is_default.is_(True),
        )
        if payload.warehouse_id is None:
            default_query = default_query.where(EquipmentProfile.warehouse_id.is_(None))
        else:
            default_query = default_query.where(EquipmentProfile.warehouse_id == payload.warehouse_id)
        for existing_default in db.scalars(default_query):
            existing_default.is_default = False

    data = payload.model_dump()
    data["code"] = code
    data["name"] = payload.name.strip()
    data["device_kind"] = payload.device_kind.value
    data["connection_type"] = payload.connection_type.value
    item = EquipmentProfile(**data)
    db.add(item)
    create_event(
        db,
        operation="equipment_profile_created",
        object_type="equipment_profile",
        object_uid=code,
        after={
            "name": item.name,
            "device_kind": item.device_kind,
            "connection_type": item.connection_type,
            "host": item.host,
            "port": item.port,
            "warehouse_id": item.warehouse_id,
            "is_default": item.is_default,
        },
    )
    commit_or_409(db, "equipment profile already exists")
    db.refresh(item)
    return item


def update_equipment_profile(
    db: Session,
    profile_id: int,
    payload: EquipmentProfileUpdate,
) -> EquipmentProfile:
    item = db.get(EquipmentProfile, profile_id)
    if item is None:
        raise not_found("equipment_profile")
    if payload.warehouse_id is not None and db.get(Warehouse, payload.warehouse_id) is None:
        raise not_found("warehouse")

    if payload.is_default:
        default_query = select(EquipmentProfile).where(
            EquipmentProfile.id != item.id,
            EquipmentProfile.device_kind == payload.device_kind.value,
            EquipmentProfile.is_default.is_(True),
        )
        if payload.warehouse_id is None:
            default_query = default_query.where(EquipmentProfile.warehouse_id.is_(None))
        else:
            default_query = default_query.where(EquipmentProfile.warehouse_id == payload.warehouse_id)
        for existing_default in db.scalars(default_query):
            existing_default.is_default = False

    before = {
        "code": item.code,
        "name": item.name,
        "device_kind": item.device_kind,
        "connection_type": item.connection_type,
        "host": item.host,
        "port": item.port,
        "warehouse_id": item.warehouse_id,
        "is_default": item.is_default,
        "is_active": item.is_active,
    }
    data = payload.model_dump()
    data["code"] = payload.code.strip().upper()
    data["name"] = payload.name.strip()
    data["device_kind"] = payload.device_kind.value
    data["connection_type"] = payload.connection_type.value
    for field, value in data.items():
        setattr(item, field, value)
    after = {
        "code": item.code,
        "name": item.name,
        "device_kind": item.device_kind,
        "connection_type": item.connection_type,
        "host": item.host,
        "port": item.port,
        "warehouse_id": item.warehouse_id,
        "is_default": item.is_default,
        "is_active": item.is_active,
    }
    create_event(
        db,
        operation="equipment_profile_updated",
        object_type="equipment_profile",
        object_uid=item.code,
        before=before,
        after=after,
    )
    commit_or_409(db, "equipment profile code already exists")
    db.refresh(item)
    return item


def create_product(db: Session, payload: ProductCreate) -> Product:
    ensure_reference_catalogs(db)
    data = payload.model_dump()
    base_uom_id = data.get("base_uom_id")
    if base_uom_id is not None:
        unit = db.get(UnitOfMeasure, base_uom_id)
        if unit is None:
            raise not_found("base_uom")
        data["unit"] = unit.symbol
    else:
        legacy_unit = payload.unit.strip()
        unit = db.scalar(
            select(UnitOfMeasure).where(
                (func.upper(UnitOfMeasure.code) == legacy_unit.upper()) | (UnitOfMeasure.symbol == legacy_unit)
            )
        )
        data["base_uom_id"] = unit.id if unit else None
        data["unit"] = legacy_unit
    product = Product(**data)
    db.add(product)
    commit_or_409(db, "product already exists")
    db.refresh(product)
    return product


def create_batch(db: Session, payload: BatchCreate) -> Batch:
    product = db.get(Product, payload.product_id)
    if product is None:
        raise not_found("product")
    if payload.expiry_date <= payload.production_date:
        raise bad_request("expiry_date must be after production_date")
    batch = Batch(**payload.model_dump())
    db.add(batch)
    commit_or_409(db, "batch already exists for this product")
    db.refresh(batch)
    return batch


def create_warehouse(db: Session, payload: WarehouseCreate) -> Warehouse:
    warehouse = Warehouse(**payload.model_dump())
    db.add(warehouse)
    commit_or_409(db, "warehouse already exists")
    db.refresh(warehouse)
    return warehouse


def create_zone(db: Session, payload: ZoneCreate) -> Zone:
    warehouse = db.get(Warehouse, payload.warehouse_id)
    if warehouse is None:
        raise not_found("warehouse")
    zone = Zone(**payload.model_dump())
    db.add(zone)
    commit_or_409(db, "zone already exists in this warehouse")
    db.refresh(zone)
    return zone


def create_location(db: Session, payload: LocationCreate) -> Location:
    warehouse = db.get(Warehouse, payload.warehouse_id)
    if warehouse is None:
        raise not_found("warehouse")
    zone = db.get(Zone, payload.zone_id)
    if zone is None:
        raise not_found("zone")
    if zone.warehouse_id != warehouse.id:
        raise bad_request("zone belongs to another warehouse")
    location = Location(**payload.model_dump())
    db.add(location)
    commit_or_409(db, "location already exists")
    db.refresh(location)
    return location


def generate_box_uid(db: Session) -> str:
    while True:
        candidate = f"{BOX_CODE_PREFIX}{CODE_SEPARATOR}{uuid4().hex[:14].upper()}"
        exists = db.scalar(select(Box.id).where(Box.box_uid == candidate))
        if not exists:
            return candidate


def generate_pallet_uid(db: Session) -> str:
    while True:
        candidate = f"{PALLET_CODE_PREFIX}{CODE_SEPARATOR}{uuid4().hex[:12].upper()}"
        exists = db.scalar(select(Pallet.id).where(Pallet.pallet_uid == candidate))
        if not exists:
            return candidate


def generate_shipment_uid(db: Session) -> str:
    while True:
        candidate = f"{SHIPMENT_CODE_PREFIX}{CODE_SEPARATOR}{uuid4().hex[:10].upper()}"
        exists = db.scalar(select(Shipment.id).where(Shipment.shipment_uid == candidate))
        if not exists:
            return candidate


def generate_inventory_uid(db: Session) -> str:
    while True:
        candidate = f"{INVENTORY_CODE_PREFIX}{CODE_SEPARATOR}{uuid4().hex[:10].upper()}"
        exists = db.scalar(select(InventorySession.id).where(InventorySession.inventory_uid == candidate))
        if not exists:
            return candidate


def generate_boxes(db: Session, *, batch_id: int, quantity: int, actor: str = "system") -> list[Box]:
    batch = db.get(Batch, batch_id)
    if batch is None:
        raise not_found("batch")
    boxes: list[Box] = []
    for _ in range(quantity):
        box = Box(box_uid=generate_box_uid(db), product_id=batch.product_id, batch_id=batch.id)
        db.add(box)
        boxes.append(box)
    create_event(
        db,
        operation="boxes_generated",
        object_type="batch",
        object_uid=batch.batch_number,
        actor=actor,
        after={"quantity": quantity},
    )
    db.commit()
    for box in boxes:
        db.refresh(box)
    return boxes


def ensure_demo_catalog(db: Session, payload: DemoCatalogRequest) -> dict:
    created = {
        "created_products": 0,
        "created_batches": 0,
        "created_warehouses": 0,
        "created_zones": 0,
        "created_locations": 0,
        "product_ids": [],
        "batch_ids": [],
    }
    warehouse = db.scalar(select(Warehouse).where(Warehouse.code == payload.warehouse_code))
    if warehouse is None:
        warehouse = create_warehouse(
            db,
            WarehouseCreate(
                code=payload.warehouse_code,
                name=payload.warehouse_name,
                city=DEFAULT_CITY,
            ),
        )
        created["created_warehouses"] += 1

    storage = db.scalar(select(Zone).where(Zone.warehouse_id == warehouse.id, Zone.code == STORAGE_ZONE_CODE))
    if storage is None:
        storage = create_zone(
            db,
            ZoneCreate(
                warehouse_id=warehouse.id,
                code=STORAGE_ZONE_CODE,
                name=STORAGE_ZONE_NAME,
                kind=LocationKind.STORAGE,
            ),
        )
        created["created_zones"] += 1
    receiving = db.scalar(select(Zone).where(Zone.warehouse_id == warehouse.id, Zone.code == RECEIVING_ZONE_CODE))
    if receiving is None:
        receiving = create_zone(
            db,
            ZoneCreate(
                warehouse_id=warehouse.id,
                code=RECEIVING_ZONE_CODE,
                name=RECEIVING_ZONE_NAME,
                kind=LocationKind.RECEIVING,
            ),
        )
        created["created_zones"] += 1

    receiving_code = f"{warehouse.code}{CODE_SEPARATOR}{RECEIVING_ZONE_CODE}{CODE_SEPARATOR}{RECEIVING_LOCATION_SUFFIX}"
    if db.scalar(select(Location.id).where(Location.code == receiving_code)) is None:
        create_location(
            db,
            LocationCreate(
                warehouse_id=warehouse.id,
                zone_id=receiving.id,
                code=receiving_code,
                name="Приемка палет 1",
                kind=LocationKind.RECEIVING,
                capacity_pallets=4,
            ),
        )
        created["created_locations"] += 1

    for idx in range(1, payload.storage_locations + 1):
        code = f"{warehouse.code}{CODE_SEPARATOR}{STORAGE_ZONE_CODE}{CODE_SEPARATOR}{STORAGE_LOCATION_PATTERN.format(index=idx)}"
        if db.scalar(select(Location.id).where(Location.code == code)) is None:
            create_location(
                db,
                LocationCreate(
                    warehouse_id=warehouse.id,
                    zone_id=storage.id,
                    code=code,
                    name=f"Палетоместо {idx}",
                    kind=LocationKind.STORAGE,
                    capacity_pallets=1,
                ),
            )
            created["created_locations"] += 1

    demo_products = [
        ("ICE-VAN-100", "Мороженое ванильное 100 г", 24, 96, 365),
        ("ICE-CHO-100", "Мороженое шоколадное 100 г", 20, 96, 365),
        ("ICE-BER-80", "Пломбир ягодный 80 г", 30, 80, 300),
    ]
    production_date, expiry_date = seed_batch_dates()
    for code, name, quantity_per_box, boxes_per_pallet, shelf_life_days in demo_products:
        product = db.scalar(select(Product).where(Product.code == code))
        if product is None:
            product = create_product(
                db,
                ProductCreate(
                    code=code,
                    name=name,
                    unit=DEFAULT_UNIT,
                    quantity_per_box=quantity_per_box,
                    boxes_per_pallet=boxes_per_pallet,
                    shelf_life_days=shelf_life_days,
                ),
            )
            created["created_products"] += 1
        created["product_ids"].append(product.id)
        batch_number = f"DEMO-{code}-20260721"
        batch = db.scalar(select(Batch).where(Batch.product_id == product.id, Batch.batch_number == batch_number))
        if batch is None:
            batch = create_batch(
                db,
                BatchCreate(
                    product_id=product.id,
                    batch_number=batch_number,
                    production_date=production_date,
                    expiry_date=expiry_date,
                ),
            )
            created["created_batches"] += 1
        created["batch_ids"].append(batch.id)

    create_event(
        db,
        operation="demo_catalog_generated",
        object_type="warehouse",
        object_uid=warehouse.code,
        actor=payload.actor,
        after=created,
    )
    db.commit()
    return created


def empty_storage_locations(db: Session) -> list[Location]:
    locations = list(
        db.scalars(
            select(Location)
            .where(Location.kind == LocationKind.STORAGE, Location.is_active.is_(True))
            .order_by(Location.code)
        )
    )
    return [location for location in locations if location_occupied_count(db, location.id) < location.capacity_pallets]


def generate_demo_pallets(db: Session, payload: DemoPalletsRequest) -> dict:
    batch = db.get(Batch, payload.batch_id) if payload.batch_id else None
    if batch is None:
        batch = db.scalar(select(Batch).order_by(Batch.id))
    if batch is None:
        raise bad_request("create demo catalog first")
    product = db.get(Product, batch.product_id)
    if product is None:
        raise not_found("product")
    if payload.boxes_per_pallet > product.boxes_per_pallet:
        raise bad_request("boxes_per_pallet exceeds product capacity")

    result = {
        "created_products": 0,
        "created_batches": 0,
        "created_warehouses": 0,
        "created_zones": 0,
        "created_locations": 0,
        "created_boxes": 0,
        "created_pallets": 0,
        "placed_pallets": 0,
        "waiting_pallets": 0,
        "product_ids": [product.id],
        "batch_ids": [batch.id],
        "pallet_uids": [],
    }
    for _ in range(payload.quantity):
        boxes = generate_boxes(db, batch_id=batch.id, quantity=payload.boxes_per_pallet, actor=payload.actor)
        result["created_boxes"] += len(boxes)
        pallet = open_pallet(db, actor=payload.actor)
        for box in boxes:
            accept_box(db, box_uid=box.box_uid, actor=payload.actor)
            add_box_to_pallet(db, pallet_uid=pallet.pallet_uid, box_uid=box.box_uid, actor=payload.actor)
        close_pallet(db, pallet_uid=pallet.pallet_uid, actor=payload.actor, reason="demo")
        result["created_pallets"] += 1
        if payload.place_to_empty_locations:
            free_locations = empty_storage_locations(db)
            if free_locations:
                place_pallet(
                    db,
                    pallet_uid=pallet.pallet_uid,
                    location_code=free_locations[0].code,
                    actor=payload.actor,
                    reason="demo auto placement",
                )
                result["placed_pallets"] += 1
            else:
                result["waiting_pallets"] += 1
        else:
            result["waiting_pallets"] += 1
        result["pallet_uids"].append(pallet.pallet_uid)

    create_event(
        db,
        operation="demo_pallets_generated",
        object_type="batch",
        object_uid=batch.batch_number,
        actor=payload.actor,
        after=result,
    )
    db.commit()
    return result


def accept_box(db: Session, *, box_uid: str, actor: str = "system") -> Box:
    box = db.scalar(select(Box).where(Box.box_uid == box_uid))
    if box is None:
        raise not_found("box")
    if box.status != BoxStatus.LABEL_CREATED:
        raise bad_request(f"box cannot be accepted from status {box.status}")
    before = {"status": box.status}
    box.status = BoxStatus.ACCEPTED_FROM_PRODUCTION
    box.accepted_at = utcnow()
    create_event(
        db,
        operation="box_accepted",
        object_type="box",
        object_uid=box.box_uid,
        actor=actor,
        before=before,
        after={"status": box.status},
    )
    db.commit()
    db.refresh(box)
    return box


def open_pallet(db: Session, *, actor: str = "system") -> Pallet:
    pallet = Pallet(pallet_uid=generate_pallet_uid(db))
    db.add(pallet)
    create_event(
        db,
        operation="pallet_opened",
        object_type="pallet",
        object_uid=pallet.pallet_uid,
        actor=actor,
        after={"status": PalletStatus.OPEN},
    )
    db.commit()
    db.refresh(pallet)
    return pallet


def add_box_to_pallet(db: Session, *, pallet_uid: str, box_uid: str, actor: str = "system") -> Pallet:
    pallet = db.scalar(select(Pallet).where(Pallet.pallet_uid == pallet_uid))
    if pallet is None:
        raise not_found("pallet")
    box = db.scalar(select(Box).where(Box.box_uid == box_uid))
    if box is None:
        raise not_found("box")
    if pallet.status != PalletStatus.OPEN:
        raise bad_request("only open pallet can accept boxes")
    if box.status != BoxStatus.ACCEPTED_FROM_PRODUCTION:
        raise bad_request(f"box cannot be added from status {box.status}")
    if box.current_pallet_id is not None:
        raise bad_request("box already belongs to a pallet")
    if pallet.product_id is not None and pallet.product_id != box.product_id:
        raise bad_request("box product does not match pallet product")
    if pallet.batch_id is not None and pallet.batch_id != box.batch_id:
        raise bad_request("box batch does not match pallet batch")
    if pallet.product_id is None:
        pallet.product_id = box.product_id
        pallet.batch_id = box.batch_id
    product = db.get(Product, box.product_id)
    current_count = db.scalar(select(func.count(PalletBox.id)).where(PalletBox.pallet_id == pallet.id)) or 0
    if product and current_count >= product.boxes_per_pallet:
        raise bad_request("pallet capacity for this product is already reached")

    box.current_pallet_id = pallet.id
    box.status = BoxStatus.IN_OPEN_PALLET
    db.add(PalletBox(pallet_id=pallet.id, box_id=box.id))
    create_event(
        db,
        operation="box_added_to_pallet",
        object_type="pallet",
        object_uid=pallet.pallet_uid,
        actor=actor,
        after={"box_uid": box.box_uid, "box_count": current_count + 1},
    )
    commit_or_409(db, "box already belongs to a pallet")
    db.refresh(pallet)
    return pallet


def close_pallet(db: Session, *, pallet_uid: str, actor: str = "system", reason: str | None = None) -> Pallet:
    pallet = db.scalar(select(Pallet).where(Pallet.pallet_uid == pallet_uid))
    if pallet is None:
        raise not_found("pallet")
    if pallet.status != PalletStatus.OPEN:
        raise bad_request("only open pallet can be closed")
    box_count = db.scalar(select(func.count(PalletBox.id)).where(PalletBox.pallet_id == pallet.id)) or 0
    if box_count == 0:
        raise bad_request("empty pallet cannot be closed")
    before = {"status": pallet.status}
    pallet.status = PalletStatus.AVAILABLE if pallet.current_location_id else PalletStatus.WAITING_PLACEMENT
    pallet.closed_at = utcnow()
    db.query(Box).filter(Box.current_pallet_id == pallet.id).update({"status": BoxStatus.IN_CLOSED_PALLET})
    create_event(
        db,
        operation="pallet_closed",
        object_type="pallet",
        object_uid=pallet.pallet_uid,
        actor=actor,
        reason=reason,
        before=before,
        after={"status": pallet.status, "box_count": box_count},
    )
    db.commit()
    db.refresh(pallet)
    return pallet


def reopen_pallet(db: Session, *, pallet_uid: str, actor: str = "system", reason: str) -> Pallet:
    pallet = db.scalar(select(Pallet).where(Pallet.pallet_uid == pallet_uid))
    if pallet is None:
        raise not_found("pallet")
    if pallet.status not in {PalletStatus.CLOSED, PalletStatus.WAITING_PLACEMENT, PalletStatus.AVAILABLE}:
        raise bad_request(f"pallet cannot be reopened from status {pallet.status}")
    box_count = db.scalar(select(func.count(PalletBox.id)).where(PalletBox.pallet_id == pallet.id)) or 0
    if box_count == 0:
        raise bad_request("empty pallet does not need reopening")
    before = {"status": pallet.status, "location_id": pallet.current_location_id, "box_count": box_count}
    pallet.status = PalletStatus.OPEN
    pallet.closed_at = None
    db.query(Box).filter(Box.current_pallet_id == pallet.id).update({"status": BoxStatus.IN_OPEN_PALLET})
    create_event(
        db,
        operation="pallet_reopened",
        object_type="pallet",
        object_uid=pallet.pallet_uid,
        actor=actor,
        reason=reason,
        before=before,
        after={"status": pallet.status, "box_count": box_count},
    )
    db.commit()
    db.refresh(pallet)
    return pallet


def set_pallet_problem_status(
    db: Session,
    *,
    pallet_uid: str,
    target_status: PalletStatus,
    actor: str = "system",
    reason: str,
) -> Pallet:
    pallet = db.scalar(select(Pallet).where(Pallet.pallet_uid == pallet_uid))
    if pallet is None:
        raise not_found("pallet")
    if target_status not in {PalletStatus.BLOCKED, PalletStatus.QUARANTINE}:
        raise bad_request("target status must be blocked or quarantine")
    if pallet.status in {PalletStatus.SHIPPED, PalletStatus.WRITTEN_OFF, PalletStatus.DISASSEMBLED}:
        raise bad_request(f"pallet cannot be changed from status {pallet.status}")
    before = {"status": pallet.status}
    pallet.status = target_status
    create_event(
        db,
        operation=f"pallet_{target_status.value}",
        object_type="pallet",
        object_uid=pallet.pallet_uid,
        actor=actor,
        reason=reason,
        before=before,
        after={"status": pallet.status},
    )
    db.commit()
    db.refresh(pallet)
    return pallet


def release_pallet(db: Session, *, pallet_uid: str, actor: str = "system", reason: str) -> Pallet:
    pallet = db.scalar(select(Pallet).where(Pallet.pallet_uid == pallet_uid))
    if pallet is None:
        raise not_found("pallet")
    if pallet.status not in {PalletStatus.BLOCKED, PalletStatus.QUARANTINE}:
        raise bad_request("only blocked or quarantine pallet can be released")
    box_count = db.scalar(select(func.count(PalletBox.id)).where(PalletBox.pallet_id == pallet.id)) or 0
    before = {"status": pallet.status}
    if box_count == 0:
        pallet.status = PalletStatus.OPEN
    elif pallet.current_location_id:
        pallet.status = PalletStatus.AVAILABLE
    else:
        pallet.status = PalletStatus.WAITING_PLACEMENT
    create_event(
        db,
        operation="pallet_released",
        object_type="pallet",
        object_uid=pallet.pallet_uid,
        actor=actor,
        reason=reason,
        before=before,
        after={"status": pallet.status},
    )
    db.commit()
    db.refresh(pallet)
    return pallet


def location_occupied_count(db: Session, location_id: int) -> int:
    return db.scalar(select(func.count(Pallet.id)).where(Pallet.current_location_id == location_id)) or 0


def place_pallet(db: Session, *, pallet_uid: str, location_code: str, actor: str = "system", reason: str | None = None) -> Pallet:
    pallet = db.scalar(select(Pallet).where(Pallet.pallet_uid == pallet_uid))
    if pallet is None:
        raise not_found("pallet")
    location = db.scalar(select(Location).where(Location.code == location_code))
    if location is None:
        raise not_found("location")
    if not location.is_active:
        raise bad_request("location is not active")
    if location.kind != LocationKind.STORAGE:
        raise bad_request("pallet can be placed only in a storage location")
    if pallet.status not in {PalletStatus.CLOSED, PalletStatus.WAITING_PLACEMENT}:
        raise bad_request(f"pallet cannot be placed from status {pallet.status}")
    current_location = db.get(Location, pallet.current_location_id) if pallet.current_location_id else None
    if (
        current_location is not None
        and current_location.kind == LocationKind.TRANSFER_IN
        and current_location.warehouse_id != location.warehouse_id
    ):
        raise bad_request("received pallet can be placed only at the destination warehouse")
    if location_occupied_count(db, location.id) >= location.capacity_pallets:
        raise bad_request("location capacity is already reached")
    before = {"status": pallet.status, "location_id": pallet.current_location_id}
    pallet.current_location_id = location.id
    pallet.status = PalletStatus.AVAILABLE
    create_event(
        db,
        operation="pallet_placed",
        object_type="pallet",
        object_uid=pallet.pallet_uid,
        actor=actor,
        reason=reason,
        before=before,
        after={"status": pallet.status, "location_code": location.code},
    )
    db.commit()
    db.refresh(pallet)
    return pallet


def move_pallet(db: Session, *, pallet_uid: str, location_code: str, actor: str = "system", reason: str | None = None) -> Pallet:
    pallet = db.scalar(select(Pallet).where(Pallet.pallet_uid == pallet_uid))
    if pallet is None:
        raise not_found("pallet")
    location = db.scalar(select(Location).where(Location.code == location_code))
    if location is None:
        raise not_found("location")
    if not location.is_active or location.kind != LocationKind.STORAGE:
        raise bad_request("pallet can be moved only to an active storage location")
    if pallet.status != PalletStatus.AVAILABLE:
        raise bad_request(f"pallet cannot be moved from status {pallet.status}")
    current_location = db.get(Location, pallet.current_location_id) if pallet.current_location_id else None
    if current_location is None:
        raise bad_request("available pallet must have a current location")
    if current_location.warehouse_id != location.warehouse_id:
        raise bad_request("pallet cannot be moved between warehouses without a transfer")
    if pallet.current_location_id == location.id:
        raise bad_request("pallet is already in this location")
    if location_occupied_count(db, location.id) >= location.capacity_pallets:
        raise bad_request("location capacity is already reached")
    before = {"location_id": pallet.current_location_id}
    pallet.current_location_id = location.id
    create_event(
        db,
        operation="pallet_moved",
        object_type="pallet",
        object_uid=pallet.pallet_uid,
        actor=actor,
        reason=reason,
        before=before,
        after={"location_code": location.code},
    )
    db.commit()
    db.refresh(pallet)
    return pallet


def seed_batch_dates() -> tuple[date, date]:
    production_date = date(2026, 7, 21)
    expiry_date = date(2027, 7, 21)
    return production_date, expiry_date


def create_shipment(db: Session, payload: ShipmentCreate) -> Shipment:
    shipment = Shipment(
        shipment_uid=generate_shipment_uid(db),
        customer_name=payload.customer_name,
        destination=payload.destination,
        planned_date=payload.planned_date,
    )
    db.add(shipment)
    create_event(
        db,
        operation="shipment_created",
        object_type="shipment",
        object_uid=shipment.shipment_uid,
        actor=payload.actor,
        after={"customer_name": shipment.customer_name, "destination": shipment.destination},
    )
    db.commit()
    db.refresh(shipment)
    return shipment


def get_shipment(db: Session, shipment_uid: str) -> Shipment:
    shipment = db.scalar(select(Shipment).where(Shipment.shipment_uid == shipment_uid))
    if shipment is None:
        raise not_found("shipment")
    return shipment


def reserve_pallet_for_shipment(
    db: Session,
    *,
    shipment_uid: str,
    pallet_uid: str,
    actor: str = "system",
) -> Shipment:
    shipment = get_shipment(db, shipment_uid)
    if shipment.status not in {ShipmentStatus.DRAFT, ShipmentStatus.RESERVED}:
        raise bad_request(f"shipment cannot accept pallets from status {shipment.status}")
    pallet = db.scalar(select(Pallet).where(Pallet.pallet_uid == pallet_uid))
    if pallet is None:
        raise not_found("pallet")
    if pallet.status != PalletStatus.AVAILABLE:
        raise bad_request(f"only available pallet can be reserved, got {pallet.status}")
    if pallet.current_location_id is None:
        raise bad_request("available pallet must have a current location")
    already_reserved = db.scalar(select(ShipmentPallet.id).where(ShipmentPallet.pallet_id == pallet.id))
    if already_reserved:
        raise bad_request("pallet already belongs to a shipment")
    first_shipment_pallet = db.scalar(
        select(Pallet)
        .join(ShipmentPallet, ShipmentPallet.pallet_id == Pallet.id)
        .where(ShipmentPallet.shipment_id == shipment.id)
        .limit(1)
    )
    if first_shipment_pallet is not None:
        first_location = db.get(Location, first_shipment_pallet.current_location_id)
        pallet_location = db.get(Location, pallet.current_location_id)
        if (
            first_location is None
            or pallet_location is None
            or first_location.warehouse_id != pallet_location.warehouse_id
        ):
            raise bad_request("shipment pallets must belong to one warehouse")

    before = {"pallet_status": pallet.status, "shipment_status": shipment.status}
    pallet.status = PalletStatus.RESERVED
    shipment.status = ShipmentStatus.RESERVED
    db.add(ShipmentPallet(shipment_id=shipment.id, pallet_id=pallet.id, status="reserved"))
    create_event(
        db,
        operation="shipment_pallet_reserved",
        object_type="shipment",
        object_uid=shipment.shipment_uid,
        actor=actor,
        before=before,
        after={"pallet_uid": pallet.pallet_uid, "shipment_status": shipment.status},
    )
    create_event(
        db,
        operation="pallet_reserved_for_shipment",
        object_type="pallet",
        object_uid=pallet.pallet_uid,
        actor=actor,
        before={"status": before["pallet_status"]},
        after={"status": pallet.status, "shipment_uid": shipment.shipment_uid},
    )
    commit_or_409(db, "pallet already belongs to a shipment")
    db.refresh(shipment)
    return shipment


def move_shipment_to_expedition(db: Session, *, shipment_uid: str, actor: str = "system") -> Shipment:
    shipment = get_shipment(db, shipment_uid)
    if shipment.status != ShipmentStatus.RESERVED:
        raise bad_request("only reserved shipment can be moved to expedition")
    links = list(db.scalars(select(ShipmentPallet).where(ShipmentPallet.shipment_id == shipment.id)))
    if not links:
        raise bad_request("shipment has no reserved pallets")
    now = utcnow()
    for link in links:
        pallet = db.get(Pallet, link.pallet_id)
        if not pallet or pallet.status != PalletStatus.RESERVED:
            raise bad_request("all shipment pallets must be reserved")
        pallet.status = PalletStatus.EXPEDITION
        link.status = "expedition"
        link.moved_to_expedition_at = now
        create_event(
            db,
            operation="pallet_moved_to_expedition",
            object_type="pallet",
            object_uid=pallet.pallet_uid,
            actor=actor,
            after={"shipment_uid": shipment.shipment_uid, "status": pallet.status},
        )
    before = {"status": shipment.status}
    shipment.status = ShipmentStatus.EXPEDITION
    create_event(
        db,
        operation="shipment_moved_to_expedition",
        object_type="shipment",
        object_uid=shipment.shipment_uid,
        actor=actor,
        before=before,
        after={"status": shipment.status, "pallet_count": len(links)},
    )
    db.commit()
    db.refresh(shipment)
    return shipment


def load_shipment_pallet(
    db: Session,
    *,
    shipment_uid: str,
    pallet_uid: str,
    actor: str = "system",
) -> Shipment:
    shipment = get_shipment(db, shipment_uid)
    if shipment.status not in {ShipmentStatus.EXPEDITION, ShipmentStatus.LOADING}:
        raise bad_request("shipment must be in expedition or loading status")
    pallet = db.scalar(select(Pallet).where(Pallet.pallet_uid == pallet_uid))
    if pallet is None:
        raise not_found("pallet")
    link = db.scalar(
        select(ShipmentPallet).where(ShipmentPallet.shipment_id == shipment.id, ShipmentPallet.pallet_id == pallet.id)
    )
    if link is None:
        raise bad_request("pallet does not belong to this shipment")
    if link.status == "loaded":
        raise bad_request("pallet already loaded")
    if pallet.status != PalletStatus.EXPEDITION:
        raise bad_request(f"pallet cannot be loaded from status {pallet.status}")

    before = {"shipment_status": shipment.status, "pallet_status": pallet.status}
    shipment.status = ShipmentStatus.LOADING
    pallet.status = PalletStatus.LOADED
    link.status = "loaded"
    link.loaded_at = utcnow()
    create_event(
        db,
        operation="shipment_pallet_loaded",
        object_type="shipment",
        object_uid=shipment.shipment_uid,
        actor=actor,
        before=before,
        after={"pallet_uid": pallet.pallet_uid, "shipment_status": shipment.status},
    )
    create_event(
        db,
        operation="pallet_loaded",
        object_type="pallet",
        object_uid=pallet.pallet_uid,
        actor=actor,
        before={"status": before["pallet_status"]},
        after={"status": pallet.status, "shipment_uid": shipment.shipment_uid},
    )
    db.commit()
    db.refresh(shipment)
    return shipment


def close_shipment(db: Session, *, shipment_uid: str, actor: str = "system", reason: str | None = None) -> Shipment:
    shipment = get_shipment(db, shipment_uid)
    if shipment.status != ShipmentStatus.LOADING:
        raise bad_request("shipment can be closed only after loading has started")
    links = list(db.scalars(select(ShipmentPallet).where(ShipmentPallet.shipment_id == shipment.id)))
    if not links:
        raise bad_request("shipment has no pallets")
    not_loaded = [link for link in links if link.status != "loaded"]
    if not_loaded:
        raise bad_request("all shipment pallets must be loaded before close")

    before = {"status": shipment.status}
    shipment.status = ShipmentStatus.COMPLETED
    shipment.closed_at = utcnow()
    for link in links:
        pallet = db.get(Pallet, link.pallet_id)
        if pallet:
            previous_location_id = pallet.current_location_id
            previous_location_code = None
            if previous_location_id:
                previous_location_code = db.scalar(select(Location.code).where(Location.id == previous_location_id))
            pallet.status = PalletStatus.SHIPPED
            pallet.current_location_id = None
            db.query(Box).filter(Box.current_pallet_id == pallet.id).update({"status": BoxStatus.SHIPPED})
            create_event(
                db,
                operation="pallet_shipped",
                object_type="pallet",
                object_uid=pallet.pallet_uid,
                actor=actor,
                reason=reason,
                before={"location_id": previous_location_id, "location_code": previous_location_code},
                after={"shipment_uid": shipment.shipment_uid, "status": pallet.status, "location_id": None},
            )
    create_event(
        db,
        operation="shipment_closed",
        object_type="shipment",
        object_uid=shipment.shipment_uid,
        actor=actor,
        reason=reason,
        before=before,
        after={"status": shipment.status, "pallet_count": len(links)},
    )
    db.commit()
    db.refresh(shipment)
    return shipment


def start_inventory(db: Session, payload: InventoryStartRequest) -> InventorySession:
    warehouse = None
    initial_location = None
    if payload.warehouse_code:
        warehouse = db.scalar(select(Warehouse).where(Warehouse.code == payload.warehouse_code))
        if warehouse is None:
            raise not_found("warehouse")
    if payload.location_code:
        initial_location = db.scalar(select(Location).where(Location.code == payload.location_code))
        if initial_location is None:
            raise not_found("location")
        if initial_location.kind != LocationKind.STORAGE:
            raise bad_request("only storage locations are included in this inventory")
        warehouse = db.get(Warehouse, initial_location.warehouse_id)
    if warehouse is None:
        warehouse = db.scalar(select(Warehouse).order_by(Warehouse.code))
    if warehouse is None:
        raise not_found("warehouse")
    existing_open = db.scalar(
        select(InventorySession.id).where(
            InventorySession.warehouse_id == warehouse.id,
            InventorySession.status == InventoryStatus.OPEN,
        )
    )
    if existing_open:
        raise bad_request("warehouse already has open inventory")

    inventory = InventorySession(
        inventory_uid=generate_inventory_uid(db),
        warehouse_id=warehouse.id,
        location_id=initial_location.id if initial_location else None,
        current_location_id=initial_location.id if initial_location else None,
        actor=payload.actor,
    )
    db.add(inventory)
    db.flush()
    expected_stmt = select(Pallet).join(Location, Pallet.current_location_id == Location.id).where(
        Location.warehouse_id == warehouse.id,
        Location.kind == LocationKind.STORAGE,
        Location.is_active.is_(True),
    )
    if initial_location:
        expected_stmt = expected_stmt.where(Pallet.current_location_id == initial_location.id)
    expected_pallets = list(db.scalars(expected_stmt))
    for pallet in expected_pallets:
        db.add(
            InventoryLine(
                inventory_id=inventory.id,
                pallet_id=pallet.id,
                expected_location_id=pallet.current_location_id,
                status=InventoryLineStatus.EXPECTED,
            )
        )
    create_event(
        db,
        operation="inventory_started",
        object_type="inventory",
        object_uid=inventory.inventory_uid,
        actor=payload.actor,
        after={
            "warehouse_code": warehouse.code,
            "location_code": initial_location.code if initial_location else None,
            "expected_count": len(expected_pallets),
        },
    )
    db.commit()
    db.refresh(inventory)
    return inventory


def get_inventory(db: Session, inventory_uid: str) -> InventorySession:
    inventory = db.scalar(select(InventorySession).where(InventorySession.inventory_uid == inventory_uid))
    if inventory is None:
        raise not_found("inventory")
    return inventory


def inventory_scope_locations(db: Session, inventory: InventorySession) -> list[Location]:
    warehouse_id = inventory.warehouse_id
    if warehouse_id is None and inventory.location_id:
        warehouse_id = db.scalar(select(Location.warehouse_id).where(Location.id == inventory.location_id))
    if warehouse_id is None:
        return []
    stmt = select(Location).where(
        Location.warehouse_id == warehouse_id,
        Location.kind == LocationKind.STORAGE,
        Location.is_active.is_(True),
    )
    start_event = db.scalar(
        select(OperationEvent)
        .where(
            OperationEvent.object_type == "inventory",
            OperationEvent.object_uid == inventory.inventory_uid,
            OperationEvent.operation == "inventory_started",
        )
        .order_by(OperationEvent.created_at)
    )
    initial_location_code = (start_event.after or {}).get("location_code") if start_event else None
    if initial_location_code:
        stmt = stmt.where(Location.code == initial_location_code)
    return list(db.scalars(stmt.order_by(Location.code)))


def confirmed_inventory_location_codes(db: Session, inventory: InventorySession) -> set[str]:
    events = db.scalars(
        select(OperationEvent).where(
            OperationEvent.object_type == "inventory",
            OperationEvent.object_uid == inventory.inventory_uid,
            OperationEvent.operation == "inventory_location_confirmed",
        )
    )
    confirmed = set()
    for event in events:
        event_after = event.after or {}
        code = event_after.get("location_code")
        if code:
            confirmed.add(code)
    return confirmed


def unchecked_inventory_locations(db: Session, inventory: InventorySession) -> list[Location]:
    lines = list(db.scalars(select(InventoryLine).where(InventoryLine.inventory_id == inventory.id)))
    confirmed_codes = confirmed_inventory_location_codes(db, inventory)
    unchecked = []
    for location in inventory_scope_locations(db, inventory):
        expected = [line for line in lines if line.expected_location_id == location.id]
        actual = [line for line in lines if line.actual_location_id == location.id]
        checked = (
            location.code in confirmed_codes
            or bool(actual)
            or any(line.status in {InventoryLineStatus.SCANNED, InventoryLineStatus.MISSING} for line in expected)
        )
        if not checked:
            unchecked.append(location)
    return unchecked


def resolved_inventory_line_ids(db: Session, inventory: InventorySession) -> set[int]:
    events = db.scalars(
        select(OperationEvent).where(
            OperationEvent.object_type == "inventory",
            OperationEvent.object_uid == inventory.inventory_uid,
            OperationEvent.operation == "inventory_discrepancy_resolved",
        )
    )
    resolved = set()
    for event in events:
        event_after = event.after or {}
        line_id = event_after.get("line_id")
        if line_id:
            resolved.add(int(line_id))
    return resolved


def inventory_line_resolution_event(db: Session, inventory: InventorySession, line: InventoryLine) -> OperationEvent | None:
    events = db.scalars(
        select(OperationEvent)
        .where(
            OperationEvent.object_type == "inventory",
            OperationEvent.object_uid == inventory.inventory_uid,
            OperationEvent.operation == "inventory_discrepancy_resolved",
        )
        .order_by(OperationEvent.created_at.desc())
    )
    for event in events:
        event_after = event.after or {}
        if event_after.get("line_id") == line.id:
            return event
    return None


def scan_inventory_location(
    db: Session,
    *,
    inventory_uid: str,
    location_code: str,
    actor: str = "system",
) -> InventorySession:
    inventory = get_inventory(db, inventory_uid)
    if inventory.status != InventoryStatus.OPEN:
        raise bad_request("inventory is already completed")
    location = db.scalar(select(Location).where(Location.code == location_code))
    if location is None:
        raise not_found("location")
    if location.kind != LocationKind.STORAGE:
        raise bad_request("only storage locations are included in this inventory")
    if inventory.warehouse_id and location.warehouse_id != inventory.warehouse_id:
        raise bad_request("location belongs to another warehouse")
    inventory.current_location_id = location.id
    existing_expected_ids = set(
        db.scalars(
            select(InventoryLine.pallet_id).where(
                InventoryLine.inventory_id == inventory.id,
                InventoryLine.expected_location_id == location.id,
            )
        )
    )
    expected_pallets = list(db.scalars(select(Pallet).where(Pallet.current_location_id == location.id)))
    for pallet in expected_pallets:
        if pallet.id not in existing_expected_ids:
            db.add(
                InventoryLine(
                    inventory_id=inventory.id,
                    pallet_id=pallet.id,
                    expected_location_id=location.id,
                    status=InventoryLineStatus.EXPECTED,
                )
            )
    create_event(
        db,
        operation="inventory_location_scanned",
        object_type="inventory",
        object_uid=inventory.inventory_uid,
        actor=actor,
        after={"location_code": location.code, "expected_count": len(expected_pallets)},
    )
    db.commit()
    db.refresh(inventory)
    return inventory


def confirm_inventory_location(
    db: Session,
    *,
    inventory_uid: str,
    location_code: str | None = None,
    actor: str = "system",
) -> InventorySession:
    inventory = get_inventory(db, inventory_uid)
    if inventory.status != InventoryStatus.OPEN:
        raise bad_request("inventory is already completed")
    location = None
    if location_code:
        location = db.scalar(select(Location).where(Location.code == location_code))
        if location is None:
            raise not_found("location")
        if location.kind != LocationKind.STORAGE:
            raise bad_request("only storage locations are included in this inventory")
        if inventory.warehouse_id and location.warehouse_id != inventory.warehouse_id:
            raise bad_request("location belongs to another warehouse")
        inventory.current_location_id = location.id
    elif inventory.current_location_id:
        location = db.get(Location, inventory.current_location_id)
    if location is None:
        raise bad_request("scan location first")

    now = utcnow()
    missing_lines = list(
        db.scalars(
            select(InventoryLine).where(
                InventoryLine.inventory_id == inventory.id,
                InventoryLine.expected_location_id == location.id,
                InventoryLine.status == InventoryLineStatus.EXPECTED,
                InventoryLine.scanned_at.is_(None),
            )
        )
    )
    for line in missing_lines:
        line.status = InventoryLineStatus.MISSING
        line.scanned_at = now
    create_event(
        db,
        operation="inventory_location_confirmed",
        object_type="inventory",
        object_uid=inventory.inventory_uid,
        actor=actor,
        after={"location_code": location.code, "missing_count": len(missing_lines)},
    )
    inventory.current_location_id = None
    db.commit()
    db.refresh(inventory)
    return inventory


def scan_inventory_pallet(
    db: Session,
    *,
    inventory_uid: str,
    pallet_uid: str,
    actor: str = "system",
) -> InventorySession:
    inventory = get_inventory(db, inventory_uid)
    if inventory.status != InventoryStatus.OPEN:
        raise bad_request("inventory is already completed")
    if inventory.current_location_id is None:
        raise bad_request("scan location first")
    pallet = db.scalar(select(Pallet).where(Pallet.pallet_uid == pallet_uid))
    if pallet is None:
        raise not_found("pallet")
    line = db.scalar(select(InventoryLine).where(InventoryLine.inventory_id == inventory.id, InventoryLine.pallet_id == pallet.id))
    if line is None:
        line = InventoryLine(
            inventory_id=inventory.id,
            pallet_id=pallet.id,
            expected_location_id=pallet.current_location_id,
        )
        db.add(line)
    if line.scanned_at:
        raise bad_request("pallet already scanned in this inventory")
    line.actual_location_id = inventory.current_location_id
    line.scanned_at = utcnow()
    if line.expected_location_id == inventory.current_location_id:
        line.status = InventoryLineStatus.SCANNED
    elif line.expected_location_id is None:
        line.status = InventoryLineStatus.EXTRA
    else:
        line.status = InventoryLineStatus.WRONG_LOCATION
    create_event(
        db,
        operation="inventory_pallet_scanned",
        object_type="inventory",
        object_uid=inventory.inventory_uid,
        actor=actor,
        after={"pallet_uid": pallet.pallet_uid, "status": line.status, "location_id": inventory.current_location_id},
    )
    inventory.current_location_id = None
    db.commit()
    db.refresh(inventory)
    return inventory


def inventory_problem_line_by_pallet(db: Session, inventory: InventorySession, pallet_uid: str) -> tuple[InventoryLine, Pallet]:
    pallet = db.scalar(select(Pallet).where(Pallet.pallet_uid == pallet_uid))
    if pallet is None:
        raise not_found("pallet")
    line = db.scalar(
        select(InventoryLine).where(
            InventoryLine.inventory_id == inventory.id,
            InventoryLine.pallet_id == pallet.id,
            InventoryLine.status.in_(
                {
                    InventoryLineStatus.MISSING,
                    InventoryLineStatus.EXTRA,
                    InventoryLineStatus.WRONG_LOCATION,
                }
            ),
        )
    )
    if line is None:
        raise bad_request("inventory discrepancy line not found")
    if inventory_line_resolution_event(db, inventory, line):
        raise bad_request("inventory discrepancy is already resolved")
    return line, pallet


def ensure_location_capacity_for_resolution(db: Session, pallet: Pallet, location: Location) -> None:
    occupied = (
        db.scalar(
            select(func.count(Pallet.id)).where(
                Pallet.current_location_id == location.id,
                Pallet.id != pallet.id,
            )
        )
        or 0
    )
    if occupied >= location.capacity_pallets:
        raise bad_request("location capacity is already reached")


def create_inventory_resolution_events(
    db: Session,
    *,
    inventory: InventorySession,
    line: InventoryLine,
    pallet: Pallet,
    action: str,
    actor: str,
    reason: str | None,
    before: dict | None = None,
    after: dict | None = None,
) -> None:
    expected_location = db.get(Location, line.expected_location_id) if line.expected_location_id else None
    actual_location = db.get(Location, line.actual_location_id) if line.actual_location_id else None
    payload = {
        "line_id": line.id,
        "pallet_id": pallet.id,
        "pallet_uid": pallet.pallet_uid,
        "line_status": line.status,
        "action": action,
        "expected_location_code": expected_location.code if expected_location else None,
        "actual_location_code": actual_location.code if actual_location else None,
    }
    if after:
        payload.update(after)
    create_event(
        db,
        operation="inventory_discrepancy_resolved",
        object_type="inventory",
        object_uid=inventory.inventory_uid,
        actor=actor,
        reason=reason,
        before=before,
        after=payload,
    )
    create_event(
        db,
        operation=f"pallet_inventory_{action}",
        object_type="pallet",
        object_uid=pallet.pallet_uid,
        actor=actor,
        reason=reason,
        before=before,
        after={
            "inventory_uid": inventory.inventory_uid,
            "line_id": line.id,
            "line_status": line.status,
            **(after or {}),
        },
    )


def confirm_inventory_missing(
    db: Session,
    *,
    inventory_uid: str,
    pallet_uid: str,
    actor: str = "system",
    reason: str | None = None,
) -> InventoryLine:
    inventory = get_inventory(db, inventory_uid)
    line, pallet = inventory_problem_line_by_pallet(db, inventory, pallet_uid)
    if line.status != InventoryLineStatus.MISSING:
        raise bad_request("only missing discrepancy can be confirmed as shortage")
    create_inventory_resolution_events(
        db,
        inventory=inventory,
        line=line,
        pallet=pallet,
        action="missing_confirmed",
        actor=actor,
        reason=reason,
        before={"pallet_status": pallet.status, "location_id": pallet.current_location_id},
    )
    db.commit()
    db.refresh(line)
    return line


def place_inventory_found_pallet(
    db: Session,
    *,
    inventory_uid: str,
    pallet_uid: str,
    actor: str = "system",
    reason: str | None = None,
) -> InventoryLine:
    inventory = get_inventory(db, inventory_uid)
    line, pallet = inventory_problem_line_by_pallet(db, inventory, pallet_uid)
    if line.status != InventoryLineStatus.EXTRA:
        raise bad_request("only extra pallet can be placed as found")
    if line.actual_location_id is None:
        raise bad_request("actual location is missing")
    if pallet.status in {
        PalletStatus.RESERVED,
        PalletStatus.EXPEDITION,
        PalletStatus.LOADED,
        PalletStatus.IN_TRANSIT,
        PalletStatus.SHIPPED,
        PalletStatus.WRITTEN_OFF,
        PalletStatus.DISASSEMBLED,
    }:
        raise bad_request(f"pallet cannot be placed from status {pallet.status}")
    location = db.get(Location, line.actual_location_id)
    if location is None:
        raise not_found("location")
    ensure_location_capacity_for_resolution(db, pallet, location)
    before = {"status": pallet.status, "location_id": pallet.current_location_id}
    pallet.current_location_id = location.id
    if pallet.status in {PalletStatus.CLOSED, PalletStatus.WAITING_PLACEMENT}:
        pallet.status = PalletStatus.AVAILABLE
    create_inventory_resolution_events(
        db,
        inventory=inventory,
        line=line,
        pallet=pallet,
        action="found_placed",
        actor=actor,
        reason=reason,
        before=before,
        after={"status": pallet.status, "location_code": location.code},
    )
    db.commit()
    db.refresh(line)
    return line


def move_inventory_pallet_to_actual(
    db: Session,
    *,
    inventory_uid: str,
    pallet_uid: str,
    actor: str = "system",
    reason: str | None = None,
) -> InventoryLine:
    inventory = get_inventory(db, inventory_uid)
    line, pallet = inventory_problem_line_by_pallet(db, inventory, pallet_uid)
    if line.status != InventoryLineStatus.WRONG_LOCATION:
        raise bad_request("only wrong-location discrepancy can be moved to actual location")
    if line.actual_location_id is None:
        raise bad_request("actual location is missing")
    if pallet.status in {
        PalletStatus.RESERVED,
        PalletStatus.EXPEDITION,
        PalletStatus.LOADED,
        PalletStatus.IN_TRANSIT,
        PalletStatus.SHIPPED,
        PalletStatus.WRITTEN_OFF,
        PalletStatus.DISASSEMBLED,
    }:
        raise bad_request(f"pallet cannot be moved from status {pallet.status}")
    location = db.get(Location, line.actual_location_id)
    if location is None:
        raise not_found("location")
    ensure_location_capacity_for_resolution(db, pallet, location)
    before = {"status": pallet.status, "location_id": pallet.current_location_id}
    pallet.current_location_id = location.id
    create_inventory_resolution_events(
        db,
        inventory=inventory,
        line=line,
        pallet=pallet,
        action="moved_to_actual",
        actor=actor,
        reason=reason,
        before=before,
        after={"status": pallet.status, "location_code": location.code},
    )
    db.commit()
    db.refresh(line)
    return line


def complete_inventory(db: Session, *, inventory_uid: str, actor: str = "system") -> InventorySession:
    inventory = get_inventory(db, inventory_uid)
    if inventory.status != InventoryStatus.OPEN:
        raise bad_request("inventory is already completed")
    unchecked_locations = unchecked_inventory_locations(db, inventory)
    if unchecked_locations:
        preview = ", ".join(location.code for location in unchecked_locations[:5])
        suffix = "" if len(unchecked_locations) <= 5 else f" and {len(unchecked_locations) - 5} more"
        raise bad_request(f"inventory has unchecked locations: {preview}{suffix}")
    lines = list(db.scalars(select(InventoryLine).where(InventoryLine.inventory_id == inventory.id)))
    for line in lines:
        if line.status == InventoryLineStatus.EXPECTED and line.scanned_at is None:
            line.status = InventoryLineStatus.MISSING
    inventory.status = InventoryStatus.COMPLETED
    inventory.completed_at = utcnow()
    create_event(
        db,
        operation="inventory_completed",
        object_type="inventory",
        object_uid=inventory.inventory_uid,
        actor=actor,
        after={"line_count": len(lines)},
    )
    db.commit()
    db.refresh(inventory)
    return inventory
