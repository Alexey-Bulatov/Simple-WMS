from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.entities import (
    Batch,
    LogisticUnit,
    LogisticUnitType,
    Location,
    Product,
    UnitOfMeasure,
    Warehouse,
)
from app.models.enums import LocationKind
from app.schemas import (
    BatchCreate,
    DemoCatalogRequest,
    DemoLogisticUnitsRequest,
    LogisticUnitAcceptRequest,
    LogisticUnitActionRequest,
    LogisticUnitChildRequest,
    LogisticUnitContentCreate,
    LogisticUnitCreate,
    LogisticUnitLocationRequest,
    ProductCreate,
)
from app.services import (
    accept_logistic_unit,
    add_logistic_unit_child,
    add_logistic_unit_content,
    bad_request,
    close_logistic_unit,
    create_batch,
    create_event,
    create_logistic_unit,
    create_product,
    ensure_demo_catalog,
    ensure_reference_catalogs,
    logistic_location_occupied_count,
    not_found,
    place_logistic_unit,
    seed_batch_dates,
)


def _reference(db: Session, model, code: str):
    item = db.scalar(select(model).where(model.code == code))
    if item is None:
        raise not_found(code.lower())
    return item


def _empty_storage_locations(db: Session, warehouse_id: int) -> list[Location]:
    locations = list(
        db.scalars(
            select(Location)
            .where(
                Location.warehouse_id == warehouse_id,
                Location.kind == LocationKind.STORAGE,
                Location.is_active.is_(True),
            )
            .order_by(Location.code)
        )
    )
    return [
        location
        for location in locations
        if logistic_location_occupied_count(db, location.id) < location.capacity_units
    ]


def _batch_for_content_unit(
    db: Session,
    *,
    catalog_batch_ids: list[int],
    requested_batch_id: int | None,
    content_uom: UnitOfMeasure,
) -> tuple[Batch, Product, bool, bool]:
    if requested_batch_id is not None:
        batch = db.get(Batch, requested_batch_id)
        if batch is None:
            raise not_found("batch")
        product = db.get(Product, batch.product_id)
        if product is None:
            raise not_found("product")
        base_uom = db.get(UnitOfMeasure, product.base_uom_id) if product.base_uom_id else None
        if base_uom is not None and base_uom.dimension != content_uom.dimension:
            raise bad_request("content_uom_code is incompatible with the selected batch")
        return batch, product, False, False

    for batch in db.scalars(
        select(Batch).where(Batch.id.in_(catalog_batch_ids)).order_by(Batch.id)
    ):
        product = db.get(Product, batch.product_id)
        base_uom = db.get(UnitOfMeasure, product.base_uom_id) if product and product.base_uom_id else None
        if product is not None and base_uom is not None and base_uom.dimension == content_uom.dimension:
            return batch, product, False, False

    product_code = f"DEMO-{content_uom.code}"
    product = db.scalar(select(Product).where(Product.code == product_code))
    product_created = product is None
    if product is None:
        product = create_product(
            db,
            ProductCreate(
                code=product_code,
                name=f"Демонстрационный товар, {content_uom.name.lower()}",
                unit=content_uom.symbol,
                base_uom_id=content_uom.id,
                shelf_life_days=365,
            ),
        )
    batch_number = f"DEMO-{content_uom.code}-001"
    batch = db.scalar(
        select(Batch).where(
            Batch.product_id == product.id,
            Batch.batch_number == batch_number,
        )
    )
    batch_created = batch is None
    if batch is None:
        production_date, expiry_date = seed_batch_dates()
        batch = create_batch(
            db,
            BatchCreate(
                product_id=product.id,
                batch_number=batch_number,
                production_date=production_date,
                expiry_date=expiry_date,
            ),
        )
    return batch, product, product_created, batch_created


def generate_demo_logistic_units(
    db: Session,
    payload: DemoLogisticUnitsRequest,
) -> dict:
    ensure_reference_catalogs(db)
    parent_type: LogisticUnitType = _reference(
        db,
        LogisticUnitType,
        payload.parent_type_code.strip().upper(),
    )
    child_type = (
        _reference(db, LogisticUnitType, payload.child_type_code)
        if payload.child_type_code
        else None
    )
    content_uom: UnitOfMeasure = _reference(
        db,
        UnitOfMeasure,
        payload.content_uom_code.strip().upper(),
    )
    if child_type is None and not parent_type.can_contain_goods:
        raise bad_request("parent logistic unit type cannot contain goods directly")
    if child_type is not None and not parent_type.can_contain_units:
        raise bad_request("parent logistic unit type cannot contain child units")
    if child_type is not None and not child_type.can_contain_goods:
        raise bad_request("child logistic unit type cannot contain goods directly")
    if (
        child_type is not None
        and child_type.id not in parent_type.allowed_child_type_ids
    ):
        raise bad_request("child logistic unit type is not allowed for this parent")

    selected_content = None
    if payload.batch_id is not None:
        selected_content = _batch_for_content_unit(
            db,
            catalog_batch_ids=[],
            requested_batch_id=payload.batch_id,
            content_uom=content_uom,
        )

    catalog = ensure_demo_catalog(
        db,
        DemoCatalogRequest(
            warehouse_code=payload.warehouse_code.strip().upper(),
            warehouse_name=payload.warehouse_name,
            storage_locations=payload.storage_locations,
            actor=payload.actor,
        ),
    )
    warehouse = db.scalar(
        select(Warehouse).where(Warehouse.code == payload.warehouse_code.strip().upper())
    )
    if warehouse is None:
        raise not_found("warehouse")

    batch, product, product_created, batch_created = selected_content or _batch_for_content_unit(
        db,
        catalog_batch_ids=catalog["batch_ids"],
        requested_batch_id=None,
        content_uom=content_uom,
    )
    if product.id not in catalog["product_ids"]:
        catalog["product_ids"].append(product.id)
    if batch.id not in catalog["batch_ids"]:
        catalog["batch_ids"].append(batch.id)
    catalog["created_products"] += int(product_created)
    catalog["created_batches"] += int(batch_created)

    result = {
        **catalog,
        "created_logistic_units": 0,
        "created_child_units": 0,
        "placed_logistic_units": 0,
        "waiting_logistic_units": 0,
        "logistic_unit_uids": [],
        "parent_type_code": parent_type.code,
        "child_type_code": child_type.code if child_type else None,
        "content_uom_code": content_uom.code,
        "content_quantity": payload.content_quantity,
    }

    for _ in range(payload.quantity):
        free_locations = (
            _empty_storage_locations(db, warehouse.id)
            if payload.place_to_empty_locations
            else []
        )
        parent: LogisticUnit = create_logistic_unit(
            db,
            LogisticUnitCreate(type_id=parent_type.id, actor=payload.actor),
        )
        if free_locations:
            receiving = db.scalar(
                select(Location)
                .where(
                    Location.warehouse_id == warehouse.id,
                    Location.kind == LocationKind.RECEIVING,
                    Location.is_active.is_(True),
                )
                .order_by(Location.code)
            )
            if receiving is None:
                raise bad_request("demo warehouse has no receiving location")
            accept_logistic_unit(
                db,
                parent.uid,
                LogisticUnitAcceptRequest(
                    location_code=receiving.code,
                    actor=payload.actor,
                    reason="demo generation",
                ),
            )

        if child_type is None:
            add_logistic_unit_content(
                db,
                parent.uid,
                LogisticUnitContentCreate(
                    product_id=product.id,
                    batch_id=batch.id,
                    quantity=payload.content_quantity,
                    uom_id=content_uom.id,
                    actor=payload.actor,
                ),
            )
        else:
            for _ in range(payload.child_units_per_parent):
                child = create_logistic_unit(
                    db,
                    LogisticUnitCreate(type_id=child_type.id, actor=payload.actor),
                )
                add_logistic_unit_content(
                    db,
                    child.uid,
                    LogisticUnitContentCreate(
                        product_id=product.id,
                        batch_id=batch.id,
                        quantity=payload.content_quantity,
                        uom_id=content_uom.id,
                        actor=payload.actor,
                    ),
                )
                close_logistic_unit(
                    db,
                    child.uid,
                    LogisticUnitActionRequest(actor=payload.actor, reason="demo generation"),
                )
                add_logistic_unit_child(
                    db,
                    parent.uid,
                    LogisticUnitChildRequest(child_uid=child.uid, actor=payload.actor),
                )
                result["created_logistic_units"] += 1
                result["created_child_units"] += 1

        close_logistic_unit(
            db,
            parent.uid,
            LogisticUnitActionRequest(actor=payload.actor, reason="demo generation"),
        )
        result["created_logistic_units"] += 1
        result["logistic_unit_uids"].append(parent.uid)

        if free_locations:
            place_logistic_unit(
                db,
                parent.uid,
                LogisticUnitLocationRequest(
                    location_code=free_locations[0].code,
                    actor=payload.actor,
                    reason="demo auto placement",
                ),
            )
            result["placed_logistic_units"] += 1
        else:
            result["waiting_logistic_units"] += 1

    create_event(
        db,
        operation="demo_logistic_units_generated",
        object_type="warehouse",
        object_uid=warehouse.code,
        actor=payload.actor,
        after={
            "quantity": payload.quantity,
            "child_units_per_parent": payload.child_units_per_parent,
            "parent_type_code": parent_type.code,
            "child_type_code": child_type.code if child_type else None,
            "content_uom_code": content_uom.code,
            "content_quantity": str(payload.content_quantity),
            "created_logistic_units": result["created_logistic_units"],
            "placed_logistic_units": result["placed_logistic_units"],
            "waiting_logistic_units": result["waiting_logistic_units"],
            "batch_number": batch.batch_number,
        },
    )
    db.commit()
    return result
