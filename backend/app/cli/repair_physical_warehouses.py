"""WMS-516 maintenance command. No marketplace call is part of the data transaction.

python -m app.cli.repair_physical_warehouses prepare --run UUID --tenant UUID
    --source UUID [--target UUID]
python -m app.cli.repair_physical_warehouses apply|verify|rollback --run UUID
"""

from __future__ import annotations

import argparse
import asyncio
import json
import uuid

from app.db.session import SessionLocal
from app.services import physical_warehouse_repair_service as repair


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["prepare", "apply", "verify", "rollback", "publish"])
    parser.add_argument("--run", type=uuid.UUID, required=True)
    parser.add_argument("--tenant", type=uuid.UUID)
    parser.add_argument("--source", type=uuid.UUID)
    parser.add_argument("--target", type=uuid.UUID)
    args = parser.parse_args()
    if args.action == "publish":
        from app.services.physical_warehouse_repair_publish import publish

        print(json.dumps(await publish(args.run), ensure_ascii=False, indent=2))
        return
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
