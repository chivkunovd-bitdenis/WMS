"""WMS-425: another marketplace must never supply missing order identifiers."""
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from app.models.fbs_order import FbsOrder, FbsOrderProduct
from app.models.product import Product
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
