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
from app.models.entities import LogisticUnitType, Product, ProductPackaging, UnitOfMeasure
from app.schemas import LogisticUnitContentCreate, LogisticUnitCreate, ProductCreate, ProductPackagingCreate
from app.services import (
    add_logistic_unit_content,
    create_logistic_unit,
    create_product,
    create_product_packaging,
    ensure_reference_catalogs,
    logistic_unit_payload,
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


def product(db, code: str, uom_code: str) -> Product:
    ensure_reference_catalogs(db)
    uom = reference(db, UnitOfMeasure, uom_code)
    return create_product(
        db,
        ProductCreate(code=code, name=f"Номенклатура {code}", base_uom_id=uom.id),
    )


def test_product_packaging_converts_to_product_base_unit(db):
    item = product(db, "PEN-001", "PCS")
    pieces = reference(db, UnitOfMeasure, "PCS")

    packaging = create_product_packaging(
        db,
        ProductPackagingCreate(
            product_id=item.id,
            code="box-12",
            name="Коробка 12 штук",
            quantity=Decimal("12"),
            uom_id=pieces.id,
            barcode="4600000000012",
        ),
    )

    assert packaging.code == "BOX-12"
    assert packaging.quantity == Decimal("12")
    assert packaging.base_quantity == Decimal("12")
    assert packaging.barcode == "4600000000012"


def test_mass_packaging_and_logistic_content_are_normalized_to_kilograms(db):
    item = product(db, "CHEM-001", "KG")
    grams = reference(db, UnitOfMeasure, "G")
    packaging = create_product_packaging(
        db,
        ProductPackagingCreate(
            product_id=item.id,
            code="BAG-1000G",
            name="Пакет 1000 граммов",
            quantity=Decimal("1000"),
            uom_id=grams.id,
            barcode="CHEM-001-BAG",
        ),
    )
    assert packaging.base_quantity == Decimal("1.000")

    box_type = reference(db, LogisticUnitType, "BOX")
    unit = create_logistic_unit(
        db,
        LogisticUnitCreate(type_id=box_type.id, uid="BOX-MASS-001", actor="test"),
    )
    add_logistic_unit_content(
        db,
        unit.uid,
        LogisticUnitContentCreate(
            product_id=item.id,
            quantity=Decimal("5000"),
            uom_id=grams.id,
            actor="test",
        ),
    )

    content = logistic_unit_payload(db, unit)["contents"][0]
    assert content["quantity"] == Decimal("5.000000")
    assert content["uom_code"] == "KG"


def test_packaging_rejects_incompatible_unit_and_precision_loss(db):
    pieces_item = product(db, "GLOVES-001", "PCS")
    kilograms = reference(db, UnitOfMeasure, "KG")
    pieces = reference(db, UnitOfMeasure, "PCS")

    with pytest.raises(HTTPException, match="incompatible with the product base unit"):
        create_product_packaging(
            db,
            ProductPackagingCreate(
                product_id=pieces_item.id,
                code="BAD-KG",
                name="Несовместимая упаковка",
                quantity=Decimal("1"),
                uom_id=kilograms.id,
            ),
        )

    with pytest.raises(HTTPException, match="exceeds product base unit precision"):
        create_product_packaging(
            db,
            ProductPackagingCreate(
                product_id=pieces_item.id,
                code="HALF",
                name="Половина штуки",
                quantity=Decimal("0.5"),
                uom_id=pieces.id,
            ),
        )


def test_packaging_barcode_is_globally_unique(db):
    first_product = product(db, "ITEM-001", "PCS")
    second_product = product(db, "ITEM-002", "PCS")
    pieces = reference(db, UnitOfMeasure, "PCS")
    create_product_packaging(
        db,
        ProductPackagingCreate(
            product_id=first_product.id,
            code="EACH",
            name="Штука",
            quantity=Decimal("1"),
            uom_id=pieces.id,
            barcode="SHARED-CODE",
        ),
    )

    with pytest.raises(HTTPException, match="code or barcode already exists"):
        create_product_packaging(
            db,
            ProductPackagingCreate(
                product_id=second_product.id,
                code="EACH",
                name="Штука",
                quantity=Decimal("1"),
                uom_id=pieces.id,
                barcode="SHARED-CODE",
            ),
        )


def test_product_packaging_api_creates_and_resolves_barcode(db):
    item = product(db, "API-ITEM", "L")
    litres = reference(db, UnitOfMeasure, "L")

    def override_db():
        yield db

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[api_routes.get_db] = override_db
    try:
        with TestClient(app) as client:
            created = client.post(
                "/api/product-packagings",
                json={
                    "product_id": item.id,
                    "code": "CAN-20",
                    "name": "Канистра 20 литров",
                    "quantity": "20",
                    "uom_id": litres.id,
                    "barcode": "API-ITEM-CAN-20",
                },
            )
            assert created.status_code == 200
            assert created.json()["base_quantity"] == "20.00000000"

            resolved = client.get(
                "/api/product-packagings",
                params={"barcode": "API-ITEM-CAN-20"},
            )
            assert resolved.status_code == 200
            assert len(resolved.json()) == 1
            assert resolved.json()[0]["product_id"] == item.id
            assert db.scalar(select(ProductPackaging).where(ProductPackaging.barcode == "API-ITEM-CAN-20"))

            schema = client.get("/openapi.json").json()
            summary = schema["paths"]["/api/product-packagings"]["post"]["summary"]
            assert "Создать товарную упаковку" in summary
    finally:
        app.dependency_overrides.clear()
