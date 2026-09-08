from __future__ import annotations

import json
import uuid
import weakref

import fitz
import pytest
from httpx import AsyncClient
from marking_datamatrix_test_helpers import build_datamatrix_pdf
from sqlalchemy import select
from test_packaging_tasks import _register_admin

from app.db.session import SessionLocal
from app.models.marking_code import MarkingCode
from app.services import marking_code_service as svc
from app.services.marking_datamatrix_service import decode_datamatrix_codes_on_pdf_page

GTIN = "04600000000001"
FULL = f"01{GTIN}21SYNTHETIC0831\x1d91ABCD\x1d92SYNTHETIC+/=CRYPTO083"
OTHER = f"01{GTIN}21SECOND083\x1d93OTHER+/=TAIL"


@pytest.mark.parametrize("channels", [1, 3])
def test_decoder_keeps_pixel_buffer_alive_during_native_read(
    monkeypatch: pytest.MonkeyPatch, channels: int
) -> None:
    import zxingcpp

    class PixelBuffer(bytearray):
        pass

    buffers: list[weakref.ReferenceType[PixelBuffer]] = []

    class Pixmap:
        width = 10
        height = 10
        n = channels

        @property
        def samples(self) -> PixelBuffer:
            # Like PyMuPDF's samples, each access returns a separate buffer.
            pixels = PixelBuffer(b"\xff" * self.width * self.height * self.n)
            buffers.append(weakref.ref(pixels))
            return pixels

    class Page:
        def get_pixmap(self, **kwargs: object) -> Pixmap:
            return Pixmap()

    native_read = zxingcpp.read_barcodes

    def checked_read(view: object, **kwargs: object) -> list:
        # Fail safely before the real decoder can dereference freed memory.
        assert buffers[-1]() is not None, "ImageView outlived its pixel buffer"
        return native_read(view, **kwargs)

    monkeypatch.setattr(zxingcpp, "read_barcodes", checked_read)
    assert decode_datamatrix_codes_on_pdf_page(Page()) == []
    assert len(buffers) == 1
    assert buffers[0]() is None


@pytest.mark.parametrize("caption", [True, False])
@pytest.mark.asyncio
async def test_pdf_preview_import_and_artifact_keep_decoded_bytes(
    async_client: AsyncClient,
    caption: bool,
) -> None:
    headers = await _register_admin(async_client)
    seller = await async_client.post("/sellers", headers=headers, json={"name": "DM seller"})
    seller_id = seller.json()["id"]
    pdf = build_datamatrix_pdf([FULL, OTHER], caption=caption)
    files = [("files", ("synthetic.pdf", pdf, "application/pdf"))]
    preview = await async_client.post(
        "/operations/marking-codes/import/preview",
        headers=headers,
        data={"seller_id": seller_id},
        files=files,
    )
    assert preview.status_code == 200, preview.text
    assert preview.json()["total_codes"] == 2
    imported = await async_client.post(
        "/operations/marking-codes/import",
        headers=headers,
        data={
            "seller_id": seller_id,
            "pools_json": json.dumps([{"title": "DM pool", "gtin": GTIN}]),
        },
        files=files,
    )
    assert imported.status_code == 200, imported.text
    assert imported.json()["accepted_count"] == 2
    async with SessionLocal() as session:
        codes = list(
            (
                await session.scalars(
                    select(MarkingCode).where(MarkingCode.seller_id == uuid.UUID(seller_id))
                )
            ).all()
        )
        assert {code.cis_code.encode() for code in codes} == {FULL.encode(), OTHER.encode()}
        for code in codes:
            assert code.label_artifact_pdf
            assert svc.is_printable_label_artifact(code.label_artifact_pdf, code.cis_code)
            with fitz.open(stream=code.label_artifact_pdf, filetype="pdf") as doc:
                decoded = [
                    item.value for page in doc for item in decode_datamatrix_codes_on_pdf_page(page)
                ]
            assert decoded == [code.cis_code]
            assert code.status == "available"


def test_pdf_caption_without_datamatrix_cannot_create_a_code() -> None:
    with fitz.open() as doc:
        page = doc.new_page()
        page.insert_text((20, 30), FULL.split("\x1d")[0])
        pdf = doc.tobytes()
    with pytest.raises(svc.MarkingCodeServiceError, match="no_valid_codes"):
        svc.parse_import_file("text-only.pdf", pdf)


@pytest.mark.parametrize("content", [FULL, FULL + "\r\n" + OTHER, "cis\n" + FULL])
def test_text_import_keeps_gs_inside_each_record(content: str) -> None:
    rows = svc.parse_import_file("codes.txt", content.encode())
    assert [row["cis"] for row in rows] == ([FULL, OTHER] if OTHER in content else [FULL])
    grouped, invalid, _, _ = svc._group_cis_codes_from_rows(rows)
    assert invalid == 0
    assert grouped[GTIN] == [row["cis"] for row in rows]


def test_grid_import_artifacts_each_retain_one_whole_datamatrix() -> None:
    values = [FULL.replace("SYNTHETIC0831", f"SYNTHETIC083{i}") for i in range(4)]
    rows = svc.parse_import_file("grid.pdf", build_datamatrix_pdf(values, columns=2))
    assert {row["cis"] for row in rows} == set(values)
    for row in rows:
        with fitz.open(stream=row["label_pdf"], filetype="pdf") as doc:
            decoded = [
                item.value for page in doc for item in decode_datamatrix_codes_on_pdf_page(page)
            ]
        assert decoded == [row["cis"]]
