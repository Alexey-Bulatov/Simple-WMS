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
    Location,
    LogisticUnit,
    LogisticUnitType,
    LogisticTask,
    OperationEvent,
    Product,
    StockDocument,
    StockOwner,
    StockPosition,
    StockReservation,
    StockMovement,
    UnitOfMeasure,
    Warehouse,
    Zone,
)
from app.models.enums import (
    LocationKind,
    LogisticUnitStatus,
    StockReservationStatus,
    TaskPriority,
    TaskStatus,
    TaskType,
)
from app.schemas import (
    ProductCreate,
    StockDocumentPost,
    StockDocumentReverseRequest,
    StockMovementPost,
    StockReservationConsumeRequest,
    StockReservationCreate,
    StockReservationReleaseRequest,
)
from app.services import create_product, ensure_reference_catalogs
from app.stock import remove_logistic_unit_stock_positions, stock_position_payload
from app.stock_ledger import post_stock_document, reverse_stock_document
from app.stock_reservations import (
    consume_stock_reservation,
    create_stock_reservation,
    release_stock_reservation,
)


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


def create_stock_context(db, *, quantity: str = "5"):
    ensure_reference_catalogs(db)
    pieces = reference(db, UnitOfMeasure, "PCS")
    owner = reference(db, StockOwner, "INTERNAL")
    product = create_product(
        db,
        ProductCreate(
            code="GLOVES",
            name="Перчатки",
            base_uom_id=pieces.id,
        ),
    )
    warehouse = Warehouse(code="WH-RSV", name="Склад резервов")
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
        code="WH-RSV-ST01-01",
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
    db.add(position)
    db.commit()
    return product, pieces, owner, location, position


def reserve_command(
    position,
    pieces,
    *,
    key: str,
    quantity: str = "3",
    reference_type: str = "internal_issue",
    reference_uid: str = "ISSUE-001",
    reference_line_uid: str = "LINE-001",
    task_uid: str | None = None,
):
    return StockReservationCreate(
        stock_position_id=position.id,
        input_quantity=Decimal(quantity),
        input_uom_id=pieces.id,
        reference_type=reference_type,
        reference_uid=reference_uid,
        reference_line_uid=reference_line_uid,
        task_uid=task_uid,
        idempotency_key=key,
        actor="storekeeper",
        reason="Выдача сотруднику",
    )


def release_command(*, key: str, reason: str = "Выдача отменена"):
    return StockReservationReleaseRequest(
        idempotency_key=key,
        actor="senior-storekeeper",
        reason=reason,
    )


def consume_command(
    *,
    key: str,
    actor: str = "storekeeper",
    reason: str = "Фактический отбор",
    destination_location_id: int | None = None,
):
    return StockReservationConsumeRequest(
        idempotency_key=key,
        actor=actor,
        reason=reason,
        destination_location_id=destination_location_id,
    )


def create_linked_task(db, location, *, object_uid: str = "SHIP-QTY-001"):
    task = LogisticTask(
        task_uid=f"TSK-{object_uid}",
        warehouse_id=location.warehouse_id,
        task_type=TaskType.SHIP,
        status=TaskStatus.NEW,
        priority=TaskPriority.NORMAL,
        title="Отобрать зарезервированный товар",
        object_type="logistic_shipment",
        object_uid=object_uid,
        parameters={},
        created_by="dispatcher",
    )
    db.add(task)
    db.commit()
    return task


def issue_command(product, pieces, owner, location, *, key: str, quantity: str):
    return StockDocumentPost(
        document_type="internal_issue",
        reference_type="test",
        reference_uid="ISSUE-OTHER",
        idempotency_key=key,
        actor="storekeeper",
        movements=[
            StockMovementPost(
                product_id=product.id,
                owner_id=owner.id,
                source_quality_status="released",
                input_quantity=Decimal(quantity),
                input_uom_id=pieces.id,
                source_location_id=location.id,
            )
        ],
    )


def test_reservation_changes_available_quantity_and_release_restores_it(db):
    _, pieces, _, _, position = create_stock_context(db)

    first = create_stock_reservation(
        db,
        reserve_command(position, pieces, key="reserve:issue-001"),
    )
    repeated = create_stock_reservation(
        db,
        reserve_command(position, pieces, key="reserve:issue-001"),
    )

    assert repeated.id == first.id
    assert first.status == StockReservationStatus.ACTIVE
    assert first.quantity == Decimal("3")
    assert stock_position_payload(db, position)["available_quantity"] == Decimal("2")
    assert stock_position_payload(db, position)["reserved_quantity"] == Decimal("3")

    released = release_stock_reservation(
        db,
        first.uid,
        release_command(key="release:issue-001"),
    )
    repeated_release = release_stock_reservation(
        db,
        first.uid,
        release_command(key="release:issue-001"),
    )

    assert repeated_release.id == released.id
    assert released.status == StockReservationStatus.RELEASED
    assert stock_position_payload(db, position)["available_quantity"] == Decimal("5")
    assert stock_position_payload(db, position)["reserved_quantity"] == Decimal("0")
    assert db.scalar(select(func.count(OperationEvent.id))) == 2


def test_reservation_rejects_overbooking_and_protects_reserved_stock(db):
    product, pieces, owner, location, position = create_stock_context(db)
    create_stock_reservation(
        db,
        reserve_command(position, pieces, key="reserve:protected", quantity="3"),
    )

    with pytest.raises(HTTPException, match="insufficient available stock"):
        create_stock_reservation(
            db,
            reserve_command(position, pieces, key="reserve:too-much", quantity="3"),
        )

    post_stock_document(
        db,
        issue_command(
            product,
            pieces,
            owner,
            location,
            key="issue:unreserved-two",
            quantity="2",
        ),
    )
    with pytest.raises(HTTPException, match="insufficient unreserved source stock"):
        post_stock_document(
            db,
            issue_command(
                product,
                pieces,
                owner,
                location,
                key="issue:reserved-one",
                quantity="1",
            ),
        )

    assert db.get(StockPosition, position.id).quantity == Decimal("3")
    assert db.scalar(select(func.count(StockDocument.id))) == 1


def test_active_reservation_blocks_bulk_logistic_unit_stock_removal(db):
    _, pieces, _, location, position = create_stock_context(db)
    box_type = reference(db, LogisticUnitType, "BOX")
    unit = LogisticUnit(
        uid="BOX-RESERVED-001",
        type_id=box_type.id,
        status=LogisticUnitStatus.AVAILABLE,
        current_location_id=location.id,
    )
    db.add(unit)
    db.flush()
    position.location_id = None
    position.logistic_unit_id = unit.id
    db.commit()
    reservation = create_stock_reservation(
        db,
        reserve_command(position, pieces, key="reserve:unit-removal", quantity="2"),
    )

    with pytest.raises(HTTPException, match="active reservation"):
        remove_logistic_unit_stock_positions(db, unit.id)
    assert db.get(StockPosition, position.id) is not None

    release_stock_reservation(
        db,
        reservation.uid,
        release_command(key="release:unit-removal"),
    )
    remove_logistic_unit_stock_positions(db, unit.id)
    db.commit()
    assert db.get(StockPosition, position.id) is None


def test_reservation_and_release_idempotency_keys_reject_changed_commands(db):
    _, pieces, _, _, position = create_stock_context(db)
    reservation = create_stock_reservation(
        db,
        reserve_command(position, pieces, key="reserve:immutable", quantity="2"),
    )

    with pytest.raises(HTTPException, match="another reservation command"):
        create_stock_reservation(
            db,
            reserve_command(position, pieces, key="reserve:immutable", quantity="1"),
        )

    release_stock_reservation(
        db,
        reservation.uid,
        release_command(key="release:immutable"),
    )
    with pytest.raises(HTTPException, match="another reservation release"):
        release_stock_reservation(
            db,
            reservation.uid,
            release_command(key="release:immutable", reason="Другая причина"),
        )
    with pytest.raises(HTTPException, match="already released"):
        release_stock_reservation(
            db,
            reservation.uid,
            release_command(key="release:second-command"),
        )


def test_consumption_posts_movement_and_completes_linked_task_atomically(db):
    _, pieces, _, location, position = create_stock_context(db)
    task = create_linked_task(db, location)
    reservation = create_stock_reservation(
        db,
        reserve_command(
            position,
            pieces,
            key="reserve:consume-linked",
            reference_type="logistic_shipment",
            reference_uid=task.object_uid,
            task_uid=task.task_uid,
        ),
    )

    consumed = consume_stock_reservation(
        db,
        reservation.uid,
        consume_command(key="consume:linked"),
    )
    repeated = consume_stock_reservation(
        db,
        reservation.uid,
        consume_command(key="consume:linked"),
    )

    db.refresh(task)
    assert repeated.id == consumed.id
    assert consumed.status == StockReservationStatus.CONSUMED
    assert consumed.consumed_by_document.document_type == "stock_issue"
    assert consumed.consumed_by_document.status.value == "posted"
    assert db.get(StockPosition, position.id).quantity == Decimal("2")
    assert db.scalar(select(func.count(StockDocument.id))) == 1
    assert db.scalar(select(func.count(StockMovement.id))) == 1
    assert task.status == TaskStatus.COMPLETED
    assert task.assigned_to == "storekeeper"
    assert task.parameters["completed_by_reservation_uid"] == reservation.uid
    assert task.parameters["stock_document_uid"] == consumed.consumed_by_document.uid

    with pytest.raises(HTTPException, match="another reservation consumption"):
        consume_stock_reservation(
            db,
            reservation.uid,
            consume_command(key="consume:linked", reason="Изменённая команда"),
        )
    with pytest.raises(HTTPException, match="cannot be released"):
        release_stock_reservation(
            db,
            reservation.uid,
            release_command(key="release:consumed"),
        )


def test_consumption_can_move_reserved_stock_to_another_location(db):
    _, pieces, _, source, position = create_stock_context(db)
    destination = Location(
        warehouse_id=source.warehouse_id,
        zone_id=source.zone_id,
        code="WH-RSV-ST01-02",
        name="Ячейка 02",
        kind=LocationKind.STORAGE,
    )
    db.add(destination)
    db.commit()
    reservation = create_stock_reservation(
        db,
        reserve_command(
            position,
            pieces,
            key="reserve:pick-location",
            quantity="2",
        ),
    )

    consumed = consume_stock_reservation(
        db,
        reservation.uid,
        consume_command(
            key="consume:pick-location",
            destination_location_id=destination.id,
        ),
    )

    positions = list(db.scalars(select(StockPosition).order_by(StockPosition.id)))
    assert consumed.consumed_by_document.document_type == "stock_pick"
    assert [(item.location_id, item.quantity) for item in positions] == [
        (source.id, Decimal("3")),
        (destination.id, Decimal("2")),
    ]


def test_linked_task_completes_only_after_all_reservations_are_consumed(db):
    _, pieces, _, location, position = create_stock_context(db)
    task = create_linked_task(db, location)
    first = create_stock_reservation(
        db,
        reserve_command(
            position,
            pieces,
            key="reserve:multi:first",
            quantity="1",
            reference_type="logistic_shipment",
            reference_uid=task.object_uid,
            reference_line_uid="LINE-001",
            task_uid=task.task_uid,
        ),
    )
    second = create_stock_reservation(
        db,
        reserve_command(
            position,
            pieces,
            key="reserve:multi:second",
            quantity="2",
            reference_type="logistic_shipment",
            reference_uid=task.object_uid,
            reference_line_uid="LINE-002",
            task_uid=task.task_uid,
        ),
    )

    first_consumption = consume_stock_reservation(
        db,
        first.uid,
        consume_command(key="consume:multi:first"),
    )
    db.refresh(task)
    assert task.status == TaskStatus.IN_PROGRESS
    assert task.parameters["remaining_reservation_count"] == 1

    reverse_stock_document(
        db,
        first_consumption.consumed_by_document.uid,
        StockDocumentReverseRequest(
            idempotency_key="reverse:multi:first",
            actor="senior-storekeeper",
            reason="Повторить первую строку",
        ),
    )
    db.refresh(first)
    db.refresh(task)
    assert first.status == StockReservationStatus.ACTIVE
    assert task.status == TaskStatus.IN_PROGRESS

    consume_stock_reservation(
        db,
        first.uid,
        consume_command(key="consume:multi:first:retry"),
    )

    consume_stock_reservation(
        db,
        second.uid,
        consume_command(key="consume:multi:second"),
    )
    db.refresh(task)
    assert task.status == TaskStatus.COMPLETED
    assert task.parameters["completed_by_reservation_uid"] == second.uid


def test_reservation_rejects_mismatched_or_closed_task(db):
    _, pieces, _, location, position = create_stock_context(db)
    task = create_linked_task(db, location, object_uid="SHIP-OTHER")

    with pytest.raises(HTTPException, match="does not match"):
        create_stock_reservation(
            db,
            reserve_command(
                position,
                pieces,
                key="reserve:wrong-task",
                reference_type="logistic_shipment",
                reference_uid="SHIP-QTY-001",
                task_uid=task.task_uid,
            ),
        )
    task.status = TaskStatus.CANCELLED
    db.commit()
    with pytest.raises(HTTPException, match="requires an active"):
        create_stock_reservation(
            db,
            reserve_command(
                position,
                pieces,
                key="reserve:closed-task",
                reference_type="logistic_shipment",
                reference_uid=task.object_uid,
                task_uid=task.task_uid,
            ),
        )
    assert db.scalar(select(func.count(StockReservation.id))) == 0


def test_task_completion_failure_rolls_back_consumption_and_movement(db, monkeypatch):
    import app.stock_reservations as reservation_service

    _, pieces, _, location, position = create_stock_context(db)
    task = create_linked_task(db, location)
    reservation = create_stock_reservation(
        db,
        reserve_command(
            position,
            pieces,
            key="reserve:rollback",
            reference_type="logistic_shipment",
            reference_uid=task.object_uid,
            task_uid=task.task_uid,
        ),
    )

    def fail_task_completion(*args, **kwargs):
        raise HTTPException(status_code=409, detail="task completion failed")

    monkeypatch.setattr(
        reservation_service,
        "_complete_linked_task",
        fail_task_completion,
    )
    with pytest.raises(HTTPException, match="task completion failed"):
        consume_stock_reservation(
            db,
            reservation.uid,
            consume_command(key="consume:rollback"),
        )

    db.refresh(reservation)
    db.refresh(task)
    db.refresh(position)
    assert reservation.status == StockReservationStatus.ACTIVE
    assert reservation.consumed_by_document_id is None
    assert task.status == TaskStatus.NEW
    assert position.quantity == Decimal("5")
    assert db.scalar(select(func.count(StockDocument.id))) == 0
    assert db.scalar(select(func.count(StockMovement.id))) == 0


def test_reversal_reopens_consumed_reservation_and_linked_task(db):
    _, pieces, _, location, position = create_stock_context(db)
    task = create_linked_task(db, location)
    reservation = create_stock_reservation(
        db,
        reserve_command(
            position,
            pieces,
            key="reserve:reverse-consumption",
            reference_type="logistic_shipment",
            reference_uid=task.object_uid,
            task_uid=task.task_uid,
        ),
    )
    consumed = consume_stock_reservation(
        db,
        reservation.uid,
        consume_command(key="consume:before-reversal"),
    )
    original_document_uid = consumed.consumed_by_document.uid

    reverse_stock_document(
        db,
        original_document_uid,
        StockDocumentReverseRequest(
            idempotency_key="reverse:consumption",
            actor="senior-storekeeper",
            reason="Ошибочный отбор",
        ),
    )

    db.refresh(reservation)
    db.refresh(task)
    db.refresh(position)
    assert reservation.status == StockReservationStatus.ACTIVE
    assert reservation.consumed_at is None
    assert reservation.consumed_by_document_id is None
    assert task.status == TaskStatus.IN_PROGRESS
    assert task.completed_at is None
    assert position.quantity == Decimal("5")

    with pytest.raises(HTTPException, match="was reversed"):
        consume_stock_reservation(
            db,
            reservation.uid,
            consume_command(key="consume:before-reversal"),
        )

    consumed_again = consume_stock_reservation(
        db,
        reservation.uid,
        consume_command(key="consume:after-reversal"),
    )
    db.refresh(task)
    assert consumed_again.status == StockReservationStatus.CONSUMED
    assert consumed_again.consumed_by_document.uid != original_document_uid
    assert task.status == TaskStatus.COMPLETED


def test_reversal_rebinds_full_quantity_reservation_to_restored_position(db):
    _, pieces, _, _, position = create_stock_context(db)
    original_position_id = position.id
    reservation = create_stock_reservation(
        db,
        reserve_command(
            position,
            pieces,
            key="reserve:full-position",
            quantity="5",
        ),
    )
    consumed = consume_stock_reservation(
        db,
        reservation.uid,
        consume_command(key="consume:full-position"),
    )
    assert db.get(StockPosition, original_position_id) is None

    reverse_stock_document(
        db,
        consumed.consumed_by_document.uid,
        StockDocumentReverseRequest(
            idempotency_key="reverse:full-position",
            actor="senior-storekeeper",
            reason="Возврат полного отбора",
        ),
    )

    db.refresh(reservation)
    restored_position = db.get(StockPosition, reservation.stock_position_id)
    assert reservation.status == StockReservationStatus.ACTIVE
    assert restored_position is not None
    assert restored_position.quantity == Decimal("5")
    assert stock_position_payload(db, restored_position)["reserved_quantity"] == Decimal(
        "5"
    )


def test_stale_session_cannot_reserve_the_same_available_quantity_twice(tmp_path):
    engine = create_engine(
        f"sqlite:///{tmp_path / 'reservations.db'}",
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
    _, pieces, _, _, position = create_stock_context(setup, quantity="5")
    position_id = position.id
    pieces_id = pieces.id
    setup.close()

    first_session = TestingSession()
    stale_session = TestingSession()
    stale_position = stale_session.get(StockPosition, position_id)
    assert stale_position.quantity == Decimal("5")

    create_stock_reservation(
        first_session,
        StockReservationCreate(
            stock_position_id=position_id,
            input_quantity=Decimal("4"),
            input_uom_id=pieces_id,
            reference_type="shipment",
            reference_uid="SHIP-001",
            idempotency_key="reserve:parallel:first",
            actor="first",
        ),
    )
    with pytest.raises(HTTPException, match="insufficient available stock"):
        create_stock_reservation(
            stale_session,
            StockReservationCreate(
                stock_position_id=position_id,
                input_quantity=Decimal("4"),
                input_uom_id=pieces_id,
                reference_type="shipment",
                reference_uid="SHIP-002",
                idempotency_key="reserve:parallel:second",
                actor="second",
            ),
        )
    first_session.close()
    stale_session.close()

    verify = TestingSession()
    assert verify.scalar(select(func.sum(StockReservation.quantity))) == Decimal("4")
    assert verify.scalar(select(func.count(StockReservation.id))) == 1
    verify.close()
    engine.dispose()


def test_stock_reservation_api_create_list_get_and_release(db):
    _, pieces, _, _, position = create_stock_context(db)

    def override_db():
        yield db

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[api_routes.get_db] = override_db
    try:
        with TestClient(app) as client:
            created = client.post(
                "/api/stock-reservations",
                json={
                    "stock_position_id": position.id,
                    "input_quantity": "2",
                    "input_uom_id": pieces.id,
                    "reference_type": "internal_issue",
                    "reference_uid": "ISSUE-API-001",
                    "reference_line_uid": "LINE-001",
                    "idempotency_key": "reserve:api:001",
                    "actor": "api-user",
                },
            )
            assert created.status_code == 200
            reservation = created.json()
            assert reservation["status"] == "active"
            assert reservation["location_code"] == "WH-RSV-ST01-01"

            listed = client.get(
                "/api/stock-reservations",
                params={"status": "active", "reference_uid": "ISSUE-API-001"},
            )
            assert listed.status_code == 200
            assert [item["uid"] for item in listed.json()] == [reservation["uid"]]
            assert client.get(
                f"/api/stock-reservations/{reservation['uid']}"
            ).status_code == 200

            released = client.post(
                f"/api/stock-reservations/{reservation['uid']}/release",
                json={
                    "idempotency_key": "release:api:001",
                    "actor": "api-user",
                    "reason": "Отмена",
                },
            )
            assert released.status_code == 200
            assert released.json()["status"] == "released"

            created_for_consumption = client.post(
                "/api/stock-reservations",
                json={
                    "stock_position_id": position.id,
                    "input_quantity": "1",
                    "input_uom_id": pieces.id,
                    "reference_type": "internal_issue",
                    "reference_uid": "ISSUE-API-002",
                    "idempotency_key": "reserve:api:002",
                    "actor": "api-user",
                },
            ).json()
            consumed = client.post(
                f"/api/stock-reservations/{created_for_consumption['uid']}/consume",
                json={
                    "idempotency_key": "consume:api:002",
                    "actor": "api-user",
                    "reason": "Выдано сотруднику",
                },
            )
            assert consumed.status_code == 200
            assert consumed.json()["status"] == "consumed"
            assert consumed.json()["consumed_by_document_uid"].startswith("MOV-")

            openapi = client.get("/openapi.json").json()
            summary = openapi["paths"][
                "/api/stock-reservations/{reservation_uid}/release"
            ]["post"]["summary"]
            assert "снять резерв" in summary
            consume_summary = openapi["paths"][
                "/api/stock-reservations/{reservation_uid}/consume"
            ]["post"]["summary"]
            assert "погасить фактическим отбором" in consume_summary
    finally:
        app.dependency_overrides.clear()
