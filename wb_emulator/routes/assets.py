"""Public, deterministic product images for browser-level emulator tests."""

from __future__ import annotations

from functools import lru_cache
from io import BytesIO

from fastapi import APIRouter, Response
from PIL import Image, ImageDraw

router = APIRouter(prefix="/__assets", tags=["test-assets"])


@lru_cache(maxsize=128)
def _product_png(chrt_id: int) -> bytes:
    """Render a stable, non-placeholder product packshot without external I/O."""
    accent = (
        60 + (chrt_id * 37) % 150,
        60 + (chrt_id * 61) % 150,
        60 + (chrt_id * 83) % 150,
    )
    image = Image.new("RGB", (360, 480), "#f5f3ef")
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle(
        (55, 55, 305, 425), radius=34, fill="white", outline="#d9d3ca", width=4
    )
    draw.rounded_rectangle((118, 82, 242, 132), radius=12, fill=accent)
    draw.rounded_rectangle(
        (88, 125, 272, 390), radius=38, fill=accent, outline="#3f3f46", width=4
    )
    draw.rounded_rectangle((105, 205, 255, 320), radius=16, fill="white")
    draw.text((158, 225), "WB", fill="#4b2995", anchor="ma")
    draw.text((180, 275), f"{chrt_id}", fill="#27272a", anchor="mm")
    draw.ellipse((135, 340, 225, 375), fill="#ffffff", outline="#3f3f46", width=3)
    draw.text((180, 358), "EMU", fill="#27272a", anchor="mm")
    out = BytesIO()
    image.save(out, format="PNG", optimize=True)
    return out.getvalue()


@router.get("/products/{chrt_id}.png")
def product_image(chrt_id: int) -> Response:
    return Response(
        content=_product_png(chrt_id),
        media_type="image/png",
        headers={"Cache-Control": "public, max-age=31536000, immutable"},
    )
