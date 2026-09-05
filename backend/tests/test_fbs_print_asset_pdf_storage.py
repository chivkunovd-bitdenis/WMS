"""Хранилище печатных активов держит два формата, и не путает их между собой.

Wildberries отдаёт стикер заказа картинкой, Ozon — документом PDF: у всех трёх
печатных методов Ozon в его официальной спецификации объявлен
``application/pdf``. Пока проверка была жёстко привязана к сигнатуре PNG,
этикетку Ozon нельзя было сохранить вовсе — она отваливалась на
``invalid_content_type`` ещё до диска, и печать этикеток Ozon честно отказывала.

Проверка формата не ослаблена, а стала точной: формат объявляется при записи и
сверяется с сигнатурой файла. Эти тесты держат обе стороны — что PDF теперь
проходит и что подмена одного формата другим по-прежнему не проходит.
"""

from __future__ import annotations

import uuid

import pytest

from app.services.fbs_print_asset_storage import (
    ORDER_STICKER_CONTENT_TYPE,
    PDF_CONTENT_TYPE,
    FbsPrintAssetStorageError,
    order_sticker_relative_path,
    read_png,
    read_print_file,
    save_png,
    save_print_file,
)

_PNG_BYTES = bytes.fromhex(
    "89504e470d0a1a0a0000000d4948445200000001000000010806000000"
    "1f15c4890000000a49444154789c6360000002000100ffff0300000600"
    "0557bfabd40000000049454e44ae426082"
)
_PDF_BYTES = b"%PDF-1.7\n1 0 obj<</Type/Catalog>>endobj\ntrailer<</Root 1 0 R>>\n%%EOF"


def test_pdf_label_is_stored_and_read_back_untouched() -> None:
    order_id = uuid.uuid4()
    rel = order_sticker_relative_path(order_id, content_type=PDF_CONTENT_TYPE)
    assert rel.endswith(f"{order_id}.pdf")

    save_print_file(rel, _PDF_BYTES, content_type=PDF_CONTENT_TYPE)

    assert read_print_file(rel, content_type=PDF_CONTENT_TYPE) == _PDF_BYTES


def test_png_and_pdf_of_one_order_are_different_files() -> None:
    """Расширение — часть имени, поэтому форматы не затирают друг друга."""
    order_id = uuid.uuid4()
    png_path = order_sticker_relative_path(order_id)
    pdf_path = order_sticker_relative_path(order_id, content_type=PDF_CONTENT_TYPE)
    assert png_path != pdf_path

    save_png(png_path, _PNG_BYTES)
    save_print_file(pdf_path, _PDF_BYTES, content_type=PDF_CONTENT_TYPE)

    assert read_png(png_path) == _PNG_BYTES
    assert read_print_file(pdf_path, content_type=PDF_CONTENT_TYPE) == _PDF_BYTES


def test_a_pdf_declared_as_png_is_refused() -> None:
    """Путь Wildberries не ослаблен: под видом картинки документ не пройдёт."""
    rel = order_sticker_relative_path(uuid.uuid4())
    with pytest.raises(FbsPrintAssetStorageError) as caught:
        save_png(rel, _PDF_BYTES)
    assert caught.value.code == "invalid_content_type"


def test_a_png_declared_as_pdf_is_refused() -> None:
    rel = order_sticker_relative_path(uuid.uuid4(), content_type=PDF_CONTENT_TYPE)
    with pytest.raises(FbsPrintAssetStorageError) as caught:
        save_print_file(rel, _PNG_BYTES, content_type=PDF_CONTENT_TYPE)
    assert caught.value.code == "invalid_content_type"


def test_an_unknown_format_never_reaches_the_disk() -> None:
    """Список форматов закрытый: чего в нём нет, то и не сохраняется."""
    with pytest.raises(FbsPrintAssetStorageError) as caught:
        order_sticker_relative_path(uuid.uuid4(), content_type="image/jpeg")
    assert caught.value.code == "invalid_content_type"

    rel = order_sticker_relative_path(uuid.uuid4())
    with pytest.raises(FbsPrintAssetStorageError):
        save_print_file(rel, b"\xff\xd8\xff jpeg", content_type="image/jpeg")


def test_empty_content_is_still_empty_content() -> None:
    rel = order_sticker_relative_path(uuid.uuid4(), content_type=PDF_CONTENT_TYPE)
    with pytest.raises(FbsPrintAssetStorageError) as caught:
        save_print_file(rel, b"", content_type=PDF_CONTENT_TYPE)
    assert caught.value.code == "empty_content"


def test_reading_a_pdf_as_png_fails_instead_of_returning_garbage() -> None:
    rel = order_sticker_relative_path(uuid.uuid4(), content_type=PDF_CONTENT_TYPE)
    save_print_file(rel, _PDF_BYTES, content_type=PDF_CONTENT_TYPE)
    with pytest.raises(FbsPrintAssetStorageError) as caught:
        read_print_file(rel, content_type=ORDER_STICKER_CONTENT_TYPE)
    assert caught.value.code == "invalid_content_type"
