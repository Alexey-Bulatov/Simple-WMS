from decimal import Decimal

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.session import Base, get_db
from app.logistic_documents import create_logistic_transfer
from app.main import app
from app.models.entities import (
    Location,
    LogisticTask,
    LogisticTransferAllocation,
    Product,
    StockDocument,
    StockOwner,
    StockPosition,
    UnitOfMeasure,
    Warehouse,
    Zone,
)
from app.models.enums import (
    LocationKind,
    StockReservationResult,
    StockReservationStatus,
    TaskStatus,
    TransferStatus,
)
from app.quantitative_transfers import (
    dispatch_transfer_quantities,
    pick_transfer_quantities,
    receive_transfer_quantities,
    reserve_transfer_quantities,
)
from app.schemas import (
    LogisticTransferCreate,
    LogisticTransferDispatchQuantityRequest,
    LogisticTransferLineCreate,
    LogisticTransferPickQuantityRequest,
    LogisticTransferReceiveQuantityRequest,
    LogisticTransferReserveQuantityRequest,
    ProductCreate,
)
from app.services import create_product, ensure_reference_catalogs
from app.stock import stock_position_payload
from app.stock_search import search_stock


@pytest.fixture()
def db():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    testing_session = sessionmaker(
        bind=engine,
        autoflush=False,
        autocommit=False,
        expire_on_commit=False,
    )
    session = testing_session()
    try:
        yield session
    finally:
        session.close()


def reference(db, model, code: str):
    return db.scalar(select(model).where(model.code == code))


def add_location(db, warehouse, code: str, kind: LocationKind):
    zone = Zone(
        warehouse_id=warehouse.id,
        code=f"Z-{code}",
        name=kind.value,
        kind=kind,
    )
    db.add(zone)
    db.flush()
    location = Location(
        warehouse_id=warehouse.id,
        zone_id=zone.id,
        code=code,
        kind=kind,
        capacity_units=50,
    )
    db.add(location)
    db.flush()
    return location


def transfer_context(db, *, quantities=("4", "6")):
    ensure_reference_catalogs(db)
    pieces = reference(db, UnitOfMeasure, "PCS")
    owner = reference(db, StockOwner, "INTERNAL")
    product = create_product(
        db,
        ProductCreate(code="GLOVES-TRF", name="Перчатки", base_uom_id=pieces.id),
    )
    source = Warehouse(code="WH-TRF-A", name="Склад-источник")
    destination = Warehouse(code="WH-TRF-B", name="Склад-получатель")
    db.add_all([source, destination])
    db.flush()
    storages = [
        add_location(db, source, f"WH-TRF-A-ST-{index}", LocationKind.STORAGE)
        for index in range(1, len(quantities) + 1)
    ]
    transfer_out = add_location(
        db, source, "WH-TRF-A-OUT-1", LocationKind.TRANSFER_OUT
    )
    transfer_in = add_location(
        db, destination, "WH-TRF-B-IN-1", LocationKind.TRANSFER_IN
    )
    wrong_transfer_in = add_location(
        db, source, "WH-TRF-A-IN-1", LocationKind.TRANSFER_IN
    )
    positions = [
        StockPosition(
            product_id=product.id,
            owner_id=owner.id,
            quality_status="released",
            quantity=Decimal(quantity),
            location_id=location.id,
        )
        for location, quantity in zip(storages, quantities, strict=True)
    ]
    db.add_all(positions)
    db.commit()
    return (
        product,
        pieces,
        owner,
        source,
        destination,
        storages,
        transfer_out,
        transfer_in,
        wrong_transfer_in,
        positions,
    )


def create_quantity_transfer(db, product, pieces, owner, *, quantity="8"):
    return create_logistic_transfer(
        db,
        LogisticTransferCreate(
            source_warehouse_code="WH-TRF-A",
            destination_warehouse_code="WH-TRF-B",
            vehicle_number="A001AA",
            actor="dispatcher",
            lines=[
                LogisticTransferLineCreate(
                    product_id=product.id,
                    owner_id=owner.id,
                    input_quantity=Decimal(quantity),
                    input_uom_id=pieces.id,
                )
            ],
        ),
    )


def reserve(db, transfer, *, key="transfer:reserve:1"):
    return reserve_transfer_quantities(
        db,
        transfer.transfer_uid,
        LogisticTransferReserveQuantityRequest(
            idempotency_key=key,
            allow_partial=True,
            actor="dispatcher",
            reason="Резерв для межскладской передачи",
        ),
    )


def test_quantity_transfer_moves_stock_through_transit_to_destination(db):
    (
        product,
        pieces,
        owner,
        source,
        destination,
        _,
        transfer_out,
        transfer_in,
        _,
        _,
    ) = transfer_context(db)
    transfer = create_quantity_transfer(db, product, pieces, owner)

    reserve(db, transfer)
    assert transfer.status == TransferStatus.RESERVED
    assert transfer.lines[0].reservation_result == StockReservationResult.FULL
    assert transfer.lines[0].reserved_base_quantity == Decimal("8")
    assert len(transfer.lines[0].allocations) == 2

    pick_transfer_quantities(
        db,
        transfer.transfer_uid,
        LogisticTransferPickQuantityRequest(
            transfer_out_location_code=transfer_out.code,
            idempotency_key="transfer:pick:1",
            actor="picker",
            reason="Отбор в исходящую зону",
        ),
    )
    assert transfer.status == TransferStatus.EXPEDITION
    assert transfer.lines[0].picked_base_quantity == Decimal("8")
    assert all(
        allocation.reservation.status == StockReservationStatus.CONSUMED
        for allocation in transfer.lines[0].allocations
    )
    transfer_out_position = db.scalar(
        select(StockPosition).where(StockPosition.location_id == transfer_out.id)
    )
    assert transfer_out_position.quantity == Decimal("8")

    dispatch_payload = LogisticTransferDispatchQuantityRequest(
        idempotency_key="transfer:dispatch:1",
        actor="loader",
        reason="Отправка в путь",
    )
    dispatch_transfer_quantities(db, transfer.transfer_uid, dispatch_payload)
    dispatch_transfer_quantities(db, transfer.transfer_uid, dispatch_payload)
    assert transfer.status == TransferStatus.IN_TRANSIT
    assert transfer.lines[0].dispatched_base_quantity == Decimal("8")
    assert db.scalar(
        select(StockPosition).where(StockPosition.location_id == transfer_out.id)
    ) is None
    transit_item = search_stock(
        db,
        product.code,
        warehouse_scope=None,
        warehouse_id=source.id,
    )["items"][0]
    assert transit_item["total_quantity"] == Decimal("10")
    assert transit_item["available_quantity"] == Decimal("2")
    assert transit_item["in_transit_quantity"] == Decimal("8")

    receive_payload = LogisticTransferReceiveQuantityRequest(
        transfer_in_location_code=transfer_in.code,
        idempotency_key="transfer:receive:1",
        actor="receiver",
        reason="Полная приёмка передачи",
    )
    receive_transfer_quantities(db, transfer.transfer_uid, receive_payload)
    receive_transfer_quantities(db, transfer.transfer_uid, receive_payload)

    assert transfer.status == TransferStatus.COMPLETED
    assert transfer.lines[0].received_base_quantity == Decimal("8")
    destination_position = db.scalar(
        select(StockPosition).where(StockPosition.location_id == transfer_in.id)
    )
    assert destination_position.quantity == Decimal("8")
    assert stock_position_payload(db, destination_position)["warehouse_id"] == destination.id
    destination_item = search_stock(
        db,
        product.code,
        warehouse_scope=None,
        warehouse_id=destination.id,
    )["items"][0]
    assert destination_item["total_quantity"] == Decimal("8")
    assert destination_item["available_quantity"] == Decimal("0")
    assert destination_item["in_transit_quantity"] == Decimal("0")

    documents = list(
        db.scalars(
            select(StockDocument)
            .where(StockDocument.reference_uid == transfer.transfer_uid)
            .order_by(StockDocument.id)
        )
    )
    assert [item.document_type for item in documents] == [
        "transfer_pick",
        "transfer_dispatch",
        "transfer_receive",
    ]
    assert documents[0].movements[0].source_warehouse_id == source.id
    assert documents[0].movements[0].destination_warehouse_id == source.id
    assert documents[1].movements[0].source_warehouse_id == source.id
    assert documents[1].movements[0].destination_warehouse_id is None
    assert documents[2].movements[0].source_warehouse_id is None
    assert documents[2].movements[0].destination_warehouse_id == destination.id

    tasks = list(
        db.scalars(
            select(LogisticTask).where(LogisticTask.object_uid == transfer.transfer_uid)
        )
    )
    assert tasks
    assert all(task.status == TaskStatus.COMPLETED for task in tasks)


def test_quantity_transfer_rejects_wrong_receiving_warehouse(db):
    (
        product,
        pieces,
        owner,
        _,
        _,
        _,
        transfer_out,
        _,
        wrong_transfer_in,
        _,
    ) = transfer_context(db, quantities=("8",))
    transfer = create_quantity_transfer(db, product, pieces, owner)
    reserve(db, transfer)
    pick_transfer_quantities(
        db,
        transfer.transfer_uid,
        LogisticTransferPickQuantityRequest(
            transfer_out_location_code=transfer_out.code,
            idempotency_key="transfer:pick:wrong-in",
            actor="picker",
            reason="Отбор",
        ),
    )
    dispatch_transfer_quantities(
        db,
        transfer.transfer_uid,
        LogisticTransferDispatchQuantityRequest(
            idempotency_key="transfer:dispatch:wrong-in",
            actor="loader",
            reason="Отправка",
        ),
    )
    with pytest.raises(HTTPException, match="must belong to destination warehouse"):
        receive_transfer_quantities(
            db,
            transfer.transfer_uid,
            LogisticTransferReceiveQuantityRequest(
                transfer_in_location_code=wrong_transfer_in.code,
                idempotency_key="transfer:receive:wrong-in",
                actor="receiver",
                reason="Неверный склад",
            ),
        )


def test_quantity_transfer_api_exposes_full_line_progress(db):
    (
        product,
        pieces,
        owner,
        _,
        _,
        _,
        transfer_out,
        transfer_in,
        _,
        _,
    ) = transfer_context(db, quantities=("8",))

    def override_db():
        yield db

    app.dependency_overrides[get_db] = override_db
    try:
        with TestClient(app) as client:
            created = client.post(
                "/api/logistic-transfers",
                json={
                    "source_warehouse_code": "WH-TRF-A",
                    "destination_warehouse_code": "WH-TRF-B",
                    "vehicle_number": "A001AA",
                    "actor": "api-test",
                    "lines": [
                        {
                            "product_id": product.id,
                            "owner_id": owner.id,
                            "input_quantity": "8",
                            "input_uom_id": pieces.id,
                        }
                    ],
                },
            )
            assert created.status_code == 200, created.text
            transfer_uid = created.json()["transfer_uid"]
            assert created.json()["quantity_line_count"] == 1

            assert client.post(
                f"/api/logistic-transfers/{transfer_uid}/reserve-quantities",
                json={
                    "idempotency_key": "api:transfer:reserve",
                    "allow_partial": False,
                    "actor": "api-test",
                },
            ).status_code == 200
            assert client.post(
                f"/api/logistic-transfers/{transfer_uid}/pick-quantities",
                json={
                    "transfer_out_location_code": transfer_out.code,
                    "idempotency_key": "api:transfer:pick",
                    "actor": "api-test",
                    "reason": "Отбор",
                },
            ).status_code == 200
            dispatched = client.post(
                f"/api/logistic-transfers/{transfer_uid}/dispatch-quantities",
                json={
                    "idempotency_key": "api:transfer:dispatch",
                    "actor": "api-test",
                    "reason": "Отправка",
                },
            )
            assert dispatched.status_code == 200, dispatched.text
            assert dispatched.json()["quantity_dispatched_line_count"] == 1
            received = client.post(
                f"/api/logistic-transfers/{transfer_uid}/receive-quantities",
                json={
                    "transfer_in_location_code": transfer_in.code,
                    "idempotency_key": "api:transfer:receive",
                    "actor": "api-test",
                    "reason": "Приёмка",
                },
            )
            assert received.status_code == 200, received.text
            body = received.json()
            assert body["status"] == "completed"
            assert body["quantity_received_line_count"] == 1
            assert body["lines"][0]["received_base_quantity"] == "8.000000"
            assert body["receiving_stock_document_uid"]

            detail = client.get(f"/api/logistic-transfers/{transfer_uid}")
            assert detail.status_code == 200
            assert detail.json()["quantity_line_count"] == 1
    finally:
        app.dependency_overrides.clear()
