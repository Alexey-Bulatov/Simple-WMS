from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.constants import CODE_SEPARATOR, TASK_CODE_PREFIX
from app.models.entities import (
    InventorySession,
    Location,
    Pallet,
    Shipment,
    ShipmentPallet,
    Warehouse,
    WarehouseTask,
    WarehouseTransfer,
    utcnow,
)
from app.models.enums import (
    InventoryStatus,
    LocationKind,
    PalletStatus,
    ShipmentStatus,
    TaskPriority,
    TaskStatus,
    TaskType,
    TransferStatus,
)
from app.schemas import TaskCreate
from app.services import bad_request, create_event, not_found


TASK_OBJECT_TYPES = {
    TaskType.BUILD: "pallet",
    TaskType.PLACE: "pallet",
    TaskType.MOVE: "pallet",
    TaskType.SHIP: "shipment",
    TaskType.INVENTORY: "inventory",
    TaskType.TRANSFER: "transfer",
}

TASK_TITLES = {
    TaskType.BUILD: "Завершить формирование палеты",
    TaskType.PLACE: "Разместить палету",
    TaskType.MOVE: "Переместить палету",
    TaskType.SHIP: "Обработать отгрузку",
    TaskType.INVENTORY: "Продолжить инвентаризацию",
    TaskType.TRANSFER: "Обработать межскладское перемещение",
}


def generate_task_uid(db: Session) -> str:
    while True:
        candidate = f"{TASK_CODE_PREFIX}{CODE_SEPARATOR}{uuid4().hex[:10].upper()}"
        if db.scalar(select(WarehouseTask.id).where(WarehouseTask.task_uid == candidate)) is None:
            return candidate


def get_task(db: Session, task_uid: str) -> WarehouseTask:
    task = db.scalar(select(WarehouseTask).where(WarehouseTask.task_uid == task_uid))
    if task is None:
        raise not_found("task")
    return task


def task_payload(db: Session, task: WarehouseTask) -> dict:
    warehouse = db.get(Warehouse, task.warehouse_id)
    return {
        "id": task.id,
        "task_uid": task.task_uid,
        "warehouse_id": task.warehouse_id,
        "warehouse_code": warehouse.code if warehouse else "-",
        "warehouse_name": warehouse.name if warehouse else "-",
        "task_type": task.task_type,
        "status": task.status,
        "priority": task.priority,
        "title": task.title,
        "description": task.description,
        "object_type": task.object_type,
        "object_uid": task.object_uid,
        "assigned_to": task.assigned_to,
        "created_by": task.created_by,
        "created_at": task.created_at,
        "started_at": task.started_at,
        "completed_at": task.completed_at,
    }


def create_task(db: Session, payload: TaskCreate, *, commit: bool = True) -> WarehouseTask:
    warehouse = db.scalar(select(Warehouse).where(Warehouse.code == payload.warehouse_code))
    if warehouse is None:
        raise not_found("warehouse")
    title = (payload.title or "").strip() or TASK_TITLES[payload.task_type]
    object_type = (payload.object_type or "").strip() or TASK_OBJECT_TYPES[payload.task_type]
    object_uid = (payload.object_uid or "").strip() or None
    task = WarehouseTask(
        task_uid=generate_task_uid(db),
        warehouse_id=warehouse.id,
        task_type=payload.task_type,
        priority=payload.priority,
        title=title,
        description=(payload.description or "").strip() or None,
        object_type=object_type,
        object_uid=object_uid,
        assigned_to=(payload.assigned_to or "").strip() or None,
        created_by=payload.actor,
    )
    db.add(task)
    db.flush()
    create_event(
        db,
        operation="task_created",
        object_type="task",
        object_uid=task.task_uid,
        actor=payload.actor,
        after={
            "warehouse_code": warehouse.code,
            "task_type": task.task_type,
            "priority": task.priority,
            "object_uid": task.object_uid,
            "assigned_to": task.assigned_to,
        },
    )
    if commit:
        db.commit()
        db.refresh(task)
    return task


def start_task(db: Session, *, task_uid: str, actor: str) -> WarehouseTask:
    task = get_task(db, task_uid)
    if task.status in {TaskStatus.COMPLETED, TaskStatus.CANCELLED}:
        raise bad_request(f"task cannot be started from status {task.status}")
    if task.assigned_to and task.assigned_to != actor:
        raise bad_request("task is assigned to another operator")
    before = {"status": task.status, "assigned_to": task.assigned_to}
    task.status = TaskStatus.IN_PROGRESS
    task.assigned_to = actor
    task.started_at = task.started_at or utcnow()
    create_event(
        db,
        operation="task_started",
        object_type="task",
        object_uid=task.task_uid,
        actor=actor,
        before=before,
        after={"status": task.status, "assigned_to": task.assigned_to},
    )
    db.commit()
    db.refresh(task)
    return task


def assign_task(db: Session, *, task_uid: str, assigned_to: str | None, actor: str) -> WarehouseTask:
    task = get_task(db, task_uid)
    if task.status in {TaskStatus.COMPLETED, TaskStatus.CANCELLED}:
        raise bad_request(f"task cannot be assigned from status {task.status}")
    before = {"assigned_to": task.assigned_to, "status": task.status}
    task.assigned_to = (assigned_to or "").strip() or None
    create_event(
        db,
        operation="task_assigned" if task.assigned_to else "task_unassigned",
        object_type="task",
        object_uid=task.task_uid,
        actor=actor,
        before=before,
        after={"assigned_to": task.assigned_to, "status": task.status},
    )
    db.commit()
    db.refresh(task)
    return task


def cancel_task(db: Session, *, task_uid: str, actor: str) -> WarehouseTask:
    task = get_task(db, task_uid)
    if task.status == TaskStatus.COMPLETED:
        raise bad_request("completed task cannot be cancelled")
    if task.status == TaskStatus.CANCELLED:
        return task
    before = {"status": task.status, "assigned_to": task.assigned_to}
    task.status = TaskStatus.CANCELLED
    task.completed_at = utcnow()
    create_event(
        db,
        operation="task_cancelled",
        object_type="task",
        object_uid=task.task_uid,
        actor=actor,
        before=before,
        after={"status": task.status, "assigned_to": task.assigned_to},
    )
    db.commit()
    db.refresh(task)
    return task


def reopen_task(db: Session, *, task_uid: str, actor: str) -> WarehouseTask:
    task = get_task(db, task_uid)
    if task.status not in {TaskStatus.COMPLETED, TaskStatus.CANCELLED}:
        raise bad_request("only closed task can be reopened")
    before = {"status": task.status, "assigned_to": task.assigned_to}
    task.status = TaskStatus.NEW
    task.started_at = None
    task.completed_at = None
    create_event(
        db,
        operation="task_reopened",
        object_type="task",
        object_uid=task.task_uid,
        actor=actor,
        before=before,
        after={"status": task.status, "assigned_to": task.assigned_to},
    )
    db.commit()
    db.refresh(task)
    return task


def complete_task(db: Session, *, task_uid: str, actor: str, automatic: bool = False) -> WarehouseTask:
    task = get_task(db, task_uid)
    if task.status == TaskStatus.CANCELLED:
        raise bad_request("cancelled task cannot be completed")
    if task.status == TaskStatus.COMPLETED:
        return task
    before = {"status": task.status, "assigned_to": task.assigned_to}
    task.status = TaskStatus.COMPLETED
    task.assigned_to = task.assigned_to or actor
    task.completed_at = utcnow()
    create_event(
        db,
        operation="task_completed_automatically" if automatic else "task_completed",
        object_type="task",
        object_uid=task.task_uid,
        actor=actor,
        before=before,
        after={"status": task.status, "assigned_to": task.assigned_to},
    )
    db.commit()
    db.refresh(task)
    return task


def _object_is_complete(db: Session, task: WarehouseTask) -> bool:
    if not task.object_uid:
        return False
    if task.task_type in {TaskType.BUILD, TaskType.PLACE}:
        pallet = db.scalar(select(Pallet).where(Pallet.pallet_uid == task.object_uid))
        if pallet is None:
            return False
        if task.task_type == TaskType.BUILD:
            return pallet.status != PalletStatus.OPEN
        location = db.get(Location, pallet.current_location_id) if pallet.current_location_id else None
        return bool(location and location.kind == LocationKind.STORAGE)
    if task.task_type == TaskType.SHIP:
        shipment = db.scalar(select(Shipment).where(Shipment.shipment_uid == task.object_uid))
        return bool(shipment and shipment.status in {ShipmentStatus.COMPLETED, ShipmentStatus.CANCELLED})
    if task.task_type == TaskType.INVENTORY:
        inventory = db.scalar(
            select(InventorySession).where(InventorySession.inventory_uid == task.object_uid)
        )
        return bool(inventory and inventory.status == InventoryStatus.COMPLETED)
    if task.task_type == TaskType.TRANSFER:
        transfer = db.scalar(
            select(WarehouseTransfer).where(WarehouseTransfer.transfer_uid == task.object_uid)
        )
        return bool(transfer and transfer.status in {TransferStatus.COMPLETED, TransferStatus.CANCELLED})
    return False


def _has_task(db: Session, task_type: TaskType, object_uid: str, *, active_only: bool = False) -> bool:
    stmt = select(WarehouseTask.id).where(
        WarehouseTask.task_type == task_type,
        WarehouseTask.object_uid == object_uid,
    )
    if active_only:
        stmt = stmt.where(WarehouseTask.status.in_({TaskStatus.NEW, TaskStatus.IN_PROGRESS}))
    return db.scalar(stmt) is not None


def _auto_task(
    db: Session,
    *,
    warehouse: Warehouse,
    task_type: TaskType,
    object_uid: str,
    priority: TaskPriority,
    actor: str,
    description: str | None = None,
    active_only: bool = False,
) -> None:
    if _has_task(db, task_type, object_uid, active_only=active_only):
        return
    create_task(
        db,
        TaskCreate(
            warehouse_code=warehouse.code,
            task_type=task_type,
            priority=priority,
            description=description,
            object_type=TASK_OBJECT_TYPES[task_type],
            object_uid=object_uid,
            actor=actor,
        ),
        commit=False,
    )


def sync_tasks(db: Session, *, warehouse_code: str, actor: str = "system") -> list[WarehouseTask]:
    warehouse = db.scalar(select(Warehouse).where(Warehouse.code == warehouse_code))
    if warehouse is None:
        raise not_found("warehouse")

    active_tasks = list(
        db.scalars(
            select(WarehouseTask).where(
                WarehouseTask.status.in_({TaskStatus.NEW, TaskStatus.IN_PROGRESS})
            )
        )
    )
    for task in active_tasks:
        if _object_is_complete(db, task):
            task.status = TaskStatus.COMPLETED
            task.completed_at = utcnow()
            create_event(
                db,
                operation="task_completed_automatically",
                object_type="task",
                object_uid=task.task_uid,
                actor=actor,
                after={"status": task.status, "object_uid": task.object_uid},
            )

    pallets = list(
        db.scalars(
            select(Pallet).where(Pallet.status.in_({PalletStatus.OPEN, PalletStatus.WAITING_PLACEMENT}))
        )
    )
    for pallet in pallets:
        location = db.get(Location, pallet.current_location_id) if pallet.current_location_id else None
        if location is not None and location.warehouse_id != warehouse.id:
            continue
        task_type = TaskType.BUILD if pallet.status == PalletStatus.OPEN else TaskType.PLACE
        priority = TaskPriority.NORMAL if task_type == TaskType.BUILD else TaskPriority.HIGH
        _auto_task(
            db,
            warehouse=warehouse,
            task_type=task_type,
            object_uid=pallet.pallet_uid,
            priority=priority,
            actor=actor,
            description=f"Палета {pallet.pallet_uid}",
        )

    inventories = db.scalars(
        select(InventorySession).where(
            InventorySession.warehouse_id == warehouse.id,
            InventorySession.status == InventoryStatus.OPEN,
        )
    )
    for inventory in inventories:
        _auto_task(
            db,
            warehouse=warehouse,
            task_type=TaskType.INVENTORY,
            object_uid=inventory.inventory_uid,
            priority=TaskPriority.NORMAL,
            actor=actor,
        )

    transfers = db.scalars(
        select(WarehouseTransfer).where(
            WarehouseTransfer.status.not_in({TransferStatus.COMPLETED, TransferStatus.CANCELLED})
        )
    )
    for transfer in transfers:
        work_warehouse_id = (
            transfer.destination_warehouse_id
            if transfer.status in {TransferStatus.IN_TRANSIT, TransferStatus.RECEIVING}
            else transfer.source_warehouse_id
        )
        active_transfer_task = db.scalar(
            select(WarehouseTask)
            .where(
                WarehouseTask.task_type == TaskType.TRANSFER,
                WarehouseTask.object_uid == transfer.transfer_uid,
                WarehouseTask.status.in_({TaskStatus.NEW, TaskStatus.IN_PROGRESS}),
            )
            .order_by(WarehouseTask.created_at.desc())
        )
        if active_transfer_task is not None and active_transfer_task.warehouse_id != work_warehouse_id:
            before = {
                "status": active_transfer_task.status,
                "warehouse_id": active_transfer_task.warehouse_id,
                "assigned_to": active_transfer_task.assigned_to,
            }
            active_transfer_task.status = TaskStatus.COMPLETED
            active_transfer_task.completed_at = utcnow()
            create_event(
                db,
                operation="task_completed_automatically",
                object_type="task",
                object_uid=active_transfer_task.task_uid,
                actor=actor,
                before=before,
                after={
                    "status": active_transfer_task.status,
                    "warehouse_id": work_warehouse_id,
                    "reason": "transfer_handoff",
                },
            )
        if work_warehouse_id != warehouse.id:
            continue
        priority = (
            TaskPriority.HIGH
            if transfer.status in {TransferStatus.IN_TRANSIT, TransferStatus.RECEIVING, TransferStatus.LOADING}
            else TaskPriority.NORMAL
        )
        _auto_task(
            db,
            warehouse=warehouse,
            task_type=TaskType.TRANSFER,
            object_uid=transfer.transfer_uid,
            priority=priority,
            actor=actor,
            active_only=True,
        )

    shipments = db.scalars(
        select(Shipment).where(Shipment.status.not_in({ShipmentStatus.COMPLETED, ShipmentStatus.CANCELLED}))
    )
    for shipment in shipments:
        existing_task = db.scalar(
            select(WarehouseTask).where(
                WarehouseTask.task_type == TaskType.SHIP,
                WarehouseTask.object_uid == shipment.shipment_uid,
            )
        )
        if existing_task is not None:
            continue
        linked_warehouse_id = db.scalar(
            select(Location.warehouse_id)
            .join(Pallet, Pallet.current_location_id == Location.id)
            .join(ShipmentPallet, ShipmentPallet.pallet_id == Pallet.id)
            .where(ShipmentPallet.shipment_id == shipment.id)
            .limit(1)
        )
        if linked_warehouse_id is not None and linked_warehouse_id != warehouse.id:
            continue
        priority = TaskPriority.HIGH if shipment.status in {ShipmentStatus.EXPEDITION, ShipmentStatus.LOADING} else TaskPriority.NORMAL
        _auto_task(
            db,
            warehouse=warehouse,
            task_type=TaskType.SHIP,
            object_uid=shipment.shipment_uid,
            priority=priority,
            actor=actor,
        )

    db.commit()
    return list(
        db.scalars(
            select(WarehouseTask)
            .where(
                WarehouseTask.warehouse_id == warehouse.id,
                WarehouseTask.status.in_({TaskStatus.NEW, TaskStatus.IN_PROGRESS}),
            )
            .order_by(WarehouseTask.created_at)
        )
    )
