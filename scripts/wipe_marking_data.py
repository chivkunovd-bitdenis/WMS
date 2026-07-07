#!/usr/bin/env python3
"""Wipe marking (ЧЗ) data for a clean re-import. Dry-run by default."""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
import uuid
from pathlib import Path

from sqlalchemy import delete, func, select, update

BACKEND_ROOT = Path(__file__).resolve().parents[1] / "backend"
sys.path.insert(0, str(BACKEND_ROOT))

from app.db.session import SessionLocal  # noqa: E402
from app.models.marking_code import (  # noqa: E402
    MarkingCode,
    MarkingCodeEvent,
    MarkingCodeImport,
    MarkingCodeImportFile,
    MarkingPool,
    MarkingPoolProduct,
    MarkingReprintRequest,
)
from app.models.packaging_task import PackagingTaskLine  # noqa: E402


async def _counts(tenant_id: uuid.UUID | None) -> dict[str, int]:
    async with SessionLocal() as session:
        tables: list[tuple[str, object]] = [
            ("marking_codes", MarkingCode),
            ("marking_code_events", MarkingCodeEvent),
            ("marking_code_imports", MarkingCodeImport),
            ("marking_code_import_files", MarkingCodeImportFile),
            ("marking_pools", MarkingPool),
            ("marking_pool_products", MarkingPoolProduct),
            ("marking_reprint_requests", MarkingReprintRequest),
        ]
        out: dict[str, int] = {}
        for name, model in tables:
            stmt = select(func.count()).select_from(model)
            if tenant_id is not None and hasattr(model, "tenant_id"):
                stmt = stmt.where(model.tenant_id == tenant_id)
            out[name] = int((await session.execute(stmt)).scalar_one())
        line_stmt = select(func.count()).select_from(PackagingTaskLine).where(
            PackagingTaskLine.qty_marking_printed > 0,
        )
        out["packaging_lines_with_marking_printed"] = int(
            (await session.execute(line_stmt)).scalar_one(),
        )
        return out


async def _wipe(tenant_id: uuid.UUID | None) -> None:
    async with SessionLocal() as session:
        if tenant_id is None:
            await session.execute(delete(MarkingReprintRequest))
            await session.execute(delete(MarkingCodeEvent))
            await session.execute(delete(MarkingCode))
            await session.execute(delete(MarkingCodeImportFile))
            await session.execute(delete(MarkingCodeImport))
            await session.execute(delete(MarkingPoolProduct))
            await session.execute(delete(MarkingPool))
        else:
            await session.execute(
                delete(MarkingReprintRequest).where(MarkingReprintRequest.tenant_id == tenant_id),
            )
            await session.execute(
                delete(MarkingCodeEvent).where(MarkingCodeEvent.tenant_id == tenant_id),
            )
            await session.execute(delete(MarkingCode).where(MarkingCode.tenant_id == tenant_id))
            await session.execute(
                delete(MarkingCodeImportFile).where(MarkingCodeImportFile.tenant_id == tenant_id),
            )
            await session.execute(
                delete(MarkingCodeImport).where(MarkingCodeImport.tenant_id == tenant_id),
            )
            await session.execute(
                delete(MarkingPoolProduct).where(MarkingPoolProduct.tenant_id == tenant_id),
            )
            await session.execute(delete(MarkingPool).where(MarkingPool.tenant_id == tenant_id))

        await session.execute(
            update(PackagingTaskLine).values(qty_marking_printed=0),
        )
        await session.commit()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--tenant-id",
        help="Limit wipe to one tenant UUID. Omit to wipe all tenants.",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Actually delete data. Without this flag: dry-run counts only.",
    )
    parser.add_argument(
        "--confirm",
        help='Required with --apply. Type exactly: WIPE-MARKING',
    )
    args = parser.parse_args()

    if not os.environ.get("DATABASE_URL"):
        print("DATABASE_URL is required", file=sys.stderr)
        return 2

    tenant_id = uuid.UUID(args.tenant_id) if args.tenant_id else None
    counts = asyncio.run(_counts(tenant_id))

    print("Marking data counts:")
    for key, value in counts.items():
        print(f"  {key}: {value}")

    if not args.apply:
        print("\nDry-run only. Re-run with --apply --confirm WIPE-MARKING to delete.")
        return 0

    if args.confirm != "WIPE-MARKING":
        print("Refusing: --confirm WIPE-MARKING is required", file=sys.stderr)
        return 2

    asyncio.run(_wipe(tenant_id))
    print("\nWiped. Users can re-import marking PDFs from scratch.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
