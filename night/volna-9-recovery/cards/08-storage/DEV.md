# DEV · 08-storage · screen-dev · атом 6

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/frontend/tests-e2e/storage.spec.ts` — `S-11-TC-002` переведён на реальный сквозной setup: через существующий тестовый API создаются tenant с авторизованным администратором, операционный склад, селлер, товар, приёмка с фактическим движением и открытый storage-черновик. Тест проверяет реальные UUID, запрет вчерашней даты в обоих полях, один атомарный POST ставки склада и исключения селлера, HTTP 201, закрытие диалога, отсутствие дополнительного rebuild и видимые сумму/ставку из серверного `recalculated_statements`. Дублирующий route-моканный `S-11-TC-002` удалён; route-моков `/operations/storage/tariffs` и `/operations/storage/statements` в оставшемся кейсе нет.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/night/volna-9-recovery/cards/08-storage/DEV.md` — отчёт текущего атома.

## Гейты

Точный финальный TypeScript-гейт:

```text
cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/frontend && npx tsc --noEmit -p tsconfig.app.json
```

Результат: зелёный, exit 0, ошибок нет. Команда выполнена после финальной правки.

Точный финальный UI-гейт:

```text
cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage && python3 scripts/ui/ui_guard.py
```

Результат: красный, exit 1, только из-за уже существующих нарушений вне разрешённого файла и слоя атома:

```text
НОВОЕ НАРУШЕНИЕ  src/components/WbProductPickerDialog.tsx: экран-монолит 0 → 646
НОВОЕ НАРУШЕНИЕ  src/screens/v2/FfFbsSupplyWorkspace.tsx: экран-монолит 2493 → 2498
НОВОЕ НАРУШЕНИЕ  src/screens/v2/SellerInboundDraftScreen.tsx: экран-монолит 1111 → 1169
стало лучше  src/App.tsx: экран-монолит 3492 → 3491
```

`frontend/tests-e2e/storage.spec.ts` в нарушениях отсутствует. Baseline не обновлялся, несвязанные файлы не исправлялись.

Точный финальный unit-гейт затронутого экрана:

```text
cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/frontend && npm run test:unit -- src/screens/ff/FfStoragePage.test.ts
```

Результат: зелёный — `1 passed` test file, `4 passed` tests. Команда выполнена после финальной правки.

Первая диагностическая команда обнаружения браузерного кейса:

```text
cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/frontend && npx playwright test storage.spec.ts --grep '^S-11-TC-002' --list
```

Результат: красный, exit 1, `No tests found`: якорь `^` не совпал с полным заголовком, который сопоставляет Playwright. Команда исправлена без якоря.

Точная финальная команда обнаружения назначенного браузерного кейса:

```text
cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/frontend && npx playwright test storage.spec.ts --grep 'S-11-TC-002' --list
```

Результат: зелёный — найден ровно `1 test in 1 file`, `storage.spec.ts:64`.

Точный атомарный браузерный прогон:

```text
cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/frontend && npx playwright test storage.spec.ts --grep 'S-11-TC-002'
```

Результат: красный до исполнения сценария. Backend создал тестовые таблицы и дошёл до открытия сокета, затем песочница запретила привязку API к `127.0.0.1:18000`: `[Errno 1] ... operation not permitted`. Тестовый код `S-11-TC-002` не исполнялся, поэтому продуктового падения сценария этот запуск не зафиксировал.

Точная относящаяся к атому backend-регрессия пересчёта:

```text
cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/backend && pytest -q tests/test_storage_tariff_api.py::test_new_tariff_reprices_open_draft_on_reload
```

Результат: зелёный — `1 passed in 1.31s`.

Точная проверка пробелов:

```text
cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage && git diff --check -- frontend/tests-e2e/storage.spec.ts
```

Результат: зелёный, exit 0.

Полный backend `pytest`, `pytest -q` без путей, `ruff check .`, `mypy .` и полный frontend-регресс не запускались: атомарная проверка ограничена `S-11-TC-002` и непосредственно относящимися к нему тестами.

## Не реализовано

- Живое исполнение `S-11-TC-002` не подтверждено в этой песочнице: локальному Playwright webServer запрещено открыть loopback-порт. Точную команду нужно повторить в среде, где разрешён bind `127.0.0.1:18000`.
- Пункты кода атома реализованы буквально: route-моки storage API и фиктивные идентификаторы убраны из `S-11-TC-002`; тест требует реальный 201, один POST, серверный пересчёт и видимый результат. Соседние атомы и продуктовые задачи не менялись.
- Несвязанные нарушения `ui_guard.py` не исправлялись и baseline не двигался, поскольку их файлы не входят в разрешённый слой атома.

## Находки

- Новых находок по данным, персональным данным или безопасности в разрешённом файле атома нет.
- Секреты, ключи, токены, `.env`, кабинеты учётных данных, production и живой кабинет Wildberries не читались и не использовались.
