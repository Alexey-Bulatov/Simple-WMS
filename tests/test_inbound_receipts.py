from datetime import date
from decimal import Decimal

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api import auth_routes, routes as api_routes
from app.core.config import Settings, get_settings
from app.db.session import Base, get_db
from app.inbound_receipts import create_inbound_receipt, inbound_receipt_payload
from app.main import app
from app.models.entities import (
    InboundReceipt,
    InboundReceiptLine,
    OperationEvent,
    ProductPackaging,
    StockDocument,
    StockMovement,
    StockOwner,
    StockPosition,
    UnitOfMeasure,
    Warehouse,
)
from app.models.enums import InboundReceiptKind, InboundReceiptStatus
from app.schemas import (
    InboundReceiptCreate,
    InboundReceiptLineCreate,
    ProductCreate,
)
from app.services import create_product, ensure_reference_catalogs


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


@pytest.fixture()
def client(db):
    def override_db():
        yield db

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[api_routes.get_db] = override_db
    app.dependency_overrides[auth_routes.get_db] = override_db
    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.clear()


def create_context(db):
    ensure_reference_catalogs(db)
    pieces = db.scalar(select(UnitOfMeasure).where(UnitOfMeasure.code == "PCS"))
    owner = db.scalar(select(StockOwner).where(StockOwner.code == "INTERNAL"))
    product = create_product(
        db,
        ProductCreate(
            code="FILTER-001",
            name="Фильтр сменный",
            base_uom_id=pieces.id,
        ),
    )
    other_product = create_product(
        db,
        ProductCreate(
            code="FILTER-OTHER",
            name="Другой фильтр",
            base_uom_id=pieces.id,
        ),
    )
    warehouse = Warehouse(code="WH-RCV", name="Склад приёмки")
    db.add(warehouse)
    db.flush()
    packaging = ProductPackaging(
        product_id=product.id,
        code="BOX-12",
        name="Коробка 12 шт",
        quantity=Decimal("12"),
        uom_id=pieces.id,
        base_quantity=Decimal("12"),
        barcode="460000000012",
    )
    wrong_packaging = ProductPackaging(
        product_id=other_product.id,
        code="BOX-OTHER",
        name="Чужая упаковка",
        quantity=Decimal("4"),
        uom_id=pieces.id,
        base_quantity=Decimal("4"),
    )
    db.add_all([packaging, wrong_packaging])
    db.commit()
    return warehouse, product, other_product, owner, pieces, packaging, wrong_packaging


def receipt_payload(
    warehouse,
    product,
    owner,
    pieces,
    *,
    key="receipt:create:001",
    quantity="5",
    packaging_id=None,
    serial_number=None,
):
    return InboundReceiptCreate(
        warehouse_code=warehouse.code.lower(),
        receipt_kind=InboundReceiptKind.EXPECTED,
        source_name="Поставщик фильтров",
        external_reference="ПСТ-42",
        planned_date=date(2026, 8, 20),
        idempotency_key=key,
        actor="receiver",
        note="Ожидаемая поставка",
        lines=[
            InboundReceiptLineCreate(
                product_id=product.id,
                owner_id=owner.id,
                input_quantity=Decimal(quantity),
                input_uom_id=None if packaging_id else pieces.id,
                packaging_id=packaging_id,
                batch_number="LOT-2026-08",
                production_date=date(2026, 8, 1),
                expiry_date=date(2027, 8, 1),
                serial_number=serial_number,
            )
        ],
    )


def test_create_expected_receipt_keeps_quantities_without_posting_stock(db):
    warehouse, product, _, owner, pieces, _, _ = create_context(db)

    receipt = create_inbound_receipt(
        db,
        receipt_payload(warehouse, product, owner, pieces),
    )
    data = inbound_receipt_payload(db, receipt)

    assert receipt.status == InboundReceiptStatus.DRAFT
    assert data["uid"].startswith("RCPT-")
    assert data["warehouse_code"] == "WH-RCV"
    assert data["receipt_kind"] == InboundReceiptKind.EXPECTED
    assert data["line_count"] == 1
    assert data["lines"][0]["input_quantity"] == Decimal("5")
    assert data["lines"][0]["expected_base_quantity"] == Decimal("5")
    assert data["lines"][0]["batch_number"] == "LOT-2026-08"
    assert db.scalar(select(func.count(StockDocument.id))) == 0
    assert db.scalar(select(func.count(StockMovement.id))) == 0
    assert db.scalar(select(func.count(StockPosition.id))) == 0
    event = db.scalar(
        select(OperationEvent).where(
            OperationEvent.operation == "inbound_receipt_created"
        )
    )
    assert event.after["line_count"] == 1


def test_packaging_is_snapshotted_as_base_quantity(db):
    warehouse, product, _, owner, pieces, packaging, _ = create_context(db)

    receipt = create_inbound_receipt(
        db,
        receipt_payload(
            warehouse,
            product,
            owner,
            pieces,
            key="receipt:packaging",
            quantity="2",
            packaging_id=packaging.id,
        ),
    )
    line = receipt.lines[0]

    assert line.input_quantity == Decimal("2")
    assert line.packaging_id == packaging.id
    assert line.expected_base_quantity == Decimal("24")
    assert line.conversion_factor == Decimal("12")


def test_unplanned_receipt_does_not_require_supplier_or_external_reference(db):
    warehouse, product, _, owner, pieces, _, _ = create_context(db)
    payload = receipt_payload(
        warehouse,
        product,
        owner,
        pieces,
        key="receipt:unplanned",
    ).model_copy(
        update={
            "receipt_kind": InboundReceiptKind.UNPLANNED,
            "source_name": None,
            "external_reference": None,
            "planned_date": None,
        }
    )

    receipt = create_inbound_receipt(db, payload)

    assert receipt.receipt_kind == InboundReceiptKind.UNPLANNED
    assert receipt.source_name is None
    assert receipt.external_reference is None


def test_receipt_creation_is_idempotent_and_rejects_changed_command(db):
    warehouse, product, _, owner, pieces, _, _ = create_context(db)
    payload = receipt_payload(warehouse, product, owner, pieces)

    first = create_inbound_receipt(db, payload)
    repeated = create_inbound_receipt(db, payload)

    assert repeated.id == first.id
    assert db.scalar(select(func.count(InboundReceipt.id))) == 1
    assert db.scalar(select(func.count(InboundReceiptLine.id))) == 1
    with pytest.raises(HTTPException, match="belongs to another inbound receipt"):
        create_inbound_receipt(
            db,
            receipt_payload(
                warehouse,
                product,
                owner,
                pieces,
                quantity="6",
            ),
        )


def test_receipt_rejects_wrong_packaging_and_serial_quantity(db):
    warehouse, product, _, owner, pieces, _, wrong_packaging = create_context(db)

    with pytest.raises(HTTPException, match="active product packaging not found"):
        create_inbound_receipt(
            db,
            receipt_payload(
                warehouse,
                product,
                owner,
                pieces,
                key="receipt:wrong-packaging",
                packaging_id=wrong_packaging.id,
            ),
        )
    with pytest.raises(HTTPException, match="must contain one base unit"):
        create_inbound_receipt(
            db,
            receipt_payload(
                warehouse,
                product,
                owner,
                pieces,
                key="receipt:serial-many",
                quantity="2",
                serial_number="SER-001",
            ),
        )


def test_inbound_receipt_api_creates_lists_and_filters_documents(client, db):
    warehouse, product, _, owner, pieces, _, _ = create_context(db)
    payload = receipt_payload(
        warehouse,
        product,
        owner,
        pieces,
        key="receipt:api:001",
    ).model_dump(mode="json")

    created = client.post("/api/inbound-receipts", json=payload)
    assert created.status_code == 200
    data = created.json()
    assert data["status"] == "draft"
    assert data["lines"][0]["product_code"] == "FILTER-001"

    detail = client.get(f"/api/inbound-receipts/{data['uid'].lower()}")
    assert detail.status_code == 200
    assert detail.json()["uid"] == data["uid"]

    matching = client.get(
        "/api/inbound-receipts",
        params={"warehouse_code": "wh-rcv", "receipt_kind": "expected", "status": "draft"},
    )
    assert matching.status_code == 200
    assert [item["uid"] for item in matching.json()] == [data["uid"]]

    assert client.get(
        "/api/inbound-receipts",
        params={"receipt_kind": "unplanned"},
    ).json() == []


def test_receiving_clerk_is_limited_to_assigned_warehouse(client, db):
    app.dependency_overrides[get_settings] = lambda: Settings(
        auth_enforcement_enabled=True,
        auth_session_hours=12,
    )
    warehouse, product, _, owner, pieces, _, _ = create_context(db)
    foreign = Warehouse(code="WH-RCV-X", name="Чужой склад приёмки")
    db.add(foreign)
    db.commit()

    assert client.post(
        "/api/auth/bootstrap",
        json={
            "username": "admin",
            "full_name": "Администратор",
            "password": "Admin-pass-2026",
        },
    ).status_code == 200
    assert client.post(
        "/api/auth/login/password",
        json={"username": "admin", "password": "Admin-pass-2026"},
    ).status_code == 200
    assert client.post(
        "/api/auth/admin/users",
        json={
            "username": "receiver",
            "full_name": "Оператор приёмки",
            "role": "receiving_clerk",
            "password": "Receiver-pass-2026",
            "warehouse_ids": [warehouse.id],
            "must_change_password": False,
        },
    ).status_code == 200

    foreign_payload = receipt_payload(
        foreign,
        product,
        owner,
        pieces,
        key="receipt:foreign:admin",
    ).model_copy(update={"actor": "admin"})
    foreign_receipt = client.post(
        "/api/inbound-receipts",
        json=foreign_payload.model_dump(mode="json"),
    )
    assert foreign_receipt.status_code == 200

    receiver = TestClient(app)
    assert receiver.post(
        "/api/auth/login/password",
        json={"username": "receiver", "password": "Receiver-pass-2026"},
    ).status_code == 200
    own_payload = receipt_payload(
        warehouse,
        product,
        owner,
        pieces,
        key="receipt:own:receiver",
    ).model_copy(update={"actor": "receiver"})
    assert receiver.post(
        "/api/inbound-receipts",
        json=own_payload.model_dump(mode="json"),
    ).status_code == 200

    denied_payload = receipt_payload(
        foreign,
        product,
        owner,
        pieces,
        key="receipt:foreign:receiver",
    ).model_copy(update={"actor": "receiver"})
    assert receiver.post(
        "/api/inbound-receipts",
        json=denied_payload.model_dump(mode="json"),
    ).status_code == 403
    assert receiver.get(
        f"/api/inbound-receipts/{foreign_receipt.json()['uid']}"
    ).status_code == 403
    listed = receiver.get("/api/inbound-receipts")
    assert listed.status_code == 200
    assert {item["warehouse_code"] for item in listed.json()} == {warehouse.code}
