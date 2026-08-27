"""Хвост кода маркировки доезжает до экрана, а не режется схемой ответа."""

from __future__ import annotations

from app.api.fbs_orders import FbsWorklistMetadataStateOut


def test_value_tail_survives_serialization() -> None:
    """Раньше pydantic молча выбрасывал поле: сервис клал, схема снимала,
    и колонка «ЧЗ» на экране упаковки всегда показывала прочерк."""
    payload = {
        "kind": "sgtin",
        "status": "assigned",
        "reason": None,
        "source": "operator",
        "value_tail": "kXO2aEY=",
    }
    dumped = FbsWorklistMetadataStateOut(**payload).model_dump()
    assert dumped["value_tail"] == "kXO2aEY="


def test_state_without_code_keeps_empty_tail() -> None:
    """Заказ без внесённого кода — пустой хвост, экран рисует прочерк."""
    dumped = FbsWorklistMetadataStateOut(
        kind="sgtin", status="missing", reason=None
    ).model_dump()
    assert dumped["value_tail"] is None
