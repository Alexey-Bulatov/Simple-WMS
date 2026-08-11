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
    LogisticUnitContent,
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
    LogisticUnitContentCreate,
    LogisticUnitContentRemoveRequest,
    LogisticUnitCreate,
    ProductCreate,
    StockDocumentPost,
    StockDocumentReverseRequest,
    StockMovementPost,
)
from app.services import (
    add_logistic_unit_content,
    create_logistic_unit,
    create_product,
    ensure_reference_catalogs,
    remove_logistic_unit_content,
)
from app.stock_ledger import (
    post_stock_document,
    reverse_stock_document,
    stock_document_payload,
)
from app.stock_reconciliation import reconcile_stock_positions


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


def create_content(db, *, code: str = "REVERSAL-ITEM", quantity: str = "2"):
    ensure_reference_catalogs(db)
    pieces = reference(db, UnitOfMeasure, "PCS")
    product = create_product(
        db,
        ProductCreate(code=code, name=f"Товар {code}", base_uom_id=pieces.id),
    )
    box_type = reference(db, LogisticUnitType, "BOX")
    box = create_logistic_unit(
        db,
        LogisticUnitCreate(type_id=box_type.id, uid=f"BOX-{code}", actor="test"),
    )
    add_logistic_unit_content(
        db,
        box.uid,
        LogisticUnitContentCreate(
            product_id=product.id,
            quantity=Decimal(quantity),
            uom_id=pieces.id,
            actor="receiver",
            idempotency_key=f"content:add:{code}",
        ),
    )
    document = db.scalar(
        select(StockDocument).where(
            StockDocument.document_type == "logistic_unit_content_add",
            StockDocument.reference_uid == box.uid,
        )
    )
    return product, pieces, box, document


def reversal_request(*, key: str, reason: str = "Исправление ошибки"):
    return StockDocumentReverseRequest(
        idempotency_key=key,
        actor="supervisor",
        reason=reason,
    )


def test_reversal_removes_added_content_and_is_idempotent(db):
    _, _, _, original = create_content(db)
    request = reversal_request(key="reversal:add:001")

    reversal = reverse_stock_document(db, original.uid, request)
    repeated = reverse_stock_document(db, original.uid, request)

    db.refresh(original)
    assert repeated.id == reversal.id
    assert original.status == StockDocumentStatus.REVERSED
    assert original.reversed_at is not None
    assert reversal.status == StockDocumentStatus.POSTED
    assert reversal.reversal_of_id == original.id
    assert reversal.movements[0].source_logistic_unit_id == (
        original.movements[0].destination_logistic_unit_id
    )
    assert reversal.movements[0].destination_logistic_unit_id is None
    assert db.scalar(select(LogisticUnitContent)) is None
    assert db.scalar(select(StockPosition)) is None
    assert db.scalar(select(func.count(StockDocument.id))) == 2
    assert db.scalar(select(func.count(StockMovement.id))) == 2
    original_payload = stock_document_payload(db, original)
    assert original_payload["reversed_by_id"] == reversal.id
    assert original_payload["reversed_by_uid"] == reversal.uid
    reconciliation = reconcile_stock_positions(db)
    assert reconciliation["is_consistent"] is True
    assert reconciliation["zero_balance_identity_count"] == 1


def test_reversal_of_full_removal_restores_content_projection(db):
    _, pieces, box, _ = create_content(db, code="RESTORE-ITEM")
    content_id = db.scalar(select(LogisticUnitContent.id))
    remove_logistic_unit_content(
        db,
        box.uid,
        content_id,
        LogisticUnitContentRemoveRequest(
            quantity=Decimal("2"),
            actor="picker",
            reason="Ошибочная выдача",
            idempotency_key="content:remove:restore",
        ),
    )
    removal = db.scalar(
        select(StockDocument).where(
            StockDocument.document_type == "logistic_unit_content_remove"
        )
    )

    reversal = reverse_stock_document(
        db,
        removal.uid,
        reversal_request(key="reversal:remove:001"),
    )

    content = db.scalar(select(LogisticUnitContent))
    position = db.scalar(select(StockPosition))
    assert removal.status == StockDocumentStatus.REVERSED
    assert reversal.movements[0].destination_logistic_unit_id == box.id
    assert content.quantity == Decimal("2")
    assert content.uom_id == pieces.id
    assert position.quantity == Decimal("2")
    assert reconcile_stock_positions(db)["is_consistent"] is True


def test_reversal_fails_when_receipt_stock_was_partly_consumed(db):
    _, _, box, receipt = create_content(db, code="CONSUMED-ITEM")
    content_id = db.scalar(select(LogisticUnitContent.id))
    remove_logistic_unit_content(
        db,
        box.uid,
        content_id,
        LogisticUnitContentRemoveRequest(
            quantity=Decimal("1"),
            actor="picker",
            idempotency_key="content:remove:consumed",
        ),
    )

    with pytest.raises(HTTPException, match="insufficient source stock"):
        reverse_stock_document(
            db,
            receipt.uid,
            reversal_request(key="reversal:consumed:001"),
        )

    db.refresh(receipt)
    assert receipt.status == StockDocumentStatus.POSTED
    assert db.scalar(select(LogisticUnitContent.quantity)) == Decimal("1")
    assert db.scalar(select(StockPosition.quantity)) == Decimal("1")
    assert db.scalar(select(func.count(StockDocument.id))) == 2
    assert db.scalar(
        select(func.count(StockDocument.id)).where(
            StockDocument.reversal_of_id == receipt.id
        )
    ) == 0


def test_reversal_rejects_second_command_opening_balance_and_reversal_document(db):
    _, _, _, original = create_content(db, code="GUARD-ITEM")
    reversal = reverse_stock_document(
        db,
        original.uid,
        reversal_request(key="reversal:guard:001"),
    )

    with pytest.raises(HTTPException, match="already reversed"):
        reverse_stock_document(
            db,
            original.uid,
            reversal_request(key="reversal:guard:002"),
        )
    with pytest.raises(HTTPException, match="another reversal"):
        reverse_stock_document(
            db,
            original.uid,
            reversal_request(key="reversal:guard:001", reason="Другая причина"),
        )
    with pytest.raises(HTTPException, match="reversal document cannot be reversed"):
        reverse_stock_document(
            db,
            reversal.uid,
            reversal_request(key="reversal:of-reversal"),
        )

    opening = StockDocument(
        uid="OPENING-REVERSAL-TEST",
        document_type="opening_balance",
        status=StockDocumentStatus.POSTED,
        idempotency_key="opening:reversal:test",
        actor="test",
        posted_at=original.posted_at,
    )
    db.add(opening)
    db.commit()
    with pytest.raises(HTTPException, match="adjustment document"):
        reverse_stock_document(
            db,
            opening.uid,
            reversal_request(key="reversal:opening"),
        )

    changed_product, _, _, changed_document = create_content(
        db,
        code="BASE-CHANGED",
    )
    kilograms = reference(db, UnitOfMeasure, "KG")
    changed_product.base_uom_id = kilograms.id
    db.commit()
    with pytest.raises(HTTPException, match="base unit changed"):
        reverse_stock_document(
            db,
            changed_document.uid,
            reversal_request(key="reversal:base-changed"),
        )


def test_reversal_api_returns_compensation_and_links_original(db):
    _, _, _, original = create_content(db, code="API-REVERSAL")

    def override_db():
        yield db

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[api_routes.get_db] = override_db
    try:
        with TestClient(app) as client:
            response = client.post(
                f"/api/stock-documents/{original.uid}/reverse",
                json={
                    "idempotency_key": "reversal:api:001",
                    "actor": "supervisor",
                    "reason": "Исправление через API",
                },
            )
            assert response.status_code == 200
            assert response.json()["document_type"] == "stock_reversal"
            assert response.json()["reversal_of_uid"] == original.uid
            assert len(response.json()["movements"]) == 1

            original_response = client.get(f"/api/stock-documents/{original.uid}")
            assert original_response.json()["status"] == "reversed"
            assert original_response.json()["reversed_by_uid"] == response.json()["uid"]

            operation = client.get("/openapi.json").json()["paths"][
                "/api/stock-documents/{document_uid}/reverse"
            ]["post"]
            assert "компенсирующий документ" in operation["summary"]
    finally:
        app.dependency_overrides.clear()


def test_multiline_chain_is_reversed_in_opposite_order(db):
    ensure_reference_catalogs(db)
    pieces = reference(db, UnitOfMeasure, "PCS")
    owner = reference(db, StockOwner, "INTERNAL")
    product = create_product(
        db,
        ProductCreate(code="CHAIN-ITEM", name="Цепочка", base_uom_id=pieces.id),
    )
    box_type = reference(db, LogisticUnitType, "BOX")
    units = [
        create_logistic_unit(
            db,
            LogisticUnitCreate(
                type_id=box_type.id,
                uid=f"BOX-CHAIN-{number}",
                actor="test",
            ),
        )
        for number in (1, 2, 3)
    ]
    post_stock_document(
        db,
        StockDocumentPost(
            document_type="receipt",
            idempotency_key="chain:receipt",
            movements=[
                StockMovementPost(
                    product_id=product.id,
                    owner_id=owner.id,
                    destination_quality_status="released",
                    input_quantity=Decimal("5"),
                    input_uom_id=pieces.id,
                    destination_logistic_unit_id=units[0].id,
                )
            ],
        ),
    )
    chain = post_stock_document(
        db,
        StockDocumentPost(
            document_type="internal_chain",
            idempotency_key="chain:movement",
            movements=[
                StockMovementPost(
                    product_id=product.id,
                    owner_id=owner.id,
                    source_quality_status="released",
                    destination_quality_status="released",
                    input_quantity=Decimal("5"),
                    input_uom_id=pieces.id,
                    source_logistic_unit_id=units[0].id,
                    destination_logistic_unit_id=units[1].id,
                ),
                StockMovementPost(
                    product_id=product.id,
                    owner_id=owner.id,
                    source_quality_status="released",
                    destination_quality_status="released",
                    input_quantity=Decimal("5"),
                    input_uom_id=pieces.id,
                    source_logistic_unit_id=units[1].id,
                    destination_logistic_unit_id=units[2].id,
                ),
            ],
        ),
    )

    reversal = reverse_stock_document(
        db,
        chain.uid,
        reversal_request(key="reversal:chain"),
    )

    position = db.scalar(select(StockPosition))
    assert position.logistic_unit_id == units[0].id
    assert position.quantity == Decimal("5")
    assert reversal.movements[0].source_logistic_unit_id == units[2].id
    assert reversal.movements[0].destination_logistic_unit_id == units[1].id
    assert reversal.movements[1].source_logistic_unit_id == units[1].id
    assert reversal.movements[1].destination_logistic_unit_id == units[0].id
    assert reconcile_stock_positions(db)["is_consistent"] is True
