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
from app.inbound_receipts import (
    create_inbound_receipt,
    inbound_receipt_payload,
    post_inbound_receipt,
)
from app.logistic_tasks import (
    complete_logistic_task,
    putaway_inbound_receipt_result,
    start_logistic_task,
)
from app.main import app
from app.models.entities import (
    InboundReceipt,
    InboundReceiptLine,
    Batch,
    Location,
    LogisticUnit,
    LogisticUnitContent,
    LogisticUnitType,
    LogisticTask,
    OperationEvent,
    ProductPackaging,
    StockDocument,
    StockMovement,
    StockOwner,
    StockPosition,
    UnitOfMeasure,
    Warehouse,
    Zone,
)
from app.models.enums import (
    InboundReceiptKind,
    InboundReceiptStatus,
    LocationKind,
    LogisticUnitStatus,
    StockDocumentStatus,
    TaskPriority,
    TaskStatus,
    TaskType,
)
from app.schemas import (
    InboundReceiptActualLineCreate,
    InboundReceiptCreate,
    InboundReceiptLineCreate,
    InboundReceiptPost,
    InboundReceiptPutawayRequest,
    ProductCreate,
    StockDocumentReverseRequest,
)
from app.services import create_product, ensure_reference_catalogs
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


def create_receiving_destination(db, warehouse):
    zone = Zone(
        warehouse_id=warehouse.id,
        code="RCV",
        name="Приёмка",
        kind=LocationKind.RECEIVING,
    )
    db.add(zone)
    db.flush()
    location = Location(
        warehouse_id=warehouse.id,
        zone_id=zone.id,
        code=f"{warehouse.code}-RCV-P01",
        name="Ячейка приёмки",
        kind=LocationKind.RECEIVING,
        capacity_units=10,
    )
    box_type = db.scalar(select(LogisticUnitType).where(LogisticUnitType.code == "BOX"))
    unit = LogisticUnit(
        uid="BOX-RCV-001",
        type_id=box_type.id,
        warehouse_id=warehouse.id,
        current_location_id=None,
        status=LogisticUnitStatus.OPEN,
    )
    db.add_all([location, unit])
    db.flush()
    unit.current_location_id = location.id
    db.commit()
    return location, unit


def create_storage_destination(db, warehouse):
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
        code=f"{warehouse.code}-ST01-P01",
        name="Ячейка хранения",
        kind=LocationKind.STORAGE,
        capacity_units=10,
    )
    db.add(location)
    db.commit()
    return location


def actual_payload(
    receipt,
    pieces,
    destination_scan,
    *,
    key="receipt:post:001",
    quantity="5",
    packaging_id=None,
    batch_number=None,
    production_date=None,
    expiry_date=None,
    serial_number=None,
    quality_status=None,
    item_scan="FILTER-001",
):
    return InboundReceiptPost(
        idempotency_key=key,
        actor="receiver",
        reason="Фактическая приёмка",
        lines=[
            InboundReceiptActualLineCreate(
                receipt_line_id=receipt.lines[0].id,
                input_quantity=Decimal(quantity),
                input_uom_id=None if packaging_id else pieces.id,
                packaging_id=packaging_id,
                batch_number=batch_number,
                production_date=production_date,
                expiry_date=expiry_date,
                serial_number=serial_number,
                quality_status=quality_status,
                destination_scan=destination_scan,
                item_scan=item_scan,
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


def test_post_exact_receipt_creates_batch_movement_and_stock_atomically(db):
    warehouse, product, _, owner, pieces, _, _ = create_context(db)
    location, _ = create_receiving_destination(db, warehouse)
    receipt = create_inbound_receipt(
        db,
        receipt_payload(warehouse, product, owner, pieces),
    )
    command = actual_payload(receipt, pieces, location.code)

    posted = post_inbound_receipt(db, receipt.uid, command)
    repeated = post_inbound_receipt(db, receipt.uid, command)
    data = inbound_receipt_payload(db, posted)

    assert repeated.id == posted.id
    assert posted.status == InboundReceiptStatus.POSTED
    assert posted.posted_stock_document.status == StockDocumentStatus.POSTED
    assert posted.posted_stock_document.document_type == "inbound_receipt"
    assert data["has_discrepancies"] is False
    assert data["exact_line_count"] == 1
    assert data["lines"][0]["quantity_result"] == "exact"
    assert data["lines"][0]["batch_result"] == "exact"
    assert data["lines"][0]["quality_result"] == "exact"
    assert data["lines"][0]["results"][0]["destination_location_code"] == location.code
    batch = db.scalar(
        select(Batch).where(
            Batch.product_id == product.id,
            Batch.batch_number == "LOT-2026-08",
        )
    )
    assert batch is not None
    position = db.scalar(select(StockPosition))
    assert position.quantity == Decimal("5")
    assert position.batch_id == batch.id
    assert position.location_id == location.id
    assert db.scalar(select(func.count(StockDocument.id))) == 1
    assert db.scalar(select(func.count(StockMovement.id))) == 1

    with pytest.raises(HTTPException, match="already posted by another command"):
        post_inbound_receipt(
            db,
            receipt.uid,
            actual_payload(
                receipt,
                pieces,
                location.code,
                quantity="4",
            ),
        )


def test_exact_receipt_creates_putaway_task_and_places_stock_atomically(db):
    warehouse, product, _, owner, pieces, _, _ = create_context(db)
    receiving, _ = create_receiving_destination(db, warehouse)
    storage = create_storage_destination(db, warehouse)
    receipt = create_inbound_receipt(
        db,
        receipt_payload(
            warehouse,
            product,
            owner,
            pieces,
            key="receipt:putaway:draft",
        ),
    )

    post_inbound_receipt(
        db,
        receipt.uid,
        actual_payload(
            receipt,
            pieces,
            receiving.code,
            key="receipt:putaway:post",
        ),
    )
    task = db.scalar(
        select(LogisticTask).where(
            LogisticTask.object_uid == receipt.uid,
            LogisticTask.task_type == TaskType.PUTAWAY,
        )
    )
    assert task is not None
    assert task.status == TaskStatus.NEW
    assert task.priority == TaskPriority.HIGH
    assert db.scalar(
        select(func.count(LogisticTask.id)).where(
            LogisticTask.task_type == TaskType.RECEIPT_CONTROL
        )
    ) == 0

    start_logistic_task(db, task.task_uid, actor="storekeeper")
    command = InboundReceiptPutawayRequest(
        idempotency_key="receipt:putaway:movement",
        target_location_code=storage.code,
        actor="storekeeper",
        reason="Размещение после приёмки",
    )
    completed = putaway_inbound_receipt_result(db, task.task_uid, command)
    repeated = putaway_inbound_receipt_result(db, task.task_uid, command)

    assert completed.status == TaskStatus.COMPLETED
    assert repeated.id == completed.id
    result = receipt.lines[0].results[0]
    assert result.placement_stock_document.document_type == "inbound_putaway"
    assert result.placed_at is not None
    assert db.scalar(
        select(StockPosition.quantity).where(StockPosition.location_id == receiving.id)
    ) is None
    assert db.scalar(
        select(StockPosition.quantity).where(StockPosition.location_id == storage.id)
    ) == Decimal("5")
    result_payload = inbound_receipt_payload(db, receipt)["lines"][0]["results"][0]
    assert result_payload["placement_status"] == "placed"
    assert result_payload["placement_stock_document_uid"].startswith("PUT-")


def test_receipt_discrepancy_requires_control_before_putaway(db):
    warehouse, product, _, owner, pieces, _, _ = create_context(db)
    receiving, _ = create_receiving_destination(db, warehouse)
    receipt = create_inbound_receipt(
        db,
        receipt_payload(
            warehouse,
            product,
            owner,
            pieces,
            key="receipt:control:draft",
        ),
    )

    post_inbound_receipt(
        db,
        receipt.uid,
        actual_payload(
            receipt,
            pieces,
            receiving.code,
            key="receipt:control:post",
            quantity="3",
        ),
    )
    control = db.scalar(
        select(LogisticTask).where(
            LogisticTask.object_uid == receipt.uid,
            LogisticTask.task_type == TaskType.RECEIPT_CONTROL,
        )
    )
    assert control is not None
    assert control.priority == TaskPriority.URGENT
    assert db.scalar(
        select(func.count(LogisticTask.id)).where(
            LogisticTask.task_type == TaskType.PUTAWAY
        )
    ) == 0
    assert inbound_receipt_payload(db, receipt)["lines"][0]["results"][0][
        "placement_status"
    ] == "waiting_control"

    start_logistic_task(db, control.task_uid, actor="supervisor")
    complete_logistic_task(db, control.task_uid, actor="supervisor")
    putaway = db.scalar(
        select(LogisticTask).where(
            LogisticTask.object_uid == receipt.uid,
            LogisticTask.task_type == TaskType.PUTAWAY,
        )
    )
    assert control.status == TaskStatus.COMPLETED
    assert putaway is not None
    assert putaway.status == TaskStatus.NEW
    assert inbound_receipt_payload(db, receipt)["lines"][0]["results"][0][
        "placement_status"
    ] == "ready"


def test_putaway_reversal_restores_stock_and_reopens_task(db):
    warehouse, product, _, owner, pieces, _, _ = create_context(db)
    receiving, _ = create_receiving_destination(db, warehouse)
    storage = create_storage_destination(db, warehouse)
    receipt = create_inbound_receipt(
        db,
        receipt_payload(
            warehouse,
            product,
            owner,
            pieces,
            key="receipt:putaway-reverse:draft",
        ),
    )
    post_inbound_receipt(
        db,
        receipt.uid,
        actual_payload(
            receipt,
            pieces,
            receiving.code,
            key="receipt:putaway-reverse:post",
        ),
    )
    task = db.scalar(
        select(LogisticTask).where(LogisticTask.task_type == TaskType.PUTAWAY)
    )
    start_logistic_task(db, task.task_uid, actor="storekeeper")
    putaway_inbound_receipt_result(
        db,
        task.task_uid,
        InboundReceiptPutawayRequest(
            idempotency_key="receipt:putaway-reverse:movement",
            target_location_code=storage.code,
            actor="storekeeper",
            reason="Размещение после приёмки",
        ),
    )
    placement_uid = receipt.lines[0].results[0].placement_stock_document.uid

    reverse_stock_document(
        db,
        placement_uid,
        StockDocumentReverseRequest(
            idempotency_key="receipt:putaway-reverse:reversal",
            actor="manager",
            reason="Возврат задания на размещение",
        ),
    )

    result = receipt.lines[0].results[0]
    assert result.placement_stock_document_id is None
    assert result.placed_at is None
    assert task.status == TaskStatus.IN_PROGRESS
    assert task.completed_at is None
    assert db.scalar(
        select(StockPosition.quantity).where(StockPosition.location_id == receiving.id)
    ) == Decimal("5")
    assert db.scalar(
        select(StockPosition.quantity).where(StockPosition.location_id == storage.id)
    ) is None


def test_receipt_reversal_cancels_pending_putaway_task(db):
    warehouse, product, _, owner, pieces, _, _ = create_context(db)
    receiving, _ = create_receiving_destination(db, warehouse)
    receipt = create_inbound_receipt(
        db,
        receipt_payload(
            warehouse,
            product,
            owner,
            pieces,
            key="receipt:cancel-task:draft",
        ),
    )
    post_inbound_receipt(
        db,
        receipt.uid,
        actual_payload(
            receipt,
            pieces,
            receiving.code,
            key="receipt:cancel-task:post",
        ),
    )
    task = db.scalar(
        select(LogisticTask).where(LogisticTask.task_type == TaskType.PUTAWAY)
    )

    reverse_stock_document(
        db,
        receipt.posted_stock_document.uid,
        StockDocumentReverseRequest(
            idempotency_key="receipt:cancel-task:reversal",
            actor="manager",
            reason="Отмена ошибочной приёмки",
        ),
    )

    assert receipt.status == InboundReceiptStatus.REVERSED
    assert task.status == TaskStatus.CANCELLED
    assert db.scalar(select(func.count(StockPosition.id))) == 0


def test_receipt_can_split_actual_packagings_and_report_excess(db):
    warehouse, product, _, owner, pieces, packaging, _ = create_context(db)
    location, unit = create_receiving_destination(db, warehouse)
    receipt = create_inbound_receipt(
        db,
        receipt_payload(
            warehouse,
            product,
            owner,
            pieces,
            key="receipt:split:draft",
            quantity="2",
            packaging_id=packaging.id,
        ),
    )
    command = actual_payload(
        receipt,
        pieces,
        location.code,
        key="receipt:split:post",
        quantity="1",
        packaging_id=packaging.id,
        item_scan=packaging.barcode,
    )
    command.lines.append(
        InboundReceiptActualLineCreate(
            receipt_line_id=receipt.lines[0].id,
            input_quantity=Decimal("2"),
            packaging_id=packaging.id,
            destination_scan=unit.uid,
            item_scan=packaging.code,
        )
    )

    posted = post_inbound_receipt(db, receipt.uid, command)
    data = inbound_receipt_payload(db, posted)

    assert data["excess_line_count"] == 1
    assert data["discrepancy_count"] == 1
    assert data["lines"][0]["expected_base_quantity"] == Decimal("24")
    assert data["lines"][0]["received_base_quantity"] == Decimal("36")
    assert data["lines"][0]["variance_base_quantity"] == Decimal("12")
    assert len(data["lines"][0]["results"]) == 2
    assert sum(
        db.scalars(select(StockPosition.quantity)),
        Decimal("0"),
    ) == Decimal("36")
    projection = db.scalar(
        select(LogisticUnitContent).where(
            LogisticUnitContent.logistic_unit_id == unit.id
        )
    )
    assert projection.quantity == Decimal("24")


def test_receipt_reports_shortage_batch_and_quality_mismatch(db):
    warehouse, product, _, owner, pieces, _, _ = create_context(db)
    location, _ = create_receiving_destination(db, warehouse)
    receipt = create_inbound_receipt(
        db,
        receipt_payload(
            warehouse,
            product,
            owner,
            pieces,
            key="receipt:mismatch:draft",
        ),
    )

    posted = post_inbound_receipt(
        db,
        receipt.uid,
        actual_payload(
            receipt,
            pieces,
            location.code,
            key="receipt:mismatch:post",
            quantity="3",
            batch_number="LOT-ACTUAL",
            production_date=date(2026, 8, 2),
            expiry_date=date(2027, 8, 2),
            quality_status="quarantine",
        ),
    )
    line = inbound_receipt_payload(db, posted)["lines"][0]

    assert line["quantity_result"] == "shortage"
    assert line["variance_base_quantity"] == Decimal("-2")
    assert line["batch_result"] == "mismatch"
    assert line["quality_result"] == "mismatch"
    assert line["results"][0]["quality_status"] == "quarantine"
    assert db.scalar(select(StockPosition.quality_status)) == "quarantine"


def test_new_actual_batch_does_not_inherit_expected_batch_dates(db):
    warehouse, product, _, owner, pieces, _, _ = create_context(db)
    location, _ = create_receiving_destination(db, warehouse)
    receipt = create_inbound_receipt(
        db,
        receipt_payload(
            warehouse,
            product,
            owner,
            pieces,
            key="receipt:new-batch:draft",
        ),
    )

    with pytest.raises(HTTPException, match="new batch requires"):
        post_inbound_receipt(
            db,
            receipt.uid,
            actual_payload(
                receipt,
                pieces,
                location.code,
                key="receipt:new-batch:post",
                batch_number="LOT-WITHOUT-DATES",
                production_date=None,
                expiry_date=None,
            ),
        )

    db.refresh(receipt)
    assert receipt.status == InboundReceiptStatus.DRAFT
    assert db.scalar(select(func.count(Batch.id))) == 0
    assert db.scalar(select(func.count(StockDocument.id))) == 0


def test_failed_actual_receipt_rolls_back_new_batch_and_all_stock(db):
    warehouse, product, _, owner, pieces, _, _ = create_context(db)
    location, _ = create_receiving_destination(db, warehouse)
    receipt = create_inbound_receipt(
        db,
        receipt_payload(
            warehouse,
            product,
            owner,
            pieces,
            key="receipt:atomic:draft",
        ),
    )
    command = actual_payload(
        receipt,
        pieces,
        location.code,
        key="receipt:atomic:post",
        quantity="2",
        batch_number="LOT-TEMP",
        production_date=date(2026, 8, 3),
        expiry_date=date(2027, 8, 3),
    )
    command.lines.append(
        InboundReceiptActualLineCreate(
            receipt_line_id=receipt.lines[0].id,
            input_quantity=Decimal("3"),
            input_uom_id=pieces.id,
            destination_scan=location.code,
            item_scan="WRONG-CODE",
        )
    )

    with pytest.raises(HTTPException, match="does not match"):
        post_inbound_receipt(db, receipt.uid, command)

    db.refresh(receipt)
    assert receipt.status == InboundReceiptStatus.DRAFT
    assert db.scalar(select(func.count(Batch.id))) == 0
    assert db.scalar(select(func.count(StockDocument.id))) == 0
    assert db.scalar(select(func.count(StockMovement.id))) == 0
    assert db.scalar(select(func.count(StockPosition.id))) == 0


def test_reversal_removes_received_stock_and_logistic_unit_projection(db):
    warehouse, product, _, owner, pieces, _, _ = create_context(db)
    _, unit = create_receiving_destination(db, warehouse)
    receipt = create_inbound_receipt(
        db,
        receipt_payload(
            warehouse,
            product,
            owner,
            pieces,
            key="receipt:reverse:draft",
        ),
    )
    post_inbound_receipt(
        db,
        receipt.uid,
        actual_payload(
            receipt,
            pieces,
            unit.uid,
            key="receipt:reverse:post",
        ),
    )
    stock_document_uid = receipt.posted_stock_document.uid
    build_task = db.scalar(
        select(LogisticTask).where(
            LogisticTask.object_uid == unit.uid,
            LogisticTask.task_type == TaskType.BUILD,
        )
    )
    assert build_task is not None
    assert build_task.status == TaskStatus.NEW

    reversal = reverse_stock_document(
        db,
        stock_document_uid,
        StockDocumentReverseRequest(
            idempotency_key="receipt:reverse:reversal",
            actor="manager",
            reason="Ошибочная приёмка",
        ),
    )

    db.refresh(receipt)
    assert reversal.document_type == "stock_reversal"
    assert receipt.status == InboundReceiptStatus.REVERSED
    assert receipt.reversed_at is not None
    assert db.scalar(select(func.count(StockPosition.id))) == 0
    assert db.scalar(select(func.count(LogisticUnitContent.id))) == 0


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


def test_inbound_receipt_api_posts_actual_quantity(client, db):
    warehouse, product, _, owner, pieces, _, _ = create_context(db)
    location, _ = create_receiving_destination(db, warehouse)
    storage = create_storage_destination(db, warehouse)
    created = client.post(
        "/api/inbound-receipts",
        json=receipt_payload(
            warehouse,
            product,
            owner,
            pieces,
            key="receipt:api:post:draft",
        ).model_dump(mode="json"),
    )
    assert created.status_code == 200
    receipt = created.json()

    posted = client.post(
        f"/api/inbound-receipts/{receipt['uid']}/receive",
        json={
            "idempotency_key": "receipt:api:post:command",
            "actor": "api-test",
            "reason": "Фактическая приёмка через API",
            "lines": [
                {
                    "receipt_line_id": receipt["lines"][0]["id"],
                    "input_quantity": "5",
                    "input_uom_id": pieces.id,
                    "batch_number": "LOT-2026-08",
                    "production_date": "2026-08-01",
                    "expiry_date": "2027-08-01",
                    "destination_scan": location.code,
                    "item_scan": product.code,
                }
            ],
        },
    )

    assert posted.status_code == 200
    data = posted.json()
    assert data["status"] == "posted"
    assert data["has_discrepancies"] is False
    assert data["lines"][0]["quantity_result"] == "exact"
    assert data["lines"][0]["results"][0]["destination_location_code"] == location.code
    assert db.scalar(select(StockPosition.quantity)) == Decimal("5")

    task = db.scalar(
        select(LogisticTask).where(LogisticTask.task_type == TaskType.PUTAWAY)
    )
    started = client.post(
        f"/api/logistic-tasks/{task.task_uid}/start",
        json={"actor": "api-test"},
    )
    assert started.status_code == 200
    placed = client.post(
        f"/api/logistic-tasks/{task.task_uid}/putaway",
        json={
            "idempotency_key": "receipt:api:putaway",
            "target_location_code": storage.code,
            "actor": "api-test",
            "reason": "Размещение через API",
        },
    )
    assert placed.status_code == 200
    assert placed.json()["status"] == "completed"
    assert placed.json()["object_status"] == "placed"
    assert db.scalar(select(StockPosition.location_id)) == storage.id


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
