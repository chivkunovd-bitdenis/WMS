# F22 Code Review: backend safe stock sync

Дата: 2026-08-13, Europe/Moscow.
Git-root: `/Users/deniscivkunov/Projects/WMS/.worktrees/product-operations-ux-20260812`.
Роль: независимый Code Review Agent.
Dev commit: `f62e592c8bec7a0b8c7586fc0fc865b02f15b5e2` (`fix fbs stock sync unsafe zero publishing`).
Статус: `CODE_REVIEW_PASSED`.

Код не редактировался. Проверены только файлы из dev commit:

- `backend/app/services/fbs_stock_sync_service.py`
- `backend/tests/test_fbs_stock_sync.py`
- `backend/tests/test_fbs_stock_emulator_integration.py`

Обязательные инструкции прочитаны: `AGENTS.md`, `docs/WMS_FEATURE_GATE_PROTOCOL_RU.md`.
BA/Product source of truth прочитаны: `F22_BA_UX_SAFE_STOCK_SYNC_RU.md`, `F22_PRODUCT_VERDICT_SAFE_STOCK_SYNC_RU.md`.

## Короткий вывод

Блокеров не найдено. Commit закрывает P0-риск F22: отсутствие FBS-пула, неизвестная availability, пустой расчет, stale old sync item и `fbs_stock_limit=0` больше не становятся publishable `PUT amount=0`.

Новый код делает safe sync fail-closed: если количество нельзя безопасно доказать как положительное FBS-количество, target не попадает в publish batch. Для заблокированной строки создается/обновляется `FbsStockSyncItem` со статусом error и кодом `unsafe_stock_unknown` или `unsafe_zero_blocked`, но WB PUT не вызывается.

Положительная публикация сохранена: ненулевой FBS-пул идет в WB через PUT, затем обязательно сверяется POST readback. Success выставляется только после совпавшего readback.

## Проверка product constraints

1. `PASS` Missing/unknown/no FBS pool cannot become publishable 0.

   В `_build_publish_plan` отсутствие `product.id` в `availability` блокируется как `_BlockedTarget(ERROR_UNSAFE_STOCK_UNKNOWN)`, а не превращается в `availability.get(..., 0)`. Перед построением плана `sync_binding_stocks` дополнительно фильтрует availability по `direction_map.has_any`, поэтому товар без stock direction не попадает в publishable targets.

2. `PASS` Empty availability cannot become PUT 0.

   Пустой словарь availability теперь означает blocked target для каждого enabled товара с `chrtId`, а не `amount=0`. При `targets == []` `_publish_batches` возвращает без PUT.

3. `PASS` Stale old sync items do not auto-zero dangerously.

   Старый блок zeroing по `existing_items` удален. `_build_publish_plan` больше не добавляет `_PublishTarget(amount=0)` для confirmed/stale rows; `existing_items` не используется как источник публикации.

4. `PASS` `fbs_stock_limit=0` does not create unsafe zero.

   После применения лимита итоговый `amount == 0` блокируется как `ERROR_UNSAFE_ZERO_BLOCKED`. Это не отправляет ноль в WB.

5. `PASS` Positive publish still works and requires readback.

   Для положительного amount создается `_PublishTarget`, затем `_publish_batches` делает PUT и после него POST readback. `STOCK_SYNC_STATUS_CONFIRMED` и `last_confirmed_amount` выставляются только если `_compare_readback` подтвердил ту же пару `chrtId -> amount`.

6. `PASS` Existing tests are sufficient for incident WB 20 -> remains 20.

   Добавлен emulator integration test `test_wms_emulator_safe_sync_without_fbs_pool_keeps_wb_stock_20`: emulator сначала получает stock `20`, затем sync без FBS-пула не делает PUT и итоговый readback остается `20`. Unit test `test_sync_blocks_enabled_product_without_fbs_pool_before_wb_put` проверяет тот же guard на уровне сервиса и mock transport.

7. `PASS` No secrets/tokens/external panels touched.

   Diff ограничен сервисом и тестами. Нет изменений внешних кабинетов, Railway variables, secret panels, миграций ключей или destructive secret actions. Тестовые токены используются только как локальные фикстуры/emulator credentials; проверка на отсутствие token leakage в result сохранена.

8. `PASS` Migration/model risk.

   Модели и миграции не менялись. Commit меняет только алгоритм планирования/блокировки sync и тесты. Новые error codes являются строковыми значениями в существующих полях `last_error_code`; новой схемы БД не требуется.

## Дополнительные наблюдения

Zero path в этой итерации фактически не реализован: даже явный FBS-пул `0` блокируется как `unsafe_zero_blocked`. Это соответствует Product verdict для F22, потому что публикация нуля разрешалась только как отдельный product-approved сценарий с явным UX-подтверждением и readback.

UI constraints из F22 не проверялись браузером в рамках этого code review. В проверенном commit frontend не менялся, поэтому новых колонок `Лимит`, raw JSON, stack trace, технических чипов или дублирующих кнопок diff не добавляет. Browser Product QA остается отдельным Gate 6.

## Выполненные проверки

- `git show --stat --oneline --decorate --no-renames f62e592c8bec7a0b8c7586fc0fc865b02f15b5e2 -- backend/app/services/fbs_stock_sync_service.py backend/tests/test_fbs_stock_sync.py backend/tests/test_fbs_stock_emulator_integration.py`
- `git show --check --no-renames f62e592c8bec7a0b8c7586fc0fc865b02f15b5e2 -- backend/app/services/fbs_stock_sync_service.py backend/tests/test_fbs_stock_sync.py backend/tests/test_fbs_stock_emulator_integration.py`
- `pytest backend/tests/test_fbs_stock_sync.py backend/tests/test_fbs_stock_emulator_integration.py`

Результат тестов: `23 passed in 8.71s`.

## Итог

`CODE_REVIEW_PASSED`.

Blockers: нет.
