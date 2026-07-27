import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.session import Base, get_db
from app.logistic_inventory import (
    complete_logistic_inventory,
    confirm_logistic_inventory_location,
    scan_logistic_inventory_location,
    start_logistic_inventory,
)
from app.logistic_tasks import (
    assign_logistic_task,
    cancel_logistic_task,
    complete_logistic_task,
    create_logistic_task,
    reopen_logistic_task,
    start_logistic_task,
)
from app.main import app
from app.models.entities import (
    LogisticShipment,
    LogisticTransfer,
    LogisticUnit,
    LogisticUnitType,
)
from app.models.enums import (
    LocationKind,
    ShipmentStatus,
    TaskPriority,
    TaskStatus,
    TaskType,
    TransferStatus,
)
from app.schemas import (
    LogisticInventoryLocationRequest,
    LogisticInventoryStartRequest,
    LogisticTaskCreate,
    LogisticUnitActionRequest,
    LogisticUnitCreate,
    LogisticUnitLocationRequest,
    LocationCreate,
    WarehouseCreate,
    ZoneCreate,
)
from app.services import (
    close_logistic_unit,
    create_location,
    create_logistic_unit,
    create_warehouse,
    create_zone,
    ensure_reference_catalogs,
    move_logistic_unit,
    place_logistic_unit,
)


@pytest.fixture
def db():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    testing_session = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    session = testing_session()
    try:
        yield session
    finally:
        session.close()


def warehouse_layout(db, code: str = "WH-A") -> tuple:
    warehouse = create_warehouse(
        db,
        WarehouseCreate(code=code, name=f"Склад {code}"),
    )
    zone = create_zone(
        db,
        ZoneCreate(
            warehouse_id=warehouse.id,
            code="ST",
            name="Хранение",
            kind=LocationKind.STORAGE,
        ),
    )
    first = create_location(
        db,
        LocationCreate(
            warehouse_id=warehouse.id,
            zone_id=zone.id,
            code=f"{code}-ST-01",
            kind=LocationKind.STORAGE,
            capacity_pallets=10,
        ),
    )
    second = create_location(
        db,
        LocationCreate(
            warehouse_id=warehouse.id,
            zone_id=zone.id,
            code=f"{code}-ST-02",
            kind=LocationKind.STORAGE,
            capacity_pallets=10,
        ),
    )
    return warehouse, first, second


def open_unit(db, uid: str) -> LogisticUnit:
    ensure_reference_catalogs(db)
    unit_type = db.scalar(
        select(LogisticUnitType).where(LogisticUnitType.code == "PALLET")
    )
    return create_logistic_unit(
        db,
        LogisticUnitCreate(type_id=unit_type.id, uid=uid, actor="test"),
    )


def closed_unit(db, uid: str) -> LogisticUnit:
    unit = open_unit(db, uid)
    return close_logistic_unit(
        db,
        unit.uid,
        LogisticUnitActionRequest(actor="test"),
    )


def available_unit(db, uid: str, location_code: str) -> LogisticUnit:
    unit = closed_unit(db, uid)
    return place_logistic_unit(
        db,
        unit.uid,
        LogisticUnitLocationRequest(
            location_code=location_code,
            actor="test",
        ),
    )


def task_payload(
    *,
    task_type: TaskType,
    object_uid: str,
    parameters: dict | None = None,
    priority: TaskPriority = TaskPriority.NORMAL,
    assigned_to: str | None = None,
) -> LogisticTaskCreate:
    return LogisticTaskCreate(
        warehouse_code="WH-A",
        task_type=task_type,
        object_uid=object_uid,
        parameters=parameters or {},
        priority=priority,
        assigned_to=assigned_to,
        actor="dispatcher",
    )


def test_build_task_completes_only_after_unit_is_closed(db):
    warehouse_layout(db)
    unit = open_unit(db, "PLT-TASK-BUILD")
    task = create_logistic_task(
        db,
        task_payload(task_type=TaskType.BUILD, object_uid=unit.uid),
    )
    start_logistic_task(db, task.task_uid, actor="worker")

    with pytest.raises(HTTPException, match="warehouse operation is not complete"):
        complete_logistic_task(db, task.task_uid, actor="worker")

    close_logistic_unit(
        db,
        unit.uid,
        LogisticUnitActionRequest(actor="worker"),
    )
    complete_logistic_task(db, task.task_uid, actor="worker")
    assert task.status == TaskStatus.COMPLETED
    assert task.assigned_to == "worker"


def test_place_task_checks_requested_storage_location(db):
    _, first, second = warehouse_layout(db)
    unit = closed_unit(db, "PLT-TASK-PLACE")
    task = create_logistic_task(
        db,
        task_payload(
            task_type=TaskType.PLACE,
            object_uid=unit.uid,
            parameters={"target_location_code": second.code},
        ),
    )
    start_logistic_task(db, task.task_uid, actor="worker")
    place_logistic_unit(
        db,
        unit.uid,
        LogisticUnitLocationRequest(
            location_code=first.code,
            actor="worker",
        ),
    )
    with pytest.raises(HTTPException, match="warehouse operation is not complete"):
        complete_logistic_task(db, task.task_uid, actor="worker")

    move_logistic_unit(
        db,
        unit.uid,
        LogisticUnitLocationRequest(
            location_code=second.code,
            actor="worker",
        ),
    )
    complete_logistic_task(db, task.task_uid, actor="worker")
    assert task.status == TaskStatus.COMPLETED


def test_move_task_requires_target_and_assigned_operator(db):
    _, first, second = warehouse_layout(db)
    unit = available_unit(db, "PLT-TASK-MOVE", first.code)

    with pytest.raises(HTTPException, match="requires target_location_code"):
        create_logistic_task(
            db,
            task_payload(task_type=TaskType.MOVE, object_uid=unit.uid),
        )

    task = create_logistic_task(
        db,
        task_payload(
            task_type=TaskType.MOVE,
            object_uid=unit.uid,
            parameters={"target_location_code": second.code.lower()},
            assigned_to="worker",
        ),
    )
    with pytest.raises(HTTPException, match="assigned to another operator"):
        start_logistic_task(db, task.task_uid, actor="other")
    start_logistic_task(db, task.task_uid, actor="worker")
    with pytest.raises(HTTPException, match="warehouse operation is not complete"):
        complete_logistic_task(db, task.task_uid, actor="worker")

    move_logistic_unit(
        db,
        unit.uid,
        LogisticUnitLocationRequest(
            location_code=second.code,
            actor="worker",
        ),
    )
    complete_logistic_task(db, task.task_uid, actor="worker")
    assert task.status == TaskStatus.COMPLETED
    assert task.parameters["target_location_code"] == second.code


def test_duplicate_active_task_and_cancel_reopen_lifecycle(db):
    _, first, second = warehouse_layout(db)
    unit = available_unit(db, "PLT-TASK-LIFE", first.code)
    payload = task_payload(
        task_type=TaskType.MOVE,
        object_uid=unit.uid,
        parameters={"target_location_code": second.code},
    )
    task = create_logistic_task(db, payload)
    with pytest.raises(HTTPException, match="already has an active task"):
        create_logistic_task(db, payload)

    assign_logistic_task(
        db,
        task.task_uid,
        assigned_to="worker",
        actor="dispatcher",
    )
    cancel_logistic_task(db, task.task_uid, actor="dispatcher")
    assert task.status == TaskStatus.CANCELLED
    reopen_logistic_task(db, task.task_uid, actor="dispatcher")
    assert task.status == TaskStatus.NEW
    assert task.started_at is None
    assert task.completed_at is None


def test_inventory_task_waits_for_universal_inventory(db):
    _, first, second = warehouse_layout(db)
    inventory = start_logistic_inventory(
        db,
        LogisticInventoryStartRequest(
            warehouse_code="WH-A",
            actor="auditor",
        ),
    )
    task = create_logistic_task(
        db,
        task_payload(
            task_type=TaskType.INVENTORY,
            object_uid=inventory.inventory_uid,
        ),
    )
    start_logistic_task(db, task.task_uid, actor="auditor")
    with pytest.raises(HTTPException, match="warehouse operation is not complete"):
        complete_logistic_task(db, task.task_uid, actor="auditor")

    for location in (first, second):
        scan_logistic_inventory_location(
            db,
            inventory.inventory_uid,
            LogisticInventoryLocationRequest(
                location_code=location.code,
                actor="auditor",
            ),
        )
        confirm_logistic_inventory_location(
            db,
            inventory.inventory_uid,
            actor="auditor",
            require_empty=True,
        )
    complete_logistic_inventory(
        db,
        inventory.inventory_uid,
        actor="auditor",
    )
    complete_logistic_task(db, task.task_uid, actor="auditor")
    assert task.status == TaskStatus.COMPLETED


@pytest.mark.parametrize(
    ("task_type", "object_kind"),
    [
        (TaskType.SHIP, "shipment"),
        (TaskType.TRANSFER, "transfer"),
    ],
)
def test_document_task_reads_new_document_status(
    db,
    task_type,
    object_kind,
):
    warehouse, _, _ = warehouse_layout(db)
    if object_kind == "shipment":
        document = LogisticShipment(
            shipment_uid="SHP-TASK-DOC",
            warehouse_id=warehouse.id,
            customer_name="Получатель",
            destination="Москва",
        )
    else:
        destination = create_warehouse(
            db,
            WarehouseCreate(code="WH-B", name="Склад WH-B"),
        )
        document = LogisticTransfer(
            transfer_uid="TRF-TASK-DOC",
            source_warehouse_id=warehouse.id,
            destination_warehouse_id=destination.id,
        )
    db.add(document)
    db.commit()
    task = create_logistic_task(
        db,
        task_payload(task_type=task_type, object_uid=(
            document.shipment_uid
            if object_kind == "shipment"
            else document.transfer_uid
        )),
    )
    start_logistic_task(db, task.task_uid, actor="worker")
    if object_kind == "shipment":
        document.status = ShipmentStatus.COMPLETED
    else:
        document.status = TransferStatus.IN_TRANSIT
    db.commit()
    complete_logistic_task(db, task.task_uid, actor="worker")
    assert task.status == TaskStatus.COMPLETED
    if object_kind == "transfer":
        assert task.parameters["phase"] == "dispatch"

        destination_task = create_logistic_task(
            db,
            LogisticTaskCreate(
                warehouse_code="WH-B",
                task_type=TaskType.TRANSFER,
                object_uid=document.transfer_uid,
                actor="dispatcher",
            ),
        )
        assert destination_task.parameters["phase"] == "receive"
        start_logistic_task(
            db,
            destination_task.task_uid,
            actor="receiver",
        )
        with pytest.raises(
            HTTPException,
            match="warehouse operation is not complete",
        ):
            complete_logistic_task(
                db,
                destination_task.task_uid,
                actor="receiver",
            )
        document.status = TransferStatus.COMPLETED
        db.commit()
        complete_logistic_task(
            db,
            destination_task.task_uid,
            actor="receiver",
        )
        assert destination_task.status == TaskStatus.COMPLETED


def test_logistic_task_api_queue_and_lifecycle(db):
    _, first, second = warehouse_layout(db)
    normal_unit = available_unit(db, "PLT-TASK-API-N", first.code)
    urgent_unit = available_unit(db, "PLT-TASK-API-U", first.code)

    def override_db():
        yield db

    app.dependency_overrides[get_db] = override_db
    try:
        with TestClient(app) as client:
            normal = client.post(
                "/api/logistic-tasks",
                json={
                    "warehouse_code": "WH-A",
                    "task_type": "move",
                    "priority": "normal",
                    "object_uid": normal_unit.uid,
                    "parameters": {"target_location_code": second.code},
                    "actor": "api-test",
                },
            )
            assert normal.status_code == 200
            urgent = client.post(
                "/api/logistic-tasks",
                json={
                    "warehouse_code": "WH-A",
                    "task_type": "move",
                    "priority": "urgent",
                    "object_uid": urgent_unit.uid,
                    "parameters": {"target_location_code": second.code},
                    "actor": "api-test",
                },
            )
            assert urgent.status_code == 200
            urgent_uid = urgent.json()["task_uid"]
            assert urgent_uid.startswith("LTSK-")

            listed = client.get(
                "/api/logistic-tasks",
                params={"warehouse_code": "WH-A", "status": "new"},
            )
            assert listed.status_code == 200
            assert [item["priority"] for item in listed.json()] == [
                "urgent",
                "normal",
            ]

            started = client.post(
                f"/api/logistic-tasks/{urgent_uid}/start",
                json={"actor": "worker"},
            )
            assert started.status_code == 200
            premature = client.post(
                f"/api/logistic-tasks/{urgent_uid}/complete",
                json={"actor": "worker"},
            )
            assert premature.status_code == 400

            move_logistic_unit(
                db,
                urgent_unit.uid,
                LogisticUnitLocationRequest(
                    location_code=second.code,
                    actor="worker",
                ),
            )
            completed = client.post(
                f"/api/logistic-tasks/{urgent_uid}/complete",
                json={"actor": "worker"},
            )
            assert completed.status_code == 200
            assert completed.json()["status"] == "completed"
            assert completed.json()["object_status"] == "available"
            assert completed.json()["object_url"].endswith(urgent_unit.uid)
    finally:
        app.dependency_overrides.clear()
