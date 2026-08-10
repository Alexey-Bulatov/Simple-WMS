from decimal import Decimal

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.session import Base
from app.models.entities import (
    LogisticUnitType,
    Product,
    StockDocument,
    StockMovement,
    StockOwner,
    StockPosition,
    UnitOfMeasure,
)
from app.models.enums import StockDocumentStatus
from app.schemas import (
    LogisticUnitCreate,
    ProductCreate,
    StockDocumentPost,
    StockMovementPost,
)
from app.services import create_logistic_unit, create_product, ensure_reference_catalogs
from app.stock_ledger import post_stock_document, stock_document_payload


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


def create_stock_context(db, *, quantity: Decimal | None = None):
    ensure_reference_catalogs(db)
    pieces = reference(db, UnitOfMeasure, "PCS")
    owner = reference(db, StockOwner, "INTERNAL")
    product = create_product(
        db,
        ProductCreate(
            code="ISSUE-ITEM",
            name="Выдаваемый товар",
            base_uom_id=pieces.id,
        ),
    )
    box_type = reference(db, LogisticUnitType, "BOX")
    unit = create_logistic_unit(
        db,
        LogisticUnitCreate(type_id=box_type.id, uid="BOX-POSTING-001", actor="test"),
    )
    if quantity is not None:
        db.add(
            StockPosition(
                product_id=product.id,
                owner_id=owner.id,
                quality_status="released",
                quantity=quantity,
                logistic_unit_id=unit.id,
            )
        )
        db.commit()
    return product, pieces, owner, unit


def inbound_command(product, pieces, owner, unit, *, key: str, quantity: str = "2"):
    return StockDocumentPost(
        document_type="receipt",
        reference_type="test",
        reference_uid="RCPT-001",
        idempotency_key=key,
        actor="tester",
        attributes={"channel": "unit-test"},
        movements=[
            StockMovementPost(
                product_id=product.id,
                owner_id=owner.id,
                destination_quality_status="released",
                input_quantity=Decimal(quantity),
                input_uom_id=pieces.id,
                destination_logistic_unit_id=unit.id,
            )
        ],
    )


def outbound_movement(product, pieces, owner, unit, quantity: str):
    return StockMovementPost(
        product_id=product.id,
        owner_id=owner.id,
        source_quality_status="released",
        input_quantity=Decimal(quantity),
        input_uom_id=pieces.id,
        source_logistic_unit_id=unit.id,
    )


def test_posting_is_idempotent_and_preserves_input_quantity(db):
    product, pieces, owner, unit = create_stock_context(db)
    command = inbound_command(product, pieces, owner, unit, key="receipt:001")

    first = post_stock_document(db, command)
    repeated = post_stock_document(db, command)

    assert repeated.id == first.id
    assert first.status == StockDocumentStatus.POSTED
    assert db.scalar(select(func.count(StockDocument.id))) == 1
    assert db.scalar(select(func.count(StockMovement.id))) == 1
    position = db.scalar(select(StockPosition))
    assert position.quantity == Decimal("2")
    assert first.movements[0].input_quantity == Decimal("2")
    assert stock_document_payload(db, first)["attributes"] == {"channel": "unit-test"}


def test_idempotency_key_rejects_a_different_command(db):
    product, pieces, owner, unit = create_stock_context(db)
    post_stock_document(
        db,
        inbound_command(product, pieces, owner, unit, key="receipt:duplicate", quantity="2"),
    )

    with pytest.raises(HTTPException, match="belongs to another stock command") as error:
        post_stock_document(
            db,
            inbound_command(
                product,
                pieces,
                owner,
                unit,
                key="receipt:duplicate",
                quantity="3",
            ),
        )

    assert error.value.status_code == 409
    assert db.scalar(select(StockPosition)).quantity == Decimal("2")
    assert db.scalar(select(func.count(StockMovement.id))) == 1


def test_multiline_document_rolls_back_when_any_line_is_invalid(db):
    product, pieces, owner, unit = create_stock_context(db, quantity=Decimal("5"))
    command = StockDocumentPost(
        document_type="issue",
        idempotency_key="issue:atomic",
        actor="tester",
        movements=[
            outbound_movement(product, pieces, owner, unit, "3"),
            outbound_movement(product, pieces, owner, unit, "3"),
        ],
    )

    with pytest.raises(HTTPException, match="insufficient source stock"):
        post_stock_document(db, command)

    assert db.scalar(select(StockPosition)).quantity == Decimal("5")
    assert db.scalar(select(func.count(StockDocument.id))) == 0
    assert db.scalar(select(func.count(StockMovement.id))) == 0


def test_serialized_stock_moves_without_recreating_its_position(db):
    product, pieces, owner, source_unit = create_stock_context(db)
    box_type = reference(db, LogisticUnitType, "BOX")
    destination_unit = create_logistic_unit(
        db,
        LogisticUnitCreate(type_id=box_type.id, uid="BOX-POSTING-002", actor="test"),
    )
    receipt = StockDocumentPost(
        document_type="receipt",
        idempotency_key="serial:receipt",
        movements=[
            StockMovementPost(
                product_id=product.id,
                serial_number=" sn-0001 ",
                owner_id=owner.id,
                destination_quality_status="released",
                input_quantity=Decimal("1"),
                input_uom_id=pieces.id,
                destination_logistic_unit_id=source_unit.id,
            )
        ],
    )
    post_stock_document(db, receipt)
    original_position_id = db.scalar(select(StockPosition.id))

    transfer = StockDocumentPost(
        document_type="internal_transfer",
        idempotency_key="serial:transfer",
        movements=[
            StockMovementPost(
                product_id=product.id,
                serial_number="SN-0001",
                owner_id=owner.id,
                source_quality_status="released",
                destination_quality_status="released",
                input_quantity=Decimal("1"),
                input_uom_id=pieces.id,
                source_logistic_unit_id=source_unit.id,
                destination_logistic_unit_id=destination_unit.id,
            )
        ],
    )
    post_stock_document(db, transfer)

    position = db.scalar(select(StockPosition))
    assert position.id == original_position_id
    assert position.serial_number == "SN-0001"
    assert position.logistic_unit_id == destination_unit.id
    assert db.scalar(select(func.count(StockMovement.id))) == 2


def test_stale_parallel_session_cannot_overdraw_stock(tmp_path):
    engine = create_engine(
        f"sqlite:///{tmp_path / 'posting.db'}",
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
    product, pieces, owner, unit = create_stock_context(setup, quantity=Decimal("5"))
    setup.close()

    first_session = TestingSession()
    stale_session = TestingSession()
    stale_position = stale_session.scalar(select(StockPosition))
    assert stale_position.quantity == Decimal("5")

    first = StockDocumentPost(
        document_type="issue",
        idempotency_key="issue:parallel:first",
        actor="tester-1",
        movements=[outbound_movement(product, pieces, owner, unit, "4")],
    )
    second = StockDocumentPost(
        document_type="issue",
        idempotency_key="issue:parallel:second",
        actor="tester-2",
        movements=[outbound_movement(product, pieces, owner, unit, "4")],
    )
    post_stock_document(first_session, first)
    with pytest.raises(HTTPException, match="insufficient source stock"):
        post_stock_document(stale_session, second)
    first_session.close()
    stale_session.close()

    verify = TestingSession()
    assert verify.scalar(select(StockPosition.quantity)) == Decimal("1")
    assert verify.scalar(select(func.count(StockDocument.id))) == 1
    assert verify.scalar(select(func.count(StockMovement.id))) == 1
    verify.close()
    engine.dispose()
