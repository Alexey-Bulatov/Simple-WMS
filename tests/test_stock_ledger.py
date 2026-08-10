from datetime import datetime, timezone
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
    LogisticUnitType,
    Product,
    StockDocument,
    StockMovement,
    StockOwner,
    UnitOfMeasure,
)
from app.models.enums import StockDocumentStatus
from app.schemas import LogisticUnitCreate, ProductCreate
from app.services import create_logistic_unit, create_product, ensure_reference_catalogs
from app.stock_ledger import stock_document_payload, stock_movement_payload


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


def create_posted_document_with_movement(db):
    ensure_reference_catalogs(db)
    pieces = reference(db, UnitOfMeasure, "PCS")
    owner = reference(db, StockOwner, "INTERNAL")
    product = create_product(
        db,
        ProductCreate(code="GLOVE-001", name="Перчатки", base_uom_id=pieces.id),
    )
    box_type = reference(db, LogisticUnitType, "BOX")
    unit = create_logistic_unit(
        db,
        LogisticUnitCreate(type_id=box_type.id, uid="BOX-LEDGER-001", actor="test"),
    )
    now = datetime.now(timezone.utc)
    document = StockDocument(
        uid="DOC-OPENING-001",
        document_type="opening_balance",
        status=StockDocumentStatus.POSTED,
        reference_type="test",
        reference_uid="TEST-001",
        idempotency_key="test:opening:001",
        actor="test",
        reason="Начальный остаток",
        attributes={"source": "test"},
        posted_at=now,
    )
    db.add(document)
    db.flush()
    movement = StockMovement(
        document_id=document.id,
        sequence_no=1,
        product_id=product.id,
        owner_id=owner.id,
        destination_quality_status="released",
        quantity=Decimal("2"),
        base_uom_id=pieces.id,
        input_quantity=Decimal("2"),
        input_uom_id=pieces.id,
        conversion_factor=Decimal("1"),
        destination_logistic_unit_id=unit.id,
        occurred_at=now,
    )
    db.add(movement)
    db.commit()
    db.refresh(document)
    db.refresh(movement)
    return document, movement, product, owner, unit


def test_stock_ledger_payload_preserves_input_and_base_quantities(db):
    document, movement, _, _, unit = create_posted_document_with_movement(db)

    movement_data = stock_movement_payload(db, movement)
    assert movement_data["document_uid"] == document.uid
    assert movement_data["quantity"] == Decimal("2")
    assert movement_data["base_uom_code"] == "PCS"
    assert movement_data["input_quantity"] == Decimal("2")
    assert movement_data["input_uom_code"] == "PCS"
    assert movement_data["conversion_factor"] == Decimal("1")
    assert movement_data["destination_logistic_unit_uid"] == unit.uid

    document_data = stock_document_payload(db, document, include_movements=True)
    assert document_data["movement_count"] == 1
    assert document_data["movements"][0]["product_code"] == "GLOVE-001"


def test_stock_movement_requires_at_least_one_holder(db):
    document, _, product, owner, _ = create_posted_document_with_movement(db)
    pieces = reference(db, UnitOfMeasure, "PCS")
    db.add(
        StockMovement(
            document_id=document.id,
            sequence_no=2,
            product_id=product.id,
            owner_id=owner.id,
            quantity=Decimal("1"),
            base_uom_id=pieces.id,
            input_quantity=Decimal("1"),
            input_uom_id=pieces.id,
            conversion_factor=Decimal("1"),
        )
    )
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()


def test_stock_document_idempotency_key_is_unique(db):
    document, _, _, _, _ = create_posted_document_with_movement(db)
    db.add(
        StockDocument(
            uid="DOC-DUPLICATE-001",
            document_type="opening_balance",
            status=StockDocumentStatus.POSTED,
            idempotency_key=document.idempotency_key,
            actor="test",
        )
    )
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()


def test_stock_ledger_api_is_read_only(db):
    document, movement, product, _, _ = create_posted_document_with_movement(db)

    def override_db():
        yield db

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[api_routes.get_db] = override_db
    try:
        with TestClient(app) as client:
            documents = client.get(
                "/api/stock-documents",
                params={"status": "posted", "reference_uid": "TEST-001"},
            )
            assert documents.status_code == 200
            assert documents.json()[0]["uid"] == document.uid
            assert documents.json()[0]["movement_count"] == 1

            detail = client.get(f"/api/stock-documents/{document.uid}")
            assert detail.status_code == 200
            assert detail.json()["movements"][0]["id"] == movement.id

            movements = client.get(
                "/api/stock-movements",
                params={"document_uid": document.uid, "product_id": product.id},
            )
            assert movements.status_code == 200
            assert len(movements.json()) == 1
            assert movements.json()[0]["quantity"] == "2.000000"

            assert client.post("/api/stock-documents", json={}).status_code == 405
            assert client.post("/api/stock-movements", json={}).status_code == 405

            schema = client.get("/openapi.json").json()
            summary = schema["paths"]["/api/stock-movements"]["get"]["summary"]
            assert "Список движений запаса" in summary
    finally:
        app.dependency_overrides.clear()
