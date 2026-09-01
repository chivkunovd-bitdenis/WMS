#!/usr/bin/env python3
"""Dry-run/apply current loose stock reattachment to original inbound boxes."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from dataclasses import asdict
from pathlib import Path
from uuid import UUID

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT / "backend") not in sys.path:
    sys.path.insert(0, str(ROOT / "backend"))

from app.db.session import SessionLocal  # noqa: E402
from app.services.inbound_box_reconciliation_service import (  # noqa: E402
    apply_reconciliation_plan,
    build_reconciliation_plan,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--request-id", type=UUID, required=True)
    parser.add_argument("--storage-location-id", type=UUID, required=True)
    parser.add_argument("--actor-user-id", type=UUID)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--include-allocations", action="store_true")
    return parser


async def _run(args: argparse.Namespace) -> None:
    async with SessionLocal() as session:
        if args.apply:
            plan = await apply_reconciliation_plan(
                session,
                request_id=args.request_id,
                storage_location_id=args.storage_location_id,
                actor_user_id=args.actor_user_id,
            )
        else:
            plan = await build_reconciliation_plan(
                session,
                request_id=args.request_id,
                storage_location_id=args.storage_location_id,
            )
        payload = asdict(plan)
        if not args.include_allocations:
            payload.pop("allocations", None)
        payload["mode"] = "applied" if args.apply else "dry-run"
        payload["changed_lines"] = sum(
            1 for allocation in plan.allocations if allocation.delta != 0
        )
        print(json.dumps(payload, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    asyncio.run(_run(_parser().parse_args()))
