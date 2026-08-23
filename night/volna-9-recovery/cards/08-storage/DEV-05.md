# DEV · 08-storage · screen-dev · атом 5

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/frontend/src/screens/ff/FfStoragePage.tsx` — после успешного сохранения тарифа экран применяет `recalculated_statements` из того же ответа API к уже показанной таблице, не запускает отдельное формирование за месяц и не меняет строки, которых серверный пересчёт не коснулся. При ошибке исходная таблица остаётся в состоянии последней успешной загрузки, а в `ErrorNotice` диалога показано сообщение на языке оператора.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/frontend/src/screens/ff/FfStoragePage.test.ts` — добавлены точечные unit-тесты замены пересчитанного черновика, сохранения зафиксированной строки и сохранения последней таблицы при пустом результате пересчёта.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/frontend/tests-e2e/storage.spec.ts` — скорректирована регрессия `S-11-TC-002`: смена тарифа больше не ожидает POST ручного rebuild; добавлены атомарные сценарии видимого обновления суммы и ставки сразу после закрытия диалога и сохранения прежней таблицы с `ErrorNotice` при ошибке (`S-11-TC-017`).
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/night/volna-9-recovery/cards/08-storage/DEV.md` — отчёт этого атома.

## Гейты

Точная команда TypeScript-гейта:

```text
cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/frontend && npx tsc --noEmit -p tsconfig.app.json
```

Результат: зелёный, exit 0, ошибок нет.

Точная команда UI-гейта:

```text
cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage && python3 scripts/ui/ui_guard.py
```

Результат: красный, exit 1, только из-за существующих нарушений вне файлов и слоя этого атома:

```text
НОВОЕ НАРУШЕНИЕ  src/components/WbProductPickerDialog.tsx: экран-монолит 0 → 646
НОВОЕ НАРУШЕНИЕ  src/screens/v2/FfFbsSupplyWorkspace.tsx: экран-монолит 2493 → 2498
НОВОЕ НАРУШЕНИЕ  src/screens/v2/SellerInboundDraftScreen.tsx: экран-монолит 1111 → 1169
стало лучше  src/App.tsx: экран-монолит 3492 → 3491
```

`FfStoragePage.tsx`, его unit-тест и `storage.spec.ts` в выводе нарушений отсутствуют. Baseline не обновлялся, несвязанные файлы не исправлялись.

Точная команда unit-гейта затронутого экрана:

```text
cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/frontend && npm run test:unit -- src/screens/ff/FfStoragePage.test.ts
```

Результат: зелёный — `1 passed` test file, `4 passed` tests. Команда была повторена после финальной правки и оба раза завершилась с exit 0.

Точная команда проверки обнаружения только браузерных кейсов этого атома:

```text
cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/frontend && npx playwright test storage.spec.ts --grep 'S-11-TC-002|tariff repricing failure' --list
```

Результат: зелёный — обнаружены ровно три теста в одном файле: существующий живой `S-11-TC-002`, новый UI-кейс мгновенного пересчёта `S-11-TC-002` и негативный `S-11-TC-017`.

Точная команда атомарного браузерного прогона:

```text
cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/frontend && npx playwright test storage.spec.ts --grep 'S-11-TC-002|tariff repricing failure'
```

Результат: красный до исполнения трёх сценариев. Playwright поднял приложение до открытия сокета, затем песочница запретила локальному API привязаться к `127.0.0.1:18000`: `[Errno 1] ... operation not permitted`. Продуктовый код и утверждения тестов не исполнялись. Предварительный прогон только двух новых заголовков завершился на том же ограничении.

Точная команда проверки diff:

```text
cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage && git diff --check -- frontend/src/screens/ff/FfStoragePage.tsx frontend/src/screens/ff/FfStoragePage.test.ts frontend/tests-e2e/storage.spec.ts
```

Результат: зелёный, exit 0.

Полный backend `pytest`, `pytest -q` без путей, `ruff check .`, `mypy .` и полный frontend-регресс не запускались: атомарная проверка ограничена файлами и кейсами этого атома.

## Не реализовано

- Пункты контракта в коде реализованы буквально: после успешного POST открытый черновик заменяется серверным пересчётом без ручного формирования, а ошибка не очищает последнюю таблицу и отображается через `ErrorNotice`.
- Живое исполнение двух новых браузерных сценариев не подтверждено из-за запрета среды на локальный socket. Это ограничение проверки, а не пропущенный пункт реализации.
- Находка 5 из `REVIEW.md` о полном сквозном тесте с подготовкой живых UUID относится к следующему атому 6 и здесь не расширялась; текущий атом меняет только ожидание отсутствия лишнего rebuild в уже существующем живом кейсе и добавляет изолированные UI-проверки своего поведения.
- Несвязанные нарушения `ui_guard.py` не исправлялись, потому что их файлы не входят в разрешённый слой атома.

## Находки

- Новых находок по данным, персональным данным или безопасности в файлах атома нет.
- Секреты, ключи, токены, `.env`, кабинеты учётных данных, production и живой кабинет Wildberries не читались и не использовались.

## Блокеры

- Полностью зелёный набор гейтов недостижим в этой среде: `ui_guard.py` падает на трёх несвязанных файлах, а Playwright не может открыть локальный loopback-порт.
- Сохранить атом в Git из этой песочницы невозможно. Выполнена точная команда:

```text
cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage && git add -- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/frontend/src/screens/ff/FfStoragePage.tsx /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/frontend/src/screens/ff/FfStoragePage.test.ts /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/frontend/tests-e2e/storage.spec.ts /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/night/volna-9-recovery/cards/08-storage/DEV.md
```

Git завершился с exit 128: `Unable to create '/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-2-08-storage1/index.lock': Operation not permitted`. Файлы не попали в индекс, commit SHA не создан. Уже изменённый до атома `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/night/volna-9-recovery/JOURNAL.md` в команду не включался и не менялся.
