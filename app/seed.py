from datetime import date

from sqlalchemy import select

from app.core.constants import (
    CODE_SEPARATOR,
    DEFAULT_UNIT,
    DEFAULT_WAREHOUSE_CODE,
    DEFAULT_WAREHOUSE_NAME,
    RECEIVING_LOCATION_SUFFIX,
    RECEIVING_ZONE_CODE,
    RECEIVING_ZONE_NAME,
    STORAGE_LOCATION_PATTERN,
    STORAGE_ZONE_CODE,
    STORAGE_ZONE_NAME,
)
from app.db.session import SessionLocal, init_db
from app.models.enums import LocationKind, UserRole
from app.schemas import BatchCreate, LocationCreate, ProductCreate, UserCreate, WarehouseCreate, ZoneCreate
from app.services import create_batch, create_location, create_product, create_user, create_warehouse, create_zone
from app.models.entities import Product, User, Warehouse


def run() -> None:
    init_db()
    db = SessionLocal()
    try:
        if db.scalar(select(User).where(User.username == "admin")) is None:
            create_user(db, UserCreate(username="admin", full_name="Администратор WMS", role=UserRole.ADMIN))

        if db.scalar(select(Product).where(Product.code == "ICE-VAN-080")) is None:
            product = create_product(
                db,
                ProductCreate(
                    code="ICE-VAN-080",
                    name="Эскимо ванильное 80 г",
                    unit=DEFAULT_UNIT,
                    shelf_life_days=365,
                ),
            )
            create_batch(
                db,
                BatchCreate(
                    product_id=product.id,
                    batch_number="20260721-1",
                    production_date=date(2026, 7, 21),
                    expiry_date=date(2027, 7, 21),
                ),
            )

        if db.scalar(select(Product).where(Product.code == "ICE-CHO-100")) is None:
            create_product(
                db,
                ProductCreate(
                    code="ICE-CHO-100",
                    name="Мороженое шоколадное 100 г",
                    unit=DEFAULT_UNIT,
                    shelf_life_days=365,
                ),
            )

        if db.scalar(select(Warehouse).where(Warehouse.code == DEFAULT_WAREHOUSE_CODE)) is None:
            warehouse = create_warehouse(db, WarehouseCreate(code=DEFAULT_WAREHOUSE_CODE, name=DEFAULT_WAREHOUSE_NAME, city="Москва"))
            receiving = create_zone(
                db,
                ZoneCreate(
                    warehouse_id=warehouse.id,
                    code=RECEIVING_ZONE_CODE,
                    name=RECEIVING_ZONE_NAME,
                    kind=LocationKind.RECEIVING,
                ),
            )
            storage = create_zone(
                db,
                ZoneCreate(
                    warehouse_id=warehouse.id,
                    code=STORAGE_ZONE_CODE,
                    name=STORAGE_ZONE_NAME,
                    kind=LocationKind.STORAGE,
                ),
            )
            create_location(
                db,
                LocationCreate(
                    warehouse_id=warehouse.id,
                    zone_id=receiving.id,
                    code=f"{warehouse.code}{CODE_SEPARATOR}{RECEIVING_ZONE_CODE}{CODE_SEPARATOR}{RECEIVING_LOCATION_SUFFIX}",
                    name="Приемка логистических единиц",
                    kind=LocationKind.RECEIVING,
                    capacity_units=4,
                ),
            )
            for idx in range(1, 6):
                create_location(
                    db,
                    LocationCreate(
                        warehouse_id=warehouse.id,
                        zone_id=storage.id,
                        code=f"{warehouse.code}{CODE_SEPARATOR}{STORAGE_ZONE_CODE}{CODE_SEPARATOR}{STORAGE_LOCATION_PATTERN.format(index=idx)}",
                        name=f"Место хранения {idx}",
                        kind=LocationKind.STORAGE,
                        capacity_units=1,
                    ),
                )
    finally:
        db.close()


if __name__ == "__main__":
    run()
    print("Seed data loaded")
