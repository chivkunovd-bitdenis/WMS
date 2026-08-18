from __future__ import annotations

from app.services.wb_card_enrichment import (
    brand_from_card,
    collect_skus_from_card,
    color_from_card,
    composition_from_card,
    country_of_origin_from_card,
    first_photo_url_from_card,
    primary_sku_display,
    shelf_life_from_card,
    size_from_card_for_barcode,
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


def test_brand_from_card() -> None:
    assert brand_from_card({"brand": "  MeMove  "}) == "MeMove"
    assert brand_from_card({}) is None


def test_color_from_card_by_name() -> None:
    card = {"characteristics": [{"name": "Цвет", "value": ["коричневый"]}]}
    assert color_from_card(card) == "коричневый"


def test_composition_from_card() -> None:
    card = {
        "characteristics": [
            {"name": "Состав", "value": ["хлопок 95%", "эластан 5%"]},
        ],
    }
    assert composition_from_card(card) == "хлопок 95%, эластан 5%"


def test_country_of_origin_from_card_by_name() -> None:
    card = {"characteristics": [{"name": "Страна производства", "value": ["Россия"]}]}
    assert country_of_origin_from_card(card) == "Россия"


def test_country_of_origin_from_card_missing() -> None:
    assert country_of_origin_from_card({}) is None
    assert country_of_origin_from_card({"characteristics": []}) is None


def test_shelf_life_from_card_by_name() -> None:
    card = {"characteristics": [{"name": "Срок годности", "value": ["12 месяцев"]}]}
    assert shelf_life_from_card(card) == "12 месяцев"


def test_shelf_life_from_card_missing() -> None:
    assert shelf_life_from_card({}) is None
    assert shelf_life_from_card({"characteristics": []}) is None


def test_size_from_card_for_barcode() -> None:
    card = {
        "sizes": [
            {"techSize": "S", "skus": ["111"]},
            {"techSize": "L", "wbSize": "48", "skus": ["222"]},
        ],
    }
    assert size_from_card_for_barcode(card, "222") == "L"
    assert size_from_card_for_barcode(card, "111") == "S"
