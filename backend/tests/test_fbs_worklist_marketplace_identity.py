"""WMS-425: another marketplace must never supply missing order identifiers."""
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from app.api.fbs_orders import FbsWorklistOrderOut
from app.models.fbs_order import FbsOrder, FbsOrderProduct
from app.models.product import Product
from app.models.seller_wildberries_imported_card import SellerWildberriesImportedCard
from app.services.fbs_worklist_service import _map_order


@pytest.mark.parametrize("marketplace", ["ozon", "wb"])
@pytest.mark.parametrize("ozon_barcode", ["OZON-BARCODE", None])
def test_worklist_identifiers_stay_with_order_marketplace(marketplace, ozon_barcode):
    now = datetime.now(UTC)
    product = Product(
        id=uuid4(), name="Shared product", wb_vendor_code="WB-ARTICLE",
        wb_barcode="WB-BARCODE", wb_chrt_id=123, sku_code="WB-SKU",
    )
    position = FbsOrderProduct(
        id=uuid4(), product_id=product.id, name="Ozon product", offer_id=None,
        ozon_sku=5680825729, quantity=1, reserved_quantity=0, picked_quantity=0,
    )
    order = FbsOrder(
        id=uuid4(), seller_id=uuid4(), product_id=product.id, marketplace=marketplace,
        wb_order_id=1, wb_nm_id=999, wb_article="WB-ORDER-ARTICLE",
        wb_barcode="WB-ORDER-BARCODE", wb_chrt_id=456,
        status="new", supplier_status="new", mapping_status="mapped",
        created_at_wb=now, deadline_at=now + timedelta(days=1),
        product_positions=[position] if marketplace == "ozon" else [],
    )
    bindings = [
        {"marketplace": "wb", "external_barcodes": ["WB-LINK-BARCODE"]},
        {"marketplace": "ozon", "external_barcodes": [ozon_barcode] if ozon_barcode else []},
    ]
    ctx = {key: {} for key in (
        "sellers", "warehouses", "wb_names", "cards", "ozon_photos", "availability",
        "locations", "markings", "picks", "sticker_assets",
    )}
    ctx.update(
        products={product.id: product},
        positions={order.id: order.product_positions},
        marketplace_bindings={product.id: bindings},
        address_storage_enabled=False,
    )
    result = _map_order(order, ctx, now)
    item = result["product"]
    assert [b["marketplace"] for b in item["marketplace_bindings"]] == [marketplace]
    warning = next(b["message"] for b in result["selection_blockers"]
                   if b["code"] == "warehouse_unmapped")
    if marketplace == "ozon":
        assert item["seller_article"] is None
        assert item["wb_article"] is None
        assert item["chrt_id"] is None
        assert item["sku"] == "5680825729"
        assert item["barcode"] == ozon_barcode
        assert result["positions"][0]["seller_article"] is None
        assert result["positions"][0]["barcode"] == ozon_barcode
        assert "Ozon" in warning and "WB" not in warning
    else:
        assert item["seller_article"] == "WB-ARTICLE"
        assert item["wb_article"] == 999
        assert item["chrt_id"] == 456
        assert item["barcode"] == "WB-BARCODE"
        assert item["sku"] == "WB-SKU"
        assert "WB" in warning and "Ozon" not in warning


def test_ozon_positions_keep_own_catalog_metadata_and_identity():
    now = datetime.now(UTC)
    seller_id = uuid4()
    first = Product(
        id=uuid4(),
        seller_id=seller_id,
        name="WB first",
        sku_code="WB-FIRST",
        wb_nm_id=101,
        wb_barcode="WB-101",
        wb_size="S",
    )
    second = Product(
        id=uuid4(),
        seller_id=seller_id,
        name="WB second",
        sku_code="WB-SECOND",
        wb_nm_id=202,
        wb_barcode="WB-202",
        wb_size="XL",
    )
    first_position = FbsOrderProduct(
        id=uuid4(), product_id=first.id, name="Ozon first", offer_id="OZ-FIRST",
        ozon_sku=1001, quantity=2, reserved_quantity=0, picked_quantity=0,
    )
    second_position = FbsOrderProduct(
        id=uuid4(), product_id=second.id, name="Ozon second", offer_id="OZ-SECOND",
        ozon_sku=2002, quantity=1, reserved_quantity=0, picked_quantity=0,
    )
    order = FbsOrder(
        id=uuid4(), seller_id=seller_id, product_id=first.id, marketplace="ozon",
        wb_order_id=1, status="new", supplier_status="new", mapping_status="mapped",
        sticker_status="not_requested", pick_status="pending", pack_status="pending",
        created_at_wb=now, deadline_at=now + timedelta(days=1),
        product_positions=[first_position, second_position],
    )
    first_card = SellerWildberriesImportedCard(
        seller_id=seller_id,
        nm_id=101,
        raw_json={
            "brand": "First brand",
            "characteristics": [
                {"name": "Цвет", "value": "красный"},
                {"name": "Состав", "value": "хлопок"},
            ],
        },
    )
    second_card = SellerWildberriesImportedCard(
        seller_id=seller_id,
        nm_id=202,
        raw_json={
            "brand": "Second brand",
            "characteristics": [
                {"name": "Цвет", "value": "синий"},
                {"name": "Состав", "value": "лён"},
            ],
        },
    )
    ctx = {key: {} for key in (
        "sellers", "warehouses", "wb_names", "ozon_photos", "availability", "locations",
        "markings", "picks", "sticker_assets",
    )}
    ctx.update(
        products={first.id: first, second.id: second},
        positions={order.id: [first_position, second_position]},
        cards={(seller_id, 101): first_card, (seller_id, 202): second_card},
        marketplace_bindings={
            first.id: [{"marketplace": "ozon", "external_barcodes": ["OZN-1001"]}],
            second.id: [{"marketplace": "ozon", "external_barcodes": ["OZN-2002"]}],
        },
        address_storage_enabled=False,
    )

    result = _map_order(order, ctx, now)
    api_payload = FbsWorklistOrderOut(**result).model_dump()

    assert result["product"]["name"] == "Ozon first"
    assert result["product"]["barcode"] == "OZN-1001"
    assert [
        (row["name"], row["seller_article"], row["sku"], row["barcode"], row["quantity"])
        for row in result["positions"]
    ] == [
        ("Ozon first", "OZ-FIRST", "1001", "OZN-1001", 2),
        ("Ozon second", "OZ-SECOND", "2002", "OZN-2002", 1),
    ]
    assert [
        (row["size"], row["color"], row["brand"], row["composition"])
        for row in api_payload["positions"]
    ] == [
        ("S", "красный", "First brand", "хлопок"),
        ("XL", "синий", "Second brand", "лён"),
    ]
