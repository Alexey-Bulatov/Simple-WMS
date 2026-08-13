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
    DEFAULT_AISLE_CODE,
    DEFAULT_CITY,
    DEFAULT_LEVEL_CODE,
    DEFAULT_RACK_CODE,
    DEFAULT_SECTION_CODE,
    DEFAULT_UNIT,
    PALLET_CODE_PREFIX,
    RECEIVING_LOCATION_SUFFIX,
    RECEIVING_ZONE_CODE,
    RECEIVING_ZONE_NAME,
    STORAGE_POSITION_PATTERN,
    STORAGE_ZONE_CODE,
    STORAGE_ZONE_NAME,
)
from app.models.entities import (
    Aisle,
    Batch,
    EquipmentProfile,
    LogisticUnit,
    LogisticUnitContent,
    LogisticUnitType,
    LogisticUnitTypeAllowedChild,
    Location,
    OperationEvent,
    Product,
    ProductPackaging,
    Rack,
    RackLevel,
    RackSection,
    StockDocument,
    StockOwner,
    StockRecipient,
    UnitOfMeasure,
    User,
    Warehouse,
    Zone,
    utcnow,
)
from app.models.enums import (
    LocationKind,
    LogisticUnitStatus,
    MeasurementDimension,
)
from app.schemas import (
    AisleCreate,
    BatchCreate,
    DemoCatalogRequest,
    EquipmentProfileCreate,
    EquipmentProfileUpdate,
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
    ProductPackagingCreate,
    RackCreate,
    RackLevelCreate,
    RackSectionCreate,
    StockDocumentPost,
    StockMovementPost,
    StockOwnerCreate,
    StockRecipientCreate,
    StockRecipientUpdate,
    UserCreate,
    UnitOfMeasureCreate,
    WarehouseCreate,
    WarehouseUpdate,
    ZoneCreate,
)
from app.stock import (
    DEFAULT_STOCK_OWNER_CODE,
    assign_logistic_unit_tree_warehouse,
    convert_product_quantity_to_base,
    effective_logistic_unit_holder,
    ensure_default_stock_owner,
)
from app.stock_ledger import post_stock_document


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


def conflict(message: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=message)


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
    owner = db.scalar(select(StockOwner).where(StockOwner.code == DEFAULT_STOCK_OWNER_CODE))
    if owner is None:
        ensure_default_stock_owner(db)
        changed = True
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
    _, effective_location = effective_logistic_unit_holder(db, item)
    warehouse_id = (
        effective_location.warehouse_id
        if effective_location is not None
        else item.warehouse_id
    )
    warehouse = db.get(Warehouse, warehouse_id) if warehouse_id is not None else None
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
        "warehouse_id": warehouse.id if warehouse else None,
        "warehouse_code": warehouse.code if warehouse else None,
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
    if payload.warehouse_id is not None and db.get(Warehouse, payload.warehouse_id) is None:
        raise not_found("warehouse")
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
        warehouse_id=payload.warehouse_id,
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
    if item.warehouse_id is not None and item.warehouse_id != location.warehouse_id:
        raise bad_request("logistic unit belongs to another receiving warehouse")
    if logistic_location_occupied_count(db, location.id) >= location.capacity_units:
        raise bad_request("location capacity is already reached")
    item.current_location_id = location.id
    assign_logistic_unit_tree_warehouse(db, item, location.warehouse_id)
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
    from app.logistic_tasks import sync_logistic_unit_tasks

    sync_logistic_unit_tasks(db, item, actor=payload.actor)
    db.commit()
    db.refresh(item)
    return item


def require_open_logistic_unit(item: LogisticUnit) -> None:
    if item.status != LogisticUnitStatus.OPEN:
        raise bad_request("logistic unit must be open for composition changes")


def _content_idempotency_key(value: str | None) -> str:
    if value is None:
        return f"content:{uuid4().hex}"
    normalized = value.strip()
    if not normalized:
        raise bad_request("idempotency key must not be blank")
    return normalized


def _existing_content_document(
    db: Session,
    idempotency_key: str | None,
) -> StockDocument | None:
    if idempotency_key is None:
        return None
    return db.scalar(
        select(StockDocument).where(
            StockDocument.idempotency_key == _content_idempotency_key(idempotency_key)
        )
    )


def _validate_existing_content_addition(
    document: StockDocument,
    item: LogisticUnit,
    payload: LogisticUnitContentCreate,
) -> None:
    movement = document.movements[0] if len(document.movements) == 1 else None
    if not (
        document.document_type == "logistic_unit_content_add"
        and document.reference_type == "logistic_unit"
        and document.reference_uid == item.uid
        and document.actor == payload.actor.strip()
        and movement is not None
        and movement.product_id == payload.product_id
        and movement.batch_id == payload.batch_id
        and movement.input_quantity == payload.quantity
        and movement.input_uom_id == payload.uom_id
        and movement.destination_logistic_unit_id == item.id
        and movement.source_logistic_unit_id is None
        and movement.source_location_id is None
    ):
        raise conflict("idempotency key belongs to another content command")


def _validate_existing_content_removal(
    document: StockDocument,
    item: LogisticUnit,
    content_id: int,
    payload: LogisticUnitContentRemoveRequest,
) -> None:
    movement = document.movements[0] if len(document.movements) == 1 else None
    reason = payload.reason.strip() if payload.reason else None
    reason = reason or None
    if not (
        document.document_type == "logistic_unit_content_remove"
        and document.reference_type == "logistic_unit"
        and document.reference_uid == item.uid
        and document.actor == payload.actor.strip()
        and document.reason == reason
        and (document.attributes or {}).get("content_id") == content_id
        and movement is not None
        and movement.input_quantity == payload.quantity
        and movement.source_logistic_unit_id == item.id
        and movement.destination_logistic_unit_id is None
        and movement.destination_location_id is None
    ):
        raise conflict("idempotency key belongs to another content command")


def add_logistic_unit_content(
    db: Session,
    uid: str,
    payload: LogisticUnitContentCreate,
) -> LogisticUnit:
    item = get_logistic_unit(db, uid)
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
    stored_quantity = payload.quantity
    stored_uom = uom
    conversion_factor = Decimal("1")
    if product.base_uom_id is not None:
        stored_quantity, stored_uom = convert_product_quantity_to_base(
            db,
            product,
            payload.quantity,
            uom,
        )
        conversion_factor = stored_quantity / payload.quantity
    owner = ensure_default_stock_owner(db)
    idempotency_key = _content_idempotency_key(payload.idempotency_key)
    existing = _existing_content_document(db, payload.idempotency_key)
    if existing is not None:
        _validate_existing_content_addition(existing, item, payload)
        return item

    require_open_logistic_unit(item)
    unit_type = db.get(LogisticUnitType, item.type_id)
    if unit_type is None or not unit_type.can_contain_goods:
        raise bad_request("logistic unit type cannot contain goods directly")
    quality_status = batch.quality_status if batch is not None else "released"
    command = StockDocumentPost(
        document_type="logistic_unit_content_add",
        reference_type="logistic_unit",
        reference_uid=item.uid,
        idempotency_key=idempotency_key,
        actor=payload.actor,
        attributes={"operation": "content_add", "logistic_unit_uid": item.uid},
        movements=[
            StockMovementPost(
                product_id=product.id,
                batch_id=batch.id if batch else None,
                owner_id=owner.id,
                destination_quality_status=quality_status,
                input_quantity=payload.quantity,
                input_uom_id=uom.id,
                destination_logistic_unit_id=item.id,
            )
        ],
    )

    def update_content_projection(document: StockDocument) -> None:
        line_query = select(LogisticUnitContent).where(
            LogisticUnitContent.logistic_unit_id == item.id,
            LogisticUnitContent.product_id == product.id,
            LogisticUnitContent.uom_id == stored_uom.id,
        )
        if batch is None:
            line_query = line_query.where(LogisticUnitContent.batch_id.is_(None))
        else:
            line_query = line_query.where(LogisticUnitContent.batch_id == batch.id)
        line = db.scalar(line_query.execution_options(populate_existing=True).with_for_update())
        before_quantity = line.quantity if line else Decimal("0")
        if line is None:
            line = LogisticUnitContent(
                logistic_unit_id=item.id,
                product_id=product.id,
                batch_id=batch.id if batch else None,
                quantity=stored_quantity,
                uom_id=stored_uom.id,
            )
            db.add(line)
        else:
            line.quantity += stored_quantity
        db.flush()
        document.attributes = {**document.attributes, "content_id": line.id}
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
                "quantity": str(before_quantity + stored_quantity),
                "uom_code": stored_uom.code,
                "source_quantity": str(payload.quantity),
                "source_uom_code": uom.code,
                "conversion_factor": str(conversion_factor),
            },
        )

    post_stock_document(db, command, before_commit=update_content_projection)
    db.refresh(item)
    return item


def remove_logistic_unit_content(
    db: Session,
    uid: str,
    content_id: int,
    payload: LogisticUnitContentRemoveRequest,
) -> LogisticUnit:
    item = get_logistic_unit(db, uid)
    existing = _existing_content_document(db, payload.idempotency_key)
    if existing is not None:
        _validate_existing_content_removal(existing, item, content_id, payload)
        return item
    require_open_logistic_unit(item)
    line_snapshot = db.get(LogisticUnitContent, content_id)
    if line_snapshot is None or line_snapshot.logistic_unit_id != item.id:
        raise not_found("logistic_unit_content")
    product = db.scalar(
        select(Product).where(Product.id == line_snapshot.product_id).with_for_update()
    )
    if product is None:
        raise not_found("product")
    line = db.scalar(
        select(LogisticUnitContent)
        .where(LogisticUnitContent.id == content_id)
        .execution_options(populate_existing=True)
        .with_for_update()
    )
    if line is None or line.logistic_unit_id != item.id:
        raise not_found("logistic_unit_content")
    if payload.quantity > line.quantity:
        raise bad_request("removed quantity exceeds the content line quantity")
    if line.product_id != product.id:
        raise conflict("logistic unit content changed during removal")
    batch = db.get(Batch, line.batch_id) if line.batch_id is not None else None
    owner = ensure_default_stock_owner(db)
    quality_status = batch.quality_status if batch is not None else "released"
    before_quantity = line.quantity
    remaining = line.quantity - payload.quantity
    command = StockDocumentPost(
        document_type="logistic_unit_content_remove",
        reference_type="logistic_unit",
        reference_uid=item.uid,
        idempotency_key=_content_idempotency_key(payload.idempotency_key),
        actor=payload.actor,
        reason=payload.reason,
        attributes={
            "operation": "content_remove",
            "logistic_unit_uid": item.uid,
            "content_id": content_id,
        },
        movements=[
            StockMovementPost(
                product_id=product.id,
                batch_id=batch.id if batch else None,
                owner_id=owner.id,
                source_quality_status=quality_status,
                input_quantity=payload.quantity,
                input_uom_id=line.uom_id,
                source_logistic_unit_id=item.id,
            )
        ],
    )

    def update_content_projection(_: StockDocument) -> None:
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

    post_stock_document(db, command, before_commit=update_content_projection)
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

    parent_root, parent_location = effective_logistic_unit_holder(db, parent)
    parent_warehouse_id = (
        parent_location.warehouse_id if parent_location else parent_root.warehouse_id
    )
    child_warehouse_id = child.warehouse_id
    if (
        parent_warehouse_id is not None
        and child_warehouse_id is not None
        and parent_warehouse_id != child_warehouse_id
    ):
        raise bad_request("child logistic unit belongs to another warehouse")
    child.parent_unit_id = parent.id
    if parent_warehouse_id is not None:
        assign_logistic_unit_tree_warehouse(db, child, parent_warehouse_id)
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
    from app.logistic_tasks import sync_logistic_unit_tasks

    sync_logistic_unit_tasks(db, item, actor=payload.actor)
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
    from app.logistic_tasks import sync_logistic_unit_tasks

    sync_logistic_unit_tasks(db, item, actor=payload.actor)
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
    from app.logistic_tasks import sync_logistic_unit_tasks

    sync_logistic_unit_tasks(db, item, actor=payload.actor)
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
    from app.logistic_tasks import sync_logistic_unit_tasks

    sync_logistic_unit_tasks(db, item, actor=payload.actor)
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
    if logistic_location_occupied_count(db, location.id) >= location.capacity_units:
        raise bad_request("location capacity is already reached")
    before = {
        "status": item.status.value,
        "location_id": item.current_location_id,
        "location_code": current_location.code if current_location else None,
    }
    item.current_location_id = location.id
    assign_logistic_unit_tree_warehouse(db, item, location.warehouse_id)
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
    from app.logistic_tasks import sync_logistic_unit_tasks

    sync_logistic_unit_tasks(db, item, actor=payload.actor)
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
    if logistic_location_occupied_count(db, location.id) >= location.capacity_units:
        raise bad_request("location capacity is already reached")
    item.current_location_id = location.id
    assign_logistic_unit_tree_warehouse(db, item, location.warehouse_id)
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
    from app.logistic_tasks import sync_logistic_unit_tasks

    sync_logistic_unit_tasks(db, item, actor=payload.actor)
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
    data["code"] = payload.code.strip().upper()
    data["name"] = payload.name.strip()
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
    create_event(
        db,
        operation="product_created",
        object_type="product",
        object_uid=data["code"],
        after={
            "name": data["name"],
            "base_uom_id": data["base_uom_id"],
            "shelf_life_days": data["shelf_life_days"],
            "accountability_period_days": data["accountability_period_days"],
        },
    )
    commit_or_409(db, "product already exists")
    db.refresh(product)
    return product


def create_product_packaging(
    db: Session,
    payload: ProductPackagingCreate,
) -> ProductPackaging:
    product = db.get(Product, payload.product_id)
    if product is None:
        raise not_found("product")
    uom = db.get(UnitOfMeasure, payload.uom_id)
    if uom is None:
        raise not_found("unit_of_measure")
    base_quantity, _ = convert_product_quantity_to_base(
        db,
        product,
        payload.quantity,
        uom,
    )
    code = payload.code.strip().upper()
    barcode = payload.barcode.strip() if payload.barcode else None
    packaging = ProductPackaging(
        product_id=product.id,
        code=code,
        name=payload.name.strip(),
        quantity=payload.quantity,
        uom_id=uom.id,
        base_quantity=base_quantity,
        barcode=barcode,
    )
    db.add(packaging)
    create_event(
        db,
        operation="product_packaging_created",
        object_type="product_packaging",
        object_uid=f"{product.code}:{code}",
        after={
            "product_code": product.code,
            "quantity": str(payload.quantity),
            "uom_code": uom.code,
            "base_quantity": str(base_quantity),
            "barcode": barcode,
        },
    )
    commit_or_409(db, "product packaging code or barcode already exists")
    db.refresh(packaging)
    return packaging


def create_stock_owner(db: Session, payload: StockOwnerCreate) -> StockOwner:
    owner = StockOwner(
        code=payload.code.strip().upper(),
        name=payload.name.strip(),
        is_internal=payload.is_internal,
    )
    db.add(owner)
    create_event(
        db,
        operation="stock_owner_created",
        object_type="stock_owner",
        object_uid=owner.code,
        after={"name": owner.name, "is_internal": owner.is_internal},
    )
    commit_or_409(db, "stock owner code already exists")
    db.refresh(owner)
    return owner


def create_stock_recipient(
    db: Session,
    payload: StockRecipientCreate,
) -> StockRecipient:
    recipient = StockRecipient(**payload.model_dump())
    db.add(recipient)
    create_event(
        db,
        operation="stock_recipient_created",
        object_type="stock_recipient",
        object_uid=recipient.code,
        after={"name": recipient.name, "kind": recipient.kind.value},
    )
    commit_or_409(db, "stock recipient code already exists")
    db.refresh(recipient)
    return recipient


def update_stock_recipient(
    db: Session,
    recipient_id: int,
    payload: StockRecipientUpdate,
) -> StockRecipient:
    recipient = db.get(StockRecipient, recipient_id)
    if recipient is None:
        raise not_found("stock_recipient")
    before = {
        "name": recipient.name,
        "kind": recipient.kind.value,
        "is_active": recipient.is_active,
    }
    recipient.name = payload.name
    recipient.kind = payload.kind
    recipient.is_active = payload.is_active
    create_event(
        db,
        operation="stock_recipient_updated",
        object_type="stock_recipient",
        object_uid=recipient.code,
        before=before,
        after={
            "name": recipient.name,
            "kind": recipient.kind.value,
            "is_active": recipient.is_active,
        },
    )
    db.commit()
    db.refresh(recipient)
    return recipient


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


def seed_batch_dates() -> tuple[date, date]:
    return date(2026, 7, 21), date(2027, 7, 21)


def create_warehouse(db: Session, payload: WarehouseCreate) -> Warehouse:
    data = payload.model_dump()
    data["code"] = payload.code.strip().upper()
    warehouse = Warehouse(**data)
    db.add(warehouse)
    commit_or_409(db, "warehouse already exists")
    db.refresh(warehouse)
    return warehouse


def update_warehouse(db: Session, warehouse_id: int, payload: WarehouseUpdate) -> Warehouse:
    warehouse = db.get(Warehouse, warehouse_id)
    if warehouse is None:
        raise not_found("warehouse")
    warehouse.name = payload.name.strip()
    warehouse.city = payload.city.strip() if payload.city and payload.city.strip() else None
    warehouse.timezone = payload.timezone.strip()
    db.commit()
    db.refresh(warehouse)
    return warehouse


def create_zone(db: Session, payload: ZoneCreate) -> Zone:
    warehouse = db.get(Warehouse, payload.warehouse_id)
    if warehouse is None:
        raise not_found("warehouse")
    data = payload.model_dump()
    data["code"] = payload.code.strip().upper()
    zone = Zone(**data)
    db.add(zone)
    commit_or_409(db, "zone already exists in this warehouse")
    db.refresh(zone)
    return zone


def create_aisle(db: Session, payload: AisleCreate) -> Aisle:
    zone = db.get(Zone, payload.zone_id)
    if zone is None:
        raise not_found("zone")
    data = payload.model_dump()
    data["code"] = payload.code.strip().upper()
    aisle = Aisle(**data)
    db.add(aisle)
    commit_or_409(db, "aisle already exists in this zone")
    db.refresh(aisle)
    return aisle


def create_rack(db: Session, payload: RackCreate) -> Rack:
    aisle = db.get(Aisle, payload.aisle_id)
    if aisle is None:
        raise not_found("aisle")
    data = payload.model_dump()
    data["code"] = payload.code.strip().upper()
    rack = Rack(**data)
    db.add(rack)
    commit_or_409(db, "rack already exists in this aisle")
    db.refresh(rack)
    return rack


def create_rack_section(db: Session, payload: RackSectionCreate) -> RackSection:
    rack = db.get(Rack, payload.rack_id)
    if rack is None:
        raise not_found("rack")
    data = payload.model_dump()
    data["code"] = payload.code.strip().upper()
    section = RackSection(**data)
    db.add(section)
    commit_or_409(db, "section already exists in this rack")
    db.refresh(section)
    return section


def create_rack_level(db: Session, payload: RackLevelCreate) -> RackLevel:
    section = db.get(RackSection, payload.section_id)
    if section is None:
        raise not_found("rack section")
    data = payload.model_dump()
    data["code"] = payload.code.strip().upper()
    level = RackLevel(**data)
    db.add(level)
    commit_or_409(db, "level already exists in this section")
    db.refresh(level)
    return level


def ensure_address_hierarchy(
    db: Session,
    zone: Zone,
    *,
    aisle_code: str,
    rack_code: str,
    section_code: str,
    level_code: str,
) -> tuple[Aisle, Rack, RackSection, RackLevel, dict[str, int]]:
    codes = [value.strip().upper() for value in (aisle_code, rack_code, section_code, level_code)]
    if any(not value for value in codes):
        raise bad_request("address hierarchy codes must not be empty")
    aisle_code, rack_code, section_code, level_code = codes
    created = {"created_aisles": 0, "created_racks": 0, "created_sections": 0, "created_levels": 0}
    aisle = db.scalar(select(Aisle).where(Aisle.zone_id == zone.id, Aisle.code == aisle_code))
    if aisle is None:
        aisle = create_aisle(
            db,
            AisleCreate(zone_id=zone.id, code=aisle_code, name=f"Проход {aisle_code}"),
        )
        created["created_aisles"] += 1
    rack = db.scalar(select(Rack).where(Rack.aisle_id == aisle.id, Rack.code == rack_code))
    if rack is None:
        rack = create_rack(
            db,
            RackCreate(aisle_id=aisle.id, code=rack_code, name=f"Стеллаж {rack_code}"),
        )
        created["created_racks"] += 1
    section = db.scalar(
        select(RackSection).where(RackSection.rack_id == rack.id, RackSection.code == section_code)
    )
    if section is None:
        section = create_rack_section(
            db,
            RackSectionCreate(rack_id=rack.id, code=section_code, name=f"Секция {section_code}"),
        )
        created["created_sections"] += 1
    level = db.scalar(
        select(RackLevel).where(RackLevel.section_id == section.id, RackLevel.code == level_code)
    )
    if level is None:
        level = create_rack_level(
            db,
            RackLevelCreate(section_id=section.id, code=level_code, name=f"Ярус {level_code}"),
        )
        created["created_levels"] += 1
    return aisle, rack, section, level, created


def location_address_payload(location: Location) -> dict:
    return {
        "warehouse": location.zone.warehouse.code,
        "zone": location.zone.code,
        "aisle": location.aisle.code if location.aisle else None,
        "rack": location.rack.code if location.rack else None,
        "section": location.section.code if location.section else None,
        "level": location.level.code if location.level else None,
        "position": location.position_code,
        "structured": location.level_id is not None,
    }


def create_location(db: Session, payload: LocationCreate) -> Location:
    warehouse = db.get(Warehouse, payload.warehouse_id)
    if warehouse is None:
        raise not_found("warehouse")
    zone = db.get(Zone, payload.zone_id)
    if zone is None:
        raise not_found("zone")
    if zone.warehouse_id != warehouse.id:
        raise bad_request("zone belongs to another warehouse")
    data = payload.model_dump()
    if payload.level_id is not None:
        aisle = db.get(Aisle, payload.aisle_id)
        rack = db.get(Rack, payload.rack_id)
        section = db.get(RackSection, payload.section_id)
        level = db.get(RackLevel, payload.level_id)
        if aisle is None or rack is None or section is None or level is None:
            raise not_found("address hierarchy node")
        if aisle.zone_id != zone.id:
            raise bad_request("aisle belongs to another zone")
        if rack.aisle_id != aisle.id:
            raise bad_request("rack belongs to another aisle")
        if section.rack_id != rack.id:
            raise bad_request("section belongs to another rack")
        if level.section_id != section.id:
            raise bad_request("level belongs to another section")
        position_code = payload.position_code.strip().upper()
        canonical_code = CODE_SEPARATOR.join(
            (
                warehouse.code,
                zone.code,
                aisle.code,
                rack.code,
                section.code,
                level.code,
                position_code,
            )
        )
        if payload.code and payload.code.strip().upper() != canonical_code:
            raise bad_request(f"location code must match structured address: {canonical_code}")
        data["position_code"] = position_code
        data["code"] = canonical_code
    else:
        data["code"] = payload.code.strip().upper()
    location = Location(**data)
    db.add(location)
    commit_or_409(db, "location already exists")
    db.refresh(location)
    return location


def ensure_demo_catalog(db: Session, payload: DemoCatalogRequest) -> dict:
    created = {
        "created_products": 0,
        "created_batches": 0,
        "created_warehouses": 0,
        "created_zones": 0,
        "created_aisles": 0,
        "created_racks": 0,
        "created_sections": 0,
        "created_levels": 0,
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

    aisle, rack, section, level, address_created = ensure_address_hierarchy(
        db,
        storage,
        aisle_code=DEFAULT_AISLE_CODE,
        rack_code=DEFAULT_RACK_CODE,
        section_code=DEFAULT_SECTION_CODE,
        level_code=DEFAULT_LEVEL_CODE,
    )
    for key, value in address_created.items():
        created[key] += value

    receiving_code = f"{warehouse.code}{CODE_SEPARATOR}{RECEIVING_ZONE_CODE}{CODE_SEPARATOR}{RECEIVING_LOCATION_SUFFIX}"
    if db.scalar(select(Location.id).where(Location.code == receiving_code)) is None:
        create_location(
            db,
            LocationCreate(
                warehouse_id=warehouse.id,
                zone_id=receiving.id,
                code=receiving_code,
                name="Приемка логистических единиц",
                kind=LocationKind.RECEIVING,
                capacity_units=4,
            ),
        )
        created["created_locations"] += 1

    for idx in range(1, payload.storage_locations + 1):
        position_code = STORAGE_POSITION_PATTERN.format(index=idx)
        code = CODE_SEPARATOR.join(
            (
                warehouse.code,
                storage.code,
                aisle.code,
                rack.code,
                section.code,
                level.code,
                position_code,
            )
        )
        if db.scalar(select(Location.id).where(Location.code == code)) is None:
            create_location(
                db,
                LocationCreate(
                    warehouse_id=warehouse.id,
                    zone_id=storage.id,
                    aisle_id=aisle.id,
                    rack_id=rack.id,
                    section_id=section.id,
                    level_id=level.id,
                    position_code=position_code,
                    code=code,
                    name=f"Место хранения {idx}",
                    kind=LocationKind.STORAGE,
                    capacity_units=1,
                ),
            )
            created["created_locations"] += 1

    demo_products = [
        ("ICE-VAN-100", "Мороженое ванильное 100 г", 365),
        ("ICE-CHO-100", "Мороженое шоколадное 100 г", 365),
        ("ICE-BER-80", "Пломбир ягодный 80 г", 300),
    ]
    production_date, expiry_date = seed_batch_dates()
    for code, name, shelf_life_days in demo_products:
        product = db.scalar(select(Product).where(Product.code == code))
        if product is None:
            product = create_product(
                db,
                ProductCreate(
                    code=code,
                    name=name,
                    unit=DEFAULT_UNIT,
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
