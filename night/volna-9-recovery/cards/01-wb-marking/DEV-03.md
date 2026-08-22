# DEV · 01-wb-marking · атом 3 · rework

## Что реализовано

- Эндпоинты: нет.
- Сервис `fbs_marking_service._sync_order_meta_from_wb`: пропущенная строка заказа и строка без ожидаемого `kind` безопасно снимают устаревший положительный вердикт в `unknown`, не меняя привязку КИЗ, жизненный статус кода, прежние `reason`/сырой блок и время последней успешной проверки.
- Сервис `fbs_marking_service._sync_order_meta_from_wb`: любое заполненное значение WB, отличающееся от локального, получает `replacement_required`, в том числе при `invalid`; первый переход создаёт один `wb_orphaned`.
- Сервис `fbs_autopoll_service.sync_marking_statuses_for_assembling_supplies`: пропущенный из успешной пачки `order_id` передаётся в безопасное применение, но не учитывается как успешная сверка и не запускает производное обновление поставки.

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend/app/services/fbs_marking_service.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend/app/services/fbs_autopoll_service.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend/tests/test_fbs_kiz.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend/tests/test_fbs_marking.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/night/volna-9-recovery/cards/01-wb-marking/DEV.md`

## Миграции

- Нет.

## Тесты

- Расширен параметризованный тест отображения `filled`, `optional`, `pending`, `required` без значения, `invalid`, неизвестного решения и несовпадающего значения; `invalid` с чужим КИЗ теперь закреплён как `replacement_required`.
- Добавлен тест пропущенной строки WB: статус сверки становится `unknown`, но ссылка на КИЗ, статус `reserved`, причина, сырой блок и прежнее время успешной проверки сохраняются.
- Сохранён отдельный тест отсутствующего ожидаемого `kind`: свежая дата не появляется, локальные данные КИЗ не стираются.
- Тест однократного аудита расширен на конкурентные и повторные `missing` и `replacement_required`: в каждом варианте остаётся один `wb_orphaned`.
- Регрессия автополлера проверяет применение пропущенного `order_id` без счётчика успеха и уведомления, а упавшая пачка остаётся без изменений.

## Гейты

- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend && ruff check app/services/fbs_marking_service.py app/services/fbs_autopoll_service.py tests/test_fbs_kiz.py tests/test_fbs_marking.py` — успешно: `All checks passed!`.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend && mypy app/services/fbs_marking_service.py app/services/fbs_autopoll_service.py` — целевой запуск выполнен; остановлен двумя ранее существующими ошибками в импортируемых соседних файлах: `app/services/wildberries_credentials_service.py:167` и `app/services/fbs_stock_sync_service.py:617`. В изменённых строках ошибок не показано.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend && mypy --follow-imports=skip app/services/fbs_marking_service.py app/services/fbs_autopoll_service.py` — диагностический запуск выполнен; из-за пропуска типов импортов показал 16 прежних `no-any-return` в этих модулях и не является зелёным гейтом.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend && pytest -q tests/test_fbs_kiz.py::test_fbs_marking_wb_meta_decision_is_safe_and_preserves_raw_detail tests/test_fbs_kiz.py::test_fbs_marking_partial_wb_row_is_unknown_without_fresh_check_time tests/test_fbs_kiz.py::test_fbs_marking_omitted_wb_row_clears_stale_verdict_only tests/test_fbs_kiz.py::test_fbs_marking_orphaned_audit_is_created_once_for_concurrent_and_repeated_mismatch tests/test_fbs_marking.py::test_fbs_marking_autopoll_batches_unique_ids_and_skips_partial_or_failed_batches` — успешно: `14 passed in 14.44s`.
- Первый пробный `pytest` был запущен из `backend/` с ошибочным префиксом `backend/tests/...` и завершился `file or directory not found`; исправленная точная команда выше зелёная.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking && git add -- backend/app/services/fbs_marking_service.py backend/app/services/fbs_autopoll_service.py backend/tests/test_fbs_kiz.py backend/tests/test_fbs_marking.py night/volna-9-recovery/cards/01-wb-marking/DEV.md && git diff --cached --check && git status --short && git commit -m "fix(wb-marking): safely apply partial metadata"` — не выполнено средой: Git не смог создать `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-1-01-wb-marking1/index.lock` (`Operation not permitted`).
- `python3 scripts/ci/back_guard.py` — не запускался: атом не добавляет роут.
- `python3 scripts/ci/check_migrations.py` — не запускался: атом не добавляет миграцию.

## Не реализовано

- Находки ревью 2 и 4 относятся к `wildberries_fbs_client.py`, mock-контракту и `Retry-After` атома 1; в атом 3 не включались.
- Новые эндпоинты, модели, миграции, UI и обращения к внешнему WB не добавлялись.

## Находки

- Целевой `mypy` загрязнён двумя ошибками соседних импортируемых сервисов, перечисленными в разделе «Гейты»; текущий атом эти файлы не меняет.
- Секреты, ключи, токены, `.env`, кабинеты учётных данных, боевой прод и живой кабинет Wildberries не читались и не затрагивались.

## Блокеры

- Локальная реализация и артефакт не сохранены commit: песочница разрешает менять файлы рабочей копии, но запрещает запись в Git-метаданные зарегистрированного worktree за её пределами. Для сохранения требуется повторить указанную в «Гейтах» команду в процессе с доступом к `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-1-01-wb-marking1/`.
