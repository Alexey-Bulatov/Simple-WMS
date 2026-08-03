from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api import routes as api_routes
from app.db.session import Base, get_db
from app.main import app
from app.models.entities import Location, LogisticUnit, Warehouse
from app.schemas import DemoCatalogRequest
from app.services import ensure_demo_catalog


@pytest.fixture()
def db():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    session = sessionmaker(bind=engine, autoflush=False, autocommit=False)()
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


def test_demo_catalog_generator_is_idempotent(db):
    first = ensure_demo_catalog(
        db,
        DemoCatalogRequest(storage_locations=3, actor="tester"),
    )
    second = ensure_demo_catalog(
        db,
        DemoCatalogRequest(storage_locations=3, actor="tester"),
    )

    assert first["created_products"] == 3
    assert first["created_batches"] == 3
    assert first["created_aisles"] == 1
    assert first["created_racks"] == 1
    assert first["created_sections"] == 1
    assert first["created_levels"] == 1
    assert first["created_locations"] == 4
    assert second["created_products"] == 0
    assert second["created_batches"] == 0
    assert second["created_aisles"] == 0
    assert second["created_racks"] == 0
    assert second["created_sections"] == 0
    assert second["created_levels"] == 0
    assert second["created_locations"] == 0


def test_catalog_import_uses_universal_product_and_location_fields(client):
    products_csv = (
        "code;name;unit;shelf_life_days\n"
        "IMP-ICE;Импортное мороженое;шт;365\n"
    )
    response = client.post(
        "/api/import/apply/products",
        files={"file": ("products.csv", products_csv.encode(), "text/csv")},
    )
    assert response.status_code == 200, response.text
    assert response.json()["created"] == 1

    batches_csv = (
        "product_code;batch_number;production_date;expiry_date\n"
        "IMP-ICE;IMP-20260721;2026-07-21;2027-07-21\n"
    )
    response = client.post(
        "/api/import/apply/batches",
        files={"file": ("batches.csv", batches_csv.encode(), "text/csv")},
    )
    assert response.status_code == 200, response.text
    assert response.json()["created"] == 1

    locations_csv = (
        "warehouse_code;warehouse_name;zone_code;zone_name;code;name;kind;capacity_units\n"
        "IMPWH;Импортный склад;IMPZ;Импортная зона;"
        "IMPWH-IMPZ-P01;Место 1;Хранение;2\n"
    )
    response = client.post(
        "/api/import/apply/locations",
        files={"file": ("locations.csv", locations_csv.encode(), "text/csv")},
    )
    assert response.status_code == 200, response.text
    assert response.json()["created"] == 1

    locations = client.get("/api/locations").json()
    imported = next(row for row in locations if row["code"] == "IMPWH-IMPZ-P01")
    assert imported["capacity_units"] == 2


def test_universal_cards_labels_and_thermal_print(client, db, monkeypatch):
    generated = client.post(
        "/api/demo/logistic-units",
        json={
            "warehouse_code": "WH01",
            "warehouse_name": "Основной склад",
            "storage_locations": 2,
            "quantity": 1,
            "parent_type_code": "IBC",
            "child_type_code": None,
            "content_uom_code": "L",
            "content_quantity": "1000",
            "place_to_empty_locations": True,
            "actor": "tester",
        },
    )
    assert generated.status_code == 200, generated.text
    unit_uid = generated.json()["logistic_unit_uids"][0]
    unit = db.scalar(select(LogisticUnit).where(LogisticUnit.uid == unit_uid))
    location = db.get(Location, unit.current_location_id)

    resolved_unit = client.get(f"/api/cards/resolve/{unit_uid}")
    assert resolved_unit.json()["kind"] == "unit"
    assert resolved_unit.json()["code"] == unit_uid
    resolved_location = client.get(f"/api/cards/resolve/{location.code}")
    assert resolved_location.json()["kind"] == "location"
    assert resolved_location.json()["code"] == location.code

    card = client.get(f"/api/cards/locations/{location.code}")
    assert card.status_code == 200, card.text
    assert card.json()["location"]["occupied_units"] == 1
    assert card.json()["logistic_units"][0]["uid"] == unit_uid

    for path in (
        f"/api/logistic-units/{unit_uid}/label.pdf",
        f"/api/locations/{location.code}/label.pdf",
        f"/api/labels/logistic-units.pdf?unit_uid={unit_uid}",
        f"/api/labels/locations.pdf?location_code={location.code}",
    ):
        response = client.get(path)
        assert response.status_code == 200, response.text
        assert response.headers["content-type"] == "application/pdf"
        assert response.content.startswith(b"%PDF")

    captured = []

    def fake_print(item):
        captured.append((item.object_type, item.code))
        return {"queue": "ATOL_TT42", "job_id": "ATOL_TT42-1"}

    monkeypatch.setattr(api_routes, "print_thermal_label", fake_print)
    response = client.post(f"/api/logistic-units/{unit_uid}/label.print")
    assert response.status_code == 200, response.text
    assert captured == [("Еврокуб", unit_uid)]


def test_map_uses_universal_logistic_units(client, db):
    catalog = client.post(
        "/api/demo/catalog",
        json={
            "warehouse_code": "WH01",
            "warehouse_name": "Основной склад",
            "storage_locations": 10,
            "actor": "tester",
        },
    )
    assert catalog.status_code == 200, catalog.text
    setup = client.post("/api/maps/setup", json={"actor": "tester"})
    assert setup.status_code == 200, setup.text
    assert {row["code"] for row in setup.json()} == {"WH01", "WH02"}

    generated = client.post(
        "/api/demo/logistic-units",
        json={
            "warehouse_code": "WH02",
            "warehouse_name": "Учебный склад",
            "storage_locations": 8,
            "quantity": 1,
            "parent_type_code": "PALLET",
            "child_type_code": "DRUM",
            "child_units_per_parent": 2,
            "content_uom_code": "L",
            "content_quantity": "200",
            "place_to_empty_locations": False,
            "actor": "tester",
        },
    )
    assert generated.status_code == 200, generated.text
    mapped_location = db.scalar(
        select(Location).where(Location.code.like("WH02-ST01-%"))
    )
    assert mapped_location.level_id is not None
    assert len(mapped_location.code.split("-")) == 7
    placed = client.post(
        f"/api/logistic-units/{generated.json()['logistic_unit_uids'][0]}/place",
        json={
            "location_code": mapped_location.code,
            "actor": "tester",
            "reason": "map test",
        },
    )
    assert placed.status_code == 200, placed.text

    payload = client.get("/api/maps/WH02")
    assert payload.status_code == 200, payload.text
    assert payload.json()["stats"]["logistic_units"] == 1
    locations = [
        item["location"]
        for item in payload.json()["items"]
        if item["location"] and item["location"]["units"]
    ]
    assert locations[0]["units"][0]["type_code"] == "PALLET"
    assert locations[0]["units"][0]["child_count"] == 2
    assert locations[0]["address"]["structured"] is True

    warehouse = db.scalar(select(Warehouse).where(Warehouse.code == "WH02"))
    assert warehouse is not None


def test_simple_wms_pages_use_universal_operator_shell():
    from app.universal_web import (
        cards_page,
        demo_page,
        root,
        tasks,
        terminal_page,
        work_page,
    )

    assert root().headers["location"] == "/work"
    assert tasks().headers["location"] == "/work"
    pages = {
        "work": work_page(),
        "terminal": terminal_page(),
        "cards": cards_page(),
        "demo": demo_page(),
    }
    expected_links = ["/work", "/terminal", "/cards", "/demo", "/docs"]
    for active, page in pages.items():
        assert page.count('class="product-header') == 1
        assert f'class="active" href="/{active}"' in page
        indexes = [page.index(f'href="{href}"') for href in expected_links]
        assert indexes == sorted(indexes)

    assert 'class="terminal-device"' in pages["terminal"]
    assert "WMS · Wi-Fi · 87%" in pages["terminal"]
    assert "/static/universal-cards.js" in pages["cards"]
    assert "/static/universal-demo.js" in pages["demo"]


def test_operator_javascript_has_no_pilot_backend_contracts():
    static_dir = Path(__file__).parents[1] / "app" / "static"
    console = (static_dir / "universal-console.js").read_text()
    cards = (static_dir / "universal-cards.js").read_text()
    demo = (static_dir / "universal-demo.js").read_text()

    assert "/api/logistic-tasks/sync" in console
    assert "/api/logistic-units/" in console
    assert "/api/logistic-shipments/" in console
    assert "/api/logistic-transfers/" in console
    assert "/api/logistic-inventories/" in console
    assert "/api/tasks" not in console
    assert "/api/pallets" not in console
    assert "/api/boxes" not in console
    assert "/api/logistic-units/" in cards
    assert "capacity_units" in cards
    assert "/api/demo/logistic-units" in demo
    assert "/api/demo/pallets" not in demo
