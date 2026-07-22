from datetime import date

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.session import Base
from app.schemas import BatchCreate, LocationCreate, ProductCreate, WarehouseCreate, ZoneCreate
from app.services import (
    accept_box,
    add_box_to_pallet,
    close_pallet,
    close_shipment,
    complete_inventory,
    confirm_inventory_missing,
    confirm_inventory_location,
    create_shipment,
    create_batch,
    create_location,
    create_product,
    create_warehouse,
    create_zone,
    ensure_demo_catalog,
    generate_demo_pallets,
    generate_boxes,
    move_inventory_pallet_to_actual,
    move_pallet,
    open_pallet,
    place_inventory_found_pallet,
    place_pallet,
    release_pallet,
    reopen_pallet,
    reserve_pallet_for_shipment,
    load_shipment_pallet,
    move_shipment_to_expedition,
    scan_inventory_pallet,
    scan_inventory_location,
    set_pallet_problem_status,
    start_inventory,
)
from app.models.enums import (
    BoxStatus,
    InventoryLineStatus,
    InventoryStatus,
    LocationKind,
    PalletStatus,
    ShipmentStatus,
    TransferStatus,
)
from app.models.entities import InventoryLine
from app.schemas import DemoCatalogRequest, DemoPalletsRequest, InventoryStartRequest, ShipmentCreate, TransferCreate
from app.schemas import WarehouseMapItemUpdate, WarehouseMapRowCreate
from app.transfers import (
    create_transfer,
    dispatch_transfer,
    load_transfer_pallet,
    move_transfer_to_expedition,
    receive_transfer_pallet,
    reserve_pallet_for_transfer,
)
from app.warehouse_map import create_map_row, ensure_demo_maps, reset_sandbox_map, update_map_item


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


def create_fixture_data(db):
    product = create_product(
        db,
        ProductCreate(
            code="ICE-TEST",
            name="Тестовое мороженое",
            quantity_per_box=24,
            boxes_per_pallet=2,
        ),
    )
    other_product = create_product(
        db,
        ProductCreate(
            code="ICE-OTHER",
            name="Другое мороженое",
            quantity_per_box=24,
            boxes_per_pallet=2,
        ),
    )
    batch = create_batch(
        db,
        BatchCreate(
            product_id=product.id,
            batch_number="20260721-1",
            production_date=date(2026, 7, 21),
            expiry_date=date(2027, 7, 21),
        ),
    )
    other_batch = create_batch(
        db,
        BatchCreate(
            product_id=other_product.id,
            batch_number="20260721-2",
            production_date=date(2026, 7, 21),
            expiry_date=date(2027, 7, 21),
        ),
    )
    warehouse = create_warehouse(db, WarehouseCreate(code="WH01", name="Основной склад"))
    zone = create_zone(db, ZoneCreate(warehouse_id=warehouse.id, code="FR01", name="Хранение"))
    location = create_location(db, LocationCreate(warehouse_id=warehouse.id, zone_id=zone.id, code="WH01-FR01-P01"))
    return product, batch, other_batch, location


def test_box_pallet_location_flow(db):
    _, batch, _, location = create_fixture_data(db)
    box = generate_boxes(db, batch_id=batch.id, quantity=1)[0]
    accept_box(db, box_uid=box.box_uid, actor="tester")
    pallet = open_pallet(db, actor="tester")
    add_box_to_pallet(db, pallet_uid=pallet.pallet_uid, box_uid=box.box_uid, actor="tester")
    close_pallet(db, pallet_uid=pallet.pallet_uid, actor="tester")
    placed = place_pallet(db, pallet_uid=pallet.pallet_uid, location_code=location.code, actor="tester")

    assert placed.current_location_id == location.id
    assert placed.status == "available"


def test_cannot_accept_box_twice(db):
    _, batch, _, _ = create_fixture_data(db)
    box = generate_boxes(db, batch_id=batch.id, quantity=1)[0]
    accept_box(db, box_uid=box.box_uid)

    with pytest.raises(HTTPException):
        accept_box(db, box_uid=box.box_uid)


def test_cannot_mix_product_or_batch_in_standard_pallet(db):
    _, batch, other_batch, _ = create_fixture_data(db)
    box = generate_boxes(db, batch_id=batch.id, quantity=1)[0]
    other_box = generate_boxes(db, batch_id=other_batch.id, quantity=1)[0]
    accept_box(db, box_uid=box.box_uid)
    accept_box(db, box_uid=other_box.box_uid)
    pallet = open_pallet(db)
    add_box_to_pallet(db, pallet_uid=pallet.pallet_uid, box_uid=box.box_uid)

    with pytest.raises(HTTPException):
        add_box_to_pallet(db, pallet_uid=pallet.pallet_uid, box_uid=other_box.box_uid)


def test_pallet_list_api_returns_working_pallet_summary(db):
    from fastapi.testclient import TestClient

    from app.main import app

    client = TestClient(app)
    response = client.get("/api/pallets?status=open&status=waiting_placement")

    assert response.status_code == 200
    assert isinstance(response.json(), list)


def test_reopen_closed_pallet_for_supplement(db):
    _, batch, _, _ = create_fixture_data(db)
    first_box, second_box = generate_boxes(db, batch_id=batch.id, quantity=2)
    accept_box(db, box_uid=first_box.box_uid)
    pallet = open_pallet(db)
    add_box_to_pallet(db, pallet_uid=pallet.pallet_uid, box_uid=first_box.box_uid)
    close_pallet(db, pallet_uid=pallet.pallet_uid)

    reopened = reopen_pallet(db, pallet_uid=pallet.pallet_uid, actor="senior", reason="дополнение")
    reopened_status = reopened.status
    accept_box(db, box_uid=second_box.box_uid)
    add_box_to_pallet(db, pallet_uid=pallet.pallet_uid, box_uid=second_box.box_uid)
    closed = close_pallet(db, pallet_uid=pallet.pallet_uid)

    assert reopened_status == PalletStatus.OPEN
    assert closed.status == PalletStatus.WAITING_PLACEMENT


def test_block_and_release_pallet(db):
    _, batch, _, location = create_fixture_data(db)
    box = generate_boxes(db, batch_id=batch.id, quantity=1)[0]
    accept_box(db, box_uid=box.box_uid)
    pallet = open_pallet(db)
    add_box_to_pallet(db, pallet_uid=pallet.pallet_uid, box_uid=box.box_uid)
    close_pallet(db, pallet_uid=pallet.pallet_uid)
    place_pallet(db, pallet_uid=pallet.pallet_uid, location_code=location.code)

    blocked = set_pallet_problem_status(
        db,
        pallet_uid=pallet.pallet_uid,
        target_status=PalletStatus.BLOCKED,
        actor="senior",
        reason="проверка",
    )
    blocked_status = blocked.status
    released = release_pallet(db, pallet_uid=pallet.pallet_uid, actor="senior", reason="проверено")

    assert blocked_status == PalletStatus.BLOCKED
    assert released.status == PalletStatus.AVAILABLE


def test_regular_pallet_move_cannot_cross_warehouses(db):
    _, batch, _, source_location = create_fixture_data(db)
    target_location = create_location(
        db,
        LocationCreate(
            warehouse_id=source_location.warehouse_id,
            zone_id=source_location.zone_id,
            code="WH01-FR01-P02",
            kind=LocationKind.STORAGE,
        ),
    )
    other_warehouse = create_warehouse(db, WarehouseCreate(code="WH02", name="Другой склад"))
    other_zone = create_zone(
        db,
        ZoneCreate(warehouse_id=other_warehouse.id, code="FR01", name="Хранение", kind=LocationKind.STORAGE),
    )
    other_location = create_location(
        db,
        LocationCreate(
            warehouse_id=other_warehouse.id,
            zone_id=other_zone.id,
            code="WH02-FR01-P01",
            kind=LocationKind.STORAGE,
        ),
    )
    box = generate_boxes(db, batch_id=batch.id, quantity=1)[0]
    accept_box(db, box_uid=box.box_uid)
    pallet = open_pallet(db)
    add_box_to_pallet(db, pallet_uid=pallet.pallet_uid, box_uid=box.box_uid)
    close_pallet(db, pallet_uid=pallet.pallet_uid)
    place_pallet(db, pallet_uid=pallet.pallet_uid, location_code=source_location.code)

    moved = move_pallet(db, pallet_uid=pallet.pallet_uid, location_code=target_location.code)
    assert moved.current_location_id == target_location.id

    with pytest.raises(HTTPException) as error:
        move_pallet(db, pallet_uid=pallet.pallet_uid, location_code=other_location.code)
    assert "without a transfer" in error.value.detail


def test_shipment_flow_reserve_expedition_load_close(db):
    _, batch, _, location = create_fixture_data(db)
    box = generate_boxes(db, batch_id=batch.id, quantity=1)[0]
    accept_box(db, box_uid=box.box_uid)
    pallet = open_pallet(db)
    add_box_to_pallet(db, pallet_uid=pallet.pallet_uid, box_uid=box.box_uid)
    close_pallet(db, pallet_uid=pallet.pallet_uid)
    place_pallet(db, pallet_uid=pallet.pallet_uid, location_code=location.code)

    shipment = create_shipment(db, ShipmentCreate(customer_name="Клиент", destination="Точка"))
    reserve_pallet_for_shipment(db, shipment_uid=shipment.shipment_uid, pallet_uid=pallet.pallet_uid)
    expedition = move_shipment_to_expedition(db, shipment_uid=shipment.shipment_uid)
    expedition_status = expedition.status
    loading = load_shipment_pallet(db, shipment_uid=shipment.shipment_uid, pallet_uid=pallet.pallet_uid)
    loading_status = loading.status
    completed = close_shipment(db, shipment_uid=shipment.shipment_uid, reason="погрузка завершена")
    completed_status = completed.status

    db.refresh(box)
    db.refresh(pallet)
    assert expedition_status == ShipmentStatus.EXPEDITION
    assert loading_status == ShipmentStatus.LOADING
    assert completed_status == ShipmentStatus.COMPLETED
    assert pallet.status == PalletStatus.SHIPPED
    assert pallet.current_location_id is None
    assert box.status == BoxStatus.SHIPPED


def test_shipment_cannot_mix_pallets_from_different_warehouses(db):
    _, batch, _, first_location = create_fixture_data(db)
    second_warehouse = create_warehouse(db, WarehouseCreate(code="WH02", name="Учебный склад"))
    second_zone = create_zone(
        db,
        ZoneCreate(warehouse_id=second_warehouse.id, code="FR01", name="Хранение", kind=LocationKind.STORAGE),
    )
    second_location = create_location(
        db,
        LocationCreate(
            warehouse_id=second_warehouse.id,
            zone_id=second_zone.id,
            code="WH02-FR01-P01",
            kind=LocationKind.STORAGE,
        ),
    )
    first_box, second_box = generate_boxes(db, batch_id=batch.id, quantity=2)
    pallets = []
    for box, location in ((first_box, first_location), (second_box, second_location)):
        accept_box(db, box_uid=box.box_uid)
        pallet = open_pallet(db)
        add_box_to_pallet(db, pallet_uid=pallet.pallet_uid, box_uid=box.box_uid)
        close_pallet(db, pallet_uid=pallet.pallet_uid)
        place_pallet(db, pallet_uid=pallet.pallet_uid, location_code=location.code)
        pallets.append(pallet)

    shipment = create_shipment(db, ShipmentCreate(customer_name="Клиент", destination="Точка"))
    reserve_pallet_for_shipment(db, shipment_uid=shipment.shipment_uid, pallet_uid=pallets[0].pallet_uid)

    with pytest.raises(HTTPException) as error:
        reserve_pallet_for_shipment(db, shipment_uid=shipment.shipment_uid, pallet_uid=pallets[1].pallet_uid)

    assert "one warehouse" in error.value.detail


def test_interwarehouse_transfer_dispatch_receive_and_place(db):
    _, batch, _, source_location = create_fixture_data(db)
    destination = create_warehouse(db, WarehouseCreate(code="WH02", name="Учебный склад"))
    destination_zone = create_zone(
        db,
        ZoneCreate(warehouse_id=destination.id, code="FR01", name="Хранение", kind=LocationKind.STORAGE),
    )
    destination_location = create_location(
        db,
        LocationCreate(
            warehouse_id=destination.id,
            zone_id=destination_zone.id,
            code="WH02-FR01-P01",
            kind=LocationKind.STORAGE,
        ),
    )
    box = generate_boxes(db, batch_id=batch.id, quantity=1)[0]
    accept_box(db, box_uid=box.box_uid, actor="tester")
    pallet = open_pallet(db, actor="tester")
    add_box_to_pallet(db, pallet_uid=pallet.pallet_uid, box_uid=box.box_uid, actor="tester")
    close_pallet(db, pallet_uid=pallet.pallet_uid, actor="tester")
    place_pallet(db, pallet_uid=pallet.pallet_uid, location_code=source_location.code, actor="tester")

    transfer = create_transfer(
        db,
        TransferCreate(
            source_warehouse_code="WH01",
            destination_warehouse_code="WH02",
            vehicle_number="А000АА 77",
            actor="tester",
        ),
    )
    reserve_pallet_for_transfer(db, transfer_uid=transfer.transfer_uid, pallet_uid=pallet.pallet_uid, actor="tester")
    move_transfer_to_expedition(db, transfer_uid=transfer.transfer_uid, actor="tester")
    db.refresh(pallet)
    assert pallet.current_location_id is None
    assert pallet.status == PalletStatus.EXPEDITION

    load_transfer_pallet(db, transfer_uid=transfer.transfer_uid, pallet_uid=pallet.pallet_uid, actor="tester")
    dispatched = dispatch_transfer(db, transfer_uid=transfer.transfer_uid, actor="tester")
    db.refresh(pallet)
    assert dispatched.status == TransferStatus.IN_TRANSIT
    assert pallet.status == PalletStatus.IN_TRANSIT

    received = receive_transfer_pallet(
        db,
        transfer_uid=transfer.transfer_uid,
        pallet_uid=pallet.pallet_uid,
        actor="receiver",
    )
    db.refresh(pallet)
    receiving_location = db.get(type(source_location), pallet.current_location_id)
    assert received.status == TransferStatus.COMPLETED
    assert pallet.status == PalletStatus.WAITING_PLACEMENT
    assert receiving_location.warehouse_id == destination.id
    assert receiving_location.kind == LocationKind.TRANSFER_IN

    with pytest.raises(HTTPException):
        place_pallet(db, pallet_uid=pallet.pallet_uid, location_code=source_location.code, actor="receiver")
    placed = place_pallet(db, pallet_uid=pallet.pallet_uid, location_code=destination_location.code, actor="receiver")
    assert placed.status == PalletStatus.AVAILABLE
    assert placed.current_location_id == destination_location.id


def test_interwarehouse_transfer_rejects_pallet_not_in_document(db):
    _, batch, _, source_location = create_fixture_data(db)
    create_warehouse(db, WarehouseCreate(code="WH02", name="Учебный склад"))

    def make_pallet(place: bool):
        box = generate_boxes(db, batch_id=batch.id, quantity=1)[0]
        accept_box(db, box_uid=box.box_uid, actor="tester")
        pallet = open_pallet(db, actor="tester")
        add_box_to_pallet(db, pallet_uid=pallet.pallet_uid, box_uid=box.box_uid, actor="tester")
        close_pallet(db, pallet_uid=pallet.pallet_uid, actor="tester")
        if place:
            place_pallet(db, pallet_uid=pallet.pallet_uid, location_code=source_location.code, actor="tester")
        return pallet

    sent_pallet = make_pallet(True)
    wrong_pallet = make_pallet(False)
    transfer = create_transfer(
        db,
        TransferCreate(source_warehouse_code="WH01", destination_warehouse_code="WH02", actor="tester"),
    )
    reserve_pallet_for_transfer(db, transfer_uid=transfer.transfer_uid, pallet_uid=sent_pallet.pallet_uid, actor="tester")
    move_transfer_to_expedition(db, transfer_uid=transfer.transfer_uid, actor="tester")
    load_transfer_pallet(db, transfer_uid=transfer.transfer_uid, pallet_uid=sent_pallet.pallet_uid, actor="tester")
    dispatch_transfer(db, transfer_uid=transfer.transfer_uid, actor="tester")

    with pytest.raises(HTTPException):
        receive_transfer_pallet(
            db,
            transfer_uid=transfer.transfer_uid,
            pallet_uid=wrong_pallet.pallet_uid,
            actor="receiver",
        )


def test_inventory_location_scan_and_complete(db):
    _, batch, _, location = create_fixture_data(db)
    box = generate_boxes(db, batch_id=batch.id, quantity=1)[0]
    accept_box(db, box_uid=box.box_uid)
    pallet = open_pallet(db)
    add_box_to_pallet(db, pallet_uid=pallet.pallet_uid, box_uid=box.box_uid)
    close_pallet(db, pallet_uid=pallet.pallet_uid)
    place_pallet(db, pallet_uid=pallet.pallet_uid, location_code=location.code)

    inventory = start_inventory(db, InventoryStartRequest(location_code=location.code, actor="auditor"))
    scan_inventory_pallet(db, inventory_uid=inventory.inventory_uid, pallet_uid=pallet.pallet_uid, actor="auditor")
    completed = complete_inventory(db, inventory_uid=inventory.inventory_uid, actor="auditor")
    line = db.query(InventoryLine).filter(InventoryLine.inventory_id == inventory.id).one()

    assert completed.status == InventoryStatus.COMPLETED
    assert line.status == InventoryLineStatus.SCANNED


def test_inventory_warehouse_walkthrough_scan_location_then_pallet(db):
    _, batch, _, location = create_fixture_data(db)
    box = generate_boxes(db, batch_id=batch.id, quantity=1)[0]
    accept_box(db, box_uid=box.box_uid)
    pallet = open_pallet(db)
    add_box_to_pallet(db, pallet_uid=pallet.pallet_uid, box_uid=box.box_uid)
    close_pallet(db, pallet_uid=pallet.pallet_uid)
    place_pallet(db, pallet_uid=pallet.pallet_uid, location_code=location.code)

    inventory = start_inventory(db, InventoryStartRequest(warehouse_code="WH01", actor="auditor"))
    scan_inventory_location(db, inventory_uid=inventory.inventory_uid, location_code=location.code, actor="auditor")
    scan_inventory_pallet(db, inventory_uid=inventory.inventory_uid, pallet_uid=pallet.pallet_uid, actor="auditor")
    completed = complete_inventory(db, inventory_uid=inventory.inventory_uid, actor="auditor")
    line = db.query(InventoryLine).filter(InventoryLine.inventory_id == inventory.id).one()

    assert completed.status == InventoryStatus.COMPLETED
    assert line.status == InventoryLineStatus.SCANNED


def test_inventory_progress_reports_checked_and_unchecked_locations(db):
    from app.api.routes import inventory_progress

    _, batch, _, first_location = create_fixture_data(db)
    second_location = create_location(
        db,
        LocationCreate(warehouse_id=first_location.warehouse_id, zone_id=first_location.zone_id, code="WH01-FR01-P02"),
    )
    box = generate_boxes(db, batch_id=batch.id, quantity=1)[0]
    accept_box(db, box_uid=box.box_uid)
    pallet = open_pallet(db)
    add_box_to_pallet(db, pallet_uid=pallet.pallet_uid, box_uid=box.box_uid)
    close_pallet(db, pallet_uid=pallet.pallet_uid)
    place_pallet(db, pallet_uid=pallet.pallet_uid, location_code=first_location.code)

    inventory = start_inventory(db, InventoryStartRequest(warehouse_code="WH01", actor="auditor"))
    before = inventory_progress(db, inventory)
    scan_inventory_location(db, inventory_uid=inventory.inventory_uid, location_code=first_location.code, actor="auditor")
    scan_inventory_pallet(db, inventory_uid=inventory.inventory_uid, pallet_uid=pallet.pallet_uid, actor="auditor")
    after = inventory_progress(db, inventory)

    assert before["total_locations"] == 2
    assert before["unchecked_locations"] == 2
    assert after["checked_locations"] == 1
    assert after["unchecked_locations"] == 1
    assert after["unchecked_locations_list"][0]["location_code"] == second_location.code


def test_inventory_empty_location_can_be_confirmed(db):
    from app.api.routes import inventory_progress

    _, _, _, first_location = create_fixture_data(db)
    second_location = create_location(
        db,
        LocationCreate(warehouse_id=first_location.warehouse_id, zone_id=first_location.zone_id, code="WH01-FR01-P02"),
    )

    inventory = start_inventory(db, InventoryStartRequest(warehouse_code="WH01", actor="auditor"))
    confirm_inventory_location(db, inventory_uid=inventory.inventory_uid, location_code=second_location.code, actor="auditor")
    progress = inventory_progress(db, inventory)

    assert progress["checked_locations"] == 1
    assert progress["unchecked_locations"] == 1
    assert progress["unchecked_locations_list"][0]["location_code"] == first_location.code
    assert progress["problem_lines"] == []


def test_inventory_cannot_complete_until_all_storage_locations_checked(db):
    _, _, _, first_location = create_fixture_data(db)
    second_location = create_location(
        db,
        LocationCreate(warehouse_id=first_location.warehouse_id, zone_id=first_location.zone_id, code="WH01-FR01-P02"),
    )

    inventory = start_inventory(db, InventoryStartRequest(warehouse_code="WH01", actor="auditor"))
    confirm_inventory_location(db, inventory_uid=inventory.inventory_uid, location_code=first_location.code, actor="auditor")

    with pytest.raises(HTTPException):
        complete_inventory(db, inventory_uid=inventory.inventory_uid, actor="auditor")

    confirm_inventory_location(db, inventory_uid=inventory.inventory_uid, location_code=second_location.code, actor="auditor")
    completed = complete_inventory(db, inventory_uid=inventory.inventory_uid, actor="auditor")

    assert completed.status == InventoryStatus.COMPLETED


def test_inventory_progress_ignores_receiving_locations(db):
    from app.api.routes import inventory_progress

    _, _, _, storage_location = create_fixture_data(db)
    receiving_zone = create_zone(
        db,
        ZoneCreate(
            warehouse_id=storage_location.warehouse_id,
            code="RCV",
            name="Приемка",
            kind=LocationKind.RECEIVING,
        ),
    )
    create_location(
        db,
        LocationCreate(
            warehouse_id=storage_location.warehouse_id,
            zone_id=receiving_zone.id,
            code="WH01-RCV-P01",
            kind=LocationKind.RECEIVING,
        ),
    )

    inventory = start_inventory(db, InventoryStartRequest(warehouse_code="WH01", actor="auditor"))
    progress = inventory_progress(db, inventory)

    assert progress["total_locations"] == 1
    assert progress["unchecked_locations_list"][0]["location_code"] == storage_location.code


def test_inventory_confirm_location_marks_unseen_expected_pallets_missing(db):
    _, batch, _, location = create_fixture_data(db)
    box = generate_boxes(db, batch_id=batch.id, quantity=1)[0]
    accept_box(db, box_uid=box.box_uid)
    pallet = open_pallet(db)
    add_box_to_pallet(db, pallet_uid=pallet.pallet_uid, box_uid=box.box_uid)
    close_pallet(db, pallet_uid=pallet.pallet_uid)
    place_pallet(db, pallet_uid=pallet.pallet_uid, location_code=location.code)

    inventory = start_inventory(db, InventoryStartRequest(warehouse_code="WH01", actor="auditor"))
    confirm_inventory_location(db, inventory_uid=inventory.inventory_uid, location_code=location.code, actor="auditor")
    line = db.query(InventoryLine).filter(InventoryLine.inventory_id == inventory.id).one()

    assert line.status == InventoryLineStatus.MISSING


def test_inventory_detects_wrong_location_pallet(db):
    _, batch, _, first_location = create_fixture_data(db)
    warehouse_id = first_location.warehouse_id
    zone_id = first_location.zone_id
    second_location = create_location(
        db,
        LocationCreate(warehouse_id=warehouse_id, zone_id=zone_id, code="WH01-FR01-P02"),
    )
    box = generate_boxes(db, batch_id=batch.id, quantity=1)[0]
    accept_box(db, box_uid=box.box_uid)
    pallet = open_pallet(db)
    add_box_to_pallet(db, pallet_uid=pallet.pallet_uid, box_uid=box.box_uid)
    close_pallet(db, pallet_uid=pallet.pallet_uid)
    place_pallet(db, pallet_uid=pallet.pallet_uid, location_code=second_location.code)

    inventory = start_inventory(db, InventoryStartRequest(location_code=first_location.code, actor="auditor"))
    scan_inventory_pallet(db, inventory_uid=inventory.inventory_uid, pallet_uid=pallet.pallet_uid, actor="auditor")
    line = db.query(InventoryLine).filter(InventoryLine.inventory_id == inventory.id).one()

    assert line.status == InventoryLineStatus.WRONG_LOCATION


def test_inventory_missing_discrepancy_can_be_confirmed(db):
    from app.api.routes import inventory_progress
    from app.models.entities import OperationEvent

    _, batch, _, location = create_fixture_data(db)
    box = generate_boxes(db, batch_id=batch.id, quantity=1)[0]
    accept_box(db, box_uid=box.box_uid)
    pallet = open_pallet(db)
    add_box_to_pallet(db, pallet_uid=pallet.pallet_uid, box_uid=box.box_uid)
    close_pallet(db, pallet_uid=pallet.pallet_uid)
    place_pallet(db, pallet_uid=pallet.pallet_uid, location_code=location.code)

    inventory = start_inventory(db, InventoryStartRequest(warehouse_code="WH01", actor="auditor"))
    confirm_inventory_location(db, inventory_uid=inventory.inventory_uid, location_code=location.code, actor="auditor")

    before = inventory_progress(db, inventory)
    assert len(before["problem_lines"]) == 1
    assert before["problem_lines"][0]["status"] == InventoryLineStatus.MISSING

    line = confirm_inventory_missing(
        db,
        inventory_uid=inventory.inventory_uid,
        pallet_uid=pallet.pallet_uid,
        actor="manager",
        reason="факт недостачи подтвержден",
    )
    after = inventory_progress(db, inventory)
    event = db.query(OperationEvent).filter(OperationEvent.operation == "inventory_discrepancy_resolved").one()

    assert line.status == InventoryLineStatus.MISSING
    assert after["problem_lines"] == []
    assert event.after["action"] == "missing_confirmed"

    with pytest.raises(HTTPException):
        confirm_inventory_missing(
            db,
            inventory_uid=inventory.inventory_uid,
            pallet_uid=pallet.pallet_uid,
            actor="manager",
            reason="повтор",
        )


def test_inventory_extra_pallet_can_be_placed_to_actual_location(db):
    from app.api.routes import inventory_progress

    _, batch, _, location = create_fixture_data(db)
    box = generate_boxes(db, batch_id=batch.id, quantity=1)[0]
    accept_box(db, box_uid=box.box_uid)
    pallet = open_pallet(db)
    add_box_to_pallet(db, pallet_uid=pallet.pallet_uid, box_uid=box.box_uid)
    close_pallet(db, pallet_uid=pallet.pallet_uid)

    inventory = start_inventory(db, InventoryStartRequest(warehouse_code="WH01", actor="auditor"))
    scan_inventory_location(db, inventory_uid=inventory.inventory_uid, location_code=location.code, actor="auditor")
    scan_inventory_pallet(db, inventory_uid=inventory.inventory_uid, pallet_uid=pallet.pallet_uid, actor="auditor")
    line = db.query(InventoryLine).filter(InventoryLine.inventory_id == inventory.id).one()

    assert line.status == InventoryLineStatus.EXTRA

    place_inventory_found_pallet(
        db,
        inventory_uid=inventory.inventory_uid,
        pallet_uid=pallet.pallet_uid,
        actor="manager",
        reason="нашли в ячейке",
    )
    db.refresh(pallet)
    after = inventory_progress(db, inventory)

    assert pallet.current_location_id == location.id
    assert pallet.status == PalletStatus.AVAILABLE
    assert after["problem_lines"] == []


def test_inventory_wrong_location_pallet_can_be_moved_to_actual_location(db):
    from app.api.routes import inventory_progress

    _, batch, _, first_location = create_fixture_data(db)
    second_location = create_location(
        db,
        LocationCreate(warehouse_id=first_location.warehouse_id, zone_id=first_location.zone_id, code="WH01-FR01-P02"),
    )
    box = generate_boxes(db, batch_id=batch.id, quantity=1)[0]
    accept_box(db, box_uid=box.box_uid)
    pallet = open_pallet(db)
    add_box_to_pallet(db, pallet_uid=pallet.pallet_uid, box_uid=box.box_uid)
    close_pallet(db, pallet_uid=pallet.pallet_uid)
    place_pallet(db, pallet_uid=pallet.pallet_uid, location_code=second_location.code)

    inventory = start_inventory(db, InventoryStartRequest(warehouse_code="WH01", actor="auditor"))
    scan_inventory_location(db, inventory_uid=inventory.inventory_uid, location_code=first_location.code, actor="auditor")
    scan_inventory_pallet(db, inventory_uid=inventory.inventory_uid, pallet_uid=pallet.pallet_uid, actor="auditor")
    line = db.query(InventoryLine).filter(InventoryLine.inventory_id == inventory.id).one()

    assert line.status == InventoryLineStatus.WRONG_LOCATION

    move_inventory_pallet_to_actual(
        db,
        inventory_uid=inventory.inventory_uid,
        pallet_uid=pallet.pallet_uid,
        actor="manager",
        reason="факт принят",
    )
    db.refresh(pallet)
    after = inventory_progress(db, inventory)

    assert pallet.current_location_id == first_location.id
    assert after["problem_lines"] == []


def test_demo_catalog_generator_is_idempotent(db):
    first = ensure_demo_catalog(db, DemoCatalogRequest(storage_locations=3, actor="tester"))
    second = ensure_demo_catalog(db, DemoCatalogRequest(storage_locations=3, actor="tester"))

    assert first["created_products"] == 3
    assert first["created_batches"] == 3
    assert first["created_locations"] == 4
    assert second["created_products"] == 0
    assert second["created_batches"] == 0
    assert second["created_locations"] == 0


def test_demo_pallet_generator_creates_closed_placed_pallets(db):
    catalog = ensure_demo_catalog(db, DemoCatalogRequest(storage_locations=2, actor="tester"))
    result = generate_demo_pallets(
        db,
        DemoPalletsRequest(batch_id=catalog["batch_ids"][0], quantity=2, boxes_per_pallet=2, actor="tester"),
    )

    assert result["created_boxes"] == 4
    assert result["created_pallets"] == 2
    assert result["placed_pallets"] == 2
    assert result["waiting_pallets"] == 0


def test_label_pdf_endpoints_return_pdf(db):
    from fastapi.testclient import TestClient

    from app.api import routes as api_routes
    from app.db.session import get_db
    from app.main import app

    _, batch, _, location = create_fixture_data(db)
    box = generate_boxes(db, batch_id=batch.id, quantity=1)[0]
    accept_box(db, box_uid=box.box_uid)
    pallet = open_pallet(db)
    add_box_to_pallet(db, pallet_uid=pallet.pallet_uid, box_uid=box.box_uid)
    close_pallet(db, pallet_uid=pallet.pallet_uid)
    place_pallet(db, pallet_uid=pallet.pallet_uid, location_code=location.code)

    def override_db():
        yield db

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[api_routes.get_db] = override_db
    try:
        client = TestClient(app)
        for path in [
            f"/api/boxes/{box.box_uid}/label.pdf",
            f"/api/pallets/{pallet.pallet_uid}/label.pdf",
            "/api/labels/locations.pdf",
        ]:
            response = client.get(path)
            assert response.status_code == 200
            assert response.headers["content-type"] == "application/pdf"
            assert response.content.startswith(b"%PDF")
    finally:
        app.dependency_overrides.clear()


def test_label_pdf_filters_selected_objects(db, monkeypatch):
    from fastapi.testclient import TestClient

    from app.api import routes as api_routes
    from app.db.session import get_db
    from app.main import app

    _, batch, _, first_location = create_fixture_data(db)
    second_location = create_location(
        db,
        LocationCreate(warehouse_id=first_location.warehouse_id, zone_id=first_location.zone_id, code="WH01-FR01-P02"),
    )
    first_box, second_box = generate_boxes(db, batch_id=batch.id, quantity=2)
    accept_box(db, box_uid=first_box.box_uid)
    accept_box(db, box_uid=second_box.box_uid)
    first_pallet = open_pallet(db)
    second_pallet = open_pallet(db)
    add_box_to_pallet(db, pallet_uid=first_pallet.pallet_uid, box_uid=first_box.box_uid)
    add_box_to_pallet(db, pallet_uid=second_pallet.pallet_uid, box_uid=second_box.box_uid)
    close_pallet(db, pallet_uid=first_pallet.pallet_uid)
    close_pallet(db, pallet_uid=second_pallet.pallet_uid)
    place_pallet(db, pallet_uid=first_pallet.pallet_uid, location_code=first_location.code)
    place_pallet(db, pallet_uid=second_pallet.pallet_uid, location_code=second_location.code)

    captured = []

    def fake_pdf(items, *, title):
        captured.append((title, [item.code for item in items]))
        return b"%PDF fake"

    def override_db():
        yield db

    monkeypatch.setattr(api_routes, "build_labels_pdf", fake_pdf)
    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[api_routes.get_db] = override_db
    try:
        client = TestClient(app)

        boxes = client.get(f"/api/labels/boxes.pdf?box_uid={first_box.box_uid},{second_box.box_uid}&limit=10")
        assert boxes.status_code == 200
        assert captured[-1][1] == [second_box.box_uid, first_box.box_uid]

        pallets = client.get(f"/api/labels/pallets.pdf?pallet_uid={first_pallet.pallet_uid}&limit=10")
        assert pallets.status_code == 200
        assert captured[-1][1] == [first_pallet.pallet_uid]

        locations = client.get(f"/api/labels/locations.pdf?location_code={second_location.code}&storage_only=false&limit=10")
        assert locations.status_code == 200
        assert captured[-1][1] == [second_location.code]
    finally:
        app.dependency_overrides.clear()


def test_catalog_import_preview_and_apply_csv(db):
    from fastapi.testclient import TestClient

    from app.api import routes as api_routes
    from app.db.session import get_db
    from app.main import app

    def override_db():
        yield db

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[api_routes.get_db] = override_db
    try:
        client = TestClient(app)
        products_csv = "code;name;unit;quantity_per_box;boxes_per_pallet;shelf_life_days\nIMP-ICE;Импортное мороженое;шт;12;48;365\n"
        preview = client.post(
            "/api/import/preview/products",
            files={"file": ("products.csv", products_csv.encode("utf-8"), "text/csv")},
        )
        assert preview.status_code == 200
        assert preview.json()["valid_rows"] == 1
        applied = client.post(
            "/api/import/apply/products",
            files={"file": ("products.csv", products_csv.encode("utf-8"), "text/csv")},
        )
        assert applied.status_code == 200
        assert applied.json()["created"] == 1

        batches_csv = "product_code;batch_number;production_date;expiry_date\nIMP-ICE;IMP-20260721;2026-07-21;2027-07-21\n"
        batch_applied = client.post(
            "/api/import/apply/batches",
            files={"file": ("batches.csv", batches_csv.encode("utf-8"), "text/csv")},
        )
        assert batch_applied.status_code == 200
        assert batch_applied.json()["created"] == 1

        locations_csv = "warehouse_code;warehouse_name;zone_code;zone_name;code;name;kind;capacity_pallets\nIMPWH;Импортный склад;IMPZ;Импортная зона;IMPWH-IMPZ-P01;Место 1;Хранение;1\n"
        location_applied = client.post(
            "/api/import/apply/locations",
            files={"file": ("locations.csv", locations_csv.encode("utf-8"), "text/csv")},
        )
        assert location_applied.status_code == 200
        assert location_applied.json()["created"] == 1
    finally:
        app.dependency_overrides.clear()


def test_object_cards_api_returns_pallet_box_and_location_cards(db):
    from fastapi.testclient import TestClient

    from app.api import routes as api_routes
    from app.db.session import get_db
    from app.main import app

    _, batch, _, location = create_fixture_data(db)
    box = generate_boxes(db, batch_id=batch.id, quantity=1)[0]
    accept_box(db, box_uid=box.box_uid)
    pallet = open_pallet(db)
    add_box_to_pallet(db, pallet_uid=pallet.pallet_uid, box_uid=box.box_uid)
    close_pallet(db, pallet_uid=pallet.pallet_uid)
    place_pallet(db, pallet_uid=pallet.pallet_uid, location_code=location.code)

    def override_db():
        yield db

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[api_routes.get_db] = override_db
    try:
        client = TestClient(app)

        resolved = client.get(f"/api/cards/resolve/{pallet.pallet_uid}")
        assert resolved.status_code == 200
        assert resolved.json()["kind"] == "pallet"

        pallet_card = client.get(f"/api/cards/pallets/{pallet.pallet_uid}")
        assert pallet_card.status_code == 200
        assert pallet_card.json()["pallet"]["pallet_uid"] == pallet.pallet_uid
        assert pallet_card.json()["boxes"][0]["box_uid"] == box.box_uid

        box_card = client.get(f"/api/cards/boxes/{box.box_uid}")
        assert box_card.status_code == 200
        assert box_card.json()["pallet"]["pallet_uid"] == pallet.pallet_uid
        assert box_card.json()["location"]["code"] == location.code

        location_card = client.get(f"/api/cards/locations/{location.code}")
        assert location_card.status_code == 200
        assert location_card.json()["location"]["occupied_pallets"] == 1
        assert location_card.json()["pallets"][0]["pallet_uid"] == pallet.pallet_uid

        page = client.get(f"/cards?kind=pallet&code={pallet.pallet_uid}")
        assert page.status_code == 200
        assert "Карточка объекта" in page.text
    finally:
        app.dependency_overrides.clear()


def test_terminal_page_contains_compact_workflows():
    from app.web import terminal_page

    page = terminal_page()

    assert "Эмулятор экрана ТСД" in page
    assert 'id="warehouseView"' in page
    assert 'id="inventoryView"' in page
    assert 'id="transferView"' in page
    assert 'id="shippingView"' in page
    assert 'class="device"' in page


def test_scan_page_has_warehouse_switch_and_map_link():
    from app.web import scan_page

    page = scan_page()

    assert 'id="warehouseSelect"' in page
    assert 'id="warehouseMapLink"' in page
    assert "Карта склада" in page
    assert "function switchWarehouse" in page


def test_workplace_is_default_and_keeps_technical_mode_available():
    from app.web import root
    from app.work_web import tech_page, work_page

    response = root()
    assert response.status_code in {302, 307}
    assert response.headers["location"] == "/work"

    workplace = work_page()
    assert 'id="workWarehouse"' in workplace
    assert 'id="workActor"' in workplace
    assert 'data-operation="build"' in workplace
    assert 'data-operation="place"' in workplace
    assert 'data-operation="move"' in workplace
    assert 'data-operation="ship"' in workplace
    assert 'data-operation="inventory"' in workplace
    assert 'data-operation="transfer"' in workplace
    assert 'href="/tech"' in workplace
    assert 'post("/api/pallets"' in workplace
    assert '/boxes/${encodeURIComponent(boxUid)}' in workplace
    assert '/place`' in workplace
    assert '/move`' in workplace
    assert 'post("/api/shipments"' in workplace
    assert '/expedition`' in workplace
    assert '/load/${encodeURIComponent(palletUid)}`' in workplace
    assert '/close`' in workplace
    assert 'post("/api/inventories"' in workplace
    assert '/scan-location`' in workplace
    assert '/confirm-location`' in workplace
    assert '/complete`' in workplace
    assert 'post("/api/transfers"' in workplace
    assert '/transfers/${encodeURIComponent(state.transfer.transfer_uid)}/expedition`' in workplace
    assert '/load/${encodeURIComponent(palletUid)}`' in workplace
    assert '/dispatch`' in workplace
    assert '/receive/${encodeURIComponent(palletUid)}`' in workplace
    assert 'id="placeTransferBtn"' in workplace

    technical = tech_page()
    assert "Все функции системы" in technical
    assert 'href="/work"' in technical
    assert 'href="/scan"' in technical
    assert 'href="/catalog"' in technical


def test_pages_use_one_stable_navigation_header():
    from app.map_web import map_page
    from app.transfer_web import transfers_page
    from app.web import cards_page, catalog_page, inventory_page, scan_page, shipments_page, terminal_page

    pages = {
        "scan": scan_page(),
        "terminal": terminal_page(),
        "map": map_page(),
        "transfers": transfers_page(),
        "shipments": shipments_page(),
        "inventory": inventory_page(),
        "catalog": catalog_page(),
        "cards": cards_page(),
    }
    expected_links = [
        "/scan",
        "/transfers",
        "/shipments",
        "/inventory",
        "/work",
        "/terminal",
        "/map",
        "/catalog",
        "/cards",
        "/docs",
    ]

    for active, page in pages.items():
        assert page.count('class="app-header') == 1
        assert page.count('class="app-nav"') == 1
        assert f'data-page="{active}"' in page
        assert f'class="active" href="/{active}"' in page
        assert [page.index(f'href="{href}"') for href in expected_links] == sorted(
            page.index(f'href="{href}"') for href in expected_links
        )


def test_map_setup_creates_real_sandbox_warehouse_and_locations(db):
    from app.models.entities import Location, Warehouse, WarehouseMapItem

    _, _, _, existing_location = create_fixture_data(db)
    accidental = create_location(
        db,
        LocationCreate(
            warehouse_id=existing_location.warehouse_id,
            zone_id=existing_location.zone_id,
            code="WH02",
            name="Ошибочная ячейка",
        ),
    )
    assert accidental.code == "WH02"

    maps = ensure_demo_maps(db, actor="tester")

    sandbox = db.scalar(select(Warehouse).where(Warehouse.code == "WH02"))
    assert [item["code"] for item in maps] == ["WH01", "WH02"]
    assert sandbox is not None
    assert db.scalar(select(Location).where(Location.code == "WH02")) is None
    assert db.scalar(select(func.count(Location.id)).where(Location.warehouse_id == sandbox.id)) == 8
    assert db.scalar(select(func.count(WarehouseMapItem.id)).where(WarehouseMapItem.warehouse_id == sandbox.id)) == 12


def test_map_row_creates_locations_and_rack_move_updates_children(db):
    from app.models.entities import Location, Warehouse, WarehouseMapItem

    create_fixture_data(db)
    ensure_demo_maps(db, actor="tester")
    sandbox = db.scalar(select(Warehouse).where(Warehouse.code == "WH02"))

    create_map_row(
        db,
        "WH02",
        WarehouseMapRowCreate(
            row_code="R03",
            label="Тестовый стеллаж",
            location_count=3,
            x=120,
            y=250,
            actor="tester",
        ),
    )

    rack = db.scalar(
        select(WarehouseMapItem).where(
            WarehouseMapItem.warehouse_id == sandbox.id,
            WarehouseMapItem.item_key == "rack:ST01:R03",
        )
    )
    children = list(
        db.scalars(
            select(WarehouseMapItem)
            .where(WarehouseMapItem.parent_id == rack.id)
            .order_by(WarehouseMapItem.sort_order)
        )
    )
    assert db.scalar(
        select(func.count(Location.id)).where(
            Location.warehouse_id == sandbox.id,
            Location.code.like("WH02-ST01-R03-%"),
        )
    ) == 3
    assert [child.x for child in children] == [130, 248, 366]

    update_map_item(
        db,
        "WH02",
        rack.id,
        WarehouseMapItemUpdate(x=400, y=30, rotation=90, label="Вертикальный ряд", actor="tester"),
    )
    db.refresh(rack)
    children = list(
        db.scalars(
            select(WarehouseMapItem)
            .where(WarehouseMapItem.parent_id == rack.id)
            .order_by(WarehouseMapItem.sort_order)
        )
    )
    assert rack.rotation == 90
    assert rack.label == "Вертикальный ряд"
    assert [child.x for child in children] == [410, 410, 410]
    assert [child.y for child in children] == [40, 106, 172]


def test_map_reset_removes_custom_locations_from_database(db):
    from app.models.entities import Location, Warehouse

    create_fixture_data(db)
    ensure_demo_maps(db, actor="tester")
    sandbox = db.scalar(select(Warehouse).where(Warehouse.code == "WH02"))
    create_map_row(
        db,
        "WH02",
        WarehouseMapRowCreate(
            row_code="CUSTOM",
            label="Временный ряд",
            location_count=2,
            actor="tester",
        ),
    )
    assert db.scalar(select(Location.id).where(Location.code == "WH02-ST01-CUSTOM-P01"))

    result = reset_sandbox_map(db, "WH02", actor="tester")

    assert db.scalar(select(Location.id).where(Location.code == "WH02-ST01-CUSTOM-P01")) is None
    assert db.scalar(select(func.count(Location.id)).where(Location.warehouse_id == sandbox.id)) == 8
    assert result["stats"]["locations"] == 8
