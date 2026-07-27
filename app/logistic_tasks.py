from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.constants import CODE_SEPARATOR, LOGISTIC_TASK_CODE_PREFIX
from app.models.entities import (
    Location,
    LogisticInventory,
    LogisticShipment,
    LogisticTask,
    LogisticTransfer,
    LogisticUnit,
    Warehouse,
    utcnow,
)
from app.models.enums import (
    InventoryStatus,
    LocationKind,
    LogisticUnitStatus,
    ShipmentStatus,
    TaskPriority,
    TaskStatus,
    TaskType,
    TransferStatus,
)
from app.schemas import LogisticTaskCreate
from app.services import (
    bad_request,
    commit_or_409,
    create_event,
    get_active_location,
    not_found,
)


TASK_OBJECT_TYPES = {
    TaskType.BUILD: "logistic_unit",
    TaskType.PLACE: "logistic_unit",
    TaskType.MOVE: "logistic_unit",
    TaskType.SHIP: "logistic_shipment",
    TaskType.INVENTORY: "logistic_inventory",
    TaskType.TRANSFER: "logistic_transfer",
}

TASK_TITLES = {
    TaskType.BUILD: "Завершить формирование логистической единицы",
    TaskType.PLACE: "Разместить логистическую единицу",
    TaskType.MOVE: "Переместить логистическую единицу",
    TaskType.SHIP: "Обработать отгрузку",
    TaskType.INVENTORY: "Провести инвентаризацию",
    TaskType.TRANSFER: "Обработать межскладскую передачу",
}

OBJECT_URL_PREFIXES = {
    "logistic_unit": "/api/logistic-units",
    "logistic_shipment": "/api/logistic-shipments",
    "logistic_inventory": "/api/logistic-inventories",
    "logistic_transfer": "/api/logistic-transfers",
}

ACTIVE_TASK_STATUSES = {
    TaskStatus.NEW,
    TaskStatus.IN_PROGRESS,
}


def generate_logistic_task_uid(db: Session) -> str:
    while True:
        candidate = (
            f"{LOGISTIC_TASK_CODE_PREFIX}"
            f"{CODE_SEPARATOR}{uuid4().hex[:12].upper()}"
        )
        exists = db.scalar(
            select(LogisticTask.id).where(LogisticTask.task_uid == candidate)
        )
        if exists is None:
            return candidate


def get_logistic_task(
    db: Session,
    task_uid: str,
    *,
    for_update: bool = False,
) -> LogisticTask:
    query = select(LogisticTask).where(
        LogisticTask.task_uid == task_uid.strip().upper()
    )
    if for_update:
        query = query.with_for_update()
    task = db.scalar(query)
    if task is None:
        raise not_found("logistic_task")
    return task


def get_task_unit(db: Session, object_uid: str) -> LogisticUnit:
    unit = db.scalar(
        select(LogisticUnit).where(
            func.upper(LogisticUnit.uid) == object_uid.strip().upper()
        )
    )
    if unit is None:
        raise not_found("logistic_unit")
    return unit


def get_task_shipment(db: Session, object_uid: str) -> LogisticShipment:
    shipment = db.scalar(
        select(LogisticShipment).where(
            LogisticShipment.shipment_uid == object_uid.strip().upper()
        )
    )
    if shipment is None:
        raise not_found("logistic_shipment")
    return shipment


def get_task_inventory(db: Session, object_uid: str) -> LogisticInventory:
    inventory = db.scalar(
        select(LogisticInventory).where(
            LogisticInventory.inventory_uid == object_uid.strip().upper()
        )
    )
    if inventory is None:
        raise not_found("logistic_inventory")
    return inventory


def get_task_transfer(db: Session, object_uid: str) -> LogisticTransfer:
    transfer = db.scalar(
        select(LogisticTransfer).where(
            LogisticTransfer.transfer_uid == object_uid.strip().upper()
        )
    )
    if transfer is None:
        raise not_found("logistic_transfer")
    return transfer


def task_object_status(db: Session, task: LogisticTask) -> str | None:
    if task.object_type == "logistic_unit":
        return get_task_unit(db, task.object_uid).status.value
    if task.object_type == "logistic_shipment":
        return get_task_shipment(db, task.object_uid).status.value
    if task.object_type == "logistic_inventory":
        return get_task_inventory(db, task.object_uid).status.value
    if task.object_type == "logistic_transfer":
        return get_task_transfer(db, task.object_uid).status.value
    return None


def logistic_task_payload(db: Session, task: LogisticTask) -> dict:
    warehouse = db.get(Warehouse, task.warehouse_id)
    url_prefix = OBJECT_URL_PREFIXES.get(task.object_type, "")
    return {
        "id": task.id,
        "task_uid": task.task_uid,
        "warehouse_id": task.warehouse_id,
        "warehouse_code": warehouse.code if warehouse else "",
        "warehouse_name": warehouse.name if warehouse else "",
        "task_type": task.task_type,
        "status": task.status,
        "priority": task.priority,
        "title": task.title,
        "description": task.description,
        "object_type": task.object_type,
        "object_uid": task.object_uid,
        "object_status": task_object_status(db, task),
        "object_url": f"{url_prefix}/{task.object_uid}" if url_prefix else "",
        "parameters": task.parameters or {},
        "assigned_to": task.assigned_to,
        "created_by": task.created_by,
        "created_at": task.created_at,
        "started_at": task.started_at,
        "completed_at": task.completed_at,
    }


def normalize_task_parameters(
    db: Session,
    *,
    warehouse: Warehouse,
    task_type: TaskType,
    parameters: dict,
) -> dict:
    result = dict(parameters)
    target_code = str(result.get("target_location_code") or "").strip().upper()
    if task_type == TaskType.MOVE and not target_code:
        raise bad_request("move task requires target_location_code")
    if target_code:
        target = get_active_location(db, target_code)
        if (
            target.kind != LocationKind.STORAGE
            or target.warehouse_id != warehouse.id
        ):
            raise bad_request("target location must belong to the task warehouse")
        result["target_location_code"] = target.code
    return result


def validate_unit_task(
    db: Session,
    *,
    warehouse: Warehouse,
    task_type: TaskType,
    object_uid: str,
    parameters: dict,
) -> LogisticUnit:
    unit = get_task_unit(db, object_uid)
    if unit.parent_unit_id is not None:
        raise bad_request("nested logistic unit is handled with its parent")
    location = (
        db.get(Location, unit.current_location_id)
        if unit.current_location_id is not None
        else None
    )
    if location is not None and location.warehouse_id != warehouse.id:
        raise bad_request("logistic unit belongs to another warehouse")
    if task_type == TaskType.BUILD:
        if unit.status != LogisticUnitStatus.OPEN:
            raise bad_request("build task requires an open logistic unit")
    elif task_type == TaskType.PLACE:
        if unit.status != LogisticUnitStatus.CLOSED:
            raise bad_request("place task requires a closed logistic unit")
        if location is not None and location.kind == LocationKind.STORAGE:
            raise bad_request("logistic unit is already placed")
    elif task_type == TaskType.MOVE:
        if (
            unit.status != LogisticUnitStatus.AVAILABLE
            or location is None
            or location.kind != LocationKind.STORAGE
        ):
            raise bad_request("move task requires a stored available logistic unit")
        if location.code == parameters["target_location_code"]:
            raise bad_request("logistic unit is already at the target location")
    return unit


def validate_document_task(
    db: Session,
    *,
    warehouse: Warehouse,
    task_type: TaskType,
    object_uid: str,
    parameters: dict,
) -> object:
    if task_type == TaskType.SHIP:
        shipment = get_task_shipment(db, object_uid)
        if shipment.warehouse_id != warehouse.id:
            raise bad_request("shipment belongs to another warehouse")
        if shipment.status in {ShipmentStatus.COMPLETED, ShipmentStatus.CANCELLED}:
            raise bad_request("shipment is already closed")
        return shipment
    if task_type == TaskType.INVENTORY:
        inventory = get_task_inventory(db, object_uid)
        if inventory.warehouse_id != warehouse.id:
            raise bad_request("inventory belongs to another warehouse")
        if inventory.status != InventoryStatus.OPEN:
            raise bad_request("inventory is already completed")
        return inventory
    transfer = get_task_transfer(db, object_uid)
    if transfer.status in {TransferStatus.COMPLETED, TransferStatus.CANCELLED}:
        raise bad_request("transfer is already closed")
    phase = str(parameters.get("phase") or "").strip().lower()
    inferred_phase = (
        "receive"
        if transfer.status in {TransferStatus.IN_TRANSIT, TransferStatus.RECEIVING}
        else "dispatch"
    )
    phase = phase or inferred_phase
    if phase not in {"dispatch", "receive"}:
        raise bad_request("transfer task phase must be dispatch or receive")
    if phase != inferred_phase:
        raise bad_request("transfer task phase does not match current transfer status")
    work_warehouse_id = (
        transfer.source_warehouse_id
        if phase == "dispatch"
        else transfer.destination_warehouse_id
    )
    if warehouse.id != work_warehouse_id:
        raise bad_request("transfer task belongs to another warehouse")
    parameters["phase"] = phase
    return transfer


def create_logistic_task(
    db: Session,
    payload: LogisticTaskCreate,
) -> LogisticTask:
    warehouse = db.scalar(
        select(Warehouse)
        .where(Warehouse.code == payload.warehouse_code.strip().upper())
        .with_for_update()
    )
    if warehouse is None:
        raise not_found("warehouse")
    object_uid = payload.object_uid.strip().upper()
    object_type = TASK_OBJECT_TYPES[payload.task_type]
    parameters = normalize_task_parameters(
        db,
        warehouse=warehouse,
        task_type=payload.task_type,
        parameters=payload.parameters,
    )
    if object_type == "logistic_unit":
        validate_unit_task(
            db,
            warehouse=warehouse,
            task_type=payload.task_type,
            object_uid=object_uid,
            parameters=parameters,
        )
    else:
        validate_document_task(
            db,
            warehouse=warehouse,
            task_type=payload.task_type,
            object_uid=object_uid,
            parameters=parameters,
        )
    duplicate = db.scalar(
        select(LogisticTask.id).where(
            LogisticTask.task_type == payload.task_type,
            LogisticTask.object_uid == object_uid,
            LogisticTask.status.in_(ACTIVE_TASK_STATUSES),
        )
    )
    if duplicate is not None:
        raise bad_request("object already has an active task of this type")
    task = LogisticTask(
        task_uid=generate_logistic_task_uid(db),
        warehouse_id=warehouse.id,
        task_type=payload.task_type,
        priority=payload.priority,
        title=(payload.title or "").strip() or TASK_TITLES[payload.task_type],
        description=(payload.description or "").strip() or None,
        object_type=object_type,
        object_uid=object_uid,
        parameters=parameters,
        assigned_to=(payload.assigned_to or "").strip() or None,
        created_by=payload.actor,
    )
    db.add(task)
    create_event(
        db,
        operation="logistic_task_created",
        object_type="logistic_task",
        object_uid=task.task_uid,
        actor=payload.actor,
        after={
            "warehouse_code": warehouse.code,
            "task_type": task.task_type.value,
            "priority": task.priority.value,
            "object_type": task.object_type,
            "object_uid": task.object_uid,
            "parameters": task.parameters,
            "assigned_to": task.assigned_to,
        },
    )
    commit_or_409(db, "logistic task identifier conflicts with existing data")
    db.refresh(task)
    return task


def start_logistic_task(
    db: Session,
    task_uid: str,
    *,
    actor: str,
) -> LogisticTask:
    task = get_logistic_task(db, task_uid, for_update=True)
    if task.status in {TaskStatus.COMPLETED, TaskStatus.CANCELLED}:
        raise bad_request("closed task cannot be started")
    if task.assigned_to and task.assigned_to != actor:
        raise bad_request("task is assigned to another operator")
    if task.status == TaskStatus.IN_PROGRESS:
        return task
    before = {"status": task.status.value, "assigned_to": task.assigned_to}
    task.status = TaskStatus.IN_PROGRESS
    task.assigned_to = actor
    task.started_at = utcnow()
    create_event(
        db,
        operation="logistic_task_started",
        object_type="logistic_task",
        object_uid=task.task_uid,
        actor=actor,
        before=before,
        after={"status": task.status.value, "assigned_to": task.assigned_to},
    )
    db.commit()
    db.refresh(task)
    return task


def assign_logistic_task(
    db: Session,
    task_uid: str,
    *,
    assigned_to: str | None,
    actor: str,
) -> LogisticTask:
    task = get_logistic_task(db, task_uid, for_update=True)
    if task.status in {TaskStatus.COMPLETED, TaskStatus.CANCELLED}:
        raise bad_request("closed task cannot be assigned")
    before = {"assigned_to": task.assigned_to}
    task.assigned_to = (assigned_to or "").strip() or None
    create_event(
        db,
        operation=(
            "logistic_task_assigned"
            if task.assigned_to
            else "logistic_task_unassigned"
        ),
        object_type="logistic_task",
        object_uid=task.task_uid,
        actor=actor,
        before=before,
        after={"assigned_to": task.assigned_to},
    )
    db.commit()
    db.refresh(task)
    return task


def task_operation_is_complete(db: Session, task: LogisticTask) -> bool:
    parameters = task.parameters or {}
    if task.object_type == "logistic_unit":
        unit = get_task_unit(db, task.object_uid)
        location = (
            db.get(Location, unit.current_location_id)
            if unit.current_location_id is not None
            else None
        )
        if task.task_type == TaskType.BUILD:
            return unit.status in {
                LogisticUnitStatus.CLOSED,
                LogisticUnitStatus.AVAILABLE,
                LogisticUnitStatus.BLOCKED,
                LogisticUnitStatus.QUARANTINE,
            }
        if task.task_type == TaskType.PLACE:
            target_code = parameters.get("target_location_code")
            return bool(
                location
                and location.kind == LocationKind.STORAGE
                and (not target_code or location.code == target_code)
            )
        if task.task_type == TaskType.MOVE:
            return bool(
                location
                and location.kind == LocationKind.STORAGE
                and location.code == parameters.get("target_location_code")
            )
        return False
    if task.object_type == "logistic_shipment":
        return get_task_shipment(db, task.object_uid).status == ShipmentStatus.COMPLETED
    if task.object_type == "logistic_inventory":
        return get_task_inventory(db, task.object_uid).status == InventoryStatus.COMPLETED
    if task.object_type == "logistic_transfer":
        transfer = get_task_transfer(db, task.object_uid)
        if parameters.get("phase") == "dispatch":
            return transfer.status in {
                TransferStatus.IN_TRANSIT,
                TransferStatus.RECEIVING,
                TransferStatus.COMPLETED,
            }
        return transfer.status == TransferStatus.COMPLETED
    return False


def complete_logistic_task(
    db: Session,
    task_uid: str,
    *,
    actor: str,
) -> LogisticTask:
    task = get_logistic_task(db, task_uid, for_update=True)
    if task.status == TaskStatus.COMPLETED:
        return task
    if task.status == TaskStatus.CANCELLED:
        raise bad_request("cancelled task cannot be completed")
    if task.status != TaskStatus.IN_PROGRESS:
        raise bad_request("task must be started before completion")
    if task.assigned_to and task.assigned_to != actor:
        raise bad_request("task is assigned to another operator")
    if not task_operation_is_complete(db, task):
        raise bad_request("bound warehouse operation is not complete")
    before = {"status": task.status.value, "assigned_to": task.assigned_to}
    task.status = TaskStatus.COMPLETED
    task.completed_at = utcnow()
    create_event(
        db,
        operation="logistic_task_completed",
        object_type="logistic_task",
        object_uid=task.task_uid,
        actor=actor,
        before=before,
        after={
            "status": task.status.value,
            "assigned_to": task.assigned_to,
            "object_status": task_object_status(db, task),
        },
    )
    db.commit()
    db.refresh(task)
    return task


def cancel_logistic_task(
    db: Session,
    task_uid: str,
    *,
    actor: str,
) -> LogisticTask:
    task = get_logistic_task(db, task_uid, for_update=True)
    if task.status == TaskStatus.COMPLETED:
        raise bad_request("completed task cannot be cancelled")
    if task.status == TaskStatus.CANCELLED:
        return task
    before = {"status": task.status.value, "assigned_to": task.assigned_to}
    task.status = TaskStatus.CANCELLED
    task.completed_at = utcnow()
    create_event(
        db,
        operation="logistic_task_cancelled",
        object_type="logistic_task",
        object_uid=task.task_uid,
        actor=actor,
        before=before,
        after={"status": task.status.value},
    )
    db.commit()
    db.refresh(task)
    return task


def reopen_logistic_task(
    db: Session,
    task_uid: str,
    *,
    actor: str,
) -> LogisticTask:
    task = get_logistic_task(db, task_uid, for_update=True)
    if task.status not in {TaskStatus.COMPLETED, TaskStatus.CANCELLED}:
        raise bad_request("only a closed task can be reopened")
    before = {"status": task.status.value}
    task.status = TaskStatus.NEW
    task.started_at = None
    task.completed_at = None
    create_event(
        db,
        operation="logistic_task_reopened",
        object_type="logistic_task",
        object_uid=task.task_uid,
        actor=actor,
        before=before,
        after={"status": task.status.value},
    )
    db.commit()
    db.refresh(task)
    return task
