import hashlib
from decimal import Decimal
from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.constants import CODE_SEPARATOR, LOGISTIC_TASK_CODE_PREFIX
from app.models.entities import (
    InboundReceipt,
    InboundReceiptResult,
    Location,
    LogisticInventory,
    LogisticShipment,
    LogisticTask,
    LogisticTransfer,
    LogisticTransferAllocation,
    LogisticTransferLine,
    LogisticUnit,
    StockDocument,
    Warehouse,
    utcnow,
)
from app.models.enums import (
    InboundReceiptStatus,
    InventoryStatus,
    LocationKind,
    LogisticUnitStatus,
    ShipmentStatus,
    TaskPriority,
    TaskStatus,
    TaskType,
    TransferStatus,
)
from app.schemas import (
    InboundReceiptPutawayRequest,
    LogisticTaskCreate,
    StockDocumentPost,
    StockMovementPost,
)
from app.services import (
    bad_request,
    commit_or_409,
    conflict,
    create_event,
    get_active_location,
    not_found,
)
from app.stock import effective_logistic_unit_holder


TASK_OBJECT_TYPES = {
    TaskType.BUILD: "logistic_unit",
    TaskType.PLACE: "logistic_unit",
    TaskType.RECEIPT_CONTROL: "inbound_receipt",
    TaskType.PUTAWAY: "inbound_receipt",
    TaskType.MOVE: "logistic_unit",
    TaskType.SHIP: "logistic_shipment",
    TaskType.INVENTORY: "logistic_inventory",
    TaskType.TRANSFER: "logistic_transfer",
}

TASK_TITLES = {
    TaskType.BUILD: "Завершить формирование логистической единицы",
    TaskType.PLACE: "Разместить логистическую единицу",
    TaskType.RECEIPT_CONTROL: "Проверить расхождения приёмки",
    TaskType.PUTAWAY: "Разместить принятый товар",
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
    "inbound_receipt": "/api/inbound-receipts",
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


def get_task_transfer_allocation(
    db: Session,
    transfer: LogisticTransfer,
    parameters: dict,
    *,
    for_update: bool = False,
) -> LogisticTransferAllocation:
    allocation_id = parameters.get("transfer_allocation_id")
    if not isinstance(allocation_id, int):
        raise bad_request("transfer putaway task requires transfer_allocation_id")
    query = (
        select(LogisticTransferAllocation)
        .join(LogisticTransferAllocation.line)
        .where(
            LogisticTransferAllocation.id == allocation_id,
            LogisticTransferLine.transfer_id == transfer.id,
        )
    )
    if for_update:
        query = query.with_for_update()
    allocation = db.scalar(query)
    if allocation is None:
        raise bad_request("allocation does not belong to the logistic transfer")
    return allocation


def get_task_inbound_receipt(db: Session, object_uid: str) -> InboundReceipt:
    receipt = db.scalar(
        select(InboundReceipt).where(
            InboundReceipt.uid == object_uid.strip().upper()
        )
    )
    if receipt is None:
        raise not_found("inbound_receipt")
    return receipt


def get_task_inbound_result(
    db: Session,
    receipt: InboundReceipt,
    parameters: dict,
    *,
    for_update: bool = False,
) -> InboundReceiptResult:
    result_id = parameters.get("receipt_result_id")
    if not isinstance(result_id, int):
        raise bad_request("putaway task requires receipt_result_id")
    query = (
        select(InboundReceiptResult)
        .join(InboundReceiptResult.receipt_line)
        .where(
            InboundReceiptResult.id == result_id,
            InboundReceiptResult.receipt_line.has(receipt_id=receipt.id),
        )
    )
    if for_update:
        query = query.with_for_update()
    result = db.scalar(query)
    if result is None:
        raise bad_request("receipt result does not belong to the inbound receipt")
    return result


def inbound_receipt_has_discrepancies(receipt: InboundReceipt) -> bool:
    for line in receipt.lines:
        received = sum(
            (result.received_base_quantity for result in line.results),
            Decimal("0"),
        )
        if received != line.expected_base_quantity:
            return True
        if line.batch_number is not None and {
            result.batch.batch_number if result.batch else None
            for result in line.results
        } != {line.batch_number}:
            return True
        if line.serial_number is not None and {
            result.serial_number for result in line.results
        } != {line.serial_number}:
            return True
        if {result.quality_status for result in line.results} != {line.quality_status}:
            return True
    return False


def receipt_control_completed(db: Session, receipt_uid: str) -> bool:
    return db.scalar(
        select(LogisticTask.id).where(
            LogisticTask.task_type == TaskType.RECEIPT_CONTROL,
            LogisticTask.object_uid == receipt_uid,
            LogisticTask.status == TaskStatus.COMPLETED,
        )
    ) is not None


def task_object_status(db: Session, task: LogisticTask) -> str | None:
    if task.object_type == "logistic_unit":
        return get_task_unit(db, task.object_uid).status.value
    if task.object_type == "logistic_shipment":
        return get_task_shipment(db, task.object_uid).status.value
    if task.object_type == "logistic_inventory":
        return get_task_inventory(db, task.object_uid).status.value
    if task.object_type == "logistic_transfer":
        transfer = get_task_transfer(db, task.object_uid)
        if task.task_type == TaskType.PUTAWAY:
            allocation = get_task_transfer_allocation(
                db, transfer, task.parameters or {}
            )
            return "placed" if allocation.placement_stock_document_id else "ready"
        return transfer.status.value
    if task.object_type == "inbound_receipt":
        receipt = get_task_inbound_receipt(db, task.object_uid)
        if task.task_type == TaskType.PUTAWAY:
            result = get_task_inbound_result(db, receipt, task.parameters or {})
            return "placed" if result.placement_stock_document_id else "ready"
        return receipt.status.value
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


def validate_inbound_receipt_task(
    db: Session,
    *,
    warehouse: Warehouse,
    task_type: TaskType,
    object_uid: str,
    parameters: dict,
) -> InboundReceipt:
    receipt = get_task_inbound_receipt(db, object_uid)
    if receipt.warehouse_id != warehouse.id:
        raise bad_request("inbound receipt belongs to another warehouse")
    if receipt.status != InboundReceiptStatus.POSTED:
        raise bad_request("inbound receipt task requires a posted receipt")
    if task_type == TaskType.RECEIPT_CONTROL:
        if not inbound_receipt_has_discrepancies(receipt):
            raise bad_request("inbound receipt has no discrepancies to control")
        return receipt
    if inbound_receipt_has_discrepancies(receipt) and not receipt_control_completed(
        db, receipt.uid
    ):
        raise bad_request("inbound receipt discrepancies must be controlled first")
    result = get_task_inbound_result(db, receipt, parameters)
    if result.placement_stock_document_id is not None:
        raise bad_request("receipt result is already placed")
    if result.destination_location_id is None:
        raise bad_request("logistic unit receipt result uses the unit placement workflow")
    source = db.get(Location, result.destination_location_id)
    if source is None or source.kind != LocationKind.RECEIVING:
        raise bad_request("putaway task requires stock in a receiving location")
    if result.quality_status != "released":
        raise bad_request("quarantine stock cannot be placed without a quality decision")
    return receipt


def validate_document_task(
    db: Session,
    *,
    warehouse: Warehouse,
    task_type: TaskType,
    object_uid: str,
    parameters: dict,
) -> object:
    if task_type == TaskType.PUTAWAY and "transfer_allocation_id" in parameters:
        transfer = get_task_transfer(db, object_uid)
        if transfer.destination_warehouse_id != warehouse.id:
            raise bad_request("transfer putaway belongs to destination warehouse")
        if transfer.status != TransferStatus.COMPLETED:
            raise bad_request("transfer must be received before putaway")
        allocation = get_task_transfer_allocation(db, transfer, parameters)
        if allocation.placement_stock_document_id is not None:
            raise bad_request("transfer allocation is already placed")
        source = allocation.transfer_in_location
        if (
            allocation.status != "received"
            or source is None
            or source.kind != LocationKind.TRANSFER_IN
            or source.warehouse_id != transfer.destination_warehouse_id
        ):
            raise bad_request("transfer allocation is not ready for putaway")
        if allocation.line.quality_status != "released":
            raise bad_request("quarantine stock cannot be placed without a quality decision")
        return transfer
    if task_type in {TaskType.RECEIPT_CONTROL, TaskType.PUTAWAY}:
        return validate_inbound_receipt_task(
            db,
            warehouse=warehouse,
            task_type=task_type,
            object_uid=object_uid,
            parameters=parameters,
        )
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
    *,
    commit: bool = True,
    automatic: bool = False,
) -> LogisticTask:
    warehouse = db.scalar(
        select(Warehouse)
        .where(Warehouse.code == payload.warehouse_code.strip().upper())
        .with_for_update()
    )
    if warehouse is None:
        raise not_found("warehouse")
    object_uid = payload.object_uid.strip().upper()
    parameters = normalize_task_parameters(
        db,
        warehouse=warehouse,
        task_type=payload.task_type,
        parameters=payload.parameters,
    )
    object_type = TASK_OBJECT_TYPES[payload.task_type]
    if (
        payload.task_type == TaskType.PUTAWAY
        and "transfer_allocation_id" in parameters
    ):
        object_type = "logistic_transfer"
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
    duplicate = active_logistic_task(
        db,
        task_type=payload.task_type,
        object_uid=object_uid,
        phase=(parameters.get("phase") if payload.task_type == TaskType.TRANSFER else None),
        receipt_result_id=(
            parameters.get("receipt_result_id")
            if payload.task_type == TaskType.PUTAWAY
            else None
        ),
        transfer_allocation_id=(
            parameters.get("transfer_allocation_id")
            if payload.task_type == TaskType.PUTAWAY
            else None
        ),
    )
    if duplicate is not None:
        if not automatic and (duplicate.parameters or {}).get(
            "generated_automatically"
        ):
            return duplicate
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
        operation=(
            "logistic_task_created_automatically"
            if automatic
            else "logistic_task_created"
        ),
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
    if commit:
        commit_or_409(db, "logistic task identifier conflicts with existing data")
        db.refresh(task)
    else:
        db.flush()
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
        if task.task_type == TaskType.PUTAWAY:
            allocation = get_task_transfer_allocation(db, transfer, parameters)
            return allocation.placement_stock_document_id is not None
        if parameters.get("phase") == "dispatch":
            return transfer.status in {
                TransferStatus.IN_TRANSIT,
                TransferStatus.RECEIVING,
                TransferStatus.COMPLETED,
            }
        return transfer.status == TransferStatus.COMPLETED
    if task.object_type == "inbound_receipt":
        receipt = get_task_inbound_receipt(db, task.object_uid)
        if receipt.status != InboundReceiptStatus.POSTED:
            return False
        if task.task_type == TaskType.RECEIPT_CONTROL:
            return inbound_receipt_has_discrepancies(receipt)
        if task.task_type == TaskType.PUTAWAY:
            result = get_task_inbound_result(db, receipt, parameters)
            return result.placement_stock_document_id is not None
    return False


def active_logistic_task(
    db: Session,
    *,
    task_type: TaskType,
    object_uid: str,
    phase: str | None = None,
    receipt_result_id: int | None = None,
    transfer_allocation_id: int | None = None,
) -> LogisticTask | None:
    tasks = list(
        db.scalars(
            select(LogisticTask)
            .where(
                LogisticTask.task_type == task_type,
                LogisticTask.object_uid == object_uid.strip().upper(),
                LogisticTask.status.in_(ACTIVE_TASK_STATUSES),
            )
            .order_by(LogisticTask.created_at)
        )
    )
    if phase is None and receipt_result_id is None and transfer_allocation_id is None:
        return tasks[0] if tasks else None
    if transfer_allocation_id is not None:
        return next(
            (
                task
                for task in tasks
                if (task.parameters or {}).get("transfer_allocation_id")
                == transfer_allocation_id
            ),
            None,
        )
    if receipt_result_id is not None:
        return next(
            (
                task
                for task in tasks
                if (task.parameters or {}).get("receipt_result_id")
                == receipt_result_id
            ),
            None,
        )
    return next(
        (
            task
            for task in tasks
            if str((task.parameters or {}).get("phase") or "") == phase
        ),
        None,
    )


def complete_logistic_task_automatically(
    db: Session,
    task: LogisticTask,
    *,
    actor: str,
) -> LogisticTask:
    if task.status not in ACTIVE_TASK_STATUSES:
        return task
    before = {"status": task.status.value, "assigned_to": task.assigned_to}
    task.status = TaskStatus.COMPLETED
    task.completed_at = utcnow()
    create_event(
        db,
        operation="logistic_task_completed_automatically",
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
    return task


def cancel_logistic_task_automatically(
    db: Session,
    task: LogisticTask,
    *,
    actor: str,
) -> LogisticTask:
    if task.status not in ACTIVE_TASK_STATUSES:
        return task
    before = {"status": task.status.value, "assigned_to": task.assigned_to}
    task.status = TaskStatus.CANCELLED
    task.completed_at = utcnow()
    create_event(
        db,
        operation="logistic_task_cancelled_automatically",
        object_type="logistic_task",
        object_uid=task.task_uid,
        actor=actor,
        before=before,
        after={"status": task.status.value},
    )
    return task


def ensure_logistic_task(
    db: Session,
    *,
    warehouse_code: str,
    task_type: TaskType,
    object_uid: str,
    actor: str,
    priority: TaskPriority = TaskPriority.NORMAL,
    title: str | None = None,
    parameters: dict | None = None,
) -> LogisticTask:
    db.flush()
    normalized_parameters = dict(parameters or {})
    phase = (
        str(normalized_parameters.get("phase") or "") or None
        if task_type == TaskType.TRANSFER
        else None
    )
    receipt_result_id = (
        normalized_parameters.get("receipt_result_id")
        if task_type == TaskType.PUTAWAY
        else None
    )
    transfer_allocation_id = (
        normalized_parameters.get("transfer_allocation_id")
        if task_type == TaskType.PUTAWAY
        else None
    )
    existing = active_logistic_task(
        db,
        task_type=task_type,
        object_uid=object_uid,
        phase=phase,
        receipt_result_id=receipt_result_id,
        transfer_allocation_id=transfer_allocation_id,
    )
    if existing is not None:
        return existing
    normalized_parameters["generated_automatically"] = True
    return create_logistic_task(
        db,
        LogisticTaskCreate(
            warehouse_code=warehouse_code,
            task_type=task_type,
            priority=priority,
            title=title,
            object_uid=object_uid,
            parameters=normalized_parameters,
            actor=actor,
        ),
        commit=False,
        automatic=True,
    )


def sync_logistic_unit_tasks(
    db: Session,
    unit: LogisticUnit,
    *,
    actor: str,
) -> None:
    if unit.parent_unit_id is not None:
        return
    db.flush()
    location = (
        db.get(Location, unit.current_location_id)
        if unit.current_location_id is not None
        else None
    )
    warehouse = db.get(Warehouse, location.warehouse_id) if location else None
    for task in list(
        db.scalars(
            select(LogisticTask).where(
                LogisticTask.object_type == "logistic_unit",
                LogisticTask.object_uid == unit.uid,
                LogisticTask.status.in_(ACTIVE_TASK_STATUSES),
            )
        )
    ):
        if task_operation_is_complete(db, task):
            complete_logistic_task_automatically(db, task, actor=actor)
    if unit.status in {
        LogisticUnitStatus.BLOCKED,
        LogisticUnitStatus.QUARANTINE,
        LogisticUnitStatus.DISASSEMBLED,
    }:
        for task in list(
            db.scalars(
                select(LogisticTask).where(
                    LogisticTask.object_type == "logistic_unit",
                    LogisticTask.object_uid == unit.uid,
                    LogisticTask.status.in_(ACTIVE_TASK_STATUSES),
                )
            )
        ):
            cancel_logistic_task_automatically(db, task, actor=actor)
        return
    if warehouse is None:
        return
    if unit.status == LogisticUnitStatus.OPEN:
        place_task = active_logistic_task(
            db,
            task_type=TaskType.PLACE,
            object_uid=unit.uid,
        )
        if place_task is not None:
            cancel_logistic_task_automatically(db, place_task, actor=actor)
        ensure_logistic_task(
            db,
            warehouse_code=warehouse.code,
            task_type=TaskType.BUILD,
            object_uid=unit.uid,
            actor=actor,
            title=f"Завершить формирование {unit.uid}",
        )
    elif (
        unit.status == LogisticUnitStatus.CLOSED
        and location.kind != LocationKind.STORAGE
    ):
        ensure_logistic_task(
            db,
            warehouse_code=warehouse.code,
            task_type=TaskType.PLACE,
            object_uid=unit.uid,
            actor=actor,
            priority=TaskPriority.HIGH,
            title=f"Разместить {unit.uid}",
        )


def sync_logistic_shipment_tasks(
    db: Session,
    shipment: LogisticShipment,
    *,
    actor: str,
) -> None:
    db.flush()
    task = active_logistic_task(
        db,
        task_type=TaskType.SHIP,
        object_uid=shipment.shipment_uid,
    )
    if shipment.status == ShipmentStatus.COMPLETED:
        if task is not None:
            complete_logistic_task_automatically(db, task, actor=actor)
        return
    if shipment.status == ShipmentStatus.CANCELLED:
        if task is not None:
            cancel_logistic_task_automatically(db, task, actor=actor)
        return
    warehouse = db.get(Warehouse, shipment.warehouse_id)
    if warehouse is not None:
        ensure_logistic_task(
            db,
            warehouse_code=warehouse.code,
            task_type=TaskType.SHIP,
            object_uid=shipment.shipment_uid,
            actor=actor,
            priority=TaskPriority.HIGH,
            title=f"Обработать отгрузку {shipment.shipment_uid}",
        )


def sync_logistic_inventory_tasks(
    db: Session,
    inventory: LogisticInventory,
    *,
    actor: str,
) -> None:
    db.flush()
    task = active_logistic_task(
        db,
        task_type=TaskType.INVENTORY,
        object_uid=inventory.inventory_uid,
    )
    if inventory.status == InventoryStatus.COMPLETED:
        if task is not None:
            complete_logistic_task_automatically(db, task, actor=actor)
        return
    warehouse = db.get(Warehouse, inventory.warehouse_id)
    if warehouse is not None:
        ensure_logistic_task(
            db,
            warehouse_code=warehouse.code,
            task_type=TaskType.INVENTORY,
            object_uid=inventory.inventory_uid,
            actor=actor,
            title=f"Провести инвентаризацию {inventory.inventory_uid}",
        )


def sync_logistic_transfer_tasks(
    db: Session,
    transfer: LogisticTransfer,
    *,
    actor: str,
) -> None:
    db.flush()
    dispatch_task = active_logistic_task(
        db,
        task_type=TaskType.TRANSFER,
        object_uid=transfer.transfer_uid,
        phase="dispatch",
    )
    receive_task = active_logistic_task(
        db,
        task_type=TaskType.TRANSFER,
        object_uid=transfer.transfer_uid,
        phase="receive",
    )
    putaway_tasks = list(
        db.scalars(
            select(LogisticTask).where(
                LogisticTask.task_type == TaskType.PUTAWAY,
                LogisticTask.object_type == "logistic_transfer",
                LogisticTask.object_uid == transfer.transfer_uid,
                LogisticTask.status.in_(ACTIVE_TASK_STATUSES),
            )
        )
    )
    if transfer.status == TransferStatus.CANCELLED:
        for task in [dispatch_task, receive_task, *putaway_tasks]:
            if task is not None:
                cancel_logistic_task_automatically(db, task, actor=actor)
        return
    source = db.get(Warehouse, transfer.source_warehouse_id)
    destination = db.get(Warehouse, transfer.destination_warehouse_id)
    if transfer.status in {
        TransferStatus.DRAFT,
        TransferStatus.RESERVED,
        TransferStatus.EXPEDITION,
        TransferStatus.LOADING,
    }:
        if source is not None:
            ensure_logistic_task(
                db,
                warehouse_code=source.code,
                task_type=TaskType.TRANSFER,
                object_uid=transfer.transfer_uid,
                actor=actor,
                title=f"Подготовить передачу {transfer.transfer_uid}",
                parameters={"phase": "dispatch"},
            )
        return
    if dispatch_task is not None:
        complete_logistic_task_automatically(db, dispatch_task, actor=actor)
    if transfer.status in {TransferStatus.IN_TRANSIT, TransferStatus.RECEIVING}:
        if destination is not None:
            ensure_logistic_task(
                db,
                warehouse_code=destination.code,
                task_type=TaskType.TRANSFER,
                object_uid=transfer.transfer_uid,
                actor=actor,
                priority=TaskPriority.HIGH,
                title=f"Принять передачу {transfer.transfer_uid}",
                parameters={"phase": "receive"},
            )
    elif transfer.status == TransferStatus.COMPLETED:
        if receive_task is not None:
            complete_logistic_task_automatically(db, receive_task, actor=actor)
        if destination is None:
            return
        for line in transfer.lines:
            for allocation in line.allocations:
                task = active_logistic_task(
                    db,
                    task_type=TaskType.PUTAWAY,
                    object_uid=transfer.transfer_uid,
                    transfer_allocation_id=allocation.id,
                )
                if allocation.placement_stock_document_id is not None:
                    if task is not None:
                        complete_logistic_task_automatically(db, task, actor=actor)
                    continue
                source = allocation.transfer_in_location
                if (
                    allocation.status != "received"
                    or source is None
                    or source.kind != LocationKind.TRANSFER_IN
                    or line.quality_status != "released"
                ):
                    continue
                ensure_logistic_task(
                    db,
                    warehouse_code=destination.code,
                    task_type=TaskType.PUTAWAY,
                    object_uid=transfer.transfer_uid,
                    actor=actor,
                    priority=TaskPriority.HIGH,
                    title=(
                        f"Разместить передачу {transfer.transfer_uid}: "
                        f"{line.product.code}, {allocation.quantity} "
                        f"{allocation.base_uom.symbol}"
                    ),
                    parameters={
                        "transfer_uid": transfer.transfer_uid,
                        "transfer_allocation_id": allocation.id,
                        "product_code": line.product.code,
                        "product_name": line.product.name,
                        "quantity": str(allocation.quantity),
                        "uom_symbol": allocation.base_uom.symbol,
                        "source_location_code": source.code,
                    },
                )


def putaway_logistic_transfer_allocation(
    db: Session,
    task_uid: str,
    payload: InboundReceiptPutawayRequest,
) -> LogisticTask:
    task = get_logistic_task(db, task_uid, for_update=True)
    if task.task_type != TaskType.PUTAWAY or task.object_type != "logistic_transfer":
        raise bad_request("task is not a transfer putaway task")
    transfer = get_task_transfer(db, task.object_uid)
    allocation = get_task_transfer_allocation(
        db,
        transfer,
        task.parameters or {},
        for_update=True,
    )
    if allocation.placement_stock_document_id is not None:
        document = db.get(StockDocument, allocation.placement_stock_document_id)
        attributes = document.attributes if document is not None else {}
        if (
            document is not None
            and document.idempotency_key == payload.idempotency_key
            and document.actor == payload.actor
            and document.reason == payload.reason
            and attributes.get("target_location_code") == payload.target_location_code
        ):
            return task
        raise conflict("transfer allocation is already placed by another command")
    if task.status != TaskStatus.IN_PROGRESS:
        raise bad_request("putaway task must be started before placement")
    if task.assigned_to and task.assigned_to != payload.actor:
        raise bad_request("task is assigned to another operator")
    if transfer.status != TransferStatus.COMPLETED:
        raise bad_request("transfer must be received before putaway")
    source = allocation.transfer_in_location
    if (
        allocation.status != "received"
        or source is None
        or source.kind != LocationKind.TRANSFER_IN
        or source.warehouse_id != transfer.destination_warehouse_id
    ):
        raise bad_request("transfer allocation is not in a transfer-in location")
    target = get_active_location(db, payload.target_location_code)
    if (
        target.warehouse_id != transfer.destination_warehouse_id
        or target.kind != LocationKind.STORAGE
    ):
        raise bad_request("putaway target must be storage in destination warehouse")
    if allocation.line.quality_status != "released":
        raise bad_request("quarantine stock cannot be placed without a quality decision")

    reservation = allocation.reservation
    stock_payload = StockDocumentPost(
        uid=(
            "TRF-PUT-"
            f"{hashlib.sha256(payload.idempotency_key.encode()).hexdigest()[:20].upper()}"
        ),
        document_type="transfer_putaway",
        reference_type="logistic_transfer_allocation",
        reference_uid=f"{transfer.transfer_uid}:{allocation.id}",
        idempotency_key=payload.idempotency_key,
        actor=payload.actor,
        reason=payload.reason,
        attributes={
            "transfer_id": transfer.id,
            "transfer_uid": transfer.transfer_uid,
            "transfer_allocation_id": allocation.id,
            "task_uid": task.task_uid,
            "source_location_code": source.code,
            "target_location_code": target.code,
        },
        movements=[
            StockMovementPost(
                product_id=reservation.product_id,
                batch_id=reservation.batch_id,
                serial_number=reservation.serial_number,
                owner_id=reservation.owner_id,
                source_quality_status=reservation.quality_status,
                destination_quality_status=reservation.quality_status,
                input_quantity=allocation.quantity,
                input_uom_id=allocation.base_uom_id,
                source_location_id=source.id,
                destination_location_id=target.id,
            )
        ],
    )

    def finalize(document: StockDocument) -> None:
        allocation.status = "placed"
        allocation.storage_location_id = target.id
        allocation.placement_stock_document_id = document.id
        allocation.placed_at = utcnow()
        complete_logistic_task_automatically(db, task, actor=payload.actor)
        create_event(
            db,
            operation="logistic_transfer_quantity_placed",
            object_type="logistic_transfer",
            object_uid=transfer.transfer_uid,
            actor=payload.actor,
            reason=payload.reason,
            before={
                "transfer_allocation_id": allocation.id,
                "location_code": source.code,
            },
            after={
                "transfer_allocation_id": allocation.id,
                "location_code": target.code,
                "stock_document_uid": document.uid,
                "task_uid": task.task_uid,
            },
        )

    from app.stock_ledger import post_stock_document

    post_stock_document(db, stock_payload, before_commit=finalize)
    db.refresh(task)
    return task


def putaway_logistic_task(
    db: Session,
    task_uid: str,
    payload: InboundReceiptPutawayRequest,
) -> LogisticTask:
    task = get_logistic_task(db, task_uid)
    if task.object_type == "inbound_receipt":
        return putaway_inbound_receipt_result(db, task_uid, payload)
    if task.object_type == "logistic_transfer":
        return putaway_logistic_transfer_allocation(db, task_uid, payload)
    raise bad_request("task does not support quantitative putaway")


def sync_inbound_receipt_tasks(
    db: Session,
    receipt: InboundReceipt,
    *,
    actor: str,
) -> None:
    db.flush()
    active_tasks = list(
        db.scalars(
            select(LogisticTask).where(
                LogisticTask.object_type == "inbound_receipt",
                LogisticTask.object_uid == receipt.uid,
                LogisticTask.status.in_(ACTIVE_TASK_STATUSES),
            )
        )
    )
    if receipt.status != InboundReceiptStatus.POSTED:
        for task in active_tasks:
            cancel_logistic_task_automatically(db, task, actor=actor)
        return

    has_discrepancies = inbound_receipt_has_discrepancies(receipt)
    control_done = receipt_control_completed(db, receipt.uid)
    control_task = active_logistic_task(
        db,
        task_type=TaskType.RECEIPT_CONTROL,
        object_uid=receipt.uid,
    )
    if has_discrepancies and not control_done:
        for task in active_tasks:
            if task.task_type == TaskType.PUTAWAY:
                cancel_logistic_task_automatically(db, task, actor=actor)
        if control_task is None:
            ensure_logistic_task(
                db,
                warehouse_code=receipt.warehouse.code,
                task_type=TaskType.RECEIPT_CONTROL,
                object_uid=receipt.uid,
                actor=actor,
                priority=TaskPriority.URGENT,
                title=f"Проверить расхождения {receipt.uid}",
                parameters={
                    "receipt_uid": receipt.uid,
                    "discrepancy_control": True,
                },
            )
        return
    if control_task is not None:
        cancel_logistic_task_automatically(db, control_task, actor=actor)

    synced_units: set[int] = set()
    for line in receipt.lines:
        for result in line.results:
            if result.placement_stock_document_id is not None:
                task = active_logistic_task(
                    db,
                    task_type=TaskType.PUTAWAY,
                    object_uid=receipt.uid,
                    receipt_result_id=result.id,
                )
                if task is not None:
                    complete_logistic_task_automatically(db, task, actor=actor)
                continue
            if result.quality_status != "released":
                continue
            if result.destination_location_id is not None:
                source = db.get(Location, result.destination_location_id)
                if source is None or source.kind != LocationKind.RECEIVING:
                    continue
                ensure_logistic_task(
                    db,
                    warehouse_code=receipt.warehouse.code,
                    task_type=TaskType.PUTAWAY,
                    object_uid=receipt.uid,
                    actor=actor,
                    priority=TaskPriority.HIGH,
                    title=(
                        f"Разместить {line.product.code}: "
                        f"{result.received_base_quantity} {result.base_uom.symbol}"
                    ),
                    parameters={
                        "receipt_uid": receipt.uid,
                        "receipt_result_id": result.id,
                        "product_code": line.product.code,
                        "product_name": line.product.name,
                        "quantity": str(result.received_base_quantity),
                        "uom_symbol": result.base_uom.symbol,
                        "source_location_code": source.code,
                    },
                )
                continue
            unit = result.destination_logistic_unit
            if unit is None:
                continue
            root, location = effective_logistic_unit_holder(db, unit)
            if (
                root.id not in synced_units
                and location is not None
                and location.kind == LocationKind.RECEIVING
            ):
                synced_units.add(root.id)
                sync_logistic_unit_tasks(db, root, actor=actor)


def putaway_inbound_receipt_result(
    db: Session,
    task_uid: str,
    payload: InboundReceiptPutawayRequest,
) -> LogisticTask:
    task = get_logistic_task(db, task_uid, for_update=True)
    if task.task_type != TaskType.PUTAWAY or task.object_type != "inbound_receipt":
        raise bad_request("task is not an inbound putaway task")
    receipt = get_task_inbound_receipt(db, task.object_uid)
    result = get_task_inbound_result(
        db,
        receipt,
        task.parameters or {},
        for_update=True,
    )
    if result.placement_stock_document_id is not None:
        document = db.get(StockDocument, result.placement_stock_document_id)
        attributes = document.attributes if document is not None else {}
        if (
            document is not None
            and document.idempotency_key == payload.idempotency_key
            and document.actor == payload.actor
            and document.reason == payload.reason
            and attributes.get("target_location_code") == payload.target_location_code
        ):
            return task
        raise conflict("receipt result is already placed by another command")
    if task.status != TaskStatus.IN_PROGRESS:
        raise bad_request("putaway task must be started before placement")
    if task.assigned_to and task.assigned_to != payload.actor:
        raise bad_request("task is assigned to another operator")
    if receipt.status != InboundReceiptStatus.POSTED:
        raise bad_request("inbound receipt is not available for placement")
    if inbound_receipt_has_discrepancies(receipt) and not receipt_control_completed(
        db, receipt.uid
    ):
        raise bad_request("inbound receipt discrepancies must be controlled first")
    if result.destination_location_id is None:
        raise bad_request("logistic unit stock must be placed with its logistic unit")
    source = db.get(Location, result.destination_location_id)
    if source is None or source.kind != LocationKind.RECEIVING:
        raise bad_request("receipt stock is not in a receiving location")
    target = get_active_location(db, payload.target_location_code)
    if target.warehouse_id != receipt.warehouse_id or target.kind != LocationKind.STORAGE:
        raise bad_request("putaway target must be a storage location in the receipt warehouse")
    if result.quality_status != "released":
        raise bad_request("quarantine stock cannot be placed without a quality decision")

    stock_payload = StockDocumentPost(
        uid=(
            "PUT-"
            f"{hashlib.sha256(payload.idempotency_key.encode()).hexdigest()[:20].upper()}"
        ),
        document_type="inbound_putaway",
        reference_type="inbound_receipt_result",
        reference_uid=f"{receipt.uid}:{result.id}",
        idempotency_key=payload.idempotency_key,
        actor=payload.actor,
        reason=payload.reason,
        attributes={
            "receipt_id": receipt.id,
            "receipt_uid": receipt.uid,
            "receipt_result_id": result.id,
            "task_uid": task.task_uid,
            "source_location_code": source.code,
            "target_location_code": target.code,
        },
        movements=[
            StockMovementPost(
                product_id=result.receipt_line.product_id,
                batch_id=result.batch_id,
                serial_number=result.serial_number,
                owner_id=result.receipt_line.owner_id,
                source_quality_status=result.quality_status,
                destination_quality_status=result.quality_status,
                input_quantity=result.received_base_quantity,
                input_uom_id=result.base_uom_id,
                source_location_id=source.id,
                destination_location_id=target.id,
            )
        ],
    )

    def finalize(document: StockDocument) -> None:
        result.placement_stock_document_id = document.id
        result.placed_at = utcnow()
        complete_logistic_task_automatically(db, task, actor=payload.actor)
        create_event(
            db,
            operation="inbound_receipt_result_placed",
            object_type="inbound_receipt",
            object_uid=receipt.uid,
            actor=payload.actor,
            reason=payload.reason,
            before={
                "receipt_result_id": result.id,
                "location_code": source.code,
            },
            after={
                "receipt_result_id": result.id,
                "location_code": target.code,
                "stock_document_uid": document.uid,
                "task_uid": task.task_uid,
            },
        )

    from app.stock_ledger import post_stock_document

    post_stock_document(db, stock_payload, before_commit=finalize)
    db.refresh(task)
    return task


def sync_logistic_tasks(
    db: Session,
    *,
    warehouse_code: str,
    actor: str,
) -> list[LogisticTask]:
    warehouse = db.scalar(
        select(Warehouse).where(
            Warehouse.code == warehouse_code.strip().upper()
        )
    )
    if warehouse is None:
        raise not_found("warehouse")
    active_tasks = list(
        db.scalars(
            select(LogisticTask).where(
                LogisticTask.warehouse_id == warehouse.id,
                LogisticTask.status.in_(ACTIVE_TASK_STATUSES),
            )
        )
    )
    for task in active_tasks:
        if task.object_type == "logistic_unit":
            sync_logistic_unit_tasks(
                db,
                get_task_unit(db, task.object_uid),
                actor=actor,
            )
        elif task.object_type == "logistic_shipment":
            sync_logistic_shipment_tasks(
                db,
                get_task_shipment(db, task.object_uid),
                actor=actor,
            )
        elif task.object_type == "logistic_inventory":
            sync_logistic_inventory_tasks(
                db,
                get_task_inventory(db, task.object_uid),
                actor=actor,
            )
        elif task.object_type == "logistic_transfer":
            sync_logistic_transfer_tasks(
                db,
                get_task_transfer(db, task.object_uid),
                actor=actor,
            )
        elif task.object_type == "inbound_receipt":
            sync_inbound_receipt_tasks(
                db,
                get_task_inbound_receipt(db, task.object_uid),
                actor=actor,
            )
    location_ids = select(Location.id).where(Location.warehouse_id == warehouse.id)
    units = list(
        db.scalars(
            select(LogisticUnit).where(
                LogisticUnit.parent_unit_id.is_(None),
                LogisticUnit.current_location_id.in_(location_ids),
                LogisticUnit.status.in_(
                    {LogisticUnitStatus.OPEN, LogisticUnitStatus.CLOSED}
                ),
            )
        )
    )
    for unit in units:
        sync_logistic_unit_tasks(db, unit, actor=actor)
    for shipment in db.scalars(
        select(LogisticShipment).where(
            LogisticShipment.warehouse_id == warehouse.id,
            LogisticShipment.status.in_(
                {
                    ShipmentStatus.DRAFT,
                    ShipmentStatus.RESERVED,
                    ShipmentStatus.EXPEDITION,
                    ShipmentStatus.LOADING,
                }
            ),
        )
    ):
        sync_logistic_shipment_tasks(db, shipment, actor=actor)
    for inventory in db.scalars(
        select(LogisticInventory).where(
            LogisticInventory.warehouse_id == warehouse.id,
            LogisticInventory.status == InventoryStatus.OPEN,
        )
    ):
        sync_logistic_inventory_tasks(db, inventory, actor=actor)
    pending_transfer_putaway_ids = (
        select(LogisticTransferLine.transfer_id)
        .join(LogisticTransferAllocation)
        .where(
            LogisticTransferAllocation.status == "received",
            LogisticTransferAllocation.placement_stock_document_id.is_(None),
        )
    )
    for transfer in db.scalars(
        select(LogisticTransfer).where(
            (
                LogisticTransfer.status.not_in(
                    {TransferStatus.COMPLETED, TransferStatus.CANCELLED}
                )
                | LogisticTransfer.id.in_(pending_transfer_putaway_ids)
            ),
            (
                (LogisticTransfer.source_warehouse_id == warehouse.id)
                | (LogisticTransfer.destination_warehouse_id == warehouse.id)
            ),
        )
    ):
        sync_logistic_transfer_tasks(db, transfer, actor=actor)
    for receipt in db.scalars(
        select(InboundReceipt).where(
            InboundReceipt.warehouse_id == warehouse.id,
            InboundReceipt.status == InboundReceiptStatus.POSTED,
        )
    ):
        sync_inbound_receipt_tasks(db, receipt, actor=actor)
    db.commit()
    return list(
        db.scalars(
            select(LogisticTask)
            .where(
                LogisticTask.warehouse_id == warehouse.id,
                LogisticTask.status.in_(ACTIVE_TASK_STATUSES),
            )
            .order_by(LogisticTask.created_at)
        )
    )


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
    if task.task_type == TaskType.RECEIPT_CONTROL:
        sync_inbound_receipt_tasks(
            db,
            get_task_inbound_receipt(db, task.object_uid),
            actor=actor,
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
    if task.task_type == TaskType.RECEIPT_CONTROL:
        sync_inbound_receipt_tasks(
            db,
            get_task_inbound_receipt(db, task.object_uid),
            actor=actor,
        )
    db.commit()
    db.refresh(task)
    return task
