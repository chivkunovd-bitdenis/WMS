"""Chat attachment storage — thin wrapper on top of object_storage_service.

Storage layout: ``chat/<tenant_id>/<attachment_id>/<safe_filename>``.
For local development the LocalObjectStorage backend rejects paths that
escape the configured root. For S3 the same key is prefixed automatically.
Nothing here interprets the raw bytes; images vs generic files are chosen
by the caller (based on content-type sniff and paste flow).
"""

from __future__ import annotations

import re
import uuid

from app.services.object_storage_service import (
    LocalObjectStorage,
    ObjectStorageBackend,
    get_object_storage_backend,
)


_SAFE_FILENAME_RE = re.compile(r"[^A-Za-z0-9._-]+")

# 25 MB per file per contract §Одно минимальное решение владельца.
MAX_ATTACHMENT_BYTES = 25 * 1024 * 1024
# 100 MB total per message.
MAX_MESSAGE_TOTAL_BYTES = 100 * 1024 * 1024
# 10 files per message.
MAX_MESSAGE_ATTACHMENTS = 10

IMAGE_CONTENT_TYPES = frozenset(
    {"image/png", "image/jpeg", "image/gif", "image/webp", "image/bmp", "image/svg+xml"}
)


class ChatStorageUnavailable(RuntimeError):
    pass


def _safe_filename(raw: str) -> str:
    stripped = raw.strip().replace("/", "_").replace("\\", "_")
    cleaned = _SAFE_FILENAME_RE.sub("_", stripped) or "file"
    return cleaned[:200]


def build_storage_key(tenant_id: uuid.UUID, attachment_id: uuid.UUID, filename: str) -> str:
    return f"chat/{tenant_id}/{attachment_id}/{_safe_filename(filename)}"


def get_backend() -> ObjectStorageBackend:
    backend = get_object_storage_backend()
    if backend is None:
        # Fall back to a local storage under WMS_DATA_DIR so dev deployments
        # without S3 still work; production is expected to configure a real
        # backend either way.
        from app.core.settings import settings

        backend = LocalObjectStorage(settings.wms_data_dir)
    return backend


def put_bytes(storage_key: str, content: bytes, *, content_type: str) -> None:
    backend = get_backend()
    backend.put_bytes(storage_key, content, content_type=content_type)


def get_bytes(storage_key: str) -> bytes:
    backend = get_backend()
    return backend.get_bytes(storage_key)


def delete_object(storage_key: str) -> None:
    backend = get_backend()
    backend.delete_object(storage_key)


def is_image_content_type(content_type: str) -> bool:
    return content_type.lower() in IMAGE_CONTENT_TYPES
