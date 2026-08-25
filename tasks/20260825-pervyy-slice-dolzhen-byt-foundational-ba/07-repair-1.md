# Call 78 — repair round 1: F-01..F-04

Статус: локальный ремонтный slice проверен, но не может быть сохранён в commit:
`git add` не может создать
`/Users/deniscivkunov/Projects/WMS/.git/worktrees/ozon-module-sol-20260824/index.lock`
(`Operation not permitted`). Это не product browser approval, deploy или
доказательство PostgreSQL-production поведения.

## Исправления

* **F-01.** `MarketplaceAccountService` теперь принимает только настоящий
  `AsyncSession`: удалены `_test_rows`, `from_test_client`, `save_candidate`,
  `count_primary_accounts`, `ciphertext_for_test` и все ветви, поддерживавшие
  словарный fake. Service tests создают tenant/seller/user и проверяют сохранение,
  tenant isolation и очистку ciphertext через локальную SQLite DB/session.
* **F-02.** Удален любой Ozon путь через `E2E_MOCK_WB_CARDS`. Production validation
  по-прежнему делает только allowlisted `POST /v1/seller/info` с `{}` и
  `follow_redirects=False`. Только Playwright-managed disposable backend получает
  `E2E_MOCK_OZON_VALIDATION=1` вместе с `WMS_AUTO_CREATE_SCHEMA=1`; browser payload
  этот выборить не может. Отдельный test проверяет обычный путь через adapter.
* **F-03.** Перед чтением/созданием primary account сервис берёт `FOR UPDATE` на
  существующем seller scope и затем на primary row; unique constraint и один retry
  после `IntegrityError` остаются защитой от альтернативного writer/race. Test
  запускает две реальные SQLite sessions одновременно и проверяет одну primary row.
  SQLite игнорирует `FOR UPDATE`, поэтому это не утверждение о PostgreSQL lock
  semantics; PostgreSQL стратегия задана production SQLAlchemy path.
* **F-04.** PUT принимает `OzonAccountPutIn`: strict strings, `extra=forbid`,
  `client_id` 1..255, `api_key` 1..4096 и trim/nonblank validation. Local route
  mapper сохраняет frozen `client_id_required`/`api_key_required`, все остальные
  model violations безопасно возвращают `invalid_payload`. OpenAPI test проверяет
  request schema; публичный status по-прежнему не содержит credential/account data.

## Выполненная проверка

* `backend/ ruff check app/services/marketplace_account_service.py app/services/ozon_client.py app/api/ozon_integration.py tests/test_marketplace_account_service.py tests/test_ozon_integration_api.py` — passed.
* `backend/ mypy app/services/marketplace_account_service.py app/services/ozon_client.py app/api/ozon_integration.py` — passed.
* `backend/ pytest -q tests/test_marketplace_account_service.py tests/test_ozon_integration_api.py tests/test_marketplace_accounts_migration.py tests/test_wildberries_tokens_api.py` — passed (exit 0).
* `frontend/ npm run build` — passed; только существующее Vite предупреждение о
  крупных chunks.
* `frontend/ npx playwright test tests-e2e/seller-settings.spec.ts --project=chromium`
  — не пройден и не объявляется пройденным: sandbox запретил bind
  `127.0.0.1:18000` (`operation not permitted`) до collection. Все четыре browser
  case остаются unrun.

## Границы

В этом repair не менялись `SellerSettingsScreen`, тексты, layout, controls, routes,
navigation, WB или Честный Знак. Не выполнялись Ozon/stage/production HTTP calls,
не открывались credentials и не было provider mutations. Новая локальная Ozon
композиция используется только для уже существующего Playwright E2E backend.
