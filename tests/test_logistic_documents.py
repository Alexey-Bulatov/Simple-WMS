import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.session import Base, get_db
from app.logistic_documents import (
    close_logistic_shipment,
    create_logistic_shipment,
    create_logistic_transfer,
    dispatch_logistic_transfer,
    load_logistic_shipment_unit,
    load_logistic_transfer_unit,
    receive_logistic_transfer_unit,
    reserve_unit_for_logistic_shipment,
    reserve_unit_for_logistic_transfer,
    stage_logistic_shipment,
    stage_logistic_transfer,
)
from app.main import app
from app.models.entities import LogisticUnit, LogisticUnitType, OperationEvent
from app.models.enums import (
    LocationKind,
    LogisticUnitStatus,
    ShipmentStatus,
    TransferStatus,
)
from app.schemas import (
    LogisticDocumentActionRequest,
    LogisticDocumentStageRequest,
    LogisticDocumentUnitRequest,
    LogisticShipmentCreate,
    LogisticTransferCreate,
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


def warehouse_layout(db, code: str) -> dict:
    warehouse = create_warehouse(
        db,
        WarehouseCreate(code=code, name=f"Склад {code}"),
    )
    result = {"warehouse": warehouse}
    for kind, suffix in (
        (LocationKind.STORAGE, "ST"),
        (LocationKind.EXPEDITION, "EXP"),
        (LocationKind.TRANSFER_OUT, "TOUT"),
        (LocationKind.TRANSFER_IN, "TIN"),
    ):
        zone = create_zone(
            db,
            ZoneCreate(
                warehouse_id=warehouse.id,
                code=suffix,
                name=f"{code} {suffix}",
                kind=kind,
            ),
        )
        result[kind] = create_location(
            db,
            LocationCreate(
                warehouse_id=warehouse.id,
                zone_id=zone.id,
                code=f"{code}-{suffix}-01",
                kind=kind,
                capacity_pallets=10,
            ),
        )
    return result


def available_unit(db, uid: str, storage_code: str) -> LogisticUnit:
    ensure_reference_catalogs(db)
    unit_type = db.scalar(
        select(LogisticUnitType).where(LogisticUnitType.code == "PALLET")
    )
    unit = create_logistic_unit(
        db,
        LogisticUnitCreate(type_id=unit_type.id, uid=uid, actor="test"),
    )
    close_logistic_unit(db, uid, LogisticUnitActionRequest(actor="test"))
    return place_logistic_unit(
        db,
        uid,
        LogisticUnitLocationRequest(location_code=storage_code, actor="test"),
    )


def test_logistic_shipment_requires_complete_loading(db):
    source = warehouse_layout(db, "WH-A")
    first = available_unit(db, "PLT-SHP-001", source[LocationKind.STORAGE].code)
    second = available_unit(db, "PLT-SHP-002", source[LocationKind.STORAGE].code)
    shipment = create_logistic_shipment(
        db,
        LogisticShipmentCreate(
            warehouse_code="WH-A",
            customer_name="Получатель",
            destination="Москва",
            actor="dispatcher",
        ),
    )

    for unit in (first, second):
        reserve_unit_for_logistic_shipment(
            db,
            shipment.shipment_uid,
            LogisticDocumentUnitRequest(unit_uid=unit.uid, actor="dispatcher"),
        )
    stage_logistic_shipment(
        db,
        shipment.shipment_uid,
        LogisticDocumentStageRequest(
            location_code=source[LocationKind.EXPEDITION].code,
            actor="storekeeper",
        ),
    )
    load_logistic_shipment_unit(
        db,
        shipment.shipment_uid,
        LogisticDocumentUnitRequest(unit_uid=first.uid, actor="loader"),
    )

    with pytest.raises(HTTPException, match="all shipment units must be loaded"):
        close_logistic_shipment(
            db,
            shipment.shipment_uid,
            LogisticDocumentActionRequest(actor="loader"),
        )

    load_logistic_shipment_unit(
        db,
        shipment.shipment_uid,
        LogisticDocumentUnitRequest(unit_uid=second.uid, actor="loader"),
    )
    close_logistic_shipment(
        db,
        shipment.shipment_uid,
        LogisticDocumentActionRequest(actor="loader"),
    )

    assert shipment.status == ShipmentStatus.COMPLETED
    assert shipment.closed_at is not None
    assert first.status == LogisticUnitStatus.SHIPPED
    assert second.status == LogisticUnitStatus.SHIPPED
    assert first.current_location_id is None
    operations = set(
        db.scalars(
            select(OperationEvent.operation).where(
                OperationEvent.object_uid == first.uid
            )
        )
    )
    assert {
        "logistic_unit_reserved_for_shipment",
        "logistic_unit_moved_to_shipment_expedition",
        "logistic_unit_loaded_for_shipment",
        "logistic_unit_shipped",
    }.issubset(operations)


def test_logistic_transfer_finishes_at_destination_receiving(db):
    source = warehouse_layout(db, "WH-A")
    destination = warehouse_layout(db, "WH-B")
    unit = available_unit(db, "PLT-TRF-001", source[LocationKind.STORAGE].code)
    transfer = create_logistic_transfer(
        db,
        LogisticTransferCreate(
            source_warehouse_code="WH-A",
            destination_warehouse_code="WH-B",
            vehicle_number="А001АА",
            actor="dispatcher",
        ),
    )

    reserve_unit_for_logistic_transfer(
        db,
        transfer.transfer_uid,
        LogisticDocumentUnitRequest(unit_uid=unit.uid, actor="dispatcher"),
    )
    stage_logistic_transfer(
        db,
        transfer.transfer_uid,
        LogisticDocumentStageRequest(
            location_code=source[LocationKind.TRANSFER_OUT].code,
            actor="storekeeper",
        ),
    )
    load_logistic_transfer_unit(
        db,
        transfer.transfer_uid,
        LogisticDocumentUnitRequest(unit_uid=unit.uid, actor="loader"),
    )
    dispatch_logistic_transfer(
        db,
        transfer.transfer_uid,
        LogisticDocumentActionRequest(actor="loader"),
    )

    with pytest.raises(
        HTTPException,
        match="transfer-in location must belong to the destination warehouse",
    ):
        receive_logistic_transfer_unit(
            db,
            transfer.transfer_uid,
            LogisticDocumentUnitRequest(unit_uid=unit.uid, actor="receiver"),
            source[LocationKind.TRANSFER_IN].code,
        )

    receive_logistic_transfer_unit(
        db,
        transfer.transfer_uid,
        LogisticDocumentUnitRequest(unit_uid=unit.uid, actor="receiver"),
        destination[LocationKind.TRANSFER_IN].code,
    )

    assert transfer.status == TransferStatus.COMPLETED
    assert transfer.dispatched_at is not None
    assert transfer.completed_at is not None
    assert unit.status == LogisticUnitStatus.CLOSED
    assert unit.current_location_id == destination[LocationKind.TRANSFER_IN].id

    place_logistic_unit(
        db,
        unit.uid,
        LogisticUnitLocationRequest(
            location_code=destination[LocationKind.STORAGE].code,
            actor="receiver",
        ),
    )
    assert unit.status == LogisticUnitStatus.AVAILABLE
    assert unit.current_location_id == destination[LocationKind.STORAGE].id


def test_documents_reject_wrong_units_and_warehouses(db):
    source = warehouse_layout(db, "WH-A")
    destination = warehouse_layout(db, "WH-B")
    unit = available_unit(db, "PLT-RULE-001", source[LocationKind.STORAGE].code)
    shipment = create_logistic_shipment(
        db,
        LogisticShipmentCreate(
            warehouse_code="WH-B",
            customer_name="Получатель",
            destination="Казань",
        ),
    )
    with pytest.raises(
        HTTPException,
        match="logistic unit is not stored at the required warehouse",
    ):
        reserve_unit_for_logistic_shipment(
            db,
            shipment.shipment_uid,
            LogisticDocumentUnitRequest(unit_uid=unit.uid),
        )

    with pytest.raises(
        HTTPException,
        match="source and destination warehouses must be different",
    ):
        create_logistic_transfer(
            db,
            LogisticTransferCreate(
                source_warehouse_code="WH-A",
                destination_warehouse_code="WH-A",
            ),
        )

    transfer = create_logistic_transfer(
        db,
        LogisticTransferCreate(
            source_warehouse_code="WH-A",
            destination_warehouse_code="WH-B",
        ),
    )
    reserve_unit_for_logistic_transfer(
        db,
        transfer.transfer_uid,
        LogisticDocumentUnitRequest(unit_uid=unit.uid),
    )
    with pytest.raises(HTTPException, match="transfer-out location must belong"):
        stage_logistic_transfer(
            db,
            transfer.transfer_uid,
            LogisticDocumentStageRequest(
                location_code=destination[LocationKind.TRANSFER_OUT].code
            ),
        )


def test_logistic_document_api_flow(db):
    source = warehouse_layout(db, "WH-A")
    unit = available_unit(db, "PLT-API-SHP-001", source[LocationKind.STORAGE].code)

    def override_db():
        yield db

    app.dependency_overrides[get_db] = override_db
    try:
        with TestClient(app) as client:
            created = client.post(
                "/api/logistic-shipments",
                json={
                    "warehouse_code": "WH-A",
                    "customer_name": "ООО Получатель",
                    "destination": "Санкт-Петербург",
                    "actor": "api-test",
                },
            )
            assert created.status_code == 200
            shipment_uid = created.json()["shipment_uid"]

            reserved = client.post(
                f"/api/logistic-shipments/{shipment_uid}/units",
                json={"unit_uid": unit.uid, "actor": "api-test"},
            )
            assert reserved.status_code == 200
            assert reserved.json()["status"] == "reserved"

            staged = client.post(
                f"/api/logistic-shipments/{shipment_uid}/expedition",
                json={
                    "location_code": source[LocationKind.EXPEDITION].code,
                    "actor": "api-test",
                },
            )
            assert staged.status_code == 200
            loaded = client.post(
                f"/api/logistic-shipments/{shipment_uid}/load",
                json={"unit_uid": unit.uid, "actor": "api-test"},
            )
            assert loaded.status_code == 200
            closed = client.post(
                f"/api/logistic-shipments/{shipment_uid}/close",
                json={"actor": "api-test"},
            )
            assert closed.status_code == 200
            assert closed.json()["status"] == "completed"
            assert closed.json()["units"][0]["unit_status"] == "shipped"

            listed = client.get(
                "/api/logistic-shipments",
                params={"status": "completed"},
            )
            assert listed.status_code == 200
            assert [item["shipment_uid"] for item in listed.json()] == [shipment_uid]
    finally:
        app.dependency_overrides.clear()


def test_logistic_transfer_api_flow(db):
    source = warehouse_layout(db, "WH-A")
    destination = warehouse_layout(db, "WH-B")
    unit = available_unit(db, "PLT-API-TRF-001", source[LocationKind.STORAGE].code)

    def override_db():
        yield db

    app.dependency_overrides[get_db] = override_db
    try:
        with TestClient(app) as client:
            created = client.post(
                "/api/logistic-transfers",
                json={
                    "source_warehouse_code": "WH-A",
                    "destination_warehouse_code": "WH-B",
                    "vehicle_number": "В002ВВ",
                    "actor": "api-test",
                },
            )
            assert created.status_code == 200
            transfer_uid = created.json()["transfer_uid"]

            assert client.post(
                f"/api/logistic-transfers/{transfer_uid}/units",
                json={"unit_uid": unit.uid, "actor": "api-test"},
            ).status_code == 200
            assert client.post(
                f"/api/logistic-transfers/{transfer_uid}/expedition",
                json={
                    "location_code": source[LocationKind.TRANSFER_OUT].code,
                    "actor": "api-test",
                },
            ).status_code == 200
            assert client.post(
                f"/api/logistic-transfers/{transfer_uid}/load",
                json={"unit_uid": unit.uid, "actor": "api-test"},
            ).status_code == 200
            dispatched = client.post(
                f"/api/logistic-transfers/{transfer_uid}/dispatch",
                json={"actor": "api-test"},
            )
            assert dispatched.status_code == 200
            assert dispatched.json()["status"] == "in_transit"

            received = client.post(
                f"/api/logistic-transfers/{transfer_uid}/receive/{unit.uid}",
                json={
                    "location_code": destination[LocationKind.TRANSFER_IN].code,
                    "actor": "api-test",
                },
            )
            assert received.status_code == 200
            assert received.json()["status"] == "completed"
            assert received.json()["received_count"] == 1
            assert received.json()["units"][0]["unit_status"] == "closed"

            listed = client.get(
                "/api/logistic-transfers",
                params={"status": "completed"},
            )
            assert listed.status_code == 200
            assert [item["transfer_uid"] for item in listed.json()] == [transfer_uid]
    finally:
        app.dependency_overrides.clear()
