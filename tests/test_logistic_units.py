from datetime import date
from decimal import Decimal

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.session import Base, get_db
from app.main import app
from app.models.entities import (
    Batch,
    LogisticUnit,
    LogisticUnitType,
    OperationEvent,
    UnitOfMeasure,
)
from app.models.enums import LogisticUnitStatus
from app.schemas import (
    BatchCreate,
    LogisticUnitActionRequest,
    LogisticUnitChildRequest,
    LogisticUnitContentCreate,
    LogisticUnitContentRemoveRequest,
    LogisticUnitCreate,
    ProductCreate,
)
from app.services import (
    add_logistic_unit_child,
    add_logistic_unit_content,
    close_logistic_unit,
    create_batch,
    create_logistic_unit,
    create_product,
    disassemble_logistic_unit,
    ensure_reference_catalogs,
    logistic_unit_payload,
    remove_logistic_unit_child,
    remove_logistic_unit_content,
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


def reference(db, model, code: str):
    return db.scalar(select(model).where(model.code == code))


def product_and_batch(db, *, code: str = "CHEM-001", uom_code: str = "PCS"):
    ensure_reference_catalogs(db)
    uom = reference(db, UnitOfMeasure, uom_code)
    product = create_product(
        db,
        ProductCreate(
            code=code,
            name=f"Товар {code}",
            base_uom_id=uom.id,
        ),
    )
    batch = create_batch(
        db,
        BatchCreate(
            product_id=product.id,
            batch_number=f"{code}-B01",
            production_date=date(2026, 7, 1),
            expiry_date=date(2027, 7, 1),
        ),
    )
    return product, batch, uom


def create_named_unit(db, type_code: str, uid: str) -> LogisticUnit:
    ensure_reference_catalogs(db)
    unit_type = reference(db, LogisticUnitType, type_code)
    return create_logistic_unit(
        db,
        LogisticUnitCreate(type_id=unit_type.id, uid=uid, actor="test"),
    )


def test_nested_units_store_decimal_content_and_history(db):
    product, batch, pieces = product_and_batch(db)
    box = create_named_unit(db, "BOX", "BOX-DEMO-001")
    add_logistic_unit_content(
        db,
        box.uid,
        LogisticUnitContentCreate(
            product_id=product.id,
            batch_id=batch.id,
            quantity=Decimal("12"),
            uom_id=pieces.id,
            actor="receiver",
        ),
    )
    close_logistic_unit(db, box.uid, LogisticUnitActionRequest(actor="receiver"))

    pallet = create_named_unit(db, "PALLET", "PLT-DEMO-001")
    add_logistic_unit_child(
        db,
        pallet.uid,
        LogisticUnitChildRequest(child_uid=box.uid, actor="receiver"),
    )
    close_logistic_unit(db, pallet.uid, LogisticUnitActionRequest(actor="receiver"))

    payload = logistic_unit_payload(db, pallet)
    assert payload["status"] == LogisticUnitStatus.CLOSED
    assert payload["child_units"][0]["uid"] == "BOX-DEMO-001"
    box_payload = logistic_unit_payload(db, box)
    assert box_payload["parent_uid"] == "PLT-DEMO-001"
    assert box_payload["contents"][0]["quantity"] == Decimal("12.000000")
    operations = set(db.scalars(select(OperationEvent.operation)))
    assert {
        "logistic_unit_created",
        "logistic_unit_content_added",
        "logistic_unit_child_added",
        "logistic_unit_closed",
    }.issubset(operations)


def test_nesting_rejects_wrong_type_and_second_parent(db):
    ibc = create_named_unit(db, "IBC", "IBC-DEMO-001")
    close_logistic_unit(db, ibc.uid, LogisticUnitActionRequest(actor="test"))
    first_pallet = create_named_unit(db, "PALLET", "PLT-DEMO-010")

    with pytest.raises(HTTPException, match="child logistic unit type is not allowed"):
        add_logistic_unit_child(
            db,
            first_pallet.uid,
            LogisticUnitChildRequest(child_uid=ibc.uid),
        )

    box = create_named_unit(db, "BOX", "BOX-DEMO-010")
    close_logistic_unit(db, box.uid, LogisticUnitActionRequest(actor="test"))
    add_logistic_unit_child(
        db,
        first_pallet.uid,
        LogisticUnitChildRequest(child_uid=box.uid),
    )
    second_pallet = create_named_unit(db, "PALLET", "PLT-DEMO-011")
    with pytest.raises(HTTPException, match="already belongs to another parent"):
        add_logistic_unit_child(
            db,
            second_pallet.uid,
            LogisticUnitChildRequest(child_uid=box.uid),
        )


def test_content_rejects_foreign_batch_and_incompatible_measurement(db):
    product, _, pieces = product_and_batch(db, code="CHEM-A")
    _, foreign_batch, _ = product_and_batch(db, code="CHEM-B")
    kilograms = reference(db, UnitOfMeasure, "KG")
    box = create_named_unit(db, "BOX", "BOX-DEMO-020")

    with pytest.raises(HTTPException, match="batch belongs to another product"):
        add_logistic_unit_content(
            db,
            box.uid,
            LogisticUnitContentCreate(
                product_id=product.id,
                batch_id=foreign_batch.id,
                quantity=Decimal("1"),
                uom_id=pieces.id,
            ),
        )

    with pytest.raises(HTTPException, match="incompatible with the product base unit"):
        add_logistic_unit_content(
            db,
            box.uid,
            LogisticUnitContentCreate(
                product_id=product.id,
                quantity=Decimal("1"),
                uom_id=kilograms.id,
            ),
        )


def test_partial_content_removal_detach_and_disassemble(db):
    product, batch, pieces = product_and_batch(db)
    box = create_named_unit(db, "BOX", "BOX-DEMO-030")
    add_logistic_unit_content(
        db,
        box.uid,
        LogisticUnitContentCreate(
            product_id=product.id,
            batch_id=batch.id,
            quantity=Decimal("12"),
            uom_id=pieces.id,
        ),
    )
    content_id = logistic_unit_payload(db, box)["contents"][0]["id"]
    remove_logistic_unit_content(
        db,
        box.uid,
        content_id,
        LogisticUnitContentRemoveRequest(quantity=Decimal("5"), reason="Отбор"),
    )
    assert logistic_unit_payload(db, box)["contents"][0]["quantity"] == Decimal("7.000000")
    remove_logistic_unit_content(
        db,
        box.uid,
        content_id,
        LogisticUnitContentRemoveRequest(quantity=Decimal("7"), reason="Опустошение"),
    )

    close_logistic_unit(db, box.uid, LogisticUnitActionRequest())
    pallet = create_named_unit(db, "PALLET", "PLT-DEMO-030")
    add_logistic_unit_child(db, pallet.uid, LogisticUnitChildRequest(child_uid=box.uid))
    remove_logistic_unit_child(
        db,
        pallet.uid,
        box.uid,
        LogisticUnitActionRequest(reason="Расформирование"),
    )
    disassemble_logistic_unit(
        db,
        pallet.uid,
        LogisticUnitActionRequest(reason="Тара больше не используется"),
    )
    assert pallet.status == LogisticUnitStatus.DISASSEMBLED


def test_logistic_unit_api_lifecycle(db):
    product, batch, pieces = product_and_batch(db)
    box_type = reference(db, LogisticUnitType, "BOX")

    def override_db():
        yield db

    app.dependency_overrides[get_db] = override_db
    try:
        with TestClient(app) as client:
            created = client.post(
                "/api/logistic-units",
                json={"type_id": box_type.id, "uid": "BOX-API-001", "actor": "api-test"},
            )
            assert created.status_code == 200
            assert created.json()["status"] == "open"

            content = client.post(
                "/api/logistic-units/BOX-API-001/contents",
                json={
                    "product_id": product.id,
                    "batch_id": batch.id,
                    "quantity": "2.5",
                    "uom_id": pieces.id,
                    "actor": "api-test",
                },
            )
            assert content.status_code == 200
            assert content.json()["contents"][0]["quantity"] == "2.500000"

            closed = client.post(
                "/api/logistic-units/BOX-API-001/close",
                json={"actor": "api-test"},
            )
            assert closed.status_code == 200
            assert closed.json()["status"] == "closed"

            listed = client.get("/api/logistic-units", params={"status": "closed"})
            assert listed.status_code == 200
            assert [row["uid"] for row in listed.json()] == ["BOX-API-001"]
    finally:
        app.dependency_overrides.clear()
