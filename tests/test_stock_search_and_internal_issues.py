from datetime import date, timedelta
from decimal import Decimal

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.session import Base
from app.db.session import get_db
from app.main import app
from app.api import routes as api_routes
from app.internal_issues import (
    accountability_writeoff_payload,
    create_accountability_writeoff,
    create_internal_issue,
    create_internal_return,
    internal_issue_payload,
    internal_return_payload,
    process_due_accountability_writeoffs,
    reverse_internal_issue,
)
from app.models.entities import (
    Location,
    ProductPackaging,
    StockDocument,
    StockOwner,
    StockPosition,
    StockRecipient,
    UnitOfMeasure,
    Warehouse,
    Zone,
)
from app.models.enums import LocationKind, StockDocumentStatus, StockRecipientKind
from app.schemas import (
    InternalIssueCreate,
    InternalIssueLineCreate,
    InternalAccountabilityWriteoffCreate,
    InternalReturnCreate,
    InternalReturnLineCreate,
    ProductCreate,
    StockDocumentReverseRequest,
)
from app.services import create_product, ensure_reference_catalogs
from app.stock_search import search_stock
from app.stock_ledger import reverse_stock_document


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
    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.clear()


def create_context(db, *, quantity: str = "10"):
    ensure_reference_catalogs(db)
    pieces = db.scalar(select(UnitOfMeasure).where(UnitOfMeasure.code == "PCS"))
    owner = db.scalar(select(StockOwner).where(StockOwner.code == "INTERNAL"))
    product = create_product(
        db,
        ProductCreate(code="GLOVES", name="Перчатки защитные", base_uom_id=pieces.id),
    )
    warehouse = Warehouse(code="WH-ISS", name="Склад выдачи")
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
        code="WH-ISS-ST01-R01-L01-P01",
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
    recipient = StockRecipient(
        code="EMP-001",
        name="Иванов Иван",
        kind=StockRecipientKind.EMPLOYEE,
    )
    packaging = ProductPackaging(
        product_id=product.id,
        code="BOX-10",
        name="Коробка 10 пар",
        quantity=Decimal("10"),
        uom_id=pieces.id,
        base_quantity=Decimal("10"),
        barcode="460000000001",
    )
    db.add_all([position, recipient, packaging])
    db.commit()
    return product, pieces, owner, warehouse, location, position, recipient


def issue_payload(
    position,
    pieces,
    recipient,
    *,
    key="issue:001",
    quantity="3",
    issue_kind="permanent",
    accountability_policy=None,
    planned_close_date=None,
    auto_writeoff=False,
):
    return InternalIssueCreate(
        recipient_id=recipient.id,
        issue_kind=issue_kind,
        accountability_policy=accountability_policy,
        planned_close_date=planned_close_date,
        auto_writeoff=auto_writeoff,
        reason="Выдача средств защиты",
        request_reference="REQ-42",
        idempotency_key=key,
        actor="storekeeper",
        lines=[
            InternalIssueLineCreate(
                stock_position_id=position.id,
                input_quantity=Decimal(quantity),
                input_uom_id=pieces.id,
                source_scan="WH-ISS-ST01-R01-L01-P01",
                item_scan="460000000001",
            )
        ],
    )


def return_payload(issue, pieces, *, key="return:001", quantity="1", quality="released"):
    return InternalReturnCreate(
        reason="Возврат выданного имущества",
        idempotency_key=key,
        actor="storekeeper",
        lines=[
            InternalReturnLineCreate(
                issue_movement_id=issue.movements[0].id,
                input_quantity=Decimal(quantity),
                input_uom_id=pieces.id,
                quality_status=quality,
                destination_scan="WH-ISS-ST01-R01-L01-P01",
                item_scan="460000000001",
            )
        ],
    )


def test_search_resolves_packaging_barcode_and_explains_stock(db):
    product, _, owner, warehouse, location, position, _ = create_context(db)
    db.add(
        StockPosition(
            product_id=product.id,
            owner_id=owner.id,
            quality_status="quarantine",
            quantity=Decimal("2"),
            location_id=location.id,
        )
    )
    db.commit()

    result = search_stock(
        db,
        "460000000001",
        warehouse_scope={warehouse.id},
    )

    assert result["result"] == "exact"
    item = result["items"][0]
    assert item["product_code"] == "GLOVES"
    assert item["match_reason"] == "barcode"
    assert item["total_quantity"] == Decimal("12")
    assert item["available_quantity"] == Decimal("10")
    assert item["quarantine_quantity"] == Decimal("2")
    assert item["positions"][0]["warehouse_code"] == "WH-ISS"
    assert item["packagings"][0]["matched"] is True
    assert position.id in {row["id"] for row in item["positions"]}


def test_search_keeps_zero_stock_product_and_hides_other_warehouse_details(db):
    product, pieces, _, warehouse, _, _, _ = create_context(db)
    other = create_product(
        db,
        ProductCreate(code="GLOVES-WINTER", name="Перчатки зимние", base_uom_id=pieces.id),
    )

    result = search_stock(db, "перчатки", warehouse_scope={warehouse.id})

    assert result["result"] == "multiple"
    zero_item = next(item for item in result["items"] if item["product_id"] == other.id)
    assert zero_item["total_quantity"] == 0
    assert zero_item["positions"] == []
    assert product.id in {item["product_id"] for item in result["items"]}


def test_internal_issue_is_atomic_idempotent_and_keeps_recipient_snapshot(db):
    _, pieces, _, warehouse, _, position, recipient = create_context(db, quantity="5")
    payload = issue_payload(position, pieces, recipient)

    document = create_internal_issue(db, payload, warehouse_scope={warehouse.id})
    repeated = create_internal_issue(db, payload, warehouse_scope={warehouse.id})
    data = internal_issue_payload(db, document)

    assert repeated.id == document.id
    assert document.status == StockDocumentStatus.POSTED
    assert data["recipient_code"] == "EMP-001"
    assert data["recipient_name"] == "Иванов Иван"
    assert data["request_reference"] == "REQ-42"
    assert data["movements"][0]["quantity"] == Decimal("3")
    assert db.get(StockPosition, position.id).quantity == Decimal("2")
    recipient.name = "Иванов И. И."
    db.commit()
    assert internal_issue_payload(db, document)["recipient_name"] == "Иванов Иван"
    assert len(list(db.scalars(select(StockDocument)))) == 1


def test_internal_issue_rejects_wrong_scan_and_unavailable_warehouse(db):
    _, pieces, _, warehouse, _, position, recipient = create_context(db)
    payload = issue_payload(position, pieces, recipient)
    payload.lines[0].item_scan = "WRONG-CODE"

    with pytest.raises(HTTPException) as wrong_scan:
        create_internal_issue(db, payload, warehouse_scope={warehouse.id})
    assert wrong_scan.value.status_code == 400
    payload.lines[0].item_scan = "GLOVES"

    with pytest.raises(HTTPException) as wrong_warehouse:
        create_internal_issue(db, payload, warehouse_scope=set())
    assert wrong_warehouse.value.status_code == 403
    assert db.get(StockPosition, position.id).quantity == Decimal("10")


def test_internal_issue_converts_package_count_to_base_quantity(db):
    _, _, _, warehouse, _, position, recipient = create_context(db, quantity="25")
    packaging = db.scalar(select(ProductPackaging).where(ProductPackaging.code == "BOX-10"))
    payload = InternalIssueCreate(
        recipient_id=recipient.id,
        reason="Выдача двух коробок",
        idempotency_key="issue:packages",
        actor="storekeeper",
        lines=[
            InternalIssueLineCreate(
                stock_position_id=position.id,
                input_quantity=Decimal("2"),
                packaging_id=packaging.id,
                source_scan="WH-ISS-ST01-R01-L01-P01",
                item_scan=packaging.barcode,
            )
        ],
    )

    document = create_internal_issue(db, payload, warehouse_scope={warehouse.id})

    assert document.movements[0].quantity == Decimal("20")
    assert db.get(StockPosition, position.id).quantity == Decimal("5")
    assert document.attributes["line_inputs"][0]["entered_quantity"] == "2"
    assert document.attributes["line_inputs"][0]["packaging_code"] == "BOX-10"


def test_internal_issue_reversal_restores_stock_as_correction(db):
    _, pieces, _, warehouse, _, position, recipient = create_context(db, quantity="5")
    document = create_internal_issue(
        db,
        issue_payload(position, pieces, recipient),
        warehouse_scope={warehouse.id},
    )

    corrected = reverse_internal_issue(
        db,
        document.uid,
        StockDocumentReverseRequest(
            idempotency_key="issue:001:reverse",
            actor="manager",
            reason="Ошибочная выдача",
        ),
    )

    assert corrected.status == StockDocumentStatus.REVERSED
    restored = db.scalar(select(StockPosition).where(StockPosition.product_id == position.product_id))
    assert restored.quantity == Decimal("5")
    assert len(list(db.scalars(select(StockDocument)))) == 2


def test_accountable_issue_supports_partial_return_and_quarantine(db):
    product, pieces, owner, warehouse, location, position, recipient = create_context(
        db,
        quantity="8",
    )
    issue = create_internal_issue(
        db,
        issue_payload(
            position,
            pieces,
            recipient,
            quantity="5",
            issue_kind="accountable",
            accountability_policy="return_required",
            planned_close_date=date.today() + timedelta(days=30),
        ),
        warehouse_scope={warehouse.id},
    )

    first_return = create_internal_return(
        db,
        issue.uid,
        return_payload(issue, pieces, quantity="2"),
        warehouse_scope={warehouse.id},
    )
    repeated = create_internal_return(
        db,
        issue.uid,
        return_payload(issue, pieces, quantity="2"),
        warehouse_scope={warehouse.id},
    )
    second_return = create_internal_return(
        db,
        issue.uid,
        return_payload(
            issue,
            pieces,
            key="return:002",
            quantity="1",
            quality="quarantine",
        ),
        warehouse_scope={warehouse.id},
    )
    data = internal_issue_payload(db, issue)

    assert repeated.id == first_return.id
    assert internal_return_payload(db, second_return)["issue_uid"] == issue.uid
    assert data["accountability_status"] == "partial"
    assert data["movements"][0]["returned_quantity"] == Decimal("3")
    assert data["movements"][0]["remaining_quantity"] == Decimal("2")
    assert db.scalar(
        select(StockPosition.quantity).where(
            StockPosition.product_id == product.id,
            StockPosition.owner_id == owner.id,
            StockPosition.location_id == location.id,
            StockPosition.quality_status == "released",
        )
    ) == Decimal("5")
    assert db.scalar(
        select(StockPosition.quantity).where(
            StockPosition.product_id == product.id,
            StockPosition.owner_id == owner.id,
            StockPosition.location_id == location.id,
            StockPosition.quality_status == "quarantine",
        )
    ) == Decimal("1")


def test_internal_return_rejects_permanent_and_excess_quantity(db):
    _, pieces, _, warehouse, _, position, recipient = create_context(db, quantity="6")
    permanent = create_internal_issue(
        db,
        issue_payload(position, pieces, recipient, quantity="2"),
        warehouse_scope={warehouse.id},
    )
    with pytest.raises(HTTPException, match="only an accountable"):
        create_internal_return(
            db,
            permanent.uid,
            return_payload(permanent, pieces),
            warehouse_scope={warehouse.id},
        )

    position = db.scalar(select(StockPosition).where(StockPosition.product_id == position.product_id))
    accountable = create_internal_issue(
        db,
        issue_payload(
            position,
            pieces,
            recipient,
            key="issue:accountable",
            quantity="2",
            issue_kind="accountable",
            accountability_policy="return_required",
        ),
        warehouse_scope={warehouse.id},
    )
    with pytest.raises(HTTPException, match="exceeds the outstanding"):
        create_internal_return(
            db,
            accountable.uid,
            return_payload(
                accountable,
                pieces,
                key="return:excess",
                quantity="3",
            ),
            warehouse_scope={warehouse.id},
        )
    assert internal_issue_payload(db, accountable)["accountability_status"] == "open"


def test_normative_auto_writeoff_closes_only_outstanding_accountability(db):
    _, pieces, _, warehouse, _, position, recipient = create_context(db, quantity="10")
    planned_date = date.today() - timedelta(days=1)
    issue = create_internal_issue(
        db,
        issue_payload(
            position,
            pieces,
            recipient,
            quantity="4",
            issue_kind="accountable",
            accountability_policy="normative_writeoff",
            planned_close_date=planned_date,
            auto_writeoff=True,
        ),
        warehouse_scope={warehouse.id},
    )
    create_internal_return(
        db,
        issue.uid,
        return_payload(issue, pieces, quantity="1"),
        warehouse_scope={warehouse.id},
    )
    stock_before_writeoff = db.scalar(
        select(StockPosition.quantity).where(StockPosition.id == position.id)
    )

    processed = process_due_accountability_writeoffs(db, as_of_date=date.today())
    repeated = process_due_accountability_writeoffs(db, as_of_date=date.today())
    data = internal_issue_payload(db, issue)

    assert len(processed) == 1
    assert repeated == []
    assert accountability_writeoff_payload(db, processed[0])["issue_uid"] == issue.uid
    assert data["accountability_status"] == "closed_mixed"
    assert data["movements"][0]["returned_quantity"] == Decimal("1")
    assert data["movements"][0]["written_off_quantity"] == Decimal("3")
    assert data["movements"][0]["remaining_quantity"] == Decimal("0")
    assert db.scalar(
        select(StockPosition.quantity).where(StockPosition.id == position.id)
    ) == stock_before_writeoff

    reverse_stock_document(
        db,
        processed[0].uid,
        StockDocumentReverseRequest(
            idempotency_key="writeoff:auto:reverse",
            actor="manager",
            reason="Исправление ошибочного норматива",
        ),
    )
    reopened = internal_issue_payload(db, issue)
    assert reopened["accountability_status"] == "partial"
    assert reopened["movements"][0]["remaining_quantity"] == Decimal("3")
    assert db.scalar(
        select(StockPosition.quantity).where(StockPosition.id == position.id)
    ) == stock_before_writeoff


def test_normative_writeoff_cannot_run_before_due_date(db):
    _, pieces, _, warehouse, _, position, recipient = create_context(db)
    issue = create_internal_issue(
        db,
        issue_payload(
            position,
            pieces,
            recipient,
            issue_kind="accountable",
            accountability_policy="normative_writeoff",
            planned_close_date=date.today() + timedelta(days=90),
            auto_writeoff=True,
        ),
        warehouse_scope={warehouse.id},
    )

    assert process_due_accountability_writeoffs(db, as_of_date=date.today()) == []
    with pytest.raises(HTTPException, match="date has not been reached"):
        create_accountability_writeoff(
            db,
            issue.uid,
            InternalAccountabilityWriteoffCreate(
                reason="Попытка досрочного списания",
                idempotency_key="writeoff:early",
                actor="manager",
            ),
            as_of_date=date.today(),
        )


def test_search_and_internal_issue_api_contract(db, client):
    _, pieces, _, warehouse, _, position, recipient = create_context(db, quantity="5")

    search_response = client.get(
        "/api/stock-search",
        params={"query": "GLOVES", "warehouse_id": warehouse.id},
    )
    assert search_response.status_code == 200, search_response.text
    assert search_response.json()["items"][0]["positions"][0]["id"] == position.id

    issue_response = client.post(
        "/api/internal-issues",
        json=issue_payload(position, pieces, recipient).model_dump(mode="json"),
    )
    assert issue_response.status_code == 200, issue_response.text
    assert issue_response.json()["recipient_code"] == "EMP-001"
    assert issue_response.json()["issue_kind"] == "permanent"
    assert issue_response.json()["accountability_status"] == "not_applicable"
    assert issue_response.json()["movements"][0]["quantity"] == "3.000000"
    assert client.get("/api/internal-issues").json()[0]["uid"] == issue_response.json()["uid"]


def test_accountable_issue_and_return_api_contract(db, client):
    _, pieces, _, warehouse, _, position, recipient = create_context(db, quantity="5")
    payload = issue_payload(
        position,
        pieces,
        recipient,
        key="issue:api-accountable",
        quantity="2",
        issue_kind="accountable",
        accountability_policy="return_required",
    )
    issue_response = client.post(
        "/api/internal-issues",
        json=payload.model_dump(mode="json"),
    )
    assert issue_response.status_code == 200, issue_response.text
    issue = issue_response.json()
    movement_id = issue["movements"][0]["id"]

    return_response = client.post(
        f"/api/internal-issues/{issue['uid']}/returns",
        json={
            "reason": "Возврат после работ",
            "idempotency_key": "return:api-accountable",
            "actor": "storekeeper",
            "lines": [
                {
                    "issue_movement_id": movement_id,
                    "input_quantity": "2",
                    "input_uom_id": pieces.id,
                    "quality_status": "released",
                    "destination_scan": "WH-ISS-ST01-R01-L01-P01",
                    "item_scan": "GLOVES",
                }
            ],
        },
    )
    assert return_response.status_code == 200, return_response.text
    assert return_response.json()["issue_uid"] == issue["uid"]
    refreshed = client.get(f"/api/internal-issues/{issue['uid']}").json()
    assert refreshed["accountability_status"] == "returned"
    assert refreshed["movements"][0]["remaining_quantity"] == "0"
    assert len(client.get(f"/api/internal-issues/{issue['uid']}/returns").json()) == 1


def test_catalog_creation_api_feeds_stock_search_and_web_scenario(db, client):
    _, pieces, _, warehouse, _, _, _ = create_context(db)

    page = client.get("/stock")
    assert page.status_code == 200
    assert "Новая позиция" in page.text
    assert "Добавить упаковку" in page.text

    product_response = client.post(
        "/api/products",
        json={
            "code": " pen-001 ",
            "name": " Ручка шариковая ",
            "base_uom_id": pieces.id,
            "shelf_life_days": None,
        },
    )
    assert product_response.status_code == 200, product_response.text
    product = product_response.json()
    assert product["code"] == "PEN-001"
    assert product["name"] == "Ручка шариковая"

    packaging_response = client.post(
        "/api/product-packagings",
        json={
            "product_id": product["id"],
            "code": "box-50",
            "name": "Коробка 50 штук",
            "quantity": "50",
            "uom_id": pieces.id,
            "barcode": "4600000000050",
        },
    )
    assert packaging_response.status_code == 200, packaging_response.text
    assert packaging_response.json()["code"] == "BOX-50"

    search_response = client.get(
        "/api/stock-search",
        params={"query": "4600000000050", "warehouse_id": warehouse.id},
    )
    assert search_response.status_code == 200, search_response.text
    item = search_response.json()["items"][0]
    assert item["product_code"] == "PEN-001"
    assert item["available_quantity"] == "0"
    assert item["packagings"][0]["matched"] is True
