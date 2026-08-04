"""Safe on-disk storage for FBS print assets (PNG); paths never exposed in API."""

from __future__ import annotations

import base64
import binascii
import hashlib
import uuid
from pathlib import Path

from app.core.settings import settings

PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
ORDER_STICKER_WIDTH_MM = 58
ORDER_STICKER_HEIGHT_MM = 40
ORDER_STICKER_CONTENT_TYPE = "image/png"

PRINT_ASSET_SUBDIR_ORDER_STICKER = "fbs-print-assets/order-stickers"
PRINT_ASSET_SUBDIR_CARGO_QR = "fbs-print-assets/cargo-place-qr"
PRINT_ASSET_SUBDIR_SUPPLY_QR = "fbs-print-assets/supply-qr"

_ALLOWED_SUBDIRS = frozenset(
    {
        PRINT_ASSET_SUBDIR_ORDER_STICKER,
        PRINT_ASSET_SUBDIR_CARGO_QR,
        PRINT_ASSET_SUBDIR_SUPPLY_QR,
        "fbs-stickers",
        "fbs-trbx-stickers",
        "fbs-supply-barcodes",
    }
)


class FbsPrintAssetStorageError(Exception):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


def _data_root() -> Path:
    return Path(settings.wms_data_dir).resolve()


def _storage_root(subdir: str) -> Path:
    if subdir not in _ALLOWED_SUBDIRS:
        raise FbsPrintAssetStorageError("invalid_storage_subdir")
    return (_data_root() / subdir).resolve()


def validate_relative_storage_path(rel: str, *, subdir: str) -> Path:
    """Resolve relative path under wms_data_dir; reject traversal and absolute paths."""
    if not rel or not isinstance(rel, str):
        raise FbsPrintAssetStorageError("invalid_storage_path")
    normalized = rel.replace("\\", "/").strip()
    if normalized.startswith("/") or ".." in Path(normalized).parts:
        raise FbsPrintAssetStorageError("invalid_storage_path")
    root = _storage_root(subdir)
    target = (_data_root() / normalized).resolve()
    if root not in target.parents and target != root:
        raise FbsPrintAssetStorageError("invalid_storage_path")
    return target


def resolve_existing_storage_path(rel: str) -> Path:
    """Resolve a stored relative path against any allowed print-asset subdir."""
    if not rel or not isinstance(rel, str):
        raise FbsPrintAssetStorageError("invalid_storage_path")
    normalized = rel.replace("\\", "/").strip()
    if normalized.startswith("/") or ".." in Path(normalized).parts:
        raise FbsPrintAssetStorageError("invalid_storage_path")
    for subdir in _ALLOWED_SUBDIRS:
        try:
            return validate_relative_storage_path(normalized, subdir=subdir)
        except FbsPrintAssetStorageError:
            continue
    raise FbsPrintAssetStorageError("invalid_storage_path")


def order_sticker_relative_path(order_id: uuid.UUID) -> str:
    return f"{PRINT_ASSET_SUBDIR_ORDER_STICKER}/{order_id}.png"


def cargo_qr_relative_path(trbx_id: uuid.UUID) -> str:
    return f"{PRINT_ASSET_SUBDIR_CARGO_QR}/{trbx_id}.png"


def supply_qr_relative_path(supply_id: uuid.UUID) -> str:
    return f"{PRINT_ASSET_SUBDIR_SUPPLY_QR}/{supply_id}.png"


def decode_png_payload(raw: object) -> bytes | None:
    """Decode WB sticker payload; never treat a filesystem path as base64."""
    if raw is None:
        return None
    if isinstance(raw, bytes):
        payload = raw
    elif isinstance(raw, str):
        payload_str = raw.strip()
        if not payload_str:
            return None
        if payload_str.startswith("fbs-") or payload_str.startswith("/"):
            return None
        if payload_str.startswith("data:"):
            comma = payload_str.find(",")
            if comma == -1:
                return None
            payload_str = payload_str[comma + 1 :]
        try:
            payload = base64.b64decode(payload_str, validate=True)
        except (binascii.Error, ValueError):
            return None
    else:
        return None
    return payload if payload else None


def validate_png_bytes(png_bytes: bytes) -> None:
    if not png_bytes:
        raise FbsPrintAssetStorageError("empty_content")
    if not png_bytes.startswith(PNG_MAGIC):
        raise FbsPrintAssetStorageError("invalid_content_type")


def sha256_checksum(png_bytes: bytes) -> str:
    digest = hashlib.sha256(png_bytes).hexdigest()
    return f"sha256:{digest}"


def verify_checksum(png_bytes: bytes, checksum: str | None) -> None:
    if not checksum:
        return
    expected = sha256_checksum(png_bytes)
    if checksum != expected:
        raise FbsPrintAssetStorageError("checksum_mismatch")


def save_png(relative_path: str, png_bytes: bytes) -> str:
    validate_png_bytes(png_bytes)
    normalized = relative_path.replace("\\", "/")
    parts = normalized.split("/")
    if len(parts) < 2:
        raise FbsPrintAssetStorageError("invalid_storage_path")
    subdir = "/".join(parts[:-1])
    target = validate_relative_storage_path(normalized, subdir=subdir)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(png_bytes)
    return relative_path.replace("\\", "/")


def read_png(relative_path: str, *, checksum: str | None = None) -> bytes:
    target = resolve_existing_storage_path(relative_path)
    if not target.is_file():
        raise FbsPrintAssetStorageError("file_missing")
    png_bytes = target.read_bytes()
    validate_png_bytes(png_bytes)
    verify_checksum(png_bytes, checksum)
    return png_bytes
