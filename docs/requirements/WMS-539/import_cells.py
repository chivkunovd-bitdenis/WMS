"""WMS-539: one-off import of ArtMaks storage cells from the client's layout file.

Cells are created with the standard catalog_service.create_location, so each one
gets the regular system barcode (LOC-…). Existing codes are skipped, so the
script can be re-run safely after a partial failure.

Usage (inside the API container, PYTHONPATH=/app):
  python import_cells.py NAMES_JSON TENANT_ID WAREHOUSE_ID OUT_JSON [--apply]
Without --apply nothing is written.
"""

from __future__ import annotations

import asyncio
import json
import sys
import uuid

from sqlalchemy import select

from app.db.session import SessionLocal
from app.models.storage_location import StorageLocation
from app.models.warehouse import Warehouse
from app.services.catalog_service import create_location


async def main(names_path: str, tenant: str, warehouse: str, out_path: str, apply: bool) -> int:
    names: list[str] = json.load(open(names_path, encoding="utf-8"))
    if len(names) != len(set(names)):
        print("ABORT: duplicate names in input")
        return 2
    tenant_id = uuid.UUID(tenant)
    warehouse_id = uuid.UUID(warehouse)
    async with SessionLocal() as session:
        wh = await session.get(Warehouse, warehouse_id)
        if wh is None or wh.tenant_id != tenant_id:
            print("ABORT: warehouse not found for tenant")
            return 2
        rows = (
            await session.execute(
                select(StorageLocation).where(StorageLocation.warehouse_id == warehouse_id)
            )
        ).scalars().all()
        by_code = {row.code: row for row in rows}
        lower_codes = {row.code.lower(): row.code for row in rows if row.deleted_at is None}
        existing = [n for n in names if n in by_code and by_code[n].deleted_at is None]
        deleted = [n for n in names if n in by_code and by_code[n].deleted_at is not None]
        case_clash = [n for n in names if n not in by_code and n.lower() in lower_codes]
        to_create = [n for n in names if n not in by_code]
        print(f"warehouse: {wh.name} ({wh.code})")
        print(f"cells in warehouse before: {sum(1 for r in rows if r.deleted_at is None)}")
        print(f"input names: {len(names)}; already exist: {len(existing)}; to create: {len(to_create)}")
        if deleted or case_clash:
            print(f"ABORT: deleted cells with same code {deleted[:5]}; case clashes {case_clash[:5]}")
            return 2
        if apply:
            for i, name in enumerate(to_create, 1):
                await create_location(session, tenant_id, warehouse_id, code=name)
                if i % 100 == 0:
                    print(f"  created {i}/{len(to_create)}")
            print(f"created: {len(to_create)}")
        final = {
            row.code: row
            for row in (
                await session.execute(
                    select(StorageLocation).where(
                        StorageLocation.warehouse_id == warehouse_id,
                        StorageLocation.deleted_at.is_(None),
                    )
                )
            ).scalars().all()
        }
        present = [n for n in names if n in final]
        print(f"of input names present now: {len(present)} / {len(names)}")
        print(f"cells in warehouse after: {len(final)}")
        json.dump(
            [{"code": n, "barcode": final[n].barcode} for n in present],
            open(out_path, "w", encoding="utf-8"),
            ensure_ascii=False,
        )
    return 0


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if a != "--apply"]
    sys.exit(asyncio.run(main(*args, apply="--apply" in sys.argv)))
