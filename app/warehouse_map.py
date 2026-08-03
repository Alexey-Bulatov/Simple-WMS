from __future__ import annotations

from collections import defaultdict

from fastapi import HTTPException
from sqlalchemy import delete, func, or_, select
from sqlalchemy.orm import Session

from app.models.entities import (
    Aisle,
    LogisticInventory,
    LogisticInventoryLine,
    LogisticInventoryLocation,
    LogisticShipmentUnit,
    LogisticTransferUnit,
    LogisticUnit,
    Location,
    OperationEvent,
    Rack,
    RackLevel,
    RackSection,
    Warehouse,
    WarehouseMapItem,
    Zone,
)
from app.models.enums import LocationKind
from app.schemas import (
    LocationCreate,
    WarehouseMapItemUpdate,
    WarehouseMapLabelCreate,
    WarehouseMapLocationCreate,
    WarehouseMapRowCreate,
)
from app.services import create_location, ensure_address_hierarchy, location_address_payload

CANVAS_WIDTH = 1000
CANVAS_HEIGHT = 600
SANDBOX_WAREHOUSE_CODE = "WH02"
SANDBOX_ZONE_CODE = "ST01"
DEFAULT_MAP_AISLE_CODE = "A01"
DEFAULT_MAP_SECTION_CODE = "S01"
DEFAULT_MAP_LEVEL_CODE = "L01"


def _value(value: object) -> str:
    return str(getattr(value, "value", value))


def _not_found(kind: str, value: str) -> HTTPException:
    return HTTPException(status_code=404, detail=f"{kind} не найден: {value}")


def _warehouse(db: Session, code: str) -> Warehouse:
    warehouse = db.scalar(select(Warehouse).where(Warehouse.code == code.upper()))
    if not warehouse:
        raise _not_found("Склад", code)
    return warehouse


def _zone(db: Session, warehouse: Warehouse, code: str) -> Zone:
    zone = db.scalar(
        select(Zone).where(Zone.warehouse_id == warehouse.id, Zone.code == code.upper())
    )
    if not zone:
        raise _not_found("Зона", code)
    return zone


def _event(
    db: Session,
    *,
    operation: str,
    object_type: str,
    object_uid: str,
    actor: str,
    before: dict | None = None,
    after: dict | None = None,
    reason: str | None = None,
) -> None:
    db.add(
        OperationEvent(
            operation=operation,
            object_type=object_type,
            object_uid=object_uid,
            actor=actor,
            reason=reason,
            before=before,
            after=after,
        )
    )


def _location_reference_reason(db: Session, location: Location) -> str | None:
    if db.scalar(select(LogisticUnit.id).where(LogisticUnit.current_location_id == location.id).limit(1)):
        return "в ячейке находится логистическая единица"
    if db.scalar(
        select(LogisticInventory.id)
        .where(LogisticInventory.current_location_id == location.id)
        .limit(1)
    ):
        return "ячейка участвует в инвентаризации"
    if db.scalar(
        select(LogisticInventoryLocation.id)
        .where(LogisticInventoryLocation.location_id == location.id)
        .limit(1)
    ):
        return "ячейка входит в обход инвентаризации"
    if db.scalar(
        select(LogisticInventoryLine.id)
        .where(
            or_(
                LogisticInventoryLine.expected_location_id == location.id,
                LogisticInventoryLine.actual_location_id == location.id,
            )
        )
        .limit(1)
    ):
        return "ячейка присутствует в строках инвентаризации"
    if db.scalar(
        select(LogisticTransferUnit.id)
        .where(LogisticTransferUnit.source_location_id == location.id)
        .limit(1)
    ):
        return "ячейка присутствует в истории межскладского перемещения"
    if db.scalar(
        select(LogisticShipmentUnit.id)
        .where(LogisticShipmentUnit.source_location_id == location.id)
        .limit(1)
    ):
        return "ячейка присутствует в истории отгрузки"
    return None


def _prune_empty_address_branches(db: Session, locations: list[Location]) -> None:
    level_ids = {location.level_id for location in locations if location.level_id}
    for level_id in level_ids:
        if db.scalar(select(Location.id).where(Location.level_id == level_id).limit(1)):
            continue
        level = db.get(RackLevel, level_id)
        if level is None:
            continue
        section_id = level.section_id
        db.delete(level)
        db.flush()
        if db.scalar(select(RackLevel.id).where(RackLevel.section_id == section_id).limit(1)):
            continue
        section = db.get(RackSection, section_id)
        if section is None:
            continue
        rack_id = section.rack_id
        db.delete(section)
        db.flush()
        if db.scalar(select(RackSection.id).where(RackSection.rack_id == rack_id).limit(1)):
            continue
        rack = db.get(Rack, rack_id)
        if rack is None:
            continue
        aisle_id = rack.aisle_id
        db.delete(rack)
        db.flush()
        if db.scalar(select(Rack.id).where(Rack.aisle_id == aisle_id).limit(1)):
            continue
        aisle = db.get(Aisle, aisle_id)
        if aisle is not None:
            db.delete(aisle)
            db.flush()


def _assert_sandbox(warehouse: Warehouse) -> None:
    if warehouse.code != SANDBOX_WAREHOUSE_CODE:
        raise HTTPException(status_code=409, detail="Редактирование разрешено только на учебном складе WH02")


def _add_item(
    db: Session,
    *,
    warehouse: Warehouse,
    item_type: str,
    item_key: str,
    label: str,
    x: int,
    y: int,
    width: int,
    height: int,
    rotation: int = 0,
    zone: Zone | None = None,
    location: Location | None = None,
    parent: WarehouseMapItem | None = None,
    sort_order: int = 0,
    is_locked: bool = False,
) -> WarehouseMapItem:
    item = WarehouseMapItem(
        warehouse_id=warehouse.id,
        zone_id=zone.id if zone else None,
        location_id=location.id if location else None,
        parent_id=parent.id if parent else None,
        item_type=item_type,
        item_key=item_key,
        label=label,
        x=x,
        y=y,
        width=width,
        height=height,
        rotation=rotation,
        sort_order=sort_order,
        is_locked=is_locked,
    )
    db.add(item)
    db.flush()
    return item


def _layout_rack_children(db: Session, rack: WarehouseMapItem) -> None:
    children = list(
        db.scalars(
            select(WarehouseMapItem)
            .where(WarehouseMapItem.parent_id == rack.id)
            .order_by(WarehouseMapItem.sort_order, WarehouseMapItem.id)
        )
    )
    count = len(children)
    if not count:
        return
    pad = 10
    gap = 8
    if rack.rotation == 90:
        cell_width = 110
        cell_height = 58
        rack.width = cell_width + pad * 2
        rack.height = count * cell_height + (count - 1) * gap + pad * 2
        rack.x = min(rack.x, CANVAS_WIDTH - rack.width)
        rack.y = min(rack.y, CANVAS_HEIGHT - rack.height)
        for index, child in enumerate(children):
            child.x = rack.x + pad
            child.y = rack.y + pad + index * (cell_height + gap)
            child.width = cell_width
            child.height = cell_height
            child.rotation = 90
    else:
        cell_width = 110
        cell_height = 58
        rack.width = count * cell_width + (count - 1) * gap + pad * 2
        rack.height = cell_height + pad * 2
        rack.x = min(rack.x, CANVAS_WIDTH - rack.width)
        rack.y = min(rack.y, CANVAS_HEIGHT - rack.height)
        for index, child in enumerate(children):
            child.x = rack.x + pad + index * (cell_width + gap)
            child.y = rack.y + pad
            child.width = cell_width
            child.height = cell_height
            child.rotation = 0


def _create_row(
    db: Session,
    *,
    warehouse: Warehouse,
    zone: Zone,
    row_code: str,
    label: str,
    location_count: int,
    orientation: str,
    x: int,
    y: int,
    locked: bool,
) -> WarehouseMapItem:
    normalized_row = row_code.strip().upper()
    item_key = f"rack:{zone.code}:{normalized_row}"
    if db.scalar(
        select(WarehouseMapItem.id).where(
            WarehouseMapItem.warehouse_id == warehouse.id,
            WarehouseMapItem.item_key == item_key,
        )
    ):
        raise HTTPException(status_code=409, detail=f"Ряд уже существует: {normalized_row}")
    aisle, address_rack, section, level, _ = ensure_address_hierarchy(
        db,
        zone,
        aisle_code=DEFAULT_MAP_AISLE_CODE,
        rack_code=normalized_row,
        section_code=DEFAULT_MAP_SECTION_CODE,
        level_code=DEFAULT_MAP_LEVEL_CODE,
    )
    codes = [
        "-".join(
            (
                warehouse.code,
                zone.code,
                aisle.code,
                address_rack.code,
                section.code,
                level.code,
                f"P{index:02d}",
            )
        )
        for index in range(1, location_count + 1)
    ]
    existing_code = db.scalar(select(Location.code).where(Location.code.in_(codes)).limit(1))
    if existing_code:
        raise HTTPException(status_code=409, detail=f"Ячейка уже существует: {existing_code}")
    rack = _add_item(
        db,
        warehouse=warehouse,
        zone=zone,
        item_type="rack",
        item_key=item_key,
        label=label,
        x=x,
        y=y,
        width=200,
        height=78,
        rotation=90 if orientation == "vertical" else 0,
        is_locked=locked,
    )
    for index, code in enumerate(codes, start=1):
        location = create_location(
            db,
            LocationCreate(
                warehouse_id=warehouse.id,
                zone_id=zone.id,
                aisle_id=aisle.id,
                rack_id=address_rack.id,
                section_id=section.id,
                level_id=level.id,
                position_code=f"P{index:02d}",
                code=code,
                name=f"{label}, место {index}",
                kind=LocationKind.STORAGE,
                capacity_units=1,
            ),
        )
        _add_item(
            db,
            warehouse=warehouse,
            zone=zone,
            location=location,
            parent=rack,
            item_type="location",
            item_key=f"location:{location.id}",
            label=f"P{index:02d}",
            x=x,
            y=y,
            width=110,
            height=58,
            sort_order=index,
            is_locked=locked,
        )
    _layout_rack_children(db, rack)
    return rack


def _remove_accidental_wh02_location(db: Session) -> None:
    location = db.scalar(select(Location).where(Location.code == SANDBOX_WAREHOUSE_CODE))
    if not location:
        return
    owner_code = db.scalar(select(Warehouse.code).where(Warehouse.id == location.warehouse_id))
    if owner_code == SANDBOX_WAREHOUSE_CODE:
        return
    reason = _location_reference_reason(db, location)
    if reason:
        raise HTTPException(
            status_code=409,
            detail=f"Нельзя создать склад WH02: одноимённая ячейка уже используется ({reason})",
        )
    _event(
        db,
        operation="map_invalid_location_removed",
        object_type="location",
        object_uid=location.code,
        actor="map-setup",
        reason="подготовка учебного склада WH02",
    )
    db.delete(location)
    db.flush()


def _ensure_wh01_layout(db: Session, warehouse: Warehouse) -> None:
    if db.scalar(select(WarehouseMapItem.id).where(WarehouseMapItem.warehouse_id == warehouse.id).limit(1)):
        return
    locations = list(db.scalars(select(Location).where(Location.warehouse_id == warehouse.id).order_by(Location.code)))
    storage = [location for location in locations if _value(location.kind) == "storage"]
    receiving = [location for location in locations if _value(location.kind) == "receiving"]
    for index, location in enumerate(receiving):
        _add_item(
            db,
            warehouse=warehouse,
            zone=db.get(Zone, location.zone_id),
            location=location,
            item_type="location",
            item_key=f"location:{location.id}",
            label="Приемка",
            x=70 + index * 180,
            y=55,
            width=150,
            height=76,
            is_locked=True,
        )
    for row_index, chunk_start in enumerate(range(0, len(storage), 5), start=1):
        chunk = storage[chunk_start : chunk_start + 5]
        rack = _add_item(
            db,
            warehouse=warehouse,
            zone=db.get(Zone, chunk[0].zone_id) if chunk else None,
            item_type="rack",
            item_key=f"rack:demo:{row_index}",
            label=f"Стеллаж {row_index}",
            x=100,
            y=180 + (row_index - 1) * 145,
            width=610,
            height=78,
            is_locked=True,
        )
        for index, location in enumerate(chunk, start=1):
            _add_item(
                db,
                warehouse=warehouse,
                zone=db.get(Zone, location.zone_id),
                location=location,
                parent=rack,
                item_type="location",
                item_key=f"location:{location.id}",
                label=f"P{chunk_start + index:02d}",
                x=0,
                y=0,
                width=110,
                height=58,
                sort_order=index,
                is_locked=True,
            )
        _layout_rack_children(db, rack)
    _add_item(
        db,
        warehouse=warehouse,
        item_type="label",
        item_key="label:storage",
        label="Морозильное хранение",
        x=100,
        y=145,
        width=300,
        height=34,
        is_locked=True,
    )
    _add_item(
        db,
        warehouse=warehouse,
        item_type="aisle",
        item_key="aisle:main",
        label="Главный проход",
        x=100,
        y=280,
        width=610,
        height=52,
        is_locked=True,
    )


def _create_sandbox_defaults(db: Session, warehouse: Warehouse, zone: Zone) -> None:
    _add_item(
        db,
        warehouse=warehouse,
        zone=zone,
        item_type="label",
        item_key="label:training",
        label="Учебная зона",
        x=70,
        y=40,
        width=260,
        height=40,
    )
    _create_row(
        db,
        warehouse=warehouse,
        zone=zone,
        row_code="R01",
        label="Стеллаж R01",
        location_count=4,
        orientation="horizontal",
        x=90,
        y=130,
        locked=False,
    )
    _create_row(
        db,
        warehouse=warehouse,
        zone=zone,
        row_code="R02",
        label="Стеллаж R02",
        location_count=4,
        orientation="horizontal",
        x=90,
        y=390,
        locked=False,
    )
    _add_item(
        db,
        warehouse=warehouse,
        zone=zone,
        item_type="aisle",
        item_key="aisle:training",
        label="Проход",
        x=90,
        y=260,
        width=540,
        height=74,
    )


def ensure_demo_maps(db: Session, *, actor: str = "map-setup") -> list[dict]:
    _remove_accidental_wh02_location(db)
    wh01 = db.scalar(select(Warehouse).where(Warehouse.code == "WH01"))
    if not wh01:
        raise _not_found("Основной склад", "WH01")
    _ensure_wh01_layout(db, wh01)
    wh02 = db.scalar(select(Warehouse).where(Warehouse.code == SANDBOX_WAREHOUSE_CODE))
    if not wh02:
        wh02 = Warehouse(
            code=SANDBOX_WAREHOUSE_CODE,
            name="Учебный склад",
            city="Москва",
            timezone="Europe/Moscow",
        )
        db.add(wh02)
        db.flush()
    zone = db.scalar(
        select(Zone).where(Zone.warehouse_id == wh02.id, Zone.code == SANDBOX_ZONE_CODE)
    )
    if not zone:
        zone = Zone(
            warehouse_id=wh02.id,
            code=SANDBOX_ZONE_CODE,
            name="Учебная зона хранения",
            kind=LocationKind.STORAGE,
        )
        db.add(zone)
        db.flush()
    if not db.scalar(select(WarehouseMapItem.id).where(WarehouseMapItem.warehouse_id == wh02.id).limit(1)):
        _create_sandbox_defaults(db, wh02, zone)
        _event(
            db,
            operation="warehouse_map_created",
            object_type="warehouse",
            object_uid=wh02.code,
            actor=actor,
            after={"template": "sandbox", "locations": 8},
        )
    db.commit()
    return [{"code": wh01.code, "name": wh01.name}, {"code": wh02.code, "name": wh02.name}]


def _location_state(units: list[LogisticUnit]) -> str:
    statuses = {_value(unit.status) for unit in units}
    if statuses & {"blocked", "quarantine", "written_off"}:
        return "problem"
    if statuses & {"expedition", "loaded", "in_transit"}:
        return "expedition"
    if statuses & {"reserved", "picking"}:
        return "reserved"
    return "occupied" if units else "empty"


def warehouse_map_payload(db: Session, warehouse_code: str) -> dict:
    warehouse = _warehouse(db, warehouse_code)
    items = list(
        db.scalars(
            select(WarehouseMapItem)
            .where(WarehouseMapItem.warehouse_id == warehouse.id)
            .order_by(WarehouseMapItem.sort_order, WarehouseMapItem.id)
        )
    )
    locations = list(db.scalars(select(Location).where(Location.warehouse_id == warehouse.id)))
    location_ids = [location.id for location in locations]
    units = list(
        db.scalars(select(LogisticUnit).where(LogisticUnit.current_location_id.in_(location_ids)))
    ) if location_ids else []
    units_by_location: dict[int, list[LogisticUnit]] = defaultdict(list)
    for unit in units:
        if unit.current_location_id:
            units_by_location[unit.current_location_id].append(unit)
    location_map = {location.id: location for location in locations}
    placed_location_ids = {item.location_id for item in items if item.location_id}
    result_items = []
    for item in items:
        payload = {
            "id": item.id,
            "item_type": item.item_type,
            "item_key": item.item_key,
            "label": item.label,
            "x": item.x,
            "y": item.y,
            "width": item.width,
            "height": item.height,
            "rotation": item.rotation,
            "parent_id": item.parent_id,
            "is_locked": item.is_locked,
            "location": None,
        }
        if item.location_id and item.location_id in location_map:
            location = location_map[item.location_id]
            location_units = units_by_location.get(location.id, [])
            payload["location"] = {
                "id": location.id,
                "code": location.code,
                "name": location.name,
                "kind": _value(location.kind),
                "address": location_address_payload(location),
                "capacity_units": location.capacity_units,
                "state": _location_state(location_units),
                "units": [
                    {
                        "uid": unit.uid,
                        "type_code": unit.type.code,
                        "type_name": unit.type.name,
                        "status": _value(unit.status),
                        "child_count": len(unit.child_units),
                        "content_count": len(unit.contents),
                    }
                    for unit in location_units
                ],
            }
        result_items.append(payload)
    occupied_ids = {location_id for location_id, rows in units_by_location.items() if rows}
    problem_ids = {
        location_id
        for location_id, rows in units_by_location.items()
        if _location_state(rows) == "problem"
    }
    return {
        "warehouse": {
            "id": warehouse.id,
            "code": warehouse.code,
            "name": warehouse.name,
            "city": warehouse.city,
        },
        "editable": warehouse.code == SANDBOX_WAREHOUSE_CODE,
        "canvas": {"width": CANVAS_WIDTH, "height": CANVAS_HEIGHT},
        "stats": {
            "locations": len(locations),
            "occupied": len(occupied_ids),
            "empty": len(locations) - len(occupied_ids),
            "problems": len(problem_ids),
            "logistic_units": len(units),
        },
        "items": result_items,
        "unplaced_locations": [
            {"id": location.id, "code": location.code, "name": location.name}
            for location in locations
            if location.id not in placed_location_ids
        ],
    }


def create_map_row(db: Session, warehouse_code: str, payload: WarehouseMapRowCreate) -> dict:
    warehouse = _warehouse(db, warehouse_code)
    _assert_sandbox(warehouse)
    zone = _zone(db, warehouse, payload.zone_code)
    rack = _create_row(
        db,
        warehouse=warehouse,
        zone=zone,
        row_code=payload.row_code,
        label=payload.label,
        location_count=payload.location_count,
        orientation=payload.orientation,
        x=payload.x,
        y=payload.y,
        locked=False,
    )
    _event(
        db,
        operation="warehouse_map_row_created",
        object_type="warehouse",
        object_uid=warehouse.code,
        actor=payload.actor,
        after={"row": payload.row_code.upper(), "locations": payload.location_count},
    )
    db.commit()
    return warehouse_map_payload(db, warehouse.code)


def create_map_location(db: Session, warehouse_code: str, payload: WarehouseMapLocationCreate) -> dict:
    warehouse = _warehouse(db, warehouse_code)
    _assert_sandbox(warehouse)
    zone = _zone(db, warehouse, payload.zone_code)
    code = payload.code.strip().upper()
    parts = code.split("-")
    if len(parts) != 7 or parts[0] != warehouse.code or parts[1] != zone.code:
        raise HTTPException(
            status_code=422,
            detail=(
                "Код стеллажной ячейки должен иметь вид "
                f"{warehouse.code}-{zone.code}-A01-R01-S01-L01-P01"
            ),
        )
    if db.scalar(select(Location.id).where(Location.code == code)):
        raise HTTPException(status_code=409, detail=f"Ячейка уже существует: {code}")
    aisle, rack, section, level, _ = ensure_address_hierarchy(
        db,
        zone,
        aisle_code=parts[2],
        rack_code=parts[3],
        section_code=parts[4],
        level_code=parts[5],
    )
    location = create_location(
        db,
        LocationCreate(
            warehouse_id=warehouse.id,
            zone_id=zone.id,
            aisle_id=aisle.id,
            rack_id=rack.id,
            section_id=section.id,
            level_id=level.id,
            position_code=parts[6],
            code=code,
            name=payload.label,
            kind=LocationKind.STORAGE,
            capacity_units=1,
        ),
    )
    _add_item(
        db,
        warehouse=warehouse,
        zone=zone,
        location=location,
        item_type="location",
        item_key=f"location:{location.id}",
        label=payload.label,
        x=payload.x,
        y=payload.y,
        width=payload.width,
        height=payload.height,
    )
    _event(
        db,
        operation="warehouse_map_location_created",
        object_type="location",
        object_uid=location.code,
        actor=payload.actor,
        after={"warehouse": warehouse.code},
    )
    db.commit()
    return warehouse_map_payload(db, warehouse.code)


def create_map_label(db: Session, warehouse_code: str, payload: WarehouseMapLabelCreate) -> dict:
    warehouse = _warehouse(db, warehouse_code)
    _assert_sandbox(warehouse)
    next_id = (db.scalar(select(func.max(WarehouseMapItem.id))) or 0) + 1
    _add_item(
        db,
        warehouse=warehouse,
        item_type="label",
        item_key=f"label:custom:{next_id}",
        label=payload.label,
        x=payload.x,
        y=payload.y,
        width=payload.width,
        height=payload.height,
    )
    db.commit()
    return warehouse_map_payload(db, warehouse.code)


def update_map_item(
    db: Session,
    warehouse_code: str,
    item_id: int,
    payload: WarehouseMapItemUpdate,
) -> dict:
    warehouse = _warehouse(db, warehouse_code)
    _assert_sandbox(warehouse)
    item = db.scalar(
        select(WarehouseMapItem).where(
            WarehouseMapItem.id == item_id,
            WarehouseMapItem.warehouse_id == warehouse.id,
        )
    )
    if not item:
        raise _not_found("Элемент карты", str(item_id))
    if item.is_locked:
        raise HTTPException(status_code=409, detail="Элемент карты защищён от редактирования")
    before = {"x": item.x, "y": item.y, "rotation": item.rotation, "label": item.label}
    new_x = payload.x if payload.x is not None else item.x
    new_y = payload.y if payload.y is not None else item.y
    new_x = min(new_x, CANVAS_WIDTH - item.width)
    new_y = min(new_y, CANVAS_HEIGHT - item.height)
    delta_x = new_x - item.x
    delta_y = new_y - item.y
    item.x = new_x
    item.y = new_y
    if payload.label is not None:
        item.label = payload.label.strip()
        if item.location_id:
            location = db.get(Location, item.location_id)
            if location:
                location.name = item.label
    if item.item_type == "rack":
        if payload.rotation is not None:
            item.rotation = payload.rotation
            _layout_rack_children(db, item)
        elif delta_x or delta_y:
            children = db.scalars(select(WarehouseMapItem).where(WarehouseMapItem.parent_id == item.id))
            for child in children:
                child.x += delta_x
                child.y += delta_y
    else:
        if payload.width is not None:
            item.width = payload.width
        if payload.height is not None:
            item.height = payload.height
        if payload.rotation is not None:
            item.rotation = payload.rotation
    _event(
        db,
        operation="warehouse_map_item_updated",
        object_type="warehouse_map_item",
        object_uid=str(item.id),
        actor=payload.actor,
        before=before,
        after={"x": item.x, "y": item.y, "rotation": item.rotation, "label": item.label},
    )
    db.commit()
    return warehouse_map_payload(db, warehouse.code)


def delete_map_item(db: Session, warehouse_code: str, item_id: int, *, actor: str) -> dict:
    warehouse = _warehouse(db, warehouse_code)
    _assert_sandbox(warehouse)
    item = db.scalar(
        select(WarehouseMapItem).where(
            WarehouseMapItem.id == item_id,
            WarehouseMapItem.warehouse_id == warehouse.id,
        )
    )
    if not item:
        raise _not_found("Элемент карты", str(item_id))
    if item.is_locked:
        raise HTTPException(status_code=409, detail="Элемент карты защищён от удаления")
    targets = [item]
    if item.item_type == "rack":
        targets = list(db.scalars(select(WarehouseMapItem).where(WarehouseMapItem.parent_id == item.id))) + [item]
    locations = [db.get(Location, target.location_id) for target in targets if target.location_id]
    for location in locations:
        if not location:
            continue
        reason = _location_reference_reason(db, location)
        if reason:
            raise HTTPException(status_code=409, detail=f"Нельзя удалить {location.code}: {reason}")
    deleted_codes = [location.code for location in locations if location]
    if item.item_type == "rack":
        db.execute(delete(WarehouseMapItem).where(WarehouseMapItem.parent_id == item.id))
    db.execute(delete(WarehouseMapItem).where(WarehouseMapItem.id == item.id))
    for location in locations:
        if location:
            db.delete(location)
    db.flush()
    _prune_empty_address_branches(db, [location for location in locations if location])
    _event(
        db,
        operation="warehouse_map_item_deleted",
        object_type="warehouse",
        object_uid=warehouse.code,
        actor=actor,
        before={"item_id": item_id, "locations": deleted_codes},
    )
    db.commit()
    return warehouse_map_payload(db, warehouse.code)


def reset_sandbox_map(db: Session, warehouse_code: str, *, actor: str) -> dict:
    warehouse = _warehouse(db, warehouse_code)
    _assert_sandbox(warehouse)
    if db.scalar(select(LogisticInventory.id).where(LogisticInventory.warehouse_id == warehouse.id).limit(1)):
        raise HTTPException(status_code=409, detail="Сброс невозможен: по WH02 уже проводилась инвентаризация")
    locations = list(db.scalars(select(Location).where(Location.warehouse_id == warehouse.id)))
    for location in locations:
        reason = _location_reference_reason(db, location)
        if reason:
            raise HTTPException(status_code=409, detail=f"Сброс невозможен: {location.code} — {reason}")
    items = list(db.scalars(select(WarehouseMapItem).where(WarehouseMapItem.warehouse_id == warehouse.id)))
    db.execute(
        delete(WarehouseMapItem).where(
            WarehouseMapItem.warehouse_id == warehouse.id,
            WarehouseMapItem.parent_id.is_not(None),
        )
    )
    db.execute(delete(WarehouseMapItem).where(WarehouseMapItem.warehouse_id == warehouse.id))
    for location in locations:
        db.delete(location)
    db.flush()
    _prune_empty_address_branches(db, locations)
    zone = _zone(db, warehouse, SANDBOX_ZONE_CODE)
    _create_sandbox_defaults(db, warehouse, zone)
    _event(
        db,
        operation="warehouse_map_reset",
        object_type="warehouse",
        object_uid=warehouse.code,
        actor=actor,
        before={"removed_locations": len(locations), "removed_items": len(items)},
        after={"template": "sandbox", "locations": 8},
    )
    db.commit()
    return warehouse_map_payload(db, warehouse.code)
