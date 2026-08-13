from decimal import Decimal

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.models.entities import Product, ProductPackaging, StockPosition, UnitOfMeasure
from app.stock import stock_position_payload


def _match_reason(
    product: Product,
    packagings: list[ProductPackaging],
    serial_numbers: set[str],
    query: str,
) -> str:
    normalized = query.upper()
    if product.code.upper() == normalized:
        return "product_code"
    if normalized in serial_numbers:
        return "serial_number"
    if any(item.barcode and item.barcode.upper() == normalized for item in packagings):
        return "barcode"
    if any(item.code.upper() == normalized for item in packagings):
        return "packaging_code"
    if product.code.upper().startswith(normalized):
        return "product_code"
    return "name"


def search_stock(
    db: Session,
    query: str,
    *,
    warehouse_scope: set[int] | None,
    warehouse_id: int | None = None,
    active_only: bool = True,
    limit: int = 20,
) -> dict:
    term = query.strip()
    normalized = term.upper()
    contains = f"%{term}%"

    product_query = select(Product.id).where(
        or_(
            Product.code.ilike(contains),
            Product.name.ilike(contains),
        )
    )
    packaging_query = select(ProductPackaging.product_id).where(
        or_(
            ProductPackaging.code.ilike(contains),
            ProductPackaging.name.ilike(contains),
            ProductPackaging.barcode.ilike(contains),
        )
    )
    serial_query = select(StockPosition.product_id).where(
        StockPosition.serial_number.ilike(contains)
    )
    product_ids = set(db.scalars(product_query))
    product_ids.update(db.scalars(packaging_query))
    product_ids.update(db.scalars(serial_query))
    if not product_ids and any(ord(character) > 127 for character in term):
        folded = term.casefold()
        product_ids.update(
            product.id
            for product in db.scalars(select(Product))
            if folded in product.code.casefold() or folded in product.name.casefold()
        )
        product_ids.update(
            packaging.product_id
            for packaging in db.scalars(select(ProductPackaging))
            if any(
                folded in value.casefold()
                for value in (
                    packaging.code,
                    packaging.name,
                    packaging.barcode or "",
                )
            )
        )
    if not product_ids:
        return {"query": term, "result": "none", "items": []}

    products_query = select(Product).where(Product.id.in_(product_ids))
    if active_only:
        products_query = products_query.where(Product.is_active.is_(True))
    products = list(db.scalars(products_query))
    items: list[dict] = []
    for product in products:
        packagings = list(
            db.scalars(
                select(ProductPackaging)
                .where(ProductPackaging.product_id == product.id)
                .order_by(ProductPackaging.code)
            )
        )
        positions = list(
            db.scalars(
                select(StockPosition)
                .where(StockPosition.product_id == product.id)
                .order_by(StockPosition.id)
            )
        )
        position_payloads = [stock_position_payload(db, item) for item in positions]
        position_payloads = [
            item
            for item in position_payloads
            if (warehouse_scope is None or item["warehouse_id"] in warehouse_scope)
            and (warehouse_id is None or item["warehouse_id"] == warehouse_id)
        ]
        serial_numbers = {
            item["serial_number"].upper()
            for item in position_payloads
            if item["serial_number"]
        }
        reason = _match_reason(product, packagings, serial_numbers, term)
        base_uom = db.get(UnitOfMeasure, product.base_uom_id) if product.base_uom_id else None
        packaging_payloads = []
        for packaging in packagings:
            uom = db.get(UnitOfMeasure, packaging.uom_id)
            packaging_payloads.append(
                {
                    "id": packaging.id,
                    "code": packaging.code,
                    "name": packaging.name,
                    "barcode": packaging.barcode,
                    "quantity": packaging.quantity,
                    "uom_id": packaging.uom_id,
                    "uom_code": uom.code,
                    "uom_symbol": uom.symbol,
                    "base_quantity": packaging.base_quantity,
                    "matched": any(
                        value and value.upper() == normalized
                        for value in (packaging.code, packaging.barcode)
                    ),
                }
            )
        position_payloads.sort(
            key=lambda item: (
                item["warehouse_code"] or "",
                item["location_code"] or "",
                item["root_logistic_unit_uid"] or "",
                item["id"],
            )
        )
        items.append(
            {
                "product_id": product.id,
                "product_code": product.code,
                "product_name": product.name,
                "is_active": product.is_active,
                "base_uom_id": product.base_uom_id,
                "base_uom_code": base_uom.code if base_uom else None,
                "base_uom_symbol": base_uom.symbol if base_uom else None,
                "base_uom_dimension": base_uom.dimension if base_uom else None,
                "accountability_period_days": product.accountability_period_days,
                "total_quantity": sum(
                    (item["quantity"] for item in position_payloads), Decimal("0")
                ),
                "available_quantity": sum(
                    (item["available_quantity"] for item in position_payloads),
                    Decimal("0"),
                ),
                "reserved_quantity": sum(
                    (item["reserved_quantity"] for item in position_payloads),
                    Decimal("0"),
                ),
                "quarantine_quantity": sum(
                    (item["quarantine_quantity"] for item in position_payloads),
                    Decimal("0"),
                ),
                "blocked_quantity": sum(
                    (item["blocked_quantity"] for item in position_payloads),
                    Decimal("0"),
                ),
                "in_transit_quantity": sum(
                    (item["in_transit_quantity"] for item in position_payloads),
                    Decimal("0"),
                ),
                "match_reason": reason,
                "packagings": packaging_payloads,
                "positions": position_payloads,
            }
        )

    reason_order = {
        "product_code": 0,
        "barcode": 1,
        "packaging_code": 2,
        "serial_number": 3,
        "name": 4,
    }
    items.sort(
        key=lambda item: (
            reason_order[item["match_reason"]],
            item["product_code"],
        )
    )
    items = items[:limit]
    return {
        "query": term,
        "result": "none" if not items else ("exact" if len(items) == 1 else "multiple"),
        "items": items,
    }
