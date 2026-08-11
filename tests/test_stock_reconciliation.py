from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
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
    StockPosition,
    UnitOfMeasure,
    utcnow,
)
from app.models.enums import StockDocumentStatus
from app.schemas import LogisticUnitContentCreate, LogisticUnitCreate, ProductCreate
from app.services import (
    add_logistic_unit_content,
    create_logistic_unit,
    create_product,
    ensure_reference_catalogs,
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


def create_stock(
    db,
    *,
    code: str = "RECON-ITEM",
    uom_code: str = "PCS",
    post_stock: bool = True,
):
    ensure_reference_catalogs(db)
    base_uom = reference(db, UnitOfMeasure, uom_code)
    owner = reference(db, StockOwner, "INTERNAL")
    product = create_product(
        db,
        ProductCreate(code=code, name=f"Товар {code}", base_uom_id=base_uom.id),
    )
    box_type = reference(db, LogisticUnitType, "BOX")
    box = create_logistic_unit(
        db,
        LogisticUnitCreate(type_id=box_type.id, uid=f"BOX-{code}", actor="test"),
    )
    if post_stock:
        add_logistic_unit_content(
            db,
            box.uid,
            LogisticUnitContentCreate(
                product_id=product.id,
                quantity=Decimal("2"),
                uom_id=base_uom.id,
                actor="test",
                idempotency_key=f"reconciliation:add:{code}",
            ),
        )
    return product, base_uom, owner, box


def add_manual_movement(
    db,
    *,
    uid: str,
    status: StockDocumentStatus,
    product,
    owner,
    base_uom,
    quantity: Decimal,
    source_unit_id: int | None = None,
    destination_unit_id: int | None = None,
    source_quality_status: str | None = None,
    destination_quality_status: str | None = None,
):
    document = StockDocument(
        uid=uid,
        document_type="reconciliation_test",
        status=status,
        idempotency_key=f"test:{uid}",
        actor="test",
        posted_at=utcnow() if status == StockDocumentStatus.POSTED else None,
    )
    db.add(document)
    db.flush()
    db.add(
        StockMovement(
            document_id=document.id,
            sequence_no=1,
            product_id=product.id,
            owner_id=owner.id,
            source_quality_status=source_quality_status,
            destination_quality_status=destination_quality_status,
            quantity=quantity,
            base_uom_id=base_uom.id,
            input_quantity=quantity,
            input_uom_id=base_uom.id,
            conversion_factor=Decimal("1"),
            source_logistic_unit_id=source_unit_id,
            destination_logistic_unit_id=destination_unit_id,
        )
    )
    db.commit()


def test_reconciliation_accepts_positions_created_by_posted_movements(db):
    create_stock(db)

    result = reconcile_stock_positions(db)

    assert result["is_consistent"] is True
    assert result["movement_count"] == 1
    assert result["position_count"] == 1
    assert result["checked_identity_count"] == 1
    assert result["matched_identity_count"] == 1
    assert result["discrepancy_count"] == 0
    assert result["issues"] == []


def test_reconciliation_reports_changed_and_missing_positions(db):
    create_stock(db)
    position = db.scalar(select(StockPosition))
    position.quantity = Decimal("3")
    db.commit()

    changed = reconcile_stock_positions(db)
    issue = changed["issues"][0]
    assert issue["kind"] == "quantity_mismatch"
    assert issue["expected_quantity"] == Decimal("2")
    assert issue["actual_quantity"] == Decimal("3")
    assert issue["delta_quantity"] == Decimal("1")

    db.delete(position)
    db.commit()
    missing = reconcile_stock_positions(db)
    assert missing["issues"][0]["kind"] == "missing_position"
    assert missing["issues"][0]["actual_quantity"] == Decimal("0")


def test_reconciliation_ignores_drafts_and_reports_unexpected_position(db):
    product, base_uom, owner, box = create_stock(db, post_stock=False)
    db.add(
        StockPosition(
            product_id=product.id,
            owner_id=owner.id,
            quality_status="released",
            quantity=Decimal("2"),
            logistic_unit_id=box.id,
        )
    )
    db.commit()
    add_manual_movement(
        db,
        uid="DOC-DRAFT-RECON",
        status=StockDocumentStatus.DRAFT,
        product=product,
        owner=owner,
        base_uom=base_uom,
        quantity=Decimal("5"),
        destination_unit_id=box.id,
        destination_quality_status="released",
    )

    result = reconcile_stock_positions(db)

    assert result["movement_count"] == 0
    assert result["ignored_movement_count"] == 1
    assert result["issues"][0]["kind"] == "unexpected_position"


def test_reconciliation_reports_negative_and_invalid_ledger_sides(db):
    product, base_uom, owner, box = create_stock(db)
    add_manual_movement(
        db,
        uid="DOC-NEGATIVE-RECON",
        status=StockDocumentStatus.POSTED,
        product=product,
        owner=owner,
        base_uom=base_uom,
        quantity=Decimal("3"),
        source_unit_id=box.id,
        source_quality_status="released",
    )
    add_manual_movement(
        db,
        uid="DOC-INVALID-RECON",
        status=StockDocumentStatus.POSTED,
        product=product,
        owner=owner,
        base_uom=base_uom,
        quantity=Decimal("1"),
        source_unit_id=box.id,
    )

    result = reconcile_stock_positions(db)
    kinds = {issue["kind"] for issue in result["issues"]}

    assert result["negative_ledger_count"] == 1
    assert "negative_ledger_balance" in kinds
    assert "invalid_movement" in kinds


def test_reconciliation_reports_mixed_base_units(db):
    product, _, owner, box = create_stock(db, code="MASS-RECON", uom_code="KG")
    grams = reference(db, UnitOfMeasure, "G")
    add_manual_movement(
        db,
        uid="DOC-UOM-RECON",
        status=StockDocumentStatus.POSTED,
        product=product,
        owner=owner,
        base_uom=grams,
        quantity=Decimal("1000"),
        destination_unit_id=box.id,
        destination_quality_status="released",
    )

    result = reconcile_stock_positions(db)
    kinds = {issue["kind"] for issue in result["issues"]}

    assert "base_uom_mismatch" in kinds
    assert "quantity_mismatch" in kinds


def test_reconciliation_api_is_read_only_and_documented(db):
    create_stock(db)

    def override_db():
        yield db

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[api_routes.get_db] = override_db
    try:
        with TestClient(app) as client:
            response = client.get("/api/stock-reconciliation")
            assert response.status_code == 200
            assert response.json()["is_consistent"] is True
            assert response.json()["matched_identity_count"] == 1
            assert client.post("/api/stock-reconciliation", json={}).status_code == 405

            operation = client.get("/openapi.json").json()["paths"][
                "/api/stock-reconciliation"
            ]["get"]
            assert "Сверить текущие позиции" in operation["summary"]
    finally:
        app.dependency_overrides.clear()
