"""CLI: восстановление обрезанных КИЗ пула маркировки (I5).

До фикса `_canonical_cis_from_match` (backend/app/services/marking_code_service.py)
импорт PDF продавца сохранял код маркировки без GS-разделителя после
серийного номера — Wildberries отклоняет такую поставку ошибкой "sgtinNoGS".
Эта команда безопасно чинит уже накопленные в боевой базе строки: достаёт
полный код заново из PDF продавца, сохранённого при импорте, и заменяет им
обрезанный `cis_code` — только когда полный код действительно найден и не
конфликтует с уже существующей строкой. Ничего не удаляет и не перезаписывает
там, где GS-разделитель уже есть. Идемпотентна — можно гонять повторно.

Использование:

    python -m app.cli.restore_truncated_marking_cis [--dry-run] [--tenant-id UUID]
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import uuid

from app.db.session import SessionLocal
from app.services.marking_code_service import restore_truncated_pool_cis_codes

logging.basicConfig(level=logging.INFO)


async def _run(*, tenant_id: uuid.UUID | None, dry_run: bool) -> dict[str, object]:
    async with SessionLocal() as session:
        report = await restore_truncated_pool_cis_codes(
            session,
            tenant_id=tenant_id,
            dry_run=dry_run,
        )
        if not dry_run:
            await session.commit()
    return {
        "dry_run": dry_run,
        "tenant_id": str(tenant_id) if tenant_id else None,
        "scanned": report.scanned,
        "restored": report.restored,
        "by_outcome": report.counts_by_outcome(),
        "rows": [
            {
                "code_id": str(row.code_id),
                "tenant_id": str(row.tenant_id),
                "import_batch_id": str(row.import_batch_id) if row.import_batch_id else None,
                "cis_masked": row.cis_masked,
                "outcome": row.outcome,
                "detail": row.detail,
            }
            for row in report.rows
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Только посчитать, что было бы восстановлено, без записи в базу.",
    )
    parser.add_argument(
        "--tenant-id",
        type=str,
        default=None,
        help="Ограничить восстановление одним тенантом (UUID). По умолчанию — все.",
    )
    args = parser.parse_args()
    tenant_id = uuid.UUID(args.tenant_id) if args.tenant_id else None
    summary = asyncio.run(_run(tenant_id=tenant_id, dry_run=args.dry_run))
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
