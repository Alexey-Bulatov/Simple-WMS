from decimal import Decimal

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
    logistic_shipment_payload,
)
from app.main import app
from app.models.entities import (
    Location,
    LogisticShipmentAllocation,
    LogisticTask,
    Product,
    ProductPackaging,
    StockDocument,
    StockOwner,
    StockPosition,
    StockReservation,
    UnitOfMeasure,
    Warehouse,
    Zone,
)
from app.models.enums import (
    LocationKind,
    ShipmentStatus,
    StockReservationResult,
    StockReservationStatus,
    TaskStatus,
    TaskType,
)
from app.quantitative_shipments import (
    load_shipment_quantities,
    pick_shipment_quantities,
    reserve_shipment_quantities,
)
from app.schemas import (
    LogisticDocumentActionRequest,
    LogisticShipmentCreate,
    LogisticShipmentLineCreate,
    LogisticShipmentLoadQuantityRequest,
    LogisticShipmentPickQuantityRequest,
    LogisticShipmentReserveQuantityRequest,
    ProductCreate,
)
from app.services import create_product, ensure_reference_catalogs
from app.stock import stock_position_payload


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


def shipment_context(db, *, quantities=("4", "6")):
    ensure_reference_catalogs(db)
    pieces = reference(db, UnitOfMeasure, "PCS")
    owner = reference(db, StockOwner, "INTERNAL")
    product = create_product(
        db,
        ProductCreate(code="GLOVES-SHIP", name="Перчатки", base_uom_id=pieces.id),
    )
    packaging = ProductPackaging(
        product_id=product.id,
        code="BOX10",
        name="Коробка 10 шт.",
        quantity=Decimal("10"),
        uom_id=pieces.id,
        base_quantity=Decimal("10"),
    )
    warehouse = Warehouse(code="WH-SHIP", name="Склад отгрузки")
    db.add_all([packaging, warehouse])
    db.flush()
    storage_zone = Zone(
        warehouse_id=warehouse.id,
        code="ST01",
        name="Хранение",
        kind=LocationKind.STORAGE,
    )
    expedition_zone = Zone(
        warehouse_id=warehouse.id,
        code="EXP01",
        name="Экспедиция",
        kind=LocationKind.EXPEDITION,
    )
    db.add_all([storage_zone, expedition_zone])
    db.flush()
    storages = [
        Location(
            warehouse_id=warehouse.id,
            zone_id=storage_zone.id,
            code=f"WH-SHIP-ST01-{index:02d}",
            kind=LocationKind.STORAGE,
            capacity_units=20,
        )
        for index in range(1, len(quantities) + 1)
    ]
    expedition = Location(
        warehouse_id=warehouse.id,
        zone_id=expedition_zone.id,
        code="WH-SHIP-EXP01-01",
        kind=LocationKind.EXPEDITION,
        capacity_units=20,
    )
    db.add_all([*storages, expedition])
    db.flush()
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
    return product, pieces, owner, packaging, warehouse, storages, expedition, positions


def create_quantity_shipment(
    db,
    product,
    pieces,
    owner,
    *,
    quantity="8",
    packaging_id=None,
):
    line = LogisticShipmentLineCreate(
        product_id=product.id,
        owner_id=owner.id,
        input_quantity=Decimal(quantity),
        input_uom_id=pieces.id if packaging_id is None else None,
        packaging_id=packaging_id,
    )
    return create_logistic_shipment(
        db,
        LogisticShipmentCreate(
            warehouse_code="WH-SHIP",
            customer_name="Получатель",
            destination="Москва",
            actor="dispatcher",
            lines=[line],
        ),
    )


def reserve(db, shipment, *, key="ship:reserve:1", allow_partial=True):
    return reserve_shipment_quantities(
        db,
        shipment.shipment_uid,
        LogisticShipmentReserveQuantityRequest(
            idempotency_key=key,
            allow_partial=allow_partial,
            actor="dispatcher",
            reason="Резерв под отгрузку",
        ),
    )


def test_quantity_shipment_reserves_across_positions_and_preserves_input_unit(db):
    product, pieces, owner, packaging, _, _, _, positions = shipment_context(db)
    shipment = create_quantity_shipment(
        db,
        product,
        pieces,
        owner,
        quantity="1",
        packaging_id=packaging.id,
    )

    reserve(db, shipment)
    payload = logistic_shipment_payload(db, shipment)

    assert shipment.status == ShipmentStatus.RESERVED
    assert payload["quantity_line_count"] == 1
    assert payload["quantity_ready_line_count"] == 1
    assert payload["lines"][0]["input_quantity"] == Decimal("1")
    assert payload["lines"][0]["packaging_code"] == "BOX10"
    assert payload["lines"][0]["requested_base_quantity"] == Decimal("10")
    assert payload["lines"][0]["reservation_result"] == StockReservationResult.FULL
    assert len(payload["lines"][0]["allocations"]) == 2
    assert sum(
        (item.quantity for item in db.scalars(select(StockReservation))), Decimal("0")
    ) == Decimal("10")
    assert all(stock_position_payload(db, position)["available_quantity"] == 0 for position in positions)


def test_partial_reservation_blocks_pick_and_can_be_topped_up(db):
    product, pieces, owner, _, warehouse, storages, expedition, _ = shipment_context(
        db, quantities=("3",)
    )
    shipment = create_quantity_shipment(db, product, pieces, owner, quantity="5")

    reserve(db, shipment, allow_partial=True)
    assert shipment.lines[0].reservation_result == StockReservationResult.PARTIAL
    assert shipment.lines[0].reserved_base_quantity == Decimal("3")
    with pytest.raises(HTTPException, match="fully reserved"):
        pick_shipment_quantities(
            db,
            shipment.shipment_uid,
            LogisticShipmentPickQuantityRequest(
                expedition_location_code=expedition.code,
                idempotency_key="ship:pick:blocked",
                actor="picker",
                reason="Отбор",
            ),
        )

    second_location = Location(
        warehouse_id=warehouse.id,
        zone_id=storages[0].zone_id,
        code="WH-SHIP-ST01-02",
        kind=LocationKind.STORAGE,
        capacity_units=20,
    )
    db.add(second_location)
    db.flush()
    db.add(
        StockPosition(
            product_id=product.id,
            owner_id=owner.id,
            quality_status="released",
            quantity=Decimal("2"),
            location_id=second_location.id,
        )
    )
    db.commit()

    reserve(db, shipment, key="ship:reserve:2")
    assert shipment.lines[0].reservation_result == StockReservationResult.FULL
    assert shipment.lines[0].reserved_base_quantity == Decimal("5")


def test_disallowed_partial_reservation_returns_none(db):
    product, pieces, owner, _, _, _, _, _ = shipment_context(db, quantities=("3",))
    shipment = create_quantity_shipment(db, product, pieces, owner, quantity="5")

    reserve(db, shipment, allow_partial=False)

    assert shipment.status == ShipmentStatus.DRAFT
    assert shipment.lines[0].reservation_result == StockReservationResult.NONE
    assert shipment.lines[0].reserved_base_quantity == 0
    assert db.scalar(select(StockReservation.id)) is None


def test_quantity_pick_load_and_close_are_atomic_and_idempotent(db):
    product, pieces, owner, _, _, _, expedition, _ = shipment_context(db)
    shipment = create_quantity_shipment(db, product, pieces, owner, quantity="8")
    reserve(db, shipment)

    pick_payload = LogisticShipmentPickQuantityRequest(
        expedition_location_code=expedition.code,
        idempotency_key="ship:pick:1",
        actor="picker",
        reason="Отбор в экспедицию",
    )
    pick_shipment_quantities(db, shipment.shipment_uid, pick_payload)
    pick_shipment_quantities(db, shipment.shipment_uid, pick_payload)

    allocations = list(db.scalars(select(LogisticShipmentAllocation)))
    assert shipment.status == ShipmentStatus.EXPEDITION
    assert shipment.lines[0].picked_base_quantity == Decimal("8")
    assert all(item.status == "picked" for item in allocations)
    assert all(item.reservation.status == StockReservationStatus.CONSUMED for item in allocations)
    expedition_position = db.scalar(
        select(StockPosition).where(StockPosition.location_id == expedition.id)
    )
    assert expedition_position.quantity == Decimal("8")

    load_payload = LogisticShipmentLoadQuantityRequest(
        idempotency_key="ship:load:1",
        actor="loader",
        reason="Фактическая погрузка",
    )
    load_shipment_quantities(db, shipment.shipment_uid, load_payload)
    load_shipment_quantities(db, shipment.shipment_uid, load_payload)
    assert shipment.status == ShipmentStatus.LOADING
    assert shipment.lines[0].loaded_base_quantity == Decimal("8")
    assert db.scalar(select(StockPosition.id).where(StockPosition.location_id == expedition.id)) is None
    assert len(list(db.scalars(select(StockDocument)))) == 2

    close_logistic_shipment(
        db,
        shipment.shipment_uid,
        LogisticDocumentActionRequest(actor="loader", reason="Погрузка завершена"),
    )
    task = db.scalar(
        select(LogisticTask).where(
            LogisticTask.object_uid == shipment.shipment_uid,
            LogisticTask.task_type == TaskType.SHIP,
        )
    )
    assert shipment.status == ShipmentStatus.COMPLETED
    assert task.status == TaskStatus.COMPLETED


def test_quantity_shipment_cannot_close_before_quantity_loading(db):
    product, pieces, owner, _, _, _, _, _ = shipment_context(db)
    shipment = create_quantity_shipment(db, product, pieces, owner, quantity="8")
    reserve(db, shipment)
    shipment.status = ShipmentStatus.LOADING
    db.commit()

    with pytest.raises(HTTPException, match="quantity lines must be loaded"):
        close_logistic_shipment(
            db,
            shipment.shipment_uid,
            LogisticDocumentActionRequest(actor="loader", reason="Рано"),
        )


def test_quantity_pick_does_not_downgrade_mixed_shipment_loading_status(db):
    product, pieces, owner, _, _, _, expedition, _ = shipment_context(db)
    shipment = create_quantity_shipment(db, product, pieces, owner, quantity="8")
    reserve(db, shipment)
    shipment.status = ShipmentStatus.LOADING
    db.commit()

    pick_shipment_quantities(
        db,
        shipment.shipment_uid,
        LogisticShipmentPickQuantityRequest(
            expedition_location_code=expedition.code,
            idempotency_key="ship:mixed:pick:1",
            actor="picker",
            reason="Количественная часть смешанной отгрузки",
        ),
    )

    assert shipment.status == ShipmentStatus.LOADING


def test_quantity_shipment_api_exposes_lines_and_reservation_result(db):
    product, pieces, owner, _, _, _, _, _ = shipment_context(db)

    def override_db():
        yield db

    app.dependency_overrides[get_db] = override_db
    try:
        client = TestClient(app)
        created = client.post(
            "/api/logistic-shipments",
            json={
                "warehouse_code": "WH-SHIP",
                "customer_name": "Получатель API",
                "destination": "Санкт-Петербург",
                "actor": "dispatcher",
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
        assert created.status_code == 200
        shipment_uid = created.json()["shipment_uid"]
        reserved = client.post(
            f"/api/logistic-shipments/{shipment_uid}/reserve-quantities",
            json={
                "idempotency_key": "api:shipment:reserve:1",
                "allow_partial": True,
                "actor": "dispatcher",
                "reason": "API резерв",
            },
        )
        assert reserved.status_code == 200
        assert reserved.json()["quantity_ready_line_count"] == 1
        assert reserved.json()["lines"][0]["reservation_result"] == "full"
    finally:
        app.dependency_overrides.clear()
