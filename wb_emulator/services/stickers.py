"""Sticker and barcode image generation for WB Marketplace API emulator."""

from __future__ import annotations

import base64
import io
from typing import Any

import qrcode  # type: ignore[import-untyped]
from barcode import Code128  # type: ignore[import-untyped]
from barcode.writer import ImageWriter  # type: ignore[import-untyped]
from PIL import Image

PNG_MAGIC = b"\x89PNG\r\n\x1a\n"


def _png_to_base64(png_bytes: bytes) -> str:
    return base64.b64encode(png_bytes).decode("ascii")


def generate_code128_png_base64(text: str, *, width_mm: int = 58, height_mm: int = 40) -> str:
    """Render Code128 barcode as PNG base64 (order stickers)."""
    buffer = io.BytesIO()
    writer = ImageWriter()
    barcode = Code128(text, writer=writer)
    barcode.write(
        buffer,
        options={
            "module_width": 0.25,
            "module_height": max(height_mm * 0.6, 8.0),
            "quiet_zone": 2.0,
            "write_text": False,
        },
    )
    buffer.seek(0)
    image = Image.open(buffer).convert("RGB")
    target_w = max(int(width_mm * 3.78), 1)
    target_h = max(int(height_mm * 3.78), 1)
    resized = image.resize((target_w, target_h), Image.Resampling.LANCZOS)
    out = io.BytesIO()
    resized.save(out, format="PNG")
    png_bytes = out.getvalue()
    if not png_bytes.startswith(PNG_MAGIC):
        raise ValueError("generated sticker is not a PNG")
    return _png_to_base64(png_bytes)


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
    """Build WB-shaped order sticker rows with real Code128 PNG."""
    stickers: list[dict[str, Any]] = []
    for order_id in order_ids:
        barcode_text = f"WB{order_id:010d}"
        stickers.append(
            {
                "orderId": order_id,
                "partA": order_id,
                "partB": order_id + 1,
                "barcode": barcode_text,
                "file": generate_code128_png_base64(
                    barcode_text,
                    width_mm=width_mm,
                    height_mm=height_mm,
                ),
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
