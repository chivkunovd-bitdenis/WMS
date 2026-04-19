from __future__ import annotations

from app.services.wb_card_enrichment import (
    collect_skus_from_card,
    first_photo_url_from_card,
    primary_sku_display,
    subject_name_from_card,
)


def test_subject_name_from_card() -> None:
    assert subject_name_from_card({"subjectName": "  Рубашки  "}) == "Рубашки"


def test_collect_skus_from_card_sizes() -> None:
    card = {
        "sizes": [
            {"skus": ["2045526738950", "2045526738951"]},
            {"skus": ["300"]},
        ],
    }
    assert collect_skus_from_card(card) == ["2045526738950", "2045526738951", "300"]


def test_first_photo_url_priority() -> None:
    card = {
        "photos": [
            {"square": "https://example.com/sq.jpg", "big": "https://example.com/b.jpg"}
        ],
    }
    assert first_photo_url_from_card(card) == "https://example.com/b.jpg"


def test_primary_sku_display() -> None:
    assert primary_sku_display(["a", "b"]) == "a"
    assert primary_sku_display([]) is None
