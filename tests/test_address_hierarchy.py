import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api import routes as api_routes
from app.db.session import Base, get_db
from app.main import app
from app.models.entities import Aisle, Location, Rack, RackLevel, RackSection


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


def create_address(client: TestClient, *, position_code: str = "P03") -> dict:
    warehouse = client.post(
        "/api/warehouses",
        json={"code": "wh10", "name": "Адресный склад", "city": "Москва"},
    ).json()
    zone = client.post(
        "/api/zones",
        json={
            "warehouse_id": warehouse["id"],
            "code": "st01",
            "name": "Хранение",
            "kind": "storage",
        },
    ).json()
    aisle = client.post(
        "/api/aisles",
        json={"zone_id": zone["id"], "code": "a02", "name": "Проход 2"},
    ).json()
    rack = client.post(
        "/api/racks",
        json={"aisle_id": aisle["id"], "code": "r04", "name": "Стеллаж 4"},
    ).json()
    section = client.post(
        "/api/rack-sections",
        json={"rack_id": rack["id"], "code": "s02", "name": "Секция 2"},
    ).json()
    level = client.post(
        "/api/rack-levels",
        json={
            "section_id": section["id"],
            "code": "l03",
            "name": "Ярус 3",
            "elevation_mm": 1800,
        },
    ).json()
    location = client.post(
        "/api/locations",
        json={
            "warehouse_id": warehouse["id"],
            "zone_id": zone["id"],
            "aisle_id": aisle["id"],
            "rack_id": rack["id"],
            "section_id": section["id"],
            "level_id": level["id"],
            "position_code": position_code,
            "name": "Позиция 3",
            "kind": "storage",
            "capacity_units": 2,
        },
    )
    assert location.status_code == 200, location.text
    return location.json()


def test_address_api_builds_canonical_location_and_tree(client, db):
    location = create_address(client)
    assert location["code"] == "WH10-ST01-A02-R04-S02-L03-P03"
    assert location["position_code"] == "P03"

    statements = []

    def record_statement(*_):
        statements.append(1)

    event.listen(db.get_bind(), "before_cursor_execute", record_statement)
    try:
        tree = client.get("/api/warehouses/wh10/address-tree")
    finally:
        event.remove(db.get_bind(), "before_cursor_execute", record_statement)
    assert tree.status_code == 200, tree.text
    assert len(statements) == 7
    zone = tree.json()["zones"][0]
    position = zone["aisles"][0]["racks"][0]["sections"][0]["levels"][0]["positions"][0]
    assert position["code"] == location["code"]
    assert position["capacity_units"] == 2

    card = client.get(f"/api/cards/locations/{location['code']}")
    assert card.status_code == 200, card.text
    assert card.json()["location"]["address"] == {
        "warehouse": "WH10",
        "zone": "ST01",
        "aisle": "A02",
        "rack": "R04",
        "section": "S02",
        "level": "L03",
        "position": "P03",
        "structured": True,
    }


def test_location_rejects_mismatched_hierarchy(client):
    location = create_address(client)
    aisle = client.post(
        "/api/aisles",
        json={"zone_id": location["zone_id"], "code": "A03", "name": "Проход 3"},
    ).json()
    rack = client.post(
        "/api/racks",
        json={"aisle_id": aisle["id"], "code": "R01", "name": "Чужой стеллаж"},
    ).json()
    response = client.post(
        "/api/locations",
        json={
            "warehouse_id": location["warehouse_id"],
            "zone_id": location["zone_id"],
            "aisle_id": location["aisle_id"],
            "rack_id": rack["id"],
            "section_id": location["section_id"],
            "level_id": location["level_id"],
            "position_code": "P04",
            "kind": "storage",
        },
    )
    assert response.status_code == 400
    assert response.json()["detail"] == "rack belongs to another aisle"


def test_location_import_creates_complete_address_hierarchy(client, db):
    content = (
        "warehouse_code;warehouse_name;zone_code;zone_name;aisle_code;rack_code;"
        "section_code;level_code;position_code;name;kind;capacity_units\n"
        "WH20;Импортный склад;ST01;Хранение;A01;R02;S03;L04;P05;Позиция 5;Хранение;1\n"
    )
    response = client.post(
        "/api/import/apply/locations",
        files={"file": ("locations.csv", content.encode(), "text/csv")},
    )
    assert response.status_code == 200, response.text
    assert response.json()["created"] == 1

    location = db.scalar(select(Location).where(Location.code == "WH20-ST01-A01-R02-S03-L04-P05"))
    assert location is not None
    assert db.get(Aisle, location.aisle_id).code == "A01"
    assert db.get(Rack, location.rack_id).code == "R02"
    assert db.get(RackSection, location.section_id).code == "S03"
    assert db.get(RackLevel, location.level_id).code == "L04"


def test_sandbox_reset_recreates_map_and_address_hierarchy(client, db):
    catalog = client.post(
        "/api/demo/catalog",
        json={
            "warehouse_code": "WH01",
            "warehouse_name": "Основной склад",
            "storage_locations": 2,
            "actor": "tester",
        },
    )
    assert catalog.status_code == 200, catalog.text
    setup = client.post("/api/maps/setup", json={"actor": "tester"})
    assert setup.status_code == 200, setup.text

    before = client.get("/api/warehouses/WH02/address-tree").json()
    before_racks = before["zones"][0]["aisles"][0]["racks"]
    assert [rack["code"] for rack in before_racks] == ["R01", "R02"]

    reset = client.post("/api/maps/WH02/reset", json={"actor": "tester"})
    assert reset.status_code == 200, reset.text
    assert reset.json()["stats"]["locations"] == 8

    after = client.get("/api/warehouses/WH02/address-tree").json()
    after_racks = after["zones"][0]["aisles"][0]["racks"]
    assert [rack["code"] for rack in after_racks] == ["R01", "R02"]
    assert db.scalar(select(Location).where(Location.code == "WH02-ST01-A01-R01-S01-L01-P01"))
