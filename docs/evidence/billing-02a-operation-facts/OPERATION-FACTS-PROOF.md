# Волна 2А — correction round 2: доказательства

Дата: 2026-08-26. Worktree: `billing-module-20260826`.

Исходный product SHA: `b35302b145b5f353b5577c11b4584cfc11f6125a`.
Исходный baseline SHA: `b532addd7862d807e8b3933faf272a50bb2421d5`.
Round 1 product SHA: `0f0fc49135c4b577304431d96d1e1e48f1ad5798`;
round 1 migration guard SHA: `aa5d0925582ceaec31fa2c36caf3fdde7d0bf5c1`;
отдельный baseline SHA: `a07b0c5c06ca4e9170971f7eb95c7e4f9d6072a0`.
Round 2 test/recovery SHA: `3df78096c14ae93babfc0ad0a812fa988498ce6e`;
SQLite/PostgreSQL test-boundary SHA: `89fec60d9b571bb38fd4d43fadc86f247f5a4239`.

Frontend, routes, OpenAPI, legacy ledger и `DocumentEvent` не менялись.

## Тесты и машинные гейты на финальном test HEAD `89fec60d`

| Команда | Exit code | Результат |
|---|---:|---|
| `cd backend && uv run pytest tests/test_operation_facts.py tests/test_operation_fact_recovery.py tests/test_wb_import_dimensions.py -q --tb=short` | 0 | 16 passed, 6.65 s |
| `cd backend && uv run pytest` (persistent PTY session `88098`) | 0 | 1155 passed, 6 skipped, 9 warnings, 988.58 s |
| `cd backend && uv run ruff check app tests` | 0 | All checks passed |
| `cd backend && uv run mypy app` | 0 | Success: no issues found in 216 source files |
| `python3 scripts/ci/check_migrations.py` | 0 | 24 migrations checked; destructive operations not found |
| `cd backend && uv run alembic heads` | 0 | exactly `20260826_0111 (head)` |
| `python3 scripts/ci/back_guard.py` | 0 | no new deviations |
| `git diff --check` | 0 | empty output |

Новый integration test создаёт canonical `MarketplaceUnloadRequest` со
`shipped_at`, затем system cancel с `cancelled_at`; передаёт одновременно
`period_start`/`period_end` и явный `source_event_ids`, исключает source вне
периода и повторно получает `created=0`. Реальный writer test отклоняет foreign
seller, warehouse, actor, product line и reversal. Он также создаёт факт через
tenant-scoped user lookup, переименовывает реального пользователя в SQLite и
подтверждает неизменность сохранённого snapshot. SQLite connection-local FK
switch не используется: он не надёжен между pooled `AsyncSession` и меняет
поведение чужих тестов. Реальное delete/FK-null доказано ниже в PostgreSQL.

## Воспроизводимая PostgreSQL миграция, ограничения и поведение

Использовался только локальный compose PostgreSQL; staging и production не
затрагивались. `WMS_2A_PROOF_DATABASE_URL` ниже — URL одноразовой локальной БД;
он задаётся в окружении вызывающего и в доказательства не записывается.

```bash
cd /Users/deniscivkunov/Projects/WMS/.worktrees/billing-module-20260826
docker compose exec -T db dropdb -U postgres --if-exists wms_2a_round2_proof
docker compose exec -T db createdb -U postgres wms_2a_round2_proof
cd backend
export DATABASE_URL="${WMS_2A_PROOF_DATABASE_URL:?set disposable local proof URL}"
uv run alembic upgrade 20260825_0109
uv run alembic upgrade head
```

Вывод и exit: обе migration-команды завершились `0`; последняя строка —
`Running upgrade 20260826_0110 -> 20260826_0111`; `SELECT version_num FROM
alembic_version` вернул `20260826_0111`.

Следующий сохранённый heredoc запущен с exit `0`. Он перечислил все семь
ожидаемых ограничений и получил отказ двух cross-tenant вставок:

```bash
cd /Users/deniscivkunov/Projects/WMS/.worktrees/billing-module-20260826
docker compose exec -T db psql -X -v ON_ERROR_STOP=1 -U postgres -d wms_2a_round2_proof <<'SQL'
SELECT conname FROM pg_constraint
WHERE conrelid IN ('operation_facts'::regclass, 'operation_fact_lines'::regclass)
  AND conname IN (
    'fk_operation_facts_tenant_seller', 'fk_operation_facts_tenant_warehouse',
    'fk_operation_facts_tenant_actor', 'fk_operation_facts_tenant_reversal',
    'fk_operation_fact_lines_tenant_fact', 'fk_operation_fact_lines_tenant_product',
    'ck_operation_fact_lines_tenant_required'
  )
ORDER BY conname;
DO $$
DECLARE
  tenant_a uuid := gen_random_uuid(); tenant_b uuid := gen_random_uuid();
  seller_b uuid := gen_random_uuid(); fact_a uuid := gen_random_uuid(); product_b uuid := gen_random_uuid();
BEGIN
  INSERT INTO tenants (id, name, slug) VALUES
    (tenant_a, 'R2 SQL A', 'r2-sql-a-' || left(tenant_a::text, 8)),
    (tenant_b, 'R2 SQL B', 'r2-sql-b-' || left(tenant_b::text, 8));
  INSERT INTO sellers (id, tenant_id, name) VALUES (seller_b, tenant_b, 'R2 seller B');
  INSERT INTO products (id, tenant_id, seller_id, name, sku_code)
    VALUES (product_b, tenant_b, seller_b, 'R2 product B', 'R2-P-' || left(product_b::text, 8));
  INSERT INTO operation_facts (
    id, tenant_id, operation_code, source_kind, source_event_id, document_type,
    document_id, source, occurred_at, item_quantity, integrity_status
  ) VALUES (fact_a, tenant_a, 'r2_sql', 'r2_sql', gen_random_uuid(), 'r2_sql',
    gen_random_uuid(), 'system', now(), 0, 'complete');
  BEGIN
    INSERT INTO operation_facts (
      id, tenant_id, operation_code, source_kind, source_event_id, seller_id,
      document_type, document_id, source, occurred_at, item_quantity, integrity_status
    ) VALUES (gen_random_uuid(), tenant_a, 'r2_sql_foreign_seller', 'r2_sql',
      gen_random_uuid(), seller_b, 'r2_sql', gen_random_uuid(), 'system', now(), 0, 'complete');
    RAISE EXCEPTION 'cross-tenant seller unexpectedly accepted';
  EXCEPTION WHEN foreign_key_violation THEN RAISE NOTICE 'cross-tenant seller rejected'; END;
  BEGIN
    INSERT INTO operation_fact_lines (id, tenant_id, operation_fact_id, product_id, item_quantity)
      VALUES (gen_random_uuid(), tenant_a, fact_a, product_b, 0);
    RAISE EXCEPTION 'cross-tenant product line unexpectedly accepted';
  EXCEPTION WHEN foreign_key_violation THEN RAISE NOTICE 'cross-tenant product line rejected'; END;
END $$;
SQL
```

Сохранённый output: семь имён constraints, затем
`NOTICE: cross-tenant seller rejected`,
`NOTICE: cross-tenant product line rejected`, `DO`.

Поведение recovery и actor выполнено отдельным inline Python heredoc на той же
одноразовой БД: он создаёт tenant/seller/warehouse/product, два canonical
`MarketplaceUnloadRequest` (один за period), `OperationFactCutover`, и передаёт
scope `{'marketplace_unload_request': {selected_id, outside_id}}`. После первого
recovery он выставляет `selected.cancelled_at`, повторяет recovery, создаёт
user-source fact через `write_operation_fact`, переименовывает и удаляет того же
`User`, затем читает факт заново. Команда использует локальный URL только через
environment variable и не передаёт credentials в файле:

```bash
cd /Users/deniscivkunov/Projects/WMS/.worktrees/billing-module-20260826/backend
export DATABASE_URL="${WMS_2A_PROOF_DATABASE_URL:?set disposable local proof URL}"
uv run python - <<'PY'
import asyncio, uuid
from datetime import UTC, datetime, timedelta
from sqlalchemy import select
from app.db.session import SessionLocal
from app.models.marketplace_unload import MarketplaceUnloadLine, MarketplaceUnloadRequest
from app.models.operation_fact import OperationFact, OperationFactCutover
from app.models.product import Product
from app.models.seller import Seller
from app.models.tenant import Tenant
from app.models.user import User
from app.models.warehouse import Warehouse
from app.services.operation_fact_recovery_service import recover_operation_facts
from app.services.operation_fact_service import OperationFactLineInput, write_operation_fact

async def proof():
    suffix, now = uuid.uuid4().hex[:12], datetime.now(UTC)
    async with SessionLocal() as s:
        tenant = Tenant(name='R2 proof tenant', slug=f'r2-proof-{suffix}'); s.add(tenant); await s.flush()
        seller = Seller(tenant_id=tenant.id, name='R2 seller')
        warehouse = Warehouse(tenant_id=tenant.id, name='R2 warehouse', code=f'R2{suffix[:8]}')
        actor = User(tenant_id=tenant.id, email=f'actor-{suffix}@example.test', password_hash='test', role='ff_admin')
        s.add_all([seller, warehouse, actor]); await s.flush()
        product = Product(tenant_id=tenant.id, seller_id=seller.id, name='R2 product', sku_code=f'R2-{suffix}')
        selected = MarketplaceUnloadRequest(tenant_id=tenant.id, seller_id=seller.id, warehouse_id=warehouse.id, marketplace='wb', status='shipped', document_number=f'R2-selected-{suffix}', shipped_at=now-timedelta(minutes=5))
        outside = MarketplaceUnloadRequest(tenant_id=tenant.id, seller_id=seller.id, warehouse_id=warehouse.id, marketplace='wb', status='shipped', document_number=f'R2-outside-{suffix}', shipped_at=now-timedelta(hours=2))
        cutover = await s.get(OperationFactCutover, 1); assert cutover is not None
        cutover.occurred_at = now-timedelta(hours=3); s.add_all([product, selected, outside]); await s.flush()
        s.add_all([MarketplaceUnloadLine(request_id=selected.id, product_id=product.id, quantity=2), MarketplaceUnloadLine(request_id=outside.id, product_id=product.id, quantity=3)])
        await s.commit(); tenant_id, selected_id, actor_id, product_id, original_email = tenant.id, selected.id, actor.id, product.id, actor.email
    scope = {'marketplace_unload_request': {selected.id, outside.id}}
    async with SessionLocal() as s:
        first = await recover_operation_facts(s, tenant_id, period_start=now-timedelta(minutes=30), period_end=now+timedelta(minutes=30), source_event_ids=scope); await s.commit()
    async with SessionLocal() as s:
        request = await s.get(MarketplaceUnloadRequest, selected_id); assert request is not None
        request.cancelled_at = now; await s.commit()
    async with SessionLocal() as s:
        second = await recover_operation_facts(s, tenant_id, period_start=now-timedelta(minutes=30), period_end=now+timedelta(minutes=30), source_event_ids=scope); await s.commit()
        repeat = await recover_operation_facts(s, tenant_id, period_start=now-timedelta(minutes=30), period_end=now+timedelta(minutes=30), source_event_ids=scope); await s.commit()
    assert (first.found, first.created, first.already_present, first.conflicted) == (1, 1, 0, 0)
    assert (second.found, second.created, second.already_present, second.conflicted) == (2, 1, 1, 0)
    assert (repeat.found, repeat.created, repeat.already_present, repeat.conflicted) == (2, 0, 2, 0)
    async with SessionLocal() as s:
        fact = await write_operation_fact(s, tenant_id=tenant_id, operation_code='r2_actor_snapshot', source_kind='r2_actor_snapshot', source_event_id=uuid.uuid4(), document_type='r2_actor_snapshot', document_id=uuid.uuid4(), actor_user_id=actor_id, occurred_at=now, item_quantity=0, lines=[OperationFactLineInput(product_id, 'R2', 'R2 product', 0)])
        fact_id = fact.id; await s.commit(); actor = await s.get(User, actor_id); assert actor is not None
        actor.email = f'renamed-{suffix}@example.test'; await s.commit(); await s.delete(actor); await s.commit()
    async with SessionLocal() as s:
        fact = await s.get(OperationFact, fact_id)
        reversal = await s.scalar(select(OperationFact).where(OperationFact.tenant_id == tenant_id, OperationFact.operation_code == 'marketplace_outbound_reversal'))
        assert fact is not None and fact.actor_user_id is None and fact.actor_name_snapshot == original_email
        assert reversal is not None and reversal.source == 'system' and reversal.actor_user_id is None
    print('recovery first=1/1/0/0 second=2/1/1/0 repeat=2/0/2/0')
    print('actor rename/delete=actor_fk_null snapshot_immutable')
    print('system_cancel_reversal=system/no_actor')

asyncio.run(proof())
PY
```

Для PostgreSQL-служебного heredoc фактический output и exit `0` были:

```text
recovery first=1/1/0/0 second=2/1/1/0 repeat=2/0/2/0
actor rename/delete=actor_fk_null snapshot_immutable
system_cancel_reversal=system/no_actor
```

Correction не добавляет деньги, UI, API или 2B work.
