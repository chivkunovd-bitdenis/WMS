"""Распознавание DataMatrix-картинок КИЗ на PDF-этикетках селлера (I5-2).

Почему это отдельный шаг, а не текстовый разбор PDF: человекочитаемый текст,
который селлер печатает рядом с DataMatrix на этикетке, — это всегда куцая
пара "(01) <gtin>" / "(21) <серийник>". Ни ключ проверки (тег 91), ни
криптохвост (тег 92) там никогда не печатаются как текст — их несёт только
сама картинка штрихкода (проверено на боевом PDF руками — см. наряд I5-2 и
docs/BACKLOG-2026-08-19-CHAT-RU.md). Значит единственный источник полного
кода — сама картинка, и распознавать её нужно из растра страницы, а не
"досочинять" из текста (так делал старый `_canonical_cis_from_match`, и
именно он был источником обрезанных кодов пула).

Библиотека: `zxing-cpp` (PyPI `zxing-cpp`, импортируется как `zxingcpp`) —
готовые wheel-колёса под все нужные платформы (в т.ч. `python:3.11-slim` из
`backend/Dockerfile`), ставится через pip без системных библиотек. Для
сравнения, `pylibdmtx` тоже умеет DataMatrix, но требует системную
`libdmtx.so`, которой в образе нет и которую пришлось бы добавлять отдельным
слоем — `zxing-cpp` этого не требует. Дополнительный плюс: `zxingcpp.ImageView`
принимает буфер `fitz.Pixmap.samples` напрямую, без Pillow/numpy как
промежуточного слоя.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import cast

# 600 DPI — достаточно, чтобы мелкий DataMatrix на этикетке 40x60 мм остался
# читаемым после рендера страницы в растр (проверено на реальных PDF из
# наряда — при 300 DPI мелкие модули кода местами схлопывались).
_DEFAULT_DPI = 600


@dataclass(frozen=True)
class DecodedDataMatrix:
    """Один распознанный DataMatrix на странице PDF.

    `value` — точный декодированный КИЗ: реальные GS-разделители (байт
    `\\x1d`) внутри строки, а не текстовый плейсхолдер `<GS>`, который
    некоторые библиотеки подставляют для читаемости. `page_rect` — положение
    штрихкода в координатах PDF-страницы (пункты, как у `fitz.Rect`), а не в
    пикселях растра, которым он был распознан — так его можно сопоставить с
    человекочитаемым текстом рядом с картинкой на той же странице.
    """

    value: str
    page_rect: tuple[float, float, float, float]


def decode_datamatrix_codes_on_pdf_page(
    page: object,
    dpi: int = _DEFAULT_DPI,
) -> list[DecodedDataMatrix]:
    """Рендерит страницу `page` (`fitz.Page`) в растр и распознаёт на ней все
    DataMatrix-картинки. На одной странице их может быть несколько — именно
    так устроены ленты этикеток селлера (до сотни этикеток в одном PDF).

    Бросает `RuntimeError("datamatrix_support_unavailable")`, если пакет
    `zxing-cpp` не установлен — тем же способом, каким остальной код этого
    сервиса сигналит об отсутствии `pymupdf` (см. `is_printable_label_artifact`
    и `pdf_bytes_to_png`), чтобы вызывающая сторона могла явно отличить эту
    ситуацию от "код на картинке не распознан".
    """
    try:
        import zxingcpp
    except ImportError as exc:
        raise RuntimeError("datamatrix_support_unavailable") from exc
    import fitz  # pymupdf

    pg = cast(fitz.Page, page)
    scale = dpi / 72.0
    matrix = fitz.Matrix(scale, scale)
    pixmap = pg.get_pixmap(matrix=matrix, alpha=False)
    image_format = zxingcpp.ImageFormat.RGB if pixmap.n >= 3 else zxingcpp.ImageFormat.Lum
    view = zxingcpp.ImageView(pixmap.samples, pixmap.width, pixmap.height, image_format)
    formats = zxingcpp.BarcodeFormats(zxingcpp.DataMatrix)
    results = zxingcpp.read_barcodes(view, formats=formats)

    decoded: list[DecodedDataMatrix] = []
    for result in results:
        if not result.valid:
            continue
        # `.bytes` — сырые декодированные байты (реальный GS `\x1d` внутри);
        # `.text` подставляет вместо него человекочитаемый `<GS>` и для
        # восстановления кода не годится.
        try:
            value = result.bytes.decode("utf-8")
        except UnicodeDecodeError:
            value = result.bytes.decode("latin-1")
        if not value:
            continue
        position = result.position
        xs = (
            position.top_left.x,
            position.top_right.x,
            position.bottom_right.x,
            position.bottom_left.x,
        )
        ys = (
            position.top_left.y,
            position.top_right.y,
            position.bottom_right.y,
            position.bottom_left.y,
        )
        page_rect = (
            min(xs) / scale,
            min(ys) / scale,
            max(xs) / scale,
            max(ys) / scale,
        )
        decoded.append(DecodedDataMatrix(value=value, page_rect=page_rect))
    return decoded
