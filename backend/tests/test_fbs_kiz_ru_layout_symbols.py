"""WMS-575: ЧЗ со знаками «/», «?», «&» в русской раскладке.

Упаковка FBS отдаёт серверу сырую пачку клавиатуры — то, что легло бы в поле
скана, вместе с разделителем GS. Раскладку чинит normalize_scanned_cis полной
таблицей. Строки ниже — ровно то, что отправляет фронт
(frontend/src/hooks/useBarcodeScanner.test.ts, блок emitRaw, и
FfFbsSupplyWorkspace.scan.dom.test.tsx).
"""

from __future__ import annotations

import pytest

from app.services.fbs_kiz_service import normalize_scanned_cis

CASES = [
    # (исходный код, сырая пачка при русской раскладке)
    ("0104600000000017215Ab/c?d&Ef9GhJ", "0104600000000017215Фи.с,в?Уа9ПрО"),
    ("0104600000000017215Ab/c?d\x1d93Ef9G", "0104600000000017215Фи.с,в\x1d93Уа9П"),
]


@pytest.mark.parametrize(("code", "raw"), CASES)
def test_ru_layout_raw_scan_is_repaired_with_slash_question_and_ampersand(
    code: str, raw: str
) -> None:
    value, hints = normalize_scanned_cis(raw)
    assert value == code
    assert "keyboard_layout" in hints


@pytest.mark.parametrize(("code", "raw"), CASES)
def test_latin_scan_is_unchanged(code: str, raw: str) -> None:
    value, hints = normalize_scanned_cis(code)
    assert value == code
    assert "keyboard_layout" not in hints


def test_letter_only_translation_is_not_repaired() -> None:
    """Так приходил код после перевода одних букв на клиенте: кириллицы нет,
    ремонт не включается, и к заказу ушёл бы искажённый код."""
    value, hints = normalize_scanned_cis("0104600000000017215Ab.c,d?Ef9GhJ")
    assert value != "0104600000000017215Ab/c?d&Ef9GhJ"
    assert "keyboard_layout" not in hints
