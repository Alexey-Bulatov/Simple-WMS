from uuid import uuid4

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.constants import CODE_SEPARATOR, LOGISTIC_INVENTORY_CODE_PREFIX
from app.models.entities import (
    Location,
    LogisticInventory,
    LogisticInventoryLine,
    LogisticInventoryLocation,
    LogisticUnit,
    LogisticUnitType,
    Warehouse,
    utcnow,
)
from app.models.enums import (
    InventoryLineStatus,
    InventoryLocationStatus,
    InventoryStatus,
    LocationKind,
    LogisticUnitStatus,
)
from app.schemas import (
    LogisticInventoryLocationRequest,
    LogisticInventoryResolveRequest,
    LogisticInventoryStartRequest,
    LogisticInventoryUnitRequest,
)
from app.services import (
    bad_request,
    commit_or_409,
    create_event,
    get_active_location,
    logistic_location_occupied_count,
    not_found,
)


PROBLEM_STATUSES = {
    InventoryLineStatus.MISSING,
    InventoryLineStatus.EXTRA,
    InventoryLineStatus.WRONG_LOCATION,
}


def generate_logistic_inventory_uid(db: Session) -> str:
    while True:
        candidate = (
            f"{LOGISTIC_INVENTORY_CODE_PREFIX}"
            f"{CODE_SEPARATOR}{uuid4().hex[:12].upper()}"
        )
        exists = db.scalar(
            select(LogisticInventory.id).where(
                LogisticInventory.inventory_uid == candidate
            )
        )
        if exists is None:
            return candidate


def get_logistic_inventory(
    db: Session,
    inventory_uid: str,
    *,
    for_update: bool = False,
) -> LogisticInventory:
    query = select(LogisticInventory).where(
        LogisticInventory.inventory_uid == inventory_uid.strip().upper()
    )
    if for_update:
        query = query.with_for_update()
    inventory = db.scalar(query)
    if inventory is None:
        raise not_found("logistic_inventory")
    return inventory


def logistic_inventory_locations(
    db: Session,
    inventory_id: int,
) -> list[LogisticInventoryLocation]:
    return list(
        db.scalars(
            select(LogisticInventoryLocation)
            .join(Location, Location.id == LogisticInventoryLocation.location_id)
            .where(LogisticInventoryLocation.inventory_id == inventory_id)
            .order_by(Location.code)
        )
    )


def logistic_inventory_lines(
    db: Session,
    inventory_id: int,
) -> list[LogisticInventoryLine]:
    return list(
        db.scalars(
            select(LogisticInventoryLine)
            .where(LogisticInventoryLine.inventory_id == inventory_id)
            .order_by(LogisticInventoryLine.id)
        )
    )


def logistic_inventory_line_payload(
    db: Session,
    line: LogisticInventoryLine,
) -> dict:
    unit = db.get(LogisticUnit, line.logistic_unit_id)
    unit_type = db.get(LogisticUnitType, unit.type_id) if unit else None
    expected = (
        db.get(Location, line.expected_location_id)
        if line.expected_location_id is not None
        else None
    )
    actual = (
        db.get(Location, line.actual_location_id)
        if line.actual_location_id is not None
        else None
    )
    return {
        "id": line.id,
        "unit_uid": unit.uid if unit else "",
        "type_code": unit_type.code if unit_type else "",
        "unit_status": unit.status if unit else LogisticUnitStatus.WRITTEN_OFF,
        "status": line.status,
        "expected_location_code": expected.code if expected else None,
        "actual_location_code": actual.code if actual else None,
        "scanned_at": line.scanned_at,
        "resolution_action": line.resolution_action,
        "resolution_actor": line.resolution_actor,
        "resolution_reason": line.resolution_reason,
        "resolved_at": line.resolved_at,
    }


def logistic_inventory_payload(
    db: Session,
    inventory: LogisticInventory,
) -> dict:
    warehouse = db.get(Warehouse, inventory.warehouse_id)
    current = (
        db.get(Location, inventory.current_location_id)
        if inventory.current_location_id is not None
        else None
    )
    location_rows = logistic_inventory_locations(db, inventory.id)
    lines = logistic_inventory_lines(db, inventory.id)
    unresolved = [
        line
        for line in lines
        if line.status in PROBLEM_STATUSES and line.resolved_at is None
    ]
    locations_payload = []
    for row in location_rows:
        location = db.get(Location, row.location_id)
        related_problems = [
            line
            for line in unresolved
            if line.expected_location_id == row.location_id
            or line.actual_location_id == row.location_id
        ]
        locations_payload.append(
            {
                "id": row.id,
                "location_id": row.location_id,
                "location_code": location.code if location else "",
                "expected_unit_count": row.expected_unit_count,
                "scanned_unit_count": sum(
                    1
                    for line in lines
                    if line.actual_location_id == row.location_id
                    and line.scanned_at is not None
                ),
                "problem_count": len(related_problems),
                "status": row.status,
                "checked_at": row.checked_at,
                "checked_by": row.checked_by,
            }
        )
    checked_count = sum(
        1
        for row in location_rows
        if row.status != InventoryLocationStatus.UNCHECKED
    )
    total_locations = len(location_rows)
    return {
        "id": inventory.id,
        "inventory_uid": inventory.inventory_uid,
        "warehouse_id": inventory.warehouse_id,
        "warehouse_code": warehouse.code if warehouse else "",
        "scope_type": inventory.scope_type,
        "scope_parameters": inventory.scope_parameters or {},
        "current_location_id": inventory.current_location_id,
        "current_location_code": current.code if current else None,
        "status": inventory.status,
        "actor": inventory.actor,
        "created_at": inventory.created_at,
        "completed_at": inventory.completed_at,
        "total_locations": total_locations,
        "checked_locations": checked_count,
        "unchecked_locations": total_locations - checked_count,
        "progress_percent": (
            round(checked_count * 100 / total_locations, 2)
            if total_locations
            else 100.0
        ),
        "expected_count": sum(
            1 for line in lines if line.expected_location_id is not None
        ),
        "scanned_count": sum(
            1 for line in lines if line.status == InventoryLineStatus.SCANNED
        ),
        "missing_count": sum(
            1 for line in lines if line.status == InventoryLineStatus.MISSING
        ),
        "extra_count": sum(
            1 for line in lines if line.status == InventoryLineStatus.EXTRA
        ),
        "wrong_location_count": sum(
            1
            for line in lines
            if line.status == InventoryLineStatus.WRONG_LOCATION
        ),
        "unresolved_problem_count": len(unresolved),
        "locations": locations_payload,
        "lines": [logistic_inventory_line_payload(db, line) for line in lines],
    }


def start_logistic_inventory(
    db: Session,
    payload: LogisticInventoryStartRequest,
) -> LogisticInventory:
    warehouse = db.scalar(
        select(Warehouse)
        .where(Warehouse.code == payload.warehouse_code.strip().upper())
        .with_for_update()
    )
    if warehouse is None:
        raise not_found("warehouse")
    existing = db.scalar(
        select(LogisticInventory.id).where(
            LogisticInventory.warehouse_id == warehouse.id,
            LogisticInventory.status == InventoryStatus.OPEN,
        )
    )
    if existing is not None:
        raise bad_request("warehouse already has an open logistic inventory")
    locations = list(
        db.scalars(
            select(Location)
            .where(
                Location.warehouse_id == warehouse.id,
                Location.kind == LocationKind.STORAGE,
                Location.is_active.is_(True),
            )
            .order_by(Location.code)
        )
    )
    if not locations:
        raise bad_request("warehouse has no active storage locations")

    inventory = LogisticInventory(
        inventory_uid=generate_logistic_inventory_uid(db),
        warehouse_id=warehouse.id,
        scope_type=payload.scope_type,
        scope_parameters={"warehouse_code": warehouse.code},
        actor=payload.actor,
    )
    db.add(inventory)
    db.flush()
    location_ids = [location.id for location in locations]
    units = list(
        db.scalars(
            select(LogisticUnit).where(
                LogisticUnit.current_location_id.in_(location_ids),
                LogisticUnit.parent_unit_id.is_(None),
            )
        )
    )
    expected_counts = {location_id: 0 for location_id in location_ids}
    for unit in units:
        expected_counts[unit.current_location_id] += 1
        db.add(
            LogisticInventoryLine(
                inventory_id=inventory.id,
                logistic_unit_id=unit.id,
                expected_location_id=unit.current_location_id,
            )
        )
    for location in locations:
        db.add(
            LogisticInventoryLocation(
                inventory_id=inventory.id,
                location_id=location.id,
                expected_unit_count=expected_counts[location.id],
            )
        )
    create_event(
        db,
        operation="logistic_inventory_started",
        object_type="logistic_inventory",
        object_uid=inventory.inventory_uid,
        actor=payload.actor,
        after={
            "warehouse_code": warehouse.code,
            "scope_type": inventory.scope_type,
            "location_count": len(locations),
            "expected_count": len(units),
        },
    )
    from app.logistic_tasks import sync_logistic_inventory_tasks

    sync_logistic_inventory_tasks(db, inventory, actor=payload.actor)
    commit_or_409(db, "warehouse inventory conflicts with an existing document")
    db.refresh(inventory)
    return inventory


def inventory_location_row(
    db: Session,
    inventory: LogisticInventory,
    location: Location,
) -> LogisticInventoryLocation:
    row = db.scalar(
        select(LogisticInventoryLocation).where(
            LogisticInventoryLocation.inventory_id == inventory.id,
            LogisticInventoryLocation.location_id == location.id,
        )
    )
    if row is None:
        raise bad_request("location is outside this inventory scope")
    return row


def scan_logistic_inventory_location(
    db: Session,
    inventory_uid: str,
    payload: LogisticInventoryLocationRequest,
) -> LogisticInventory:
    inventory = get_logistic_inventory(db, inventory_uid, for_update=True)
    if inventory.status != InventoryStatus.OPEN:
        raise bad_request("inventory is already completed")
    location = get_active_location(db, payload.location_code)
    if (
        location.kind != LocationKind.STORAGE
        or location.warehouse_id != inventory.warehouse_id
    ):
        raise bad_request("location is outside this inventory warehouse")
    row = inventory_location_row(db, inventory, location)
    if row.status != InventoryLocationStatus.UNCHECKED:
        raise bad_request("location is already checked in this inventory")
    inventory.current_location_id = location.id
    create_event(
        db,
        operation="logistic_inventory_location_scanned",
        object_type="logistic_inventory",
        object_uid=inventory.inventory_uid,
        actor=payload.actor,
        after={
            "location_code": location.code,
            "expected_unit_count": row.expected_unit_count,
        },
    )
    db.commit()
    db.refresh(inventory)
    return inventory


def scan_logistic_inventory_unit(
    db: Session,
    inventory_uid: str,
    payload: LogisticInventoryUnitRequest,
) -> LogisticInventory:
    inventory = get_logistic_inventory(db, inventory_uid, for_update=True)
    if inventory.status != InventoryStatus.OPEN:
        raise bad_request("inventory is already completed")
    if inventory.current_location_id is None:
        raise bad_request("scan location first")
    location = db.get(Location, inventory.current_location_id)
    if location is None:
        raise not_found("location")
    row = inventory_location_row(db, inventory, location)
    if row.status != InventoryLocationStatus.UNCHECKED:
        raise bad_request("location is already checked in this inventory")
    unit = db.scalar(
        select(LogisticUnit)
        .where(func.upper(LogisticUnit.uid) == payload.unit_uid.strip().upper())
        .with_for_update()
    )
    if unit is None:
        raise not_found("logistic_unit")
    if unit.parent_unit_id is not None:
        raise bad_request("nested logistic unit is inventoried with its parent")
    line = db.scalar(
        select(LogisticInventoryLine).where(
            LogisticInventoryLine.inventory_id == inventory.id,
            LogisticInventoryLine.logistic_unit_id == unit.id,
        )
    )
    if line is None:
        line = LogisticInventoryLine(
            inventory_id=inventory.id,
            logistic_unit_id=unit.id,
            expected_location_id=None,
        )
        db.add(line)
    if line.scanned_at is not None:
        raise bad_request("logistic unit is already scanned in this inventory")
    line.actual_location_id = location.id
    line.scanned_at = utcnow()
    if line.expected_location_id == location.id:
        line.status = InventoryLineStatus.SCANNED
    elif line.expected_location_id is None:
        line.status = InventoryLineStatus.EXTRA
    else:
        line.status = InventoryLineStatus.WRONG_LOCATION
    create_event(
        db,
        operation="logistic_inventory_unit_scanned",
        object_type="logistic_inventory",
        object_uid=inventory.inventory_uid,
        actor=payload.actor,
        after={
            "unit_uid": unit.uid,
            "location_code": location.code,
            "status": line.status.value,
        },
    )
    finish_location = (
        payload.finish_location
        if payload.finish_location is not None
        else location.capacity_units == 1
    )
    if finish_location:
        db.flush()
        finalize_current_inventory_location(
            db,
            inventory,
            actor=payload.actor,
            require_empty=False,
        )
    db.commit()
    db.refresh(inventory)
    return inventory


def refresh_inventory_location_status(
    db: Session,
    inventory: LogisticInventory,
    location_id: int,
) -> None:
    row = db.scalar(
        select(LogisticInventoryLocation).where(
            LogisticInventoryLocation.inventory_id == inventory.id,
            LogisticInventoryLocation.location_id == location_id,
        )
    )
    if row is None or row.status == InventoryLocationStatus.UNCHECKED:
        return
    problem = db.scalar(
        select(LogisticInventoryLine.id).where(
            LogisticInventoryLine.inventory_id == inventory.id,
            LogisticInventoryLine.status.in_(PROBLEM_STATUSES),
            LogisticInventoryLine.resolved_at.is_(None),
            or_(
                LogisticInventoryLine.expected_location_id == location_id,
                LogisticInventoryLine.actual_location_id == location_id,
            ),
        )
    )
    row.status = (
        InventoryLocationStatus.PROBLEM
        if problem is not None
        else InventoryLocationStatus.CHECKED
    )


def finalize_current_inventory_location(
    db: Session,
    inventory: LogisticInventory,
    *,
    actor: str,
    require_empty: bool = False,
) -> None:
    if inventory.current_location_id is None:
        raise bad_request("scan location first")
    location = db.get(Location, inventory.current_location_id)
    if location is None:
        raise not_found("location")
    row = inventory_location_row(db, inventory, location)
    if row.status != InventoryLocationStatus.UNCHECKED:
        raise bad_request("location is already checked in this inventory")
    scanned_count = (
        db.scalar(
            select(func.count(LogisticInventoryLine.id)).where(
                LogisticInventoryLine.inventory_id == inventory.id,
                LogisticInventoryLine.actual_location_id == location.id,
                LogisticInventoryLine.scanned_at.is_not(None),
            )
        )
        or 0
    )
    if require_empty and scanned_count:
        raise bad_request("location already has scanned logistic units")
    now = utcnow()
    missing_lines = list(
        db.scalars(
            select(LogisticInventoryLine).where(
                LogisticInventoryLine.inventory_id == inventory.id,
                LogisticInventoryLine.expected_location_id == location.id,
                LogisticInventoryLine.status == InventoryLineStatus.EXPECTED,
                LogisticInventoryLine.scanned_at.is_(None),
            )
        )
    )
    for line in missing_lines:
        line.status = InventoryLineStatus.MISSING
        line.scanned_at = now
    row.status = InventoryLocationStatus.CHECKED
    row.checked_at = now
    row.checked_by = actor
    db.flush()
    refresh_inventory_location_status(db, inventory, location.id)
    inventory.current_location_id = None
    create_event(
        db,
        operation=(
            "logistic_inventory_location_empty"
            if require_empty
            else "logistic_inventory_location_confirmed"
        ),
        object_type="logistic_inventory",
        object_uid=inventory.inventory_uid,
        actor=actor,
        after={
            "location_code": location.code,
            "scanned_count": scanned_count,
            "missing_count": len(missing_lines),
            "location_status": row.status.value,
        },
    )


def confirm_logistic_inventory_location(
    db: Session,
    inventory_uid: str,
    *,
    actor: str,
    require_empty: bool = False,
) -> LogisticInventory:
    inventory = get_logistic_inventory(db, inventory_uid, for_update=True)
    if inventory.status != InventoryStatus.OPEN:
        raise bad_request("inventory is already completed")
    finalize_current_inventory_location(
        db,
        inventory,
        actor=actor,
        require_empty=require_empty,
    )
    db.commit()
    db.refresh(inventory)
    return inventory


def complete_logistic_inventory(
    db: Session,
    inventory_uid: str,
    *,
    actor: str,
) -> LogisticInventory:
    inventory = get_logistic_inventory(db, inventory_uid, for_update=True)
    if inventory.status != InventoryStatus.OPEN:
        raise bad_request("inventory is already completed")
    unchecked = list(
        db.scalars(
            select(LogisticInventoryLocation)
            .join(Location, Location.id == LogisticInventoryLocation.location_id)
            .where(
                LogisticInventoryLocation.inventory_id == inventory.id,
                LogisticInventoryLocation.status
                == InventoryLocationStatus.UNCHECKED,
            )
            .order_by(Location.code)
        )
    )
    if unchecked:
        codes = [
            db.get(Location, row.location_id).code
            for row in unchecked[:5]
            if db.get(Location, row.location_id) is not None
        ]
        preview = ", ".join(codes)
        suffix = (
            ""
            if len(unchecked) <= 5
            else f" and {len(unchecked) - 5} more"
        )
        raise bad_request(
            f"inventory has unchecked locations: {preview}{suffix}"
        )
    inventory.status = InventoryStatus.COMPLETED
    inventory.completed_at = utcnow()
    payload = logistic_inventory_payload(db, inventory)
    create_event(
        db,
        operation="logistic_inventory_completed",
        object_type="logistic_inventory",
        object_uid=inventory.inventory_uid,
        actor=actor,
        after={
            "location_count": payload["total_locations"],
            "line_count": len(payload["lines"]),
            "unresolved_problem_count": payload["unresolved_problem_count"],
        },
    )
    from app.logistic_tasks import sync_logistic_inventory_tasks

    sync_logistic_inventory_tasks(db, inventory, actor=actor)
    db.commit()
    db.refresh(inventory)
    return inventory


def get_logistic_inventory_problem(
    db: Session,
    inventory: LogisticInventory,
    unit_uid: str,
) -> tuple[LogisticInventoryLine, LogisticUnit]:
    unit = db.scalar(
        select(LogisticUnit)
        .where(func.upper(LogisticUnit.uid) == unit_uid.strip().upper())
        .with_for_update()
    )
    if unit is None:
        raise not_found("logistic_unit")
    line = db.scalar(
        select(LogisticInventoryLine).where(
            LogisticInventoryLine.inventory_id == inventory.id,
            LogisticInventoryLine.logistic_unit_id == unit.id,
            LogisticInventoryLine.status.in_(PROBLEM_STATUSES),
        )
    )
    if line is None:
        raise bad_request("inventory discrepancy line not found")
    if line.resolved_at is not None:
        raise bad_request("inventory discrepancy is already resolved")
    return line, unit


def resolve_logistic_inventory_line(
    db: Session,
    *,
    inventory: LogisticInventory,
    line: LogisticInventoryLine,
    unit: LogisticUnit,
    action: str,
    payload: LogisticInventoryResolveRequest,
) -> LogisticInventory:
    line.resolution_action = action
    line.resolution_actor = payload.actor
    line.resolution_reason = payload.reason
    line.resolved_at = utcnow()
    db.flush()
    for location_id in {
        line.expected_location_id,
        line.actual_location_id,
    } - {None}:
        refresh_inventory_location_status(db, inventory, location_id)
    create_event(
        db,
        operation="logistic_inventory_discrepancy_resolved",
        object_type="logistic_inventory",
        object_uid=inventory.inventory_uid,
        actor=payload.actor,
        reason=payload.reason,
        after={
            "line_id": line.id,
            "unit_uid": unit.uid,
            "line_status": line.status.value,
            "action": action,
        },
    )
    return inventory


def confirm_logistic_inventory_missing(
    db: Session,
    inventory_uid: str,
    unit_uid: str,
    payload: LogisticInventoryResolveRequest,
) -> LogisticInventory:
    inventory = get_logistic_inventory(db, inventory_uid, for_update=True)
    line, unit = get_logistic_inventory_problem(db, inventory, unit_uid)
    if line.status != InventoryLineStatus.MISSING:
        raise bad_request("only a missing discrepancy can be confirmed")
    resolve_logistic_inventory_line(
        db,
        inventory=inventory,
        line=line,
        unit=unit,
        action="missing_confirmed",
        payload=payload,
    )
    db.commit()
    db.refresh(inventory)
    return inventory


def ensure_resolution_location_capacity(
    db: Session,
    unit: LogisticUnit,
    location: Location,
) -> None:
    occupied = logistic_location_occupied_count(db, location.id)
    if unit.current_location_id == location.id:
        occupied -= 1
    if occupied >= location.capacity_units:
        raise bad_request("location capacity is already reached")


def place_logistic_inventory_found_unit(
    db: Session,
    inventory_uid: str,
    unit_uid: str,
    payload: LogisticInventoryResolveRequest,
) -> LogisticInventory:
    inventory = get_logistic_inventory(db, inventory_uid, for_update=True)
    line, unit = get_logistic_inventory_problem(db, inventory, unit_uid)
    if line.status != InventoryLineStatus.EXTRA:
        raise bad_request("only an extra discrepancy can be placed")
    if unit.status != LogisticUnitStatus.CLOSED:
        raise bad_request("found logistic unit must have closed status")
    location = db.get(Location, line.actual_location_id)
    if location is None or location.warehouse_id != inventory.warehouse_id:
        raise bad_request("actual location is outside inventory warehouse")
    current = (
        db.get(Location, unit.current_location_id)
        if unit.current_location_id is not None
        else None
    )
    if current is not None and current.kind == LocationKind.STORAGE:
        raise bad_request("stored logistic unit must be moved instead")
    if current is not None and current.warehouse_id != location.warehouse_id:
        raise bad_request("logistic unit belongs to another warehouse")
    ensure_resolution_location_capacity(db, unit, location)
    before = {
        "status": unit.status.value,
        "location_code": current.code if current else None,
    }
    unit.current_location_id = location.id
    unit.status = LogisticUnitStatus.AVAILABLE
    resolve_logistic_inventory_line(
        db,
        inventory=inventory,
        line=line,
        unit=unit,
        action="placed_to_actual",
        payload=payload,
    )
    create_event(
        db,
        operation="logistic_unit_inventory_placed_to_actual",
        object_type="logistic_unit",
        object_uid=unit.uid,
        actor=payload.actor,
        reason=payload.reason,
        before=before,
        after={
            "status": unit.status.value,
            "location_code": location.code,
            "inventory_uid": inventory.inventory_uid,
        },
    )
    db.commit()
    db.refresh(inventory)
    return inventory


def move_logistic_inventory_unit_to_actual(
    db: Session,
    inventory_uid: str,
    unit_uid: str,
    payload: LogisticInventoryResolveRequest,
) -> LogisticInventory:
    inventory = get_logistic_inventory(db, inventory_uid, for_update=True)
    line, unit = get_logistic_inventory_problem(db, inventory, unit_uid)
    if line.status != InventoryLineStatus.WRONG_LOCATION:
        raise bad_request("only a wrong-location discrepancy can be moved")
    if unit.status != LogisticUnitStatus.AVAILABLE:
        raise bad_request("only an available logistic unit can be moved")
    expected = db.get(Location, line.expected_location_id)
    actual = db.get(Location, line.actual_location_id)
    if expected is None or actual is None:
        raise bad_request("inventory discrepancy has incomplete locations")
    if unit.current_location_id != expected.id:
        raise bad_request("logistic unit location changed after inventory scan")
    if actual.warehouse_id != inventory.warehouse_id:
        raise bad_request("actual location is outside inventory warehouse")
    ensure_resolution_location_capacity(db, unit, actual)
    unit.current_location_id = actual.id
    resolve_logistic_inventory_line(
        db,
        inventory=inventory,
        line=line,
        unit=unit,
        action="moved_to_actual",
        payload=payload,
    )
    create_event(
        db,
        operation="logistic_unit_inventory_moved_to_actual",
        object_type="logistic_unit",
        object_uid=unit.uid,
        actor=payload.actor,
        reason=payload.reason,
        before={"location_code": expected.code},
        after={
            "location_code": actual.code,
            "inventory_uid": inventory.inventory_uid,
        },
    )
    db.commit()
    db.refresh(inventory)
    return inventory
