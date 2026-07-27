from decimal import Decimal

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api import routes as api_routes
from app.db.session import Base, get_db
from app.main import app
from app.models.entities import EquipmentProfile, LogisticUnitType, UnitOfMeasure
from app.models.enums import EquipmentConnection, EquipmentKind, MeasurementDimension
from app.schemas import EquipmentProfileCreate, LogisticUnitTypeCreate, ProductCreate, UnitOfMeasureCreate
from app.services import (
    create_equipment_profile,
    create_logistic_unit_type,
    create_product,
    create_unit_of_measure,
    ensure_reference_catalogs,
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


def test_reference_catalogs_seed_defaults_and_allowed_nesting(db):
    first = ensure_reference_catalogs(db)
    second = ensure_reference_catalogs(db)

    assert first == {"units_of_measure": 8, "logistic_unit_types": 8}
    assert second == first

    pcs = db.scalar(select(UnitOfMeasure).where(UnitOfMeasure.code == "PCS"))
    pallet = db.scalar(select(LogisticUnitType).where(LogisticUnitType.code == "PALLET"))
    box = db.scalar(select(LogisticUnitType).where(LogisticUnitType.code == "BOX"))

    assert pcs.symbol == "шт"
    assert pcs.is_base is True
    assert box.id in pallet.allowed_child_type_ids


def test_custom_unit_and_logistic_type_can_be_created(db):
    ensure_reference_catalogs(db)
    kg = db.scalar(select(UnitOfMeasure).where(UnitOfMeasure.code == "KG"))
    box = db.scalar(select(LogisticUnitType).where(LogisticUnitType.code == "BOX"))

    tonne = create_unit_of_measure(
        db,
        UnitOfMeasureCreate(
            code="t",
            name="Тонна",
            symbol="т",
            dimension=MeasurementDimension.MASS,
            decimal_precision=3,
            factor_to_base=Decimal("1000"),
        ),
    )
    bundle = create_logistic_unit_type(
        db,
        LogisticUnitTypeCreate(
            code="bundle",
            name="Связка",
            identifier_prefix="bdl",
            tare_weight=Decimal("0.25"),
            tare_weight_uom_id=kg.id,
            can_contain_goods=False,
            can_contain_units=True,
            allowed_child_type_ids=[box.id],
        ),
    )

    assert tonne.code == "T"
    assert tonne.factor_to_base == Decimal("1000")
    assert bundle.code == "BUNDLE"
    assert bundle.identifier_prefix == "BDL"
    assert bundle.allowed_child_type_ids == [box.id]


def test_second_base_unit_and_non_mass_weight_unit_are_rejected(db):
    ensure_reference_catalogs(db)
    litre = db.scalar(select(UnitOfMeasure).where(UnitOfMeasure.code == "L"))

    with pytest.raises(HTTPException, match="base unit already exists"):
        create_unit_of_measure(
            db,
            UnitOfMeasureCreate(
                code="ITEM",
                name="Единица",
                symbol="ед",
                dimension=MeasurementDimension.QUANTITY,
                is_base=True,
            ),
        )

    with pytest.raises(HTTPException, match="must reference a mass unit"):
        create_logistic_unit_type(
            db,
            LogisticUnitTypeCreate(
                code="BAD",
                name="Некорректная тара",
                identifier_prefix="BAD",
                tare_weight=Decimal("1"),
                tare_weight_uom_id=litre.id,
            ),
        )


def test_product_links_to_reference_unit_without_breaking_legacy_unit(db):
    ensure_reference_catalogs(db)
    litre = db.scalar(select(UnitOfMeasure).where(UnitOfMeasure.code == "L"))

    explicit = create_product(
        db,
        ProductCreate(
            code="CHEM-001",
            name="Жидкий реагент",
            base_uom_id=litre.id,
        ),
    )
    legacy = create_product(
        db,
        ProductCreate(
            code="LEGACY-001",
            name="Старый товар",
            unit="уп.",
        ),
    )

    assert explicit.base_uom_id == litre.id
    assert explicit.unit == "л"
    assert legacy.base_uom_id is None
    assert legacy.unit == "уп."


def test_reference_catalog_api_create_and_list(db):
    def override_db():
        yield db

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[api_routes.get_db] = override_db
    try:
        client = TestClient(app)
        unit_response = client.post(
            "/api/units-of-measure",
            json={
                "code": "CM",
                "name": "Сантиметр",
                "symbol": "см",
                "dimension": "length",
                "decimal_precision": 2,
                "factor_to_base": "0.01",
                "is_base": False,
            },
        )
        assert unit_response.status_code == 200
        assert unit_response.json()["code"] == "CM"

        units = client.get("/api/units-of-measure")
        assert units.status_code == 200
        assert any(row["code"] == "CM" for row in units.json())

        box = db.scalar(select(LogisticUnitType).where(LogisticUnitType.code == "BOX"))
        type_response = client.post(
            "/api/logistic-unit-types",
            json={
                "code": "BUNDLE",
                "name": "Связка",
                "identifier_prefix": "BDL",
                "can_contain_goods": False,
                "can_contain_units": True,
                "allowed_child_type_ids": [box.id],
            },
        )
        assert type_response.status_code == 200
        assert type_response.json()["allowed_child_type_ids"] == [box.id]

        types = client.get("/api/logistic-unit-types")
        assert types.status_code == 200
        assert any(row["code"] == "BUNDLE" for row in types.json())
    finally:
        app.dependency_overrides.clear()


def test_equipment_profile_stores_network_connection_and_switches_default(db):
    first = create_equipment_profile(
        db,
        EquipmentProfileCreate(
            code="ATOL_TT42",
            name="Термопринтер 47x25",
            device_kind=EquipmentKind.PRINTER,
            manufacturer="АТОЛ",
            model="ТТ42 / HPRT XT100",
            connection_type=EquipmentConnection.RAW_TCP,
            host="192.168.10.204",
            port=9100,
            driver_code="tspl_bitmap_47x25",
            parameters={"label_width_mm": 47, "label_height_mm": 25},
            is_default=True,
        ),
    )
    second = create_equipment_profile(
        db,
        EquipmentProfileCreate(
            code="PDF_A4",
            name="Обычная печать PDF",
            device_kind=EquipmentKind.PRINTER,
            connection_type=EquipmentConnection.PDF,
            driver_code="pdf",
            is_default=True,
        ),
    )

    db.refresh(first)
    assert first.is_default is False
    assert second.is_default is True
    assert second.connection_type == "pdf"


def test_equipment_profile_api_lists_by_kind(db):
    def override_db():
        yield db

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[api_routes.get_db] = override_db
    try:
        client = TestClient(app)
        response = client.post(
            "/api/equipment-profiles",
            json={
                "code": "SCALE_01",
                "name": "Весы у приёмки",
                "device_kind": "scale",
                "manufacturer": "Demo",
                "model": "RS-232",
                "connection_type": "serial",
                "serial_device": "/dev/ttyUSB0",
                "driver_code": "generic_serial_scale",
            },
        )
        assert response.status_code == 200
        profile = response.json()

        updated = client.put(
            f"/api/equipment-profiles/{profile['id']}",
            json={
                **profile,
                "name": "Весы у отгрузки",
                "serial_device": "/dev/ttyUSB1",
                "is_active": True,
            },
        )
        assert updated.status_code == 200
        assert updated.json()["name"] == "Весы у отгрузки"
        assert updated.json()["serial_device"] == "/dev/ttyUSB1"

        listed = client.get("/api/equipment-profiles", params={"device_kind": "scale"})
        assert listed.status_code == 200
        assert [row["code"] for row in listed.json()] == ["SCALE_01"]
        assert db.scalar(select(EquipmentProfile).where(EquipmentProfile.code == "SCALE_01"))
    finally:
        app.dependency_overrides.clear()
