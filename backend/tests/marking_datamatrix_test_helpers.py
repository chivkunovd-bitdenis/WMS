"""Хелперы для тестов распознавания DataMatrix КИЗ (I5-2).

Реальная этикетка селлера — это PDF с человекочитаемым текстом
"(01) <gtin>" / "(21) <serial>" рядом с картинкой DataMatrix, в которую
закодирован ПОЛНЫЙ код (с ключом проверки, тег 91, и опционально
криптохвостом, тег 92). Эти хелперы строят такой PDF по-настоящему —
кодируют код через `zxing-cpp` (ту же библиотеку, что использует прод-код
для распознавания, backend/app/services/marking_datamatrix_service.py) и
вставляют получившуюся картинку в PDF через `fitz` — чтобы тесты декодировали
именно её, а не полагались на заранее известную строку.
"""

from __future__ import annotations

import fitz
import zxingcpp

from app.services.marking_code_service import GS_SEPARATOR


def build_full_cis(gtin: str, serial: str, key: str = "A1B2", crypto_tail: str = "") -> str:
    """Собирает полный (или короткий, если crypto_tail пуст) КИЗ по
    документированной структуре: GTIN (тег 01) — серийник (тег 21) — GS —
    ключ проверки (тег 91) — [GS — криптохвост, тег 92]."""
    value = f"01{gtin}21{serial}{GS_SEPARATOR}91{key}"
    if crypto_tail:
        value = f"{value}{GS_SEPARATOR}92{crypto_tail}"
    return value


def encode_datamatrix_png(value: str) -> bytes:
    """Кодирует строку (с настоящими байтами GS-разделителя) в PNG-картинку
    DataMatrix — байт в байт то, что должен вернуть декодер на другом конце."""
    barcode = zxingcpp.create_barcode(value.encode("utf-8"), format=zxingcpp.DataMatrix)
    image = zxingcpp.write_barcode_to_image(barcode, scale=8)
    height, width = image.shape
    # `fitz.Pixmap(colorspace, width, height, samples, alpha)` строит растр
    # напрямую из 8-битного grayscale-буфера zxing-cpp — без Pillow/numpy.
    pixmap = fitz.Pixmap(fitz.csGRAY, width, height, bytes(image), 0)
    return bytes(pixmap.tobytes("png"))


def build_datamatrix_label_pdf(
    *,
    gtin: str,
    serial: str,
    key: str = "A1B2",
    crypto_tail: str = "",
    page_width: float = 170,
    page_height: float = 140,
    extra_text_lines: tuple[str, ...] = (),
) -> bytes:
    """Строит одностраничный PDF в форме реальной этикетки селлера: текст
    "(01) <gtin>" / "(21) <serial>" плюс картинка DataMatrix с полным кодом.
    Ровно то, что должен разобрать `extract_label_artifacts_from_pdf`."""
    full_cis = build_full_cis(gtin, serial, key=key, crypto_tail=crypto_tail)
    png_bytes = encode_datamatrix_png(full_cis)

    doc = fitz.open()
    try:
        page = doc.new_page(width=page_width, height=page_height)
        y = 18.0
        for line in ("Честный знак", *extra_text_lines):
            page.insert_text((12, y), line, fontsize=7)
            y += 12
        page.insert_text((12, y), f"(01) {gtin}", fontsize=6)
        y += 12
        page.insert_text((12, y), f"(21) {serial}", fontsize=6)
        y += 10
        image_rect = fitz.Rect(12, y, page_width - 12, page_height - 10)
        page.insert_image(image_rect, stream=png_bytes)
        return bytes(doc.tobytes())
    finally:
        doc.close()


def build_two_datamatrix_label_pdf(
    *,
    gtin: str,
    serial_a: str,
    serial_b: str,
    key: str = "A1B2",
) -> bytes:
    """Одна страница, два независимых лейбла бок о бок — обе картинки со
    своим полным кодом."""
    png_a = encode_datamatrix_png(build_full_cis(gtin, serial_a, key=key))
    png_b = encode_datamatrix_png(build_full_cis(gtin, serial_b, key=key))

    doc = fitz.open()
    try:
        page = doc.new_page(width=360, height=240)
        page.insert_text((12, 24), "Честный знак", fontsize=8)
        page.insert_text((12, 42), f"(01) {gtin}", fontsize=6)
        page.insert_text((12, 54), f"(21) {serial_a}", fontsize=6)
        page.insert_image(fitz.Rect(12, 62, 172, 222), stream=png_a)

        page.insert_text((190, 24), "Честный знак", fontsize=8)
        page.insert_text((190, 42), f"(01) {gtin}", fontsize=6)
        page.insert_text((190, 54), f"(21) {serial_b}", fontsize=6)
        page.insert_image(fitz.Rect(190, 62, 350, 222), stream=png_b)
        return bytes(doc.tobytes())
    finally:
        doc.close()
