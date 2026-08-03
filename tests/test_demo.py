from decimal import Decimal

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.session import Base, get_db
from app.main import app
from app.models.entities import (
    LogisticUnit,
    LogisticUnitContent,
    OperationEvent,
)
from app.models.enums import LogisticUnitStatus


def test_universal_demo_generator_is_additive_and_supports_direct_content():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    testing_session = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    db = testing_session()

    def override_db():
        yield db

    app.dependency_overrides[get_db] = override_db
    try:
        with TestClient(app) as client:
            first = client.post(
                "/api/demo/logistic-units",
                json={
                    "warehouse_code": "DEMO",
                    "warehouse_name": "Демонстрационный склад",
                    "storage_locations": 1,
                    "quantity": 2,
                    "child_units_per_parent": 2,
                    "place_to_empty_locations": True,
                    "actor": "test-demo",
                },
            )
            assert first.status_code == 200, first.text
            first_result = first.json()
            assert first_result["created_products"] == 3
            assert first_result["created_batches"] == 3
            assert first_result["created_warehouses"] == 1
            assert first_result["created_locations"] == 2
            assert first_result["created_logistic_units"] == 6
            assert first_result["created_child_units"] == 4
            assert first_result["placed_logistic_units"] == 1
            assert first_result["waiting_logistic_units"] == 1
            assert len(set(first_result["logistic_unit_uids"])) == 2

            second = client.post(
                "/api/demo/logistic-units",
                json={
                    "warehouse_code": "DEMO",
                    "warehouse_name": "Демонстрационный склад",
                    "storage_locations": 1,
                    "quantity": 1,
                    "child_units_per_parent": 2,
                    "place_to_empty_locations": False,
                    "actor": "test-demo",
                },
            )
            assert second.status_code == 200, second.text
            second_result = second.json()
            assert second_result["created_products"] == 0
            assert second_result["created_batches"] == 0
            assert second_result["created_warehouses"] == 0
            assert second_result["created_locations"] == 0
            assert second_result["created_logistic_units"] == 3
            assert second_result["placed_logistic_units"] == 0
            assert second_result["waiting_logistic_units"] == 1

            ibc = client.post(
                "/api/demo/logistic-units",
                json={
                    "warehouse_code": "DEMO",
                    "warehouse_name": "Демонстрационный склад",
                    "storage_locations": 1,
                    "quantity": 1,
                    "parent_type_code": "IBC",
                    "child_type_code": None,
                    "child_units_per_parent": 1,
                    "content_uom_code": "L",
                    "content_quantity": "1000",
                    "place_to_empty_locations": False,
                    "actor": "test-demo",
                },
            )
            assert ibc.status_code == 200, ibc.text
            ibc_result = ibc.json()
            assert ibc_result["created_products"] == 1
            assert ibc_result["created_batches"] == 1
            assert ibc_result["created_logistic_units"] == 1
            assert ibc_result["created_child_units"] == 0
            assert ibc_result["parent_type_code"] == "IBC"
            assert ibc_result["child_type_code"] is None
            assert ibc_result["content_uom_code"] == "L"

            incompatible = client.post(
                "/api/demo/logistic-units",
                json={
                    "warehouse_code": "DEMO",
                    "warehouse_name": "Демонстрационный склад",
                    "storage_locations": 1,
                    "quantity": 1,
                    "parent_type_code": "PALLET",
                    "child_type_code": "IBC",
                    "child_units_per_parent": 1,
                    "content_uom_code": "L",
                    "content_quantity": "1000",
                    "place_to_empty_locations": False,
                    "actor": "test-demo",
                },
            )
            assert incompatible.status_code == 400
            assert "not allowed" in incompatible.json()["detail"]

        assert db.scalar(select(func.count(LogisticUnit.id))) == 10

        parents = list(
            db.scalars(
                select(LogisticUnit)
                .where(LogisticUnit.parent_unit_id.is_(None))
                .order_by(LogisticUnit.id)
            )
        )
        children = list(
            db.scalars(
                select(LogisticUnit)
                .where(LogisticUnit.parent_unit_id.is_not(None))
                .order_by(LogisticUnit.id)
            )
        )
        assert len(parents) == 4
        assert len(children) == 6
        assert [parent.status for parent in parents].count(LogisticUnitStatus.AVAILABLE) == 1
        assert [parent.status for parent in parents].count(LogisticUnitStatus.CLOSED) == 3

        for child in children:
            content = db.scalar(
                select(LogisticUnitContent).where(
                    LogisticUnitContent.logistic_unit_id == child.id
                )
            )
            assert content.quantity == Decimal("24")

        ibc_parent = next(parent for parent in parents if parent.type.code == "IBC")
        ibc_content = db.scalar(
            select(LogisticUnitContent).where(
                LogisticUnitContent.logistic_unit_id == ibc_parent.id
            )
        )
        assert ibc_content.quantity == Decimal("1000")

        assert db.scalar(
            select(func.count(OperationEvent.id)).where(
                OperationEvent.operation == "demo_logistic_units_generated"
            )
        ) == 3
    finally:
        app.dependency_overrides.clear()
        db.close()
