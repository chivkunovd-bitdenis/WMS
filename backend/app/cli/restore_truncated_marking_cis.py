"""CLI: восстановление обрезанных КИЗ пула маркировки (I5, I5-2).

Импорт PDF продавца исторически сохранял код маркировки обрезанным —
"01<gtin>21<serial>" без GS-разделителя после серийного номера, а один более
ранний прогон этой же команды чинил это недостаточно: дописывал GS-разделитель,
«досочиненный» из текста PDF, но без ключа проверки (тег 91), который WB
требует даже у короткого формата (см. tasks/fbs-marketplace-orders/wb-docs/
04-labeling/kiz-common-errors.md, «Короткий и длинный КИЗ»). Оба варианта
Wildberries отклоняет ошибкой "sgtinNoGS" или эквивалентной структурной
ошибкой, как только код доходит до реальной поставки.

Единственный источник ПОЛНОГО кода — не текст PDF (там никогда нет ни ключа
проверки, ни криптохвоста), а сама картинка DataMatrix на этикетке. Эта
команда рендерит PDF-этикетку в растр и распознаёт код с картинки
(`app.services.marking_datamatrix_service`, библиотека `zxing-cpp`), проверяет,
что распознанный код относится к тому же товару (совпадает начало
"01<GTIN>21<серийник>" с уже сохранённым обрезанным значением), и только тогда
заменяет им `cis_code`.

Идемпотентна: код, который уже несёт GS-разделитель и ключ проверки, не
попадёт в выборку кандидатов повторно. Не трогает коды не в статусе
«доступен» (уже привязанные к заказу, напечатанные, применённые и т.д.) —
при привязке значение копируется отдельной строкой в другую таблицу
(`FbsOrderMarking.value`), и переписывать `cis_code` после этого значило бы
разъехаться с уже скопированным значением, а не дочинить его; такие строки
только считаются отдельно в отчёте (`skipped_not_available`), не трогаются.
Есть режим примерки без записи (`--dry-run`).

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
        "skipped_not_available": report.skipped_not_available,
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
