from decimal import Decimal

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api import routes as api_routes
from app.db.session import Base, get_db
from app.main import app
from app.models.entities import (
    Location,
    LogisticUnit,
    LogisticUnitType,
    OperationEvent,
    Product,
    StockDocument,
    StockOwner,
    StockPosition,
    StockReservation,
    UnitOfMeasure,
    Warehouse,
    Zone,
)
from app.models.enums import LocationKind, LogisticUnitStatus, StockReservationStatus
from app.schemas import (
    ProductCreate,
    StockDocumentPost,
    StockMovementPost,
    StockReservationCreate,
    StockReservationReleaseRequest,
)
from app.services import create_product, ensure_reference_catalogs
from app.stock import remove_logistic_unit_stock_positions, stock_position_payload
from app.stock_ledger import post_stock_document
from app.stock_reservations import create_stock_reservation, release_stock_reservation


@pytest.fixture()
def db():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    TestingSession = sessionmaker(
        bind=engine,
        autoflush=False,
        autocommit=False,
        expire_on_commit=False,
    )
    session = TestingSession()
    try:
        yield session
    finally:
        session.close()


def reference(db, model, code: str):
    return db.scalar(select(model).where(model.code == code))


def create_stock_context(db, *, quantity: str = "5"):
    ensure_reference_catalogs(db)
    pieces = reference(db, UnitOfMeasure, "PCS")
    owner = reference(db, StockOwner, "INTERNAL")
    product = create_product(
        db,
        ProductCreate(
            code="GLOVES",
            name="Перчатки",
            base_uom_id=pieces.id,
        ),
    )
    warehouse = Warehouse(code="WH-RSV", name="Склад резервов")
    db.add(warehouse)
    db.flush()
    zone = Zone(
        warehouse_id=warehouse.id,
        code="ST01",
        name="Хранение",
        kind=LocationKind.STORAGE,
    )
    db.add(zone)
    db.flush()
    location = Location(
        warehouse_id=warehouse.id,
        zone_id=zone.id,
        code="WH-RSV-ST01-01",
        name="Ячейка 01",
        kind=LocationKind.STORAGE,
    )
    db.add(location)
    db.flush()
    position = StockPosition(
        product_id=product.id,
        owner_id=owner.id,
        quality_status="released",
        quantity=Decimal(quantity),
        location_id=location.id,
    )
    db.add(position)
    db.commit()
    return product, pieces, owner, location, position


def reserve_command(position, pieces, *, key: str, quantity: str = "3"):
    return StockReservationCreate(
        stock_position_id=position.id,
        input_quantity=Decimal(quantity),
        input_uom_id=pieces.id,
        reference_type="internal_issue",
        reference_uid="ISSUE-001",
        reference_line_uid="LINE-001",
        idempotency_key=key,
        actor="storekeeper",
        reason="Выдача сотруднику",
    )


def release_command(*, key: str, reason: str = "Выдача отменена"):
    return StockReservationReleaseRequest(
        idempotency_key=key,
        actor="senior-storekeeper",
        reason=reason,
    )


def issue_command(product, pieces, owner, location, *, key: str, quantity: str):
    return StockDocumentPost(
        document_type="internal_issue",
        reference_type="test",
        reference_uid="ISSUE-OTHER",
        idempotency_key=key,
        actor="storekeeper",
        movements=[
            StockMovementPost(
                product_id=product.id,
                owner_id=owner.id,
                source_quality_status="released",
                input_quantity=Decimal(quantity),
                input_uom_id=pieces.id,
                source_location_id=location.id,
            )
        ],
    )


def test_reservation_changes_available_quantity_and_release_restores_it(db):
    _, pieces, _, _, position = create_stock_context(db)

    first = create_stock_reservation(
        db,
        reserve_command(position, pieces, key="reserve:issue-001"),
    )
    repeated = create_stock_reservation(
        db,
        reserve_command(position, pieces, key="reserve:issue-001"),
    )

    assert repeated.id == first.id
    assert first.status == StockReservationStatus.ACTIVE
    assert first.quantity == Decimal("3")
    assert stock_position_payload(db, position)["available_quantity"] == Decimal("2")
    assert stock_position_payload(db, position)["reserved_quantity"] == Decimal("3")

    released = release_stock_reservation(
        db,
        first.uid,
        release_command(key="release:issue-001"),
    )
    repeated_release = release_stock_reservation(
        db,
        first.uid,
        release_command(key="release:issue-001"),
    )

    assert repeated_release.id == released.id
    assert released.status == StockReservationStatus.RELEASED
    assert stock_position_payload(db, position)["available_quantity"] == Decimal("5")
    assert stock_position_payload(db, position)["reserved_quantity"] == Decimal("0")
    assert db.scalar(select(func.count(OperationEvent.id))) == 2


def test_reservation_rejects_overbooking_and_protects_reserved_stock(db):
    product, pieces, owner, location, position = create_stock_context(db)
    create_stock_reservation(
        db,
        reserve_command(position, pieces, key="reserve:protected", quantity="3"),
    )

    with pytest.raises(HTTPException, match="insufficient available stock"):
        create_stock_reservation(
            db,
            reserve_command(position, pieces, key="reserve:too-much", quantity="3"),
        )

    post_stock_document(
        db,
        issue_command(
            product,
            pieces,
            owner,
            location,
            key="issue:unreserved-two",
            quantity="2",
        ),
    )
    with pytest.raises(HTTPException, match="insufficient unreserved source stock"):
        post_stock_document(
            db,
            issue_command(
                product,
                pieces,
                owner,
                location,
                key="issue:reserved-one",
                quantity="1",
            ),
        )

    assert db.get(StockPosition, position.id).quantity == Decimal("3")
    assert db.scalar(select(func.count(StockDocument.id))) == 1


def test_active_reservation_blocks_bulk_logistic_unit_stock_removal(db):
    _, pieces, _, location, position = create_stock_context(db)
    box_type = reference(db, LogisticUnitType, "BOX")
    unit = LogisticUnit(
        uid="BOX-RESERVED-001",
        type_id=box_type.id,
        status=LogisticUnitStatus.AVAILABLE,
        current_location_id=location.id,
    )
    db.add(unit)
    db.flush()
    position.location_id = None
    position.logistic_unit_id = unit.id
    db.commit()
    reservation = create_stock_reservation(
        db,
        reserve_command(position, pieces, key="reserve:unit-removal", quantity="2"),
    )

    with pytest.raises(HTTPException, match="active reservation"):
        remove_logistic_unit_stock_positions(db, unit.id)
    assert db.get(StockPosition, position.id) is not None

    release_stock_reservation(
        db,
        reservation.uid,
        release_command(key="release:unit-removal"),
    )
    remove_logistic_unit_stock_positions(db, unit.id)
    db.commit()
    assert db.get(StockPosition, position.id) is None


def test_reservation_and_release_idempotency_keys_reject_changed_commands(db):
    _, pieces, _, _, position = create_stock_context(db)
    reservation = create_stock_reservation(
        db,
        reserve_command(position, pieces, key="reserve:immutable", quantity="2"),
    )

    with pytest.raises(HTTPException, match="another reservation command"):
        create_stock_reservation(
            db,
            reserve_command(position, pieces, key="reserve:immutable", quantity="1"),
        )

    release_stock_reservation(
        db,
        reservation.uid,
        release_command(key="release:immutable"),
    )
    with pytest.raises(HTTPException, match="another reservation release"):
        release_stock_reservation(
            db,
            reservation.uid,
            release_command(key="release:immutable", reason="Другая причина"),
        )
    with pytest.raises(HTTPException, match="already released"):
        release_stock_reservation(
            db,
            reservation.uid,
            release_command(key="release:second-command"),
        )


def test_stale_session_cannot_reserve_the_same_available_quantity_twice(tmp_path):
    engine = create_engine(
        f"sqlite:///{tmp_path / 'reservations.db'}",
        connect_args={"check_same_thread": False, "timeout": 30},
    )
    Base.metadata.create_all(bind=engine)
    TestingSession = sessionmaker(
        bind=engine,
        autoflush=False,
        autocommit=False,
        expire_on_commit=False,
    )
    setup = TestingSession()
    _, pieces, _, _, position = create_stock_context(setup, quantity="5")
    position_id = position.id
    pieces_id = pieces.id
    setup.close()

    first_session = TestingSession()
    stale_session = TestingSession()
    stale_position = stale_session.get(StockPosition, position_id)
    assert stale_position.quantity == Decimal("5")

    create_stock_reservation(
        first_session,
        StockReservationCreate(
            stock_position_id=position_id,
            input_quantity=Decimal("4"),
            input_uom_id=pieces_id,
            reference_type="shipment",
            reference_uid="SHIP-001",
            idempotency_key="reserve:parallel:first",
            actor="first",
        ),
    )
    with pytest.raises(HTTPException, match="insufficient available stock"):
        create_stock_reservation(
            stale_session,
            StockReservationCreate(
                stock_position_id=position_id,
                input_quantity=Decimal("4"),
                input_uom_id=pieces_id,
                reference_type="shipment",
                reference_uid="SHIP-002",
                idempotency_key="reserve:parallel:second",
                actor="second",
            ),
        )
    first_session.close()
    stale_session.close()

    verify = TestingSession()
    assert verify.scalar(select(func.sum(StockReservation.quantity))) == Decimal("4")
    assert verify.scalar(select(func.count(StockReservation.id))) == 1
    verify.close()
    engine.dispose()


def test_stock_reservation_api_create_list_get_and_release(db):
    _, pieces, _, _, position = create_stock_context(db)

    def override_db():
        yield db

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[api_routes.get_db] = override_db
    try:
        with TestClient(app) as client:
            created = client.post(
                "/api/stock-reservations",
                json={
                    "stock_position_id": position.id,
                    "input_quantity": "2",
                    "input_uom_id": pieces.id,
                    "reference_type": "internal_issue",
                    "reference_uid": "ISSUE-API-001",
                    "reference_line_uid": "LINE-001",
                    "idempotency_key": "reserve:api:001",
                    "actor": "api-user",
                },
            )
            assert created.status_code == 200
            reservation = created.json()
            assert reservation["status"] == "active"
            assert reservation["location_code"] == "WH-RSV-ST01-01"

            listed = client.get(
                "/api/stock-reservations",
                params={"status": "active", "reference_uid": "ISSUE-API-001"},
            )
            assert listed.status_code == 200
            assert [item["uid"] for item in listed.json()] == [reservation["uid"]]
            assert client.get(
                f"/api/stock-reservations/{reservation['uid']}"
            ).status_code == 200

            released = client.post(
                f"/api/stock-reservations/{reservation['uid']}/release",
                json={
                    "idempotency_key": "release:api:001",
                    "actor": "api-user",
                    "reason": "Отмена",
                },
            )
            assert released.status_code == 200
            assert released.json()["status"] == "released"

            openapi = client.get("/openapi.json").json()
            summary = openapi["paths"][
                "/api/stock-reservations/{reservation_uid}/release"
            ]["post"]["summary"]
            assert "снять резерв" in summary
    finally:
        app.dependency_overrides.clear()
