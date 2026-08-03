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
    confirm_logistic_inventory_missing,
    logistic_inventory_payload,
    move_logistic_inventory_unit_to_actual,
    place_logistic_inventory_found_unit,
    scan_logistic_inventory_location,
    scan_logistic_inventory_unit,
    start_logistic_inventory,
)
from app.main import app
from app.models.entities import LogisticUnit, LogisticUnitType
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
    LogisticUnitActionRequest,
    LogisticUnitChildRequest,
    LogisticUnitCreate,
    LogisticUnitLocationRequest,
    LocationCreate,
    WarehouseCreate,
    ZoneCreate,
)
from app.services import (
    add_logistic_unit_child,
    close_logistic_unit,
    create_location,
    create_logistic_unit,
    create_warehouse,
    create_zone,
    ensure_reference_catalogs,
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


def warehouse_layout(
    db,
    code: str = "WH-A",
    *,
    capacity: int = 1,
) -> tuple:
    warehouse = create_warehouse(
        db,
        WarehouseCreate(code=code, name=f"Склад {code}"),
    )
    storage_zone = create_zone(
        db,
        ZoneCreate(
            warehouse_id=warehouse.id,
            code="ST",
            name="Хранение",
            kind=LocationKind.STORAGE,
        ),
    )
    receiving_zone = create_zone(
        db,
        ZoneCreate(
            warehouse_id=warehouse.id,
            code="RCV",
            name="Приёмка",
            kind=LocationKind.RECEIVING,
        ),
    )
    first = create_location(
        db,
        LocationCreate(
            warehouse_id=warehouse.id,
            zone_id=storage_zone.id,
            code=f"{code}-ST-01",
            kind=LocationKind.STORAGE,
            capacity_units=capacity,
        ),
    )
    second = create_location(
        db,
        LocationCreate(
            warehouse_id=warehouse.id,
            zone_id=storage_zone.id,
            code=f"{code}-ST-02",
            kind=LocationKind.STORAGE,
            capacity_units=capacity,
        ),
    )
    receiving = create_location(
        db,
        LocationCreate(
            warehouse_id=warehouse.id,
            zone_id=receiving_zone.id,
            code=f"{code}-RCV-01",
            kind=LocationKind.RECEIVING,
            capacity_units=10,
        ),
    )
    return warehouse, first, second, receiving


def unit_type(db, code: str) -> LogisticUnitType:
    ensure_reference_catalogs(db)
    return db.scalar(
        select(LogisticUnitType).where(LogisticUnitType.code == code)
    )


def closed_unit(db, uid: str, type_code: str = "PALLET") -> LogisticUnit:
    item = create_logistic_unit(
        db,
        LogisticUnitCreate(
            type_id=unit_type(db, type_code).id,
            uid=uid,
            actor="test",
        ),
    )
    return close_logistic_unit(
        db,
        item.uid,
        LogisticUnitActionRequest(actor="test"),
    )


def available_unit(db, uid: str, location_code: str) -> LogisticUnit:
    item = closed_unit(db, uid)
    return place_logistic_unit(
        db,
        item.uid,
        LogisticUnitLocationRequest(
            location_code=location_code,
            actor="test",
        ),
    )


def scan_location(db, inventory_uid: str, location_code: str):
    return scan_logistic_inventory_location(
        db,
        inventory_uid,
        LogisticInventoryLocationRequest(
            location_code=location_code,
            actor="auditor",
        ),
    )


def scan_unit(
    db,
    inventory_uid: str,
    unit_uid: str,
    *,
    finish_location: bool = False,
):
    return scan_logistic_inventory_unit(
        db,
        inventory_uid,
        LogisticInventoryUnitRequest(
            unit_uid=unit_uid,
            finish_location=finish_location,
            actor="auditor",
        ),
    )


def test_inventory_walkthrough_requires_every_location(db):
    _, first, second, _ = warehouse_layout(db)
    unit = available_unit(db, "PLT-INV-001", first.code)
    inventory = start_logistic_inventory(
        db,
        LogisticInventoryStartRequest(
            warehouse_code="WH-A",
            actor="auditor",
        ),
    )
    initial = logistic_inventory_payload(db, inventory)
    assert initial["total_locations"] == 2
    assert initial["expected_count"] == 1
    assert initial["unchecked_locations"] == 2

    scan_location(db, inventory.inventory_uid, first.code)
    scan_unit(db, inventory.inventory_uid, unit.uid)
    confirm_logistic_inventory_location(
        db,
        inventory.inventory_uid,
        actor="auditor",
    )
    with pytest.raises(HTTPException, match="unchecked locations"):
        complete_logistic_inventory(
            db,
            inventory.inventory_uid,
            actor="auditor",
        )

    scan_location(db, inventory.inventory_uid, second.code)
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
    result = logistic_inventory_payload(db, inventory)

    assert inventory.status == InventoryStatus.COMPLETED
    assert result["progress_percent"] == 100
    assert result["scanned_count"] == 1
    assert result["unresolved_problem_count"] == 0
    assert all(
        row["status"] == InventoryLocationStatus.CHECKED
        for row in result["locations"]
    )


def test_empty_location_records_and_resolves_missing_unit(db):
    _, first, second, _ = warehouse_layout(db)
    unit = available_unit(db, "PLT-INV-MISSING", first.code)
    inventory = start_logistic_inventory(
        db,
        LogisticInventoryStartRequest(warehouse_code="WH-A"),
    )

    scan_location(db, inventory.inventory_uid, first.code)
    confirm_logistic_inventory_location(
        db,
        inventory.inventory_uid,
        actor="auditor",
        require_empty=True,
    )
    scan_location(db, inventory.inventory_uid, second.code)
    confirm_logistic_inventory_location(
        db,
        inventory.inventory_uid,
        actor="auditor",
        require_empty=True,
    )
    before = logistic_inventory_payload(db, inventory)
    assert before["missing_count"] == 1
    assert before["unresolved_problem_count"] == 1
    assert before["lines"][0]["status"] == InventoryLineStatus.MISSING

    confirm_logistic_inventory_missing(
        db,
        inventory.inventory_uid,
        unit.uid,
        LogisticInventoryResolveRequest(
            actor="manager",
            reason="Недостача подтверждена",
        ),
    )
    after = logistic_inventory_payload(db, inventory)
    assert after["unresolved_problem_count"] == 0
    assert after["lines"][0]["resolution_action"] == "missing_confirmed"
    assert all(
        row["status"] == InventoryLocationStatus.CHECKED
        for row in after["locations"]
    )


def test_multi_unit_location_stays_open_until_last_scan(db):
    _, first, second, _ = warehouse_layout(db, capacity=10)
    first_unit = available_unit(db, "PLT-INV-MULTI-01", first.code)
    second_unit = available_unit(db, "PLT-INV-MULTI-02", first.code)
    inventory = start_logistic_inventory(
        db,
        LogisticInventoryStartRequest(warehouse_code="WH-A"),
    )

    scan_location(db, inventory.inventory_uid, first.code)
    scan_logistic_inventory_unit(
        db,
        inventory.inventory_uid,
        LogisticInventoryUnitRequest(
            unit_uid=first_unit.uid,
            actor="auditor",
        ),
    )
    assert inventory.current_location_id == first.id
    scan_logistic_inventory_unit(
        db,
        inventory.inventory_uid,
        LogisticInventoryUnitRequest(
            unit_uid=second_unit.uid,
            finish_location=True,
            actor="auditor",
        ),
    )
    assert inventory.current_location_id is None

    scan_location(db, inventory.inventory_uid, second.code)
    confirm_logistic_inventory_location(
        db,
        inventory.inventory_uid,
        actor="auditor",
        require_empty=True,
    )
    result = logistic_inventory_payload(db, inventory)
    assert result["scanned_count"] == 2
    assert result["missing_count"] == 0


def test_wrong_location_can_be_accepted_as_fact(db):
    _, first, second, _ = warehouse_layout(db)
    unit = available_unit(db, "PLT-INV-WRONG", first.code)
    inventory = start_logistic_inventory(
        db,
        LogisticInventoryStartRequest(warehouse_code="WH-A"),
    )

    scan_location(db, inventory.inventory_uid, second.code)
    scan_unit(db, inventory.inventory_uid, unit.uid)
    confirm_logistic_inventory_location(
        db,
        inventory.inventory_uid,
        actor="auditor",
    )
    scan_location(db, inventory.inventory_uid, first.code)
    confirm_logistic_inventory_location(
        db,
        inventory.inventory_uid,
        actor="auditor",
        require_empty=True,
    )
    before = logistic_inventory_payload(db, inventory)
    assert before["wrong_location_count"] == 1
    assert before["unresolved_problem_count"] == 1

    move_logistic_inventory_unit_to_actual(
        db,
        inventory.inventory_uid,
        unit.uid,
        LogisticInventoryResolveRequest(
            actor="manager",
            reason="Фактическое место подтверждено",
        ),
    )
    after = logistic_inventory_payload(db, inventory)
    assert unit.current_location_id == second.id
    assert after["unresolved_problem_count"] == 0
    assert after["lines"][0]["resolution_action"] == "moved_to_actual"


def test_found_closed_unit_can_be_placed_to_actual_location(db):
    _, first, second, _ = warehouse_layout(db)
    inventory = start_logistic_inventory(
        db,
        LogisticInventoryStartRequest(warehouse_code="WH-A"),
    )
    found = closed_unit(db, "IBC-INV-EXTRA", type_code="IBC")

    scan_location(db, inventory.inventory_uid, first.code)
    scan_unit(db, inventory.inventory_uid, found.uid)
    confirm_logistic_inventory_location(
        db,
        inventory.inventory_uid,
        actor="auditor",
    )
    scan_location(db, inventory.inventory_uid, second.code)
    confirm_logistic_inventory_location(
        db,
        inventory.inventory_uid,
        actor="auditor",
        require_empty=True,
    )
    before = logistic_inventory_payload(db, inventory)
    assert before["extra_count"] == 1

    place_logistic_inventory_found_unit(
        db,
        inventory.inventory_uid,
        found.uid,
        LogisticInventoryResolveRequest(
            actor="manager",
            reason="Единица найдена при обходе",
        ),
    )
    assert found.status == LogisticUnitStatus.AVAILABLE
    assert found.current_location_id == first.id
    assert logistic_inventory_payload(db, inventory)[
        "unresolved_problem_count"
    ] == 0


def test_snapshot_counts_parent_but_not_nested_unit_or_receiving(db):
    _, first, _, receiving = warehouse_layout(db)
    child = closed_unit(db, "BOX-INV-NESTED", type_code="BOX")
    parent = create_logistic_unit(
        db,
        LogisticUnitCreate(
            type_id=unit_type(db, "PALLET").id,
            uid="PLT-INV-PARENT",
        ),
    )
    add_logistic_unit_child(
        db,
        parent.uid,
        LogisticUnitChildRequest(child_uid=child.uid),
    )
    close_logistic_unit(db, parent.uid, LogisticUnitActionRequest())
    place_logistic_unit(
        db,
        parent.uid,
        LogisticUnitLocationRequest(location_code=first.code),
    )
    receiving_unit = closed_unit(db, "IBC-INV-RCV", type_code="IBC")
    receiving_unit.current_location_id = receiving.id
    db.commit()

    inventory = start_logistic_inventory(
        db,
        LogisticInventoryStartRequest(warehouse_code="WH-A"),
    )
    result = logistic_inventory_payload(db, inventory)

    assert result["total_locations"] == 2
    assert result["expected_count"] == 1
    assert [line["unit_uid"] for line in result["lines"]] == [parent.uid]


def test_logistic_inventory_api_flow(db):
    _, first, second, _ = warehouse_layout(db)
    unit = available_unit(db, "PLT-INV-API", first.code)

    def override_db():
        yield db

    app.dependency_overrides[get_db] = override_db
    try:
        with TestClient(app) as client:
            created = client.post(
                "/api/logistic-inventories",
                json={"warehouse_code": "WH-A", "actor": "api-test"},
            )
            assert created.status_code == 200
            inventory_uid = created.json()["inventory_uid"]
            assert inventory_uid.startswith("LINV-")

            assert client.post(
                f"/api/logistic-inventories/{inventory_uid}/scan-location",
                json={"location_code": first.code, "actor": "api-test"},
            ).status_code == 200
            scanned = client.post(
                f"/api/logistic-inventories/{inventory_uid}/scan-unit",
                json={"unit_uid": unit.uid, "actor": "api-test"},
            )
            assert scanned.status_code == 200
            assert scanned.json()["scanned_count"] == 1
            assert scanned.json()["current_location_code"] is None

            assert client.post(
                f"/api/logistic-inventories/{inventory_uid}/scan-location",
                json={"location_code": second.code, "actor": "api-test"},
            ).status_code == 200
            assert client.post(
                f"/api/logistic-inventories/{inventory_uid}/empty",
                json={"actor": "api-test"},
            ).status_code == 200
            completed = client.post(
                f"/api/logistic-inventories/{inventory_uid}/complete",
                json={"actor": "api-test"},
            )
            assert completed.status_code == 200
            assert completed.json()["status"] == "completed"
            assert completed.json()["progress_percent"] == 100

            listed = client.get(
                "/api/logistic-inventories",
                params={"status": "completed"},
            )
            assert listed.status_code == 200
            assert [item["inventory_uid"] for item in listed.json()] == [
                inventory_uid
            ]
    finally:
        app.dependency_overrides.clear()
