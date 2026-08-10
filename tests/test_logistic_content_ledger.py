from decimal import Decimal

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.session import Base
from app.models.entities import (
    LogisticUnitContent,
    LogisticUnitType,
    OperationEvent,
    Product,
    StockDocument,
    StockMovement,
    StockOwner,
    StockPosition,
    UnitOfMeasure,
)
from app.models.enums import LogisticUnitStatus
from app.schemas import (
    LogisticUnitContentCreate,
    LogisticUnitContentRemoveRequest,
    LogisticUnitCreate,
    ProductCreate,
)
from app.services import (
    add_logistic_unit_content,
    create_logistic_unit,
    create_product,
    ensure_reference_catalogs,
    remove_logistic_unit_content,
)


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


def create_product_and_box(db, *, product_code: str, uom_code: str):
    ensure_reference_catalogs(db)
    base_uom = reference(db, UnitOfMeasure, uom_code)
    product = create_product(
        db,
        ProductCreate(
            code=product_code,
            name=f"Товар {product_code}",
            base_uom_id=base_uom.id,
        ),
    )
    box_type = reference(db, LogisticUnitType, "BOX")
    box = create_logistic_unit(
        db,
        LogisticUnitCreate(type_id=box_type.id, uid=f"BOX-{product_code}", actor="test"),
    )
    owner = reference(db, StockOwner, "INTERNAL")
    return product, base_uom, owner, box


def test_content_addition_posts_input_and_base_quantities_once(db):
    product, kilograms, owner, box = create_product_and_box(
        db,
        product_code="CHEM-LEDGER",
        uom_code="KG",
    )
    grams = reference(db, UnitOfMeasure, "G")
    payload = LogisticUnitContentCreate(
        product_id=product.id,
        quantity=Decimal("1000"),
        uom_id=grams.id,
        actor="receiver",
        idempotency_key="content:add:chem-001",
    )

    add_logistic_unit_content(db, box.uid, payload)
    box.status = LogisticUnitStatus.CLOSED
    db.commit()
    add_logistic_unit_content(db, box.uid, payload)

    content = db.scalar(select(LogisticUnitContent))
    position = db.scalar(select(StockPosition))
    document = db.scalar(select(StockDocument))
    movement = db.scalar(select(StockMovement))
    assert content.quantity == Decimal("1")
    assert content.uom_id == kilograms.id
    assert position.quantity == Decimal("1")
    assert position.owner_id == owner.id
    assert document.document_type == "logistic_unit_content_add"
    assert document.reference_uid == box.uid
    assert document.attributes["content_id"] == content.id
    assert movement.quantity == Decimal("1")
    assert movement.base_uom_id == kilograms.id
    assert movement.input_quantity == Decimal("1000")
    assert movement.input_uom_id == grams.id
    assert movement.conversion_factor == Decimal("0.001")
    assert db.scalar(select(func.count(StockDocument.id))) == 1
    assert db.scalar(select(func.count(StockMovement.id))) == 1
    assert db.scalar(
        select(func.count(OperationEvent.id)).where(
            OperationEvent.operation == "logistic_unit_content_added"
        )
    ) == 1


def test_full_content_removal_can_be_retried_after_projection_is_deleted(db):
    product, pieces, _, box = create_product_and_box(
        db,
        product_code="GLOVE-LEDGER",
        uom_code="PCS",
    )
    add_logistic_unit_content(
        db,
        box.uid,
        LogisticUnitContentCreate(
            product_id=product.id,
            quantity=Decimal("2"),
            uom_id=pieces.id,
            actor="receiver",
            idempotency_key="content:add:glove-001",
        ),
    )
    content_id = db.scalar(select(LogisticUnitContent.id))
    removal = LogisticUnitContentRemoveRequest(
        quantity=Decimal("2"),
        actor="picker",
        reason="Выдача сотруднику",
        idempotency_key="content:remove:glove-001",
    )

    remove_logistic_unit_content(db, box.uid, content_id, removal)
    remove_logistic_unit_content(db, box.uid, content_id, removal)

    assert db.scalar(select(LogisticUnitContent)) is None
    assert db.scalar(select(StockPosition)) is None
    assert db.scalar(select(func.count(StockDocument.id))) == 2
    assert db.scalar(select(func.count(StockMovement.id))) == 2
    removal_document = db.scalar(
        select(StockDocument).where(
            StockDocument.document_type == "logistic_unit_content_remove"
        )
    )
    assert removal_document.reason == "Выдача сотруднику"
    assert removal_document.movements[0].source_logistic_unit_id == box.id

    with pytest.raises(HTTPException, match="another content command") as error:
        remove_logistic_unit_content(
            db,
            box.uid,
            content_id,
            removal.model_copy(update={"quantity": Decimal("1")}),
        )
    assert error.value.status_code == 409


def test_projection_failure_rolls_back_document_movement_and_stock(db, monkeypatch):
    product, pieces, _, box = create_product_and_box(
        db,
        product_code="ROLLBACK-ITEM",
        uom_code="PCS",
    )

    def fail_projection(*args, **kwargs):
        raise RuntimeError("projection failed")

    monkeypatch.setattr("app.services.create_event", fail_projection)
    with pytest.raises(RuntimeError, match="projection failed"):
        add_logistic_unit_content(
            db,
            box.uid,
            LogisticUnitContentCreate(
                product_id=product.id,
                quantity=Decimal("3"),
                uom_id=pieces.id,
                idempotency_key="content:add:rollback",
            ),
        )

    assert db.scalar(select(LogisticUnitContent)) is None
    assert db.scalar(select(StockPosition)) is None
    assert db.scalar(select(StockDocument)) is None
    assert db.scalar(select(StockMovement)) is None
