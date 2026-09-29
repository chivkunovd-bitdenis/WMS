#!/usr/bin/env python3
"""WMS-552: bind ArtMaks printed QR codes and create six approved missing cells.

Run from backend: python scripts/artmaks_cell_qr_mapping.py --tenant-id UUID < cells.csv
Add --apply to commit; the default only validates and prints the proposed mapping.
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import io
import json
import sys
from pathlib import Path
from typing import Any
from uuid import UUID

if "__file__" in globals():
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select

from app.db.session import SessionLocal
from app.models.storage_location import StorageLocation
from app.models.warehouse import Warehouse

WAREHOUSE_ID = UUID("5740eda2-b353-4c98-9755-0f2df4e862bc")
TENANT_ID = UUID("82b36645-8662-497f-9631-a0743994632c")
ALLOWED_MISSING = {f"{letter}-5-22" for letter in "АБВГДЕ"}


def parse_mapping(raw: bytes) -> dict[str, str]:
    rows = csv.reader(io.StringIO(raw.decode("utf-8-sig")), delimiter=";")
    mapping: dict[str, str] = {}
    seen_barcodes: set[str] = set()
    for number, row in enumerate(rows, start=1):
        if number == 1 and row == ["address", "barcode"]:
            continue
        if len(row) != 2:
            raise ValueError(f"CSV row {number}: expected address;barcode")
        address, barcode = (value.strip() for value in row)
        if not address or not barcode or len(address) > 64 or len(barcode) > 64:
            raise ValueError(f"CSV row {number}: invalid address or barcode length")
        if address in mapping:
            raise ValueError(f"CSV row {number}: duplicate address {address}")
        if barcode in seen_barcodes:
            raise ValueError(f"CSV row {number}: duplicate barcode {barcode}")
        mapping[address] = barcode
        seen_barcodes.add(barcode)
    if len(mapping) != 882:
        raise ValueError(f"Expected 882 CSV mappings, got {len(mapping)}")
    return mapping


async def run(mapping: dict[str, str], *, tenant_id: UUID, apply: bool) -> dict[str, Any]:
    async with SessionLocal() as session, session.begin():
        warehouse = await session.get(Warehouse, WAREHOUSE_ID)
        if tenant_id != TENANT_ID or warehouse is None or warehouse.tenant_id != tenant_id:
            raise ValueError("ArtMaks warehouse ID does not belong to the specified tenant")
        query = select(StorageLocation).where(
            StorageLocation.tenant_id == tenant_id,
            StorageLocation.warehouse_id == WAREHOUSE_ID,
            StorageLocation.code.in_(mapping),
            StorageLocation.deleted_at.is_(None),
        ).order_by(StorageLocation.id)
        if apply:
            query = query.with_for_update()
        cells = list((await session.scalars(query)).all())
        by_address = {cell.code: cell for cell in cells}
        missing = set(mapping) - set(by_address)
        if not ((len(cells) == 876 and missing == ALLOWED_MISSING)
                or (len(cells) == 882 and not missing)):
            raise ValueError(
                f"Expected 876 cells plus six approved additions, or 882 on replay; "
                f"found {len(cells)}, missing {sorted(missing)}"
            )
        # Include archived cells and other warehouses: barcodes are tenant-unique.
        occupied = list((await session.scalars(select(StorageLocation).where(
            StorageLocation.tenant_id == tenant_id,
            StorageLocation.barcode.in_(mapping.values()),
        ))).all())
        address_for_barcode = {barcode: address for address, barcode in mapping.items()}
        for cell in occupied:
            wanted = by_address.get(address_for_barcode[cell.barcode])
            if wanted is None or wanted.id != cell.id:
                raise ValueError(
                    f"Barcode collision: {cell.barcode} already belongs to cell {cell.id}"
                )
        audit: list[dict[str, Any]] = [
            {"id": str(cell.id), "code": cell.code,
             "before": cell.barcode, "after": mapping[cell.code]}
            for cell in sorted(cells, key=lambda cell: cell.code)
        ]
        changed = sum(row["before"] != row["after"] for row in audit)
        if apply:
            for cell in cells:
                cell.barcode = mapping[cell.code]
            for address in sorted(missing):
                cell = StorageLocation(
                    tenant_id=tenant_id, warehouse_id=WAREHOUSE_ID,
                    code=address, barcode=mapping[address],
                )
                session.add(cell)
                await session.flush()
                audit.append({"id": str(cell.id), "code": address,
                              "before": None, "after": mapping[address]})
            await session.flush()
        result = {
            "mode": "applied" if apply else "dry-run",
            "tenant_id": str(tenant_id), "warehouse_id": str(WAREHOUSE_ID),
            "warehouse_name": warehouse.name,
            "csv_rows": len(mapping), "matched": len(cells),
            "changed": changed, "unchanged": len(cells) - changed,
            "created" if apply else "to_create": sorted(missing), "mappings": audit,
        }
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tenant-id", type=UUID, required=True)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    try:
        data = parse_mapping(sys.stdin.buffer.read())
        report = asyncio.run(run(data, tenant_id=args.tenant_id, apply=args.apply))
    except ValueError as exc:
        parser.exit(1, f"Preflight rejected: {exc}\n")
    print(json.dumps(report, ensure_ascii=False))
