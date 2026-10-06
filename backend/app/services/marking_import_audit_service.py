from __future__ import annotations

import hashlib
import json
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
from app.services.marking_label_artifact_service import extract_label_artifacts_from_pdf


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


def _relative_rect(rect: fitz.Rect, page: fitz.Page) -> tuple[float, float, float, float]:
    """Return a page-position signature that survives proportional scaling."""
    page_rect = page.rect
    if not page_rect.width or not page_rect.height:
        return (0.0, 0.0, 0.0, 0.0)
    return tuple(
        round(value, 4)
        for value in (
            (rect.x0 - page_rect.x0) / page_rect.width,
            (rect.y0 - page_rect.y0) / page_rect.height,
            rect.width / page_rect.width,
            rect.height / page_rect.height,
        )
    )


def _layout_signatures(pdf_bytes: bytes) -> list[str]:
    """Describe visible label structure without treating a payload match as layout proof.

    Coordinates are relative so the permitted proportional print scaling does
    not itself create a divergence.  Text, embedded-image placement, and
    vector drawing placement make a newly composed label distinguishable from
    an imported label that happens to encode the same DataMatrix value. Image
    bytes are part of the evidence too: position alone cannot establish that
    a rasterized supplier label was not replaced.
    """
    signatures: list[str] = []
    with fitz.open(stream=pdf_bytes, filetype="pdf") as document:
        for page in document:
            text_blocks = [
                (" ".join(str(block[4]).split()), _relative_rect(fitz.Rect(block[:4]), page))
                for block in page.get_text("blocks", sort=True)
                if len(block) >= 5 and str(block[4]).strip()
            ]
            images = sorted(
                (
                    _relative_rect(rect, page),
                    hashlib.sha256(document.extract_image(int(image[0]))["image"]).hexdigest(),
                )
                for image in page.get_images(full=True)
                for rect in page.get_image_rects(int(image[0]))
            )
            drawing_rects = sorted(
                _relative_rect(rect, page)
                for drawing in page.get_drawings()
                if isinstance((rect := drawing.get("rect")), fitz.Rect)
            )
            signatures.append(
                json.dumps(
                    {
                        "ratio": round(page.rect.width / page.rect.height, 4)
                        if page.rect.height
                        else 0.0,
                        "text": text_blocks,
                        "images": images,
                        "drawings": drawing_rects,
                    },
                    ensure_ascii=False,
                    separators=(",", ":"),
                )
            )
    return signatures


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
    source_layouts: dict[str, list[str]] = {}
    if not source_files:
        evidence_gaps.append("source_pdf")
    else:
        for source_file in source_files:
            try:
                source_pdf = read_source_pdf(source_file.storage_key)
                decoded_source = _decode_pdf(source_pdf)
                if not decoded_source:
                    evidence_gaps.append("source_pdf")
                    evidence_gaps.append(f"source_pdf:{source_file.id}")
                    break
                source_payloads.extend(decoded_source)
                # Use the same evidence-based label boundaries as ingestion.
                # Whole-sheet coordinates cannot be compared with a cropped
                # label. Match the extracted region by its full payload, not
                # by page count or an arbitrary permitted crop.
                for label in extract_label_artifacts_from_pdf(source_pdf):
                    if label.code_valid:
                        source_layouts.setdefault(label.cis, []).extend(
                            _layout_signatures(label.label_pdf)
                        )
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
    artifact_layouts: list[str] = []
    source_layout_mismatch = False
    code_rows: list[dict[str, object]] = []
    artifact_mismatch = False
    for code in codes:
        decoded_artifact: list[str] = []
        if code.label_artifact_pdf:
            try:
                decoded_artifact = _decode_pdf(code.label_artifact_pdf)
                code_layouts = _layout_signatures(code.label_artifact_pdf)
                artifact_layouts.extend(code_layouts)
                source_candidates = source_layouts.get(code.cis_code, [])
                if source_candidates:
                    if len(code_layouts) != 1 or len(set(source_candidates)) != 1:
                        evidence_gaps.append("source_to_artifact_layout")
                    elif code_layouts[0] != source_candidates[0]:
                        source_layout_mismatch = True
                elif source_layouts:
                    evidence_gaps.append("source_to_artifact_layout")
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
    final_layouts: list[str] | None = None
    final_artifact_invalid = False
    if final_print_pdf is None:
        # Lack of the actual final print artifact is not evidence that the
        # print matched the preserved import.
        evidence_gaps.append("final_print_pdf")
    else:
        try:
            final_payloads = _decode_pdf(final_print_pdf)
            final_layouts = _layout_signatures(final_print_pdf)
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
    if source_evidence_complete and source_payloads and not source_layouts:
        evidence_gaps.append("source_to_artifact_layout")
    if (
        source_evidence_complete
        and source_payloads
        and (
            len(saved_payloads) != batch.accepted_count
            or not _source_contains_saved_payloads(source_payloads, saved_payloads)
        )
    ):
        first_divergence = "saved_cis"
    elif source_evidence_complete and source_layout_mismatch:
        evidence_gaps.append("label_artifact_pdf")
        first_divergence = "label_artifact_pdf"
    elif artifact_mismatch:
        first_divergence = "label_artifact_pdf"
    elif final_artifact_invalid or (
        final_payloads is not None and final_payloads != saved_payloads
    ):
        first_divergence = "final_print_pdf"
    elif final_layouts is not None and any(
        signature not in artifact_layouts for signature in final_layouts
    ):
        # A DataMatrix value can survive a fresh render while the supplier's
        # label format is lost.  Report that evidence gap explicitly rather
        # than treating payload equality as a successful investigation.
        evidence_gaps.append("final_print_layout")
        first_divergence = "final_print_layout"

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
