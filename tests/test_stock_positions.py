from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api import routes as api_routes
from app.db.session import Base, get_db
from app.main import app
from app.models.entities import (
    Location,
    LogisticUnitContent,
    LogisticUnitType,
    Product,
    StockOwner,
    StockPosition,
    UnitOfMeasure,
    Warehouse,
    Zone,
)
from app.models.enums import LocationKind, LogisticUnitStatus
from app.schemas import (
    LogisticUnitContentCreate,
    LogisticUnitContentRemoveRequest,
    LogisticUnitCreate,
    ProductCreate,
    ProductPackagingCreate,
)
from app.services import (
    add_logistic_unit_content,
    create_logistic_unit,
    create_product,
    create_product_packaging,
    ensure_reference_catalogs,
    remove_logistic_unit_content,
)
from app.stock import remove_logistic_unit_stock_positions, stock_position_payload


@pytest.fixture()
def db():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    TestingSession = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    session = TestingSession()
    try:
        yield session
    finally:
        session.close()


def reference(db, model, code: str):
    return db.scalar(select(model).where(model.code == code))


def create_piece_product_and_unit(db):
    ensure_reference_catalogs(db)
    pieces = reference(db, UnitOfMeasure, "PCS")
    product = create_product(
        db,
        ProductCreate(
            code="JAR-450",
            name="Банка продукта 450 г",
            base_uom_id=pieces.id,
        ),
    )
    packaging = create_product_packaging(
        db,
        ProductPackagingCreate(
            product_id=product.id,
            code="JAR",
            name="Банка 450 г",
            quantity=Decimal("1"),
            uom_id=pieces.id,
            barcode="4600000000450",
        ),
    )
    box_type = reference(db, LogisticUnitType, "BOX")
    unit = create_logistic_unit(
        db,
        LogisticUnitCreate(type_id=box_type.id, uid="BOX-JARS-001", actor="test"),
    )
    return product, packaging, pieces, unit


def test_two_450_gram_jars_are_two_pieces_in_stock(db):
    product, packaging, pieces, unit = create_piece_product_and_unit(db)

    add_logistic_unit_content(
        db,
        unit.uid,
        LogisticUnitContentCreate(
            product_id=product.id,
            quantity=Decimal("2"),
            uom_id=pieces.id,
            actor="test",
        ),
    )

    position = db.scalar(select(StockPosition))
    assert packaging.base_quantity == Decimal("1")
    assert position.quantity == Decimal("2")
    assert position.product_id == product.id
    assert db.get(UnitOfMeasure, product.base_uom_id).code == "PCS"


def test_stock_position_follows_content_reduction_and_removal(db):
    product, _, pieces, unit = create_piece_product_and_unit(db)
    add_logistic_unit_content(
        db,
        unit.uid,
        LogisticUnitContentCreate(
            product_id=product.id,
            quantity=Decimal("2"),
            uom_id=pieces.id,
            actor="test",
        ),
    )
    line = db.scalar(select(LogisticUnitContent))

    remove_logistic_unit_content(
        db,
        unit.uid,
        line.id,
        LogisticUnitContentRemoveRequest(quantity=Decimal("1"), actor="test"),
    )
    assert db.scalar(select(StockPosition)).quantity == Decimal("1")

    remove_logistic_unit_content(
        db,
        unit.uid,
        line.id,
        LogisticUnitContentRemoveRequest(quantity=Decimal("1"), actor="test"),
    )
    assert db.scalar(select(StockPosition)) is None


def test_stock_position_payload_resolves_available_warehouse_stock(db):
    product, _, pieces, unit = create_piece_product_and_unit(db)
    add_logistic_unit_content(
        db,
        unit.uid,
        LogisticUnitContentCreate(
            product_id=product.id,
            quantity=Decimal("2"),
            uom_id=pieces.id,
            actor="test",
        ),
    )
    warehouse = Warehouse(code="WH01", name="Основной склад")
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
        code="WH01-ST01-FLOOR",
        name="Напольное хранение",
        kind=LocationKind.STORAGE,
        capacity_units=10,
    )
    db.add(location)
    db.flush()
    unit.current_location_id = location.id
    unit.status = LogisticUnitStatus.AVAILABLE
    db.commit()

    payload = stock_position_payload(db, db.scalar(select(StockPosition)))
    assert payload["quantity"] == Decimal("2")
    assert payload["available_quantity"] == Decimal("2")
    assert payload["warehouse_code"] == "WH01"
    assert payload["location_code"] == "WH01-ST01-FLOOR"


def test_stock_position_identity_is_unique_without_batch(db):
    product, _, pieces, unit = create_piece_product_and_unit(db)
    owner = reference(db, StockOwner, "INTERNAL")
    first = StockPosition(
        product_id=product.id,
        owner_id=owner.id,
        quality_status="released",
        quantity=Decimal("1"),
        logistic_unit_id=unit.id,
    )
    duplicate = StockPosition(
        product_id=product.id,
        owner_id=owner.id,
        quality_status="released",
        quantity=Decimal("1"),
        logistic_unit_id=unit.id,
    )
    db.add_all([first, duplicate])
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()


def test_serial_stock_position_is_one_piece_and_globally_unique(db):
    product, _, _, unit = create_piece_product_and_unit(db)
    owner = reference(db, StockOwner, "INTERNAL")
    db.add(
        StockPosition(
            product_id=product.id,
            owner_id=owner.id,
            quality_status="released",
            serial_number="SN-0001",
            quantity=Decimal("1"),
            logistic_unit_id=unit.id,
        )
    )
    db.commit()

    db.add(
        StockPosition(
            product_id=product.id,
            owner_id=owner.id,
            quality_status="released",
            serial_number="SN-0001",
            quantity=Decimal("1"),
            logistic_unit_id=unit.id,
        )
    )
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()

    db.add(
        StockPosition(
            product_id=product.id,
            owner_id=owner.id,
            quality_status="released",
            serial_number="SN-0002",
            quantity=Decimal("2"),
            logistic_unit_id=unit.id,
        )
    )
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()


def test_removing_parent_stock_removes_nested_unit_positions(db):
    product, _, pieces, child = create_piece_product_and_unit(db)
    add_logistic_unit_content(
        db,
        child.uid,
        LogisticUnitContentCreate(
            product_id=product.id,
            quantity=Decimal("2"),
            uom_id=pieces.id,
            actor="test",
        ),
    )
    pallet_type = reference(db, LogisticUnitType, "PALLET")
    parent = create_logistic_unit(
        db,
        LogisticUnitCreate(type_id=pallet_type.id, uid="PLT-JARS-001", actor="test"),
    )
    child.parent_unit_id = parent.id
    db.commit()

    remove_logistic_unit_stock_positions(db, parent.id)
    db.commit()

    assert db.scalar(select(StockPosition)) is None


def test_stock_position_api_lists_positions_and_owners(db):
    product, _, pieces, unit = create_piece_product_and_unit(db)
    add_logistic_unit_content(
        db,
        unit.uid,
        LogisticUnitContentCreate(
            product_id=product.id,
            quantity=Decimal("2"),
            uom_id=pieces.id,
            actor="test",
        ),
    )

    def override_db():
        yield db

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[api_routes.get_db] = override_db
    try:
        with TestClient(app) as client:
            owners = client.get("/api/stock-owners")
            assert owners.status_code == 200
            assert owners.json()[0]["code"] == "INTERNAL"

            positions = client.get(
                "/api/stock-positions",
                params={"product_id": product.id, "logistic_unit_uid": unit.uid},
            )
            assert positions.status_code == 200
            assert len(positions.json()) == 1
            assert positions.json()[0]["quantity"] == "2.000000"
            assert positions.json()[0]["base_uom_code"] == "PCS"

            schema = client.get("/openapi.json").json()
            summary = schema["paths"]["/api/stock-positions"]["get"]["summary"]
            assert "Список позиций остатка" in summary
    finally:
        app.dependency_overrides.clear()
