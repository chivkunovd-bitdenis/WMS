from __future__ import annotations

import uuid
from collections import Counter
from typing import Any

import fitz
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.marking_code import (
    MarkingCode,
    MarkingCodeImport,
    MarkingCodeImportFile,
)
from app.services.marking_datamatrix_service import decode_datamatrix_codes_on_pdf_page
from app.services.marking_import_storage_service import read_marking_import_source_pdf


def read_source_pdf(storage_key: str) -> bytes:
    """Read one preserved import artifact; split out for a read-only audit stub."""
    return read_marking_import_source_pdf(storage_key)


def _decode_pdf(pdf_bytes: bytes) -> list[str]:
    with fitz.open(stream=pdf_bytes, filetype="pdf") as document:
        return [
            decoded.value
            for page in document
            for decoded in decode_datamatrix_codes_on_pdf_page(page)
        ]


def _source_contains_saved_payloads(source: list[str], saved: list[str]) -> bool:
    """Treat duplicates/unassigned source rows as valid skipped import input."""
    return not (Counter(saved) - Counter(source))


async def audit_marking_import(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    import_id: uuid.UUID,
    *,
    final_print_pdf: bytes | None,
) -> dict[str, Any]:
    """Compare preserved evidence without changing or recreating any artifact."""
    batch = await session.get(MarkingCodeImport, import_id)
    if batch is None or batch.tenant_id != tenant_id:
        raise ValueError("import_not_found")

    source_files = list(
        (
            await session.scalars(
                select(MarkingCodeImportFile)
                .where(
                    MarkingCodeImportFile.tenant_id == tenant_id,
                    MarkingCodeImportFile.import_batch_id == import_id,
                )
                .order_by(MarkingCodeImportFile.created_at, MarkingCodeImportFile.id)
            )
        ).all()
    )
    evidence_gaps: list[str] = []
    source_payloads: list[str] = []
    if not source_files:
        evidence_gaps.append("source_pdf")
    else:
        for source_file in source_files:
            try:
                decoded_source = _decode_pdf(read_source_pdf(source_file.storage_key))
                if not decoded_source:
                    evidence_gaps.append("source_pdf")
                    evidence_gaps.append(f"source_pdf:{source_file.id}")
                    break
                source_payloads.extend(decoded_source)
            except Exception:
                evidence_gaps.append("source_pdf")
                evidence_gaps.append(f"source_pdf:{source_file.id}")
                break

    codes = list(
        (
            await session.scalars(
                select(MarkingCode)
                .where(
                    MarkingCode.tenant_id == tenant_id,
                    MarkingCode.import_batch_id == import_id,
                )
                .order_by(MarkingCode.created_at, MarkingCode.id)
            )
        ).all()
    )
    saved_payloads = [code.cis_code for code in codes]
    artifact_payloads: list[str] = []
    code_rows: list[dict[str, object]] = []
    artifact_mismatch = False
    for code in codes:
        decoded_artifact: list[str] = []
        if code.label_artifact_pdf:
            try:
                decoded_artifact = _decode_pdf(code.label_artifact_pdf)
            except Exception:
                evidence_gaps.append(f"label_artifact_pdf:{code.id}")
                artifact_mismatch = True
            else:
                if not decoded_artifact:
                    evidence_gaps.append(f"label_artifact_pdf:{code.id}")
                    artifact_mismatch = True
        else:
            if code.label_artifact_required:
                evidence_gaps.append(f"label_artifact_pdf:{code.id}")
                artifact_mismatch = True
        artifact_payloads.extend(decoded_artifact)
        if decoded_artifact and decoded_artifact != [code.cis_code]:
            artifact_mismatch = True
        code_rows.append(
            {
                "id": str(code.id),
                "cis_code": code.cis_code,
                "product_id": str(code.product_id) if code.product_id is not None else None,
                "pool_id": str(code.pool_id) if code.pool_id is not None else None,
                "artifact_payloads": decoded_artifact,
            }
        )

    final_payloads: list[str] | None = None
    final_artifact_invalid = False
    if final_print_pdf is not None:
        try:
            final_payloads = _decode_pdf(final_print_pdf)
        except Exception:
            evidence_gaps.append("final_print_pdf")
            final_artifact_invalid = True
        else:
            if not final_payloads:
                evidence_gaps.append("final_print_pdf")
                final_artifact_invalid = True

    first_divergence: str | None = None
    source_evidence_complete = not any(
        gap == "source_pdf" or gap.startswith("source_pdf:") for gap in evidence_gaps
    )
    if (
        source_evidence_complete
        and source_payloads
        and (
            len(saved_payloads) != batch.accepted_count
            or not _source_contains_saved_payloads(source_payloads, saved_payloads)
        )
    ):
        first_divergence = "saved_cis"
    elif artifact_mismatch:
        first_divergence = "label_artifact_pdf"
    elif final_artifact_invalid or (
        final_payloads is not None and final_payloads != saved_payloads
    ):
        first_divergence = "final_print_pdf"

    return {
        "import_id": str(import_id),
        "first_divergence": first_divergence,
        "source_payloads": source_payloads,
        "saved_payloads": saved_payloads,
        "artifact_payloads": artifact_payloads,
        "final_print_payloads": final_payloads,
        "evidence_gaps": list(dict.fromkeys(evidence_gaps)),
        "codes": code_rows,
    }
