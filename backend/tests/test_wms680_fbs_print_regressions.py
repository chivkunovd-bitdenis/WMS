"""WMS-680 regressions found by independent review before the correction."""

import uuid

from app.models.product import Product
from app.models.seller_wildberries_imported_card import SellerWildberriesImportedCard
from app.services.fbs_worklist_service import _product_label_metadata


def test_c680_05_and_c680_07_whitespace_saved_size_falls_back_to_own_card_variant() -> None:
    """A whitespace-only saved size is absent, not a value that masks barcode fallback."""
    tenant_id = uuid.uuid4()
    seller_id = uuid.uuid4()
    product = Product(
        tenant_id=tenant_id,
        seller_id=seller_id,
        name="Variant M",
        sku_code="WMS-680-M",
        wb_nm_id=680,
        wb_barcode="222",
        wb_size="   ",
    )
    card = SellerWildberriesImportedCard(
        tenant_id=tenant_id,
        seller_id=seller_id,
        nm_id=680,
        raw_json={
            "sizes": [
                {"techSize": "S", "skus": ["111"]},
                {"techSize": "M", "skus": ["222"]},
            ],
            "characteristics": [{"name": "Цвет", "value": ["Blue"]}],
        },
    )

    metadata = _product_label_metadata(product, {"cards": {(seller_id, 680): card}})

    assert metadata["size"] == "M"
    assert metadata["color"] == "Blue"
