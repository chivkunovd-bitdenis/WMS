"""Unit tests for WB card size variant parsing."""

from __future__ import annotations

from app.services.wb_card_enrichment import (
    iter_size_variants_from_card,
    sku_code_for_wb_variant,
)


def test_iter_size_variants_one_per_barcode() -> None:
    card = {
        "sizes": [
            {"techSize": "S", "skus": ["111"]},
            {"techSize": "M", "skus": ["222"]},
        ]
    }
    variants = iter_size_variants_from_card(card)
    assert len(variants) == 2
    assert variants[0].barcode == "111"
    assert variants[0].size_label == "S"
    assert variants[1].barcode == "222"


def test_sku_code_suffix_for_multi_variant() -> None:
    v = iter_size_variants_from_card({"sizes": [{"techSize": "L", "skus": ["999"]}]})[0]
    assert sku_code_for_wb_variant("ART", 1, v, multi_variant=True) == "ART/L"
    assert sku_code_for_wb_variant("ART", 1, v, multi_variant=False) == "ART"
