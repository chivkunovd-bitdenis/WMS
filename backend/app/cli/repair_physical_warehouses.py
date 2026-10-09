"""WMS-516 maintenance command. No marketplace call is part of the data transaction.

python -m app.cli.repair_physical_warehouses prepare --run UUID --tenant UUID
    --source UUID [--target UUID]
python -m app.cli.repair_physical_warehouses apply|verify|rollback --run UUID
python -m app.cli.repair_physical_warehouses run-map --tenant UUID --map path/to/map.json

``run-map`` is a thin convenience loop over the same prepare/apply/verify
calls above, for a tenant with several legacy warehouses to migrate (WMS-516
review P3-2: without it, a tenant with N legacy warehouses needs N manual
prepare->apply pairs run back to back). It does not change the run/manifest
model: every entry still gets its own fresh run UUID and goes through the
exact same reviewed prepare -> apply -> verify -> publish sequence, one entry
at a time, so a blocked or ambiguous source only stops that one entry, not
the whole map. The map file is a JSON list::

    [{"source": "<legacy warehouse UUID>", "target": "<physical warehouse UUID, optional>"}, ...]

``target`` is optional exactly like ``--target`` on a single ``prepare`` call:
omit it when the tenant has one physical warehouse (it is found
automatically); an ambiguous tenant needs it filled in from the owner's map.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import uuid

from app.db.session import SessionLocal
from app.services import physical_warehouse_repair_service as repair


async def _run_map(tenant_id: uuid.UUID, map_path: str) -> list[dict[str, object]]:
    with open(map_path, encoding="utf-8") as handle:
        entries = json.load(handle)
    summary: list[dict[str, object]] = []
    for entry in entries:
        source_id = uuid.UUID(entry["source"])
        target_id = uuid.UUID(entry["target"]) if entry.get("target") else None
        run_id = uuid.uuid4()
        entry_result: dict[str, object] = {
            "source": str(source_id), "target": str(target_id) if target_id else None,
            "run": str(run_id),
        }
        async with SessionLocal() as session, session.begin():
            entry_result["prepare"] = await repair.prepare(
                session, run_id=run_id, tenant_id=tenant_id,
                source_id=source_id, target_id=target_id,
            )
        if entry_result["prepare"]["status"] == "prepared":
            async with SessionLocal() as session, session.begin():
                entry_result["apply"] = await repair.apply(session, run_id)
            async with SessionLocal() as session, session.begin():
                entry_result["verify"] = await repair.verify(session, run_id)
            if entry_result["apply"]["status"] == "completed":
                from app.services.physical_warehouse_repair_publish import publish

                entry_result["publish"] = await publish(run_id)
        summary.append(entry_result)
    return summary


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "action", choices=["prepare", "apply", "verify", "rollback", "publish", "run-map"]
    )
    parser.add_argument("--run", type=uuid.UUID)
    parser.add_argument("--tenant", type=uuid.UUID)
    parser.add_argument("--source", type=uuid.UUID)
    parser.add_argument("--target", type=uuid.UUID)
    parser.add_argument("--map", dest="map_path")
    args = parser.parse_args()

    if args.action == "run-map":
        if not args.tenant or not args.map_path:
            parser.error("run-map requires --tenant and --map")
        summary = await _run_map(args.tenant, args.map_path)
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return

    if args.action == "publish":
        if not args.run:
            parser.error("publish requires --run")
        from app.services.physical_warehouse_repair_publish import publish

        print(json.dumps(await publish(args.run), ensure_ascii=False, indent=2))
        return

    if not args.run:
        parser.error(f"{args.action} requires --run")
    async with SessionLocal() as session, session.begin():
        if args.action == "prepare":
            if not args.tenant or not args.source:
                parser.error("prepare requires --tenant and --source")
            result = await repair.prepare(session, run_id=args.run, tenant_id=args.tenant,
                                          source_id=args.source, target_id=args.target)
        else:
            result = await getattr(repair, args.action)(session, args.run)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if args.action == "apply" and result["status"] == "completed":
        from app.services.physical_warehouse_repair_publish import publish

        print(json.dumps(await publish(args.run), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
