from __future__ import annotations

import hashlib
import logging
import re
import uuid
from dataclasses import dataclass
from pathlib import Path

from app.services.object_storage_service import get_object_storage_backend

logger = logging.getLogger(__name__)

MARKING_IMPORT_SUBDIR = "marking-imports"


@dataclass(frozen=True)
class StoredMarkingImportFile:
    file_id: uuid.UUID
    original_filename: str
    storage_key: str
    size_bytes: int
    sha256_hex: str
    content_type: str


def is_pdf_import_filename(filename: str) -> bool:
    return filename.lower().endswith(".pdf")


def build_marking_import_storage_key(
    *,
    tenant_id: uuid.UUID,
    import_batch_id: uuid.UUID,
    file_id: uuid.UUID,
) -> str:
    rel_dir = Path(MARKING_IMPORT_SUBDIR) / str(tenant_id) / str(import_batch_id)
    return str(rel_dir / f"{file_id}.pdf").replace("\\", "/")


def save_marking_import_source_pdf(
    *,
    tenant_id: uuid.UUID,
    import_batch_id: uuid.UUID,
    original_filename: str,
    content: bytes,
    file_id: uuid.UUID | None = None,
) -> StoredMarkingImportFile:
    if not content:
        raise ValueError("empty_pdf")
    if not content.startswith(b"%PDF"):
        raise ValueError("not_a_pdf")

    backend = get_object_storage_backend()
    if backend is None:
        raise RuntimeError("object_storage_not_configured")

    stored_id = file_id or uuid.uuid4()
    sha256_hex = hashlib.sha256(content).hexdigest()
    storage_key = build_marking_import_storage_key(
        tenant_id=tenant_id,
        import_batch_id=import_batch_id,
        file_id=stored_id,
    )
    backend.put_bytes(storage_key, content, content_type="application/pdf")

    safe_name = Path(original_filename).name.strip() or "upload.pdf"
    return StoredMarkingImportFile(
        file_id=stored_id,
        original_filename=safe_name[:512],
        storage_key=storage_key,
        size_bytes=len(content),
        sha256_hex=sha256_hex,
        content_type="application/pdf",
    )


def read_marking_import_source_pdf(storage_key: str) -> bytes:
    backend = get_object_storage_backend()
    if backend is None:
        raise RuntimeError("object_storage_not_configured")
    return backend.get_bytes(storage_key)


def sanitize_storage_filename(filename: str) -> str:
    base = Path(filename).name.strip() or "upload.pdf"
    safe = re.sub(r"[^A-Za-z0-9._-]+", "_", base).strip("._") or "upload.pdf"
    if not safe.lower().endswith(".pdf"):
        safe = f"{safe}.pdf"
    return safe[:200]
