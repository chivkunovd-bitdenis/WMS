"""Restore imported KIZ identifiers from their own saved DataMatrix artifacts.

Defaults to read-only reporting. Applying requires --apply and an explicit tenant;
only proven, currently available and unbound codes may change. This command does
not determine marketplace validity and never synthesizes a crypto tail.

python -m app.cli.restore_truncated_marking_cis --tenant-id UUID [--code-id UUID] [--apply]
"""

from __future__ import annotations

import argparse
import asyncio
import json
import uuid

from app.services.marking_code_service import restore_truncated_pool_cis_codes


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tenant-id", type=uuid.UUID, required=True)
    parser.add_argument("--code-id", type=uuid.UUID, action="append", dest="code_ids")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", help="Report only (the default).")
    mode.add_argument("--apply", action="store_true", help="Apply verified restorations.")
    args = parser.parse_args()
    report = asyncio.run(
        restore_truncated_pool_cis_codes(
            tenant_id=args.tenant_id,
            apply=args.apply,
            code_ids=args.code_ids,
        )
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
