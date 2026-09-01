"""Sticker and barcode image generation for WB Marketplace API emulator."""

from __future__ import annotations

import base64
import io
import json
from functools import lru_cache
from pathlib import Path
from typing import Any

import qrcode
from PIL import Image

PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
_ORDER_STICKER_FIXTURES_PATH = (
    Path(__file__).resolve().parent.parent / "seed" / "wb_order_sticker_fixtures.json"
)


def _png_to_base64(png_bytes: bytes) -> str:
    return base64.b64encode(png_bytes).decode("ascii")


@lru_cache
def _real_order_sticker_fixtures() -> tuple[dict[str, Any], ...]:
    """Load exact 580x400 order stickers archived from the real WB API.

    An order sticker is not a standalone Code128 image. WB returns the complete
    58x40 layout with a central QR, four duplicate corner QRs, two linear
    barcodes, the WB mark and the visible partA/partB number. Keeping the
    original PNG is the only honest emulator response; reconstructing a QR from
    the fake order id produces a label that WB never issued.
    """
    raw = json.loads(_ORDER_STICKER_FIXTURES_PATH.read_text(encoding="utf-8"))
    fixtures = raw.get("fixtures")
    if not isinstance(fixtures, list) or not fixtures:
        raise ValueError("WB order sticker fixtures are missing")
    validated: list[dict[str, Any]] = []
    for fixture in fixtures:
        if not isinstance(fixture, dict):
            raise ValueError("invalid WB order sticker fixture")
        png_bytes = base64.b64decode(str(fixture.get("file", "")), validate=True)
        if not png_bytes.startswith(PNG_MAGIC):
            raise ValueError("WB order sticker fixture is not PNG")
        with Image.open(io.BytesIO(png_bytes)) as image:
            if image.size != (580, 400):
                raise ValueError("WB order sticker fixture must be 580x400")
        barcode = fixture.get("barcode")
        if not isinstance(barcode, str) or not barcode.startswith("*"):
            raise ValueError("WB order sticker scanner barcode is missing")
        validated.append(fixture)
    return tuple(validated)


def generate_qr_png_base64(data: str) -> str:
    """Render QR code as PNG base64 (supply barcode, trbx stickers)."""
    qr = qrcode.QRCode(version=1, box_size=8, border=2)
    qr.add_data(data)
    qr.make(fit=True)
    image = qr.make_image(fill_color="black", back_color="white")
    out = io.BytesIO()
    image.save(out, format="PNG")
    png_bytes = out.getvalue()
    if not png_bytes.startswith(PNG_MAGIC):
        raise ValueError("generated QR is not a PNG")
    return _png_to_base64(png_bytes)


def generate_qr_png_bytes(data: str) -> bytes:
    """Render QR code as raw PNG bytes (supply barcode GET)."""
    encoded = generate_qr_png_base64(data)
    return base64.b64decode(encoded)


def build_order_stickers(
    order_ids: list[int],
    *,
    width_mm: int = 58,
    height_mm: int = 40,
) -> list[dict[str, Any]]:
    """Return complete real-WB 58x40 sticker PNGs for emulator orders."""
    _ = width_mm, height_mm
    fixtures = _real_order_sticker_fixtures()
    stickers: list[dict[str, Any]] = []
    for order_id in order_ids:
        fixture = fixtures[order_id % len(fixtures)]
        stickers.append(
            {
                "orderId": order_id,
                "partA": fixture["partA"],
                "partB": fixture["partB"],
                "barcode": fixture["barcode"],
                "file": fixture["file"],
            }
        )
    return stickers


def build_trbx_stickers(trbx_ids: list[str]) -> list[dict[str, Any]]:
    """Build WB-shaped trbx sticker rows with QR PNG."""
    return [
        {
            "trbxId": trbx_id,
            "barcode": f"TRBX-{trbx_id}",
            "file": generate_qr_png_base64(f"TRBX:{trbx_id}"),
        }
        for trbx_id in trbx_ids
    ]
