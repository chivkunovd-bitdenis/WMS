"""Актив печати без файла на диске не выдаётся оператору как готовый.

Бой 27.08.2026: выкатка пересоздала контейнер, вместе с ним пропали 1756 файлов
стикеров и QR — они лежали внутри контейнера, а не на томе. В базе активы
остались готовыми, экран печати обещал «Готово 1» и тут же говорил «готовых
изображений нет»: карточка есть, файла нет, запрос за картинкой отвечал 404.
"""

from __future__ import annotations

import uuid

from app.models.fbs_print_asset import (
    PRINT_ASSET_KIND_ORDER_STICKER,
    PRINT_ASSET_STATUS_ERROR,
    PRINT_ASSET_STATUS_READY,
    FbsPrintAsset,
)
from app.services.fbs_print_asset_service import map_print_asset
from app.services.fbs_print_asset_storage import order_sticker_relative_path, save_png

# Минимальный валидный PNG 1x1: хранилище проверяет сигнатуру файла.
_PNG_BYTES = bytes.fromhex(
    "89504e470d0a1a0a0000000d4948445200000001000000010806000000"
    "1f15c4890000000a49444154789c6360000002000100ffff0300000600"
    "0557bfabd40000000049454e44ae426082"
)


def _asset(storage_path: str | None, status: str = PRINT_ASSET_STATUS_READY) -> FbsPrintAsset:
    asset = FbsPrintAsset()
    asset.id = uuid.uuid4()
    asset.kind = PRINT_ASSET_KIND_ORDER_STICKER
    asset.status = status
    asset.storage_path = storage_path
    asset.content_type = "image/png"
    return asset


def test_ready_asset_with_file_is_printable() -> None:
    """Файл на месте — актив готов, ссылка на картинку есть."""
    order_id = uuid.uuid4()
    rel = save_png(order_sticker_relative_path(order_id), _PNG_BYTES)
    payload = map_print_asset(_asset(rel))
    assert payload["status"] == PRINT_ASSET_STATUS_READY
    assert payload["preview_url"] is not None
    assert payload["error"] is None


def test_ready_asset_without_file_is_not_printable() -> None:
    """Файла нет — актив не готов, ссылки нет, причина названа словами."""
    payload = map_print_asset(_asset(order_sticker_relative_path(uuid.uuid4())))
    assert payload["status"] == PRINT_ASSET_STATUS_ERROR
    assert payload["preview_url"] is None
    assert payload["download_url"] is None
    assert payload["error"] is not None
    assert payload["error"]["code"] == "file_missing"
    assert "заново" in payload["error"]["message"]


def test_asset_without_storage_path_is_not_printable() -> None:
    payload = map_print_asset(_asset(None))
    assert payload["preview_url"] is None
    assert payload["error"]["code"] == "file_missing"


def test_already_failed_asset_keeps_its_own_error() -> None:
    """Свою причину ошибки не затираем — она точнее общей «файла нет»."""
    asset = _asset(None, status=PRINT_ASSET_STATUS_ERROR)
    asset.error_code = "wb_upstream_error_409"
    asset.error_message = "WB не отдал стикер."
    payload = map_print_asset(asset)
    assert payload["status"] == PRINT_ASSET_STATUS_ERROR
    assert payload["error"]["code"] == "wb_upstream_error_409"
