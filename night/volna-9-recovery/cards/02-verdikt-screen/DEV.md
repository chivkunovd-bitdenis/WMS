# Фича 1

# Разработка · 02-verdikt-screen · атом 1

## Что реализовано

- Эндпоинты: новых эндпоинтов нет; существующие пути синхронизации метаданных используют защищённый сервисный результат.
- Сервис: `_sync_order_meta_from_wb` сохраняет снимок заказа и привязанного кода на старте запроса, а перед применением ответа блокирует и перечитывает текущее состояние. Ответ отбрасывается, если уже записан результат более поздней проверки или код заказа изменился.
- Сервис: ошибка старого запроса также больше не очищает более новый вердикт; актуальная ошибка по-прежнему переводит заказ в закрытое для сдачи состояние.

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/backend/app/services/fbs_marking_service.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/backend/tests/test_fbs_marking.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/night/volna-9-recovery/cards/02-verdikt-screen/DEV.md`

## Миграции

Нет. Атом использует уже существующее поле `fbs_orders.metadata_last_checked_at` и не меняет схему данных.

## Тесты

- Добавлен `test_fbs_marking_sync_does_not_apply_stale_response` с идентификатором `S-03-TC-016`: два конкурентных запроса синхронизации одного заказа и одного кода управляются событиями. Более поздний запрос первым сохраняет `filled + uinBadStatus`, ранний положительный `filled` возвращается после него и не перезаписывает отказ.
- Тест проверяет сохранение причины, `metadata_delivery_allowed = false` и закрытый серверный гейт `_build_delivery_checks` с результатом `marking_not_allowed`.
- Полностью пройден разрешённый контрактом файл `tests/test_fbs_marking.py`: 32 теста.

## Гейты

Рабочий каталог всех команд ниже: `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/backend`.

- `pytest -q tests/test_fbs_marking.py::test_fbs_marking_sync_does_not_apply_stale_response` — успешно, `1 passed in 1.17s`.
- `ruff check app/services/fbs_marking_service.py tests/test_fbs_marking.py` — успешно, `All checks passed!`.
- `mypy app/services/fbs_marking_service.py` — целевой модуль проверен, но команда завершилась с кодом 1 из-за четырёх уже существующих ошибок в импортируемых файлах `wildberries_credentials_service.py`, `fbs_stock_sync_service.py` и `fbs_warehouse_binding_service.py`, которые не входят в разрешённые файлы атома.
- `mypy --follow-imports=skip app/services/fbs_marking_service.py` — диагностический запуск неприменим как гейт: при полном пропуске импортов девять существующих возвратов констант стали `Any`.
- `mypy --follow-imports=silent app/services/fbs_marking_service.py` — успешно, `Success: no issues found in 1 source file`; ошибки импортируемого чужого слоя подавлены, изменённый модуль проверен.
- `pytest -q tests/test_fbs_marking.py` — успешно, `32 passed in 7.56s`.
- `.venv/bin/pytest -q tests/test_fbs_marking.py::test_fbs_marking_sync_does_not_apply_stale_response` — пробный запуск не стартовал: локального `backend/.venv/bin/pytest` нет; после этого использован доступный системный `pytest`.
- `python3 scripts/ci/back_guard.py` не запускался: атом не добавляет роут.
- `python3 scripts/ci/check_migrations.py` не запускался: атом не добавляет миграцию.
- Полный `pytest`, `ruff check .` и `mypy .` не запускались согласно запрету атомарного шага.
- `git add -- backend/app/services/fbs_marking_service.py backend/tests/test_fbs_marking.py night/volna-9-recovery/cards/02-verdikt-screen/DEV.md && git diff --cached --check && git diff --cached --stat && git commit -m "fix(fbs): ignore stale WB marking verdicts"` — не выполнено: Git не смог создать `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-2-02-verdikt-screen1/index.lock`, `Operation not permitted`.

## Не реализовано

- Внутри атома 1 не осталось нереализованных пунктов.
- Фичи 2–4 из `FEATURES.md` не затрагивались: текущий запуск прямо ограничен первым атомом.

## Находки

- Обычный целевой `mypy` подхватывает четыре ошибки из трёх импортируемых модулей вне границ атома; локальная проверка самого изменённого сервиса с `--follow-imports=silent` зелёная.
- Секреты, ключи, токены, `.env`, кабинеты учётных данных, живой Wildberries и production `194.87.96.144` не читались и не затрагивались.

## Блокеры

- Реализация и отчёт существуют в рабочем дереве, но не сохранены коммитом: sandbox запрещает запись служебного `index.lock` зарегистрированного worktree. Обходной Git-каталог не создавался, чтобы не нарушить требование работать только в данной зарегистрированной копии.

# Фича 2

# Разработка · 02-verdikt-screen · атом 2

## Что реализовано

- Эндпоинты: новых эндпоинтов нет; публичный API не менялся.
- Сервис: `_wb_order_verdict` для решения WB `pending` возвращает подпись `WB: проверяет`, тон `neutral` и `delivery_allowed = false`.
- Сервис: остальные запрещающие решения сохраняют тон `stop`; правила разрешения сдачи не менялись.

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/backend/app/services/fbs_marking_service.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/backend/tests/test_fbs_marking.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/night/volna-9-recovery/cards/02-verdikt-screen/DEV.md`

## Миграции

Нет. Схема данных не менялась.

## Тесты

- Обновлён параметр `pending` в `test_wb_order_verdict_maps_operator_states`: ожидаются подпись `WB: проверяет`, тон `neutral` и запрет сдачи.
- Обновлён дублирующий регрессионный контракт `test_wb_order_verdict_contract`, обнаруженный полным прогоном целевого файла.
- В обеих таблицах решения `required`, неизвестное решение и отказ с причиной по-прежнему ожидают тон `stop` и `delivery_allowed = false`.

## Гейты

Рабочий каталог всех команд ниже: `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/backend`.

- `pytest -q tests/test_fbs_marking.py::test_wb_order_verdict_maps_operator_states` — успешно, `7 passed in 0.07s`.
- `ruff check app/services/fbs_marking_service.py tests/test_fbs_marking.py` — успешно, `All checks passed!`.
- `mypy app/services/fbs_marking_service.py` — завершился с кодом 1: четыре уже существующие ошибки в импортируемых файлах `wildberries_credentials_service.py`, `fbs_stock_sync_service.py` и `fbs_warehouse_binding_service.py`; изменённая строка атома типы не затрагивает.
- `pytest -q tests/test_fbs_marking.py` — первый прогон выявил вторую старую фиксацию `pending → stop`: `1 failed, 31 passed in 10.93s`; ожидание исправлено в рамках того же тестового файла.
- `pytest -q tests/test_fbs_marking.py::test_wb_order_verdict_maps_operator_states tests/test_fbs_marking.py::test_wb_order_verdict_contract` — успешно после исправления обеих таблиц, `14 passed in 0.07s`.
- `ruff check app/services/fbs_marking_service.py tests/test_fbs_marking.py` — повторно успешно, `All checks passed!`.
- `mypy --follow-imports=silent app/services/fbs_marking_service.py` — успешно, `Success: no issues found in 1 source file`; проверен затронутый сервис без ошибок импортируемого соседнего слоя.
- `pytest -q tests/test_fbs_marking.py` — финально успешно, `32 passed in 7.05s`.
- `python3 scripts/ci/back_guard.py` не запускался: атом не добавляет роут.
- `python3 scripts/ci/check_migrations.py` не запускался: атом не добавляет миграцию.
- Полный backend-регресс, `ruff check .` и `mypy .` не запускались согласно запрету атомарного шага.
- `git add -- backend/app/services/fbs_marking_service.py backend/tests/test_fbs_marking.py night/volna-9-recovery/cards/02-verdikt-screen/DEV.md && git diff --cached --check && git diff --cached --stat && git commit -m "fix(fbs): make pending WB verdict neutral"` — не выполнено: Git не смог создать `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-2-02-verdikt-screen1/index.lock`, `Operation not permitted`.

## Не реализовано

- Внутри атома 2 нереализованных пунктов нет.
- Фичи 3–4 из `FEATURES.md` не затрагивались: они относятся к frontend-слою и выходят за роль `backend-dev` и текущий атом.

## Находки

- Обычный целевой `mypy` подхватывает четыре ошибки из трёх импортируемых модулей вне границ атома; целевая проверка самого сервиса с `--follow-imports=silent` зелёная.
- Секреты, ключи, токены, `.env`, кабинеты учётных данных, живой Wildberries и production `194.87.96.144` не читались и не затрагивались.

## Блокеры

- Реализация и отчёт локально записаны в зарегистрированном worktree, но текущая среда запрещает создать служебный `index.lock` в основном Git-каталоге. Изменения не сохранены коммитом и пока не имеют восстанавливаемого SHA; риск — их можно потерять при очистке рабочей копии.

# Фича 3

# Разработка · 02-verdikt-screen · атом 3

В словаре серверных WB-вердиктов для каждого блокирующего статуса
закреплено следующее действие оператора. «WB: проверяет» теперь имеет
нейтральный тон и подсказку «WB ещё не подтвердил код»; «WB: нужен код»
показывает «Пришлите ЧЗ»; отсутствующий, явный безответный или неизвестный
вердикт блокирует сдачу с подсказкой «Ждём ответа Wildberries». Причина отказа
`uinBadStatus` по-прежнему выводится как человеческое «неверный статус УИН».

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/frontend/src/utils/metaStatus.ts`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/frontend/src/utils/metaStatus.test.ts`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/night/volna-9-recovery/cards/02-verdikt-screen/DEV.md`

`/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/frontend/src/screens/v2/FfFbsSupplyWorkspace.tsx`
проверен, но не изменён: он уже выводит `metaStatus.reason` через `TextCell`,
строку «Сдача пока недоступна» для «Нет ответа WB» и `metaStatus.disabledReason`
в подсказке заблокированной `PrimaryAction`.

## Гейты

Рабочий каталог frontend-команд:
`/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/frontend`.

- `npm run test:unit -- src/utils/metaStatus.test.ts` — **зелёный**: `1 passed`, `9 tests passed`.
- `npx tsc --noEmit -p tsconfig.app.json` — **зелёный**, код выхода 0, ошибок нет.

Рабочий каталог корневых команд:
`/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen`.

- `python3 scripts/ui/ui_guard.py` — **красный**: храповик нашёл два уже
  закоммиченных нарушения вне атома:
  `src/components/WbProductPickerDialog.tsx: экран-монолит 0 → 646` и
  `src/screens/v2/SellerInboundDraftScreen.tsx: экран-монолит 1111 → 1169`.
- `git diff --exit-code HEAD -- frontend/src/components/WbProductPickerDialog.tsx frontend/src/screens/v2/SellerInboundDraftScreen.tsx`
  — **зелёный**, код выхода 0: оба нарушения `ui_guard.py` находятся в неизменённом
  состоянии `HEAD`.
- `git diff --check` — **зелёный**, ошибок пробелов и маркеров конфликта нет.
- `git add -- frontend/src/utils/metaStatus.ts frontend/src/utils/metaStatus.test.ts night/volna-9-recovery/cards/02-verdikt-screen/DEV.md && git diff --cached --check && git diff --cached --stat && git commit -m "fix(fbs): explain blocking WB verdicts"`
  — **красный**: Git не смог создать
  `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-2-02-verdikt-screen1/index.lock`,
  `Operation not permitted`. Коммит не создан.

Полный frontend/backend-регресс не запускался: атомарная проверка ограничена
`src/utils/metaStatus.test.ts` и типизацией frontend по прямому указанию для этого шага.

## Не реализовано

- Внутри атома 3 нереализованных пунктов контракта нет.
- Находка REVIEW.md №2 про ошибку 15-секундного фонового обновления и сценарий
  `S-03-TC-018` из находки №4 вынесены в `FEATURES.md` в следующий атом 4 и по прямому
  запрету не затрагивались. Backend-часть находки №3 закрыта предыдущим атомом 2.
- Два нарушения `ui_guard.py` не исправлены: их файлы не названы в фиче 3, не входят
  в файлы S-03 в `frontend/screens.registry.json`, а обновлять базовую линию флагом `--update` запрещено.
- Изменения атома локально реализованы, но не сохранены в Git: среда запретила создать
  `index.lock`, поэтому восстанавливаемого SHA для результа нет.

## Находки

- Ключи, секреты, токены, `.env`, кабинеты учётных данных, живой Wildberries и production
  `194.87.96.144` не читались и не затрагивались.

## Блокеры

- Для полного зелёного гейта нужно исправить два чужих монолита, которые не входят в границы атома.
- Для сохранения результа в Git нужна среда с правом записи в
  `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-2-02-verdikt-screen1/`.

# Фича 4

# Разработка · 02-verdikt-screen · атом 4

Фоновая ошибка обновления рабочего места теперь закрывает передачу поставки:
старый положительный WB-вердикт не участвует в счётчике готовности, признаке
печати и гейте сдачи, а строки показывают безопасные «Нет ответа WB» и «Сдача
пока недоступна». Отдельный складской Alert не выводит HTTP-код. Следующий
успешный ответ рабочего места снимает только ошибку обновления и возвращает
свежий серверный вердикт.

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/frontend/src/screens/v2/FfFbsSupplyWorkspace.tsx`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/frontend/tests-e2e/ff-fbs-supply.spec.ts`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/night/volna-9-recovery/cards/02-verdikt-screen/DEV.md`

## Гейты

Рабочий каталог frontend-команд:
`/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/frontend`.

- `npx tsc --noEmit -p tsconfig.app.json` — **зелёный**, код выхода 0,
  ошибок типизации нет.
- `npm run test:unit -- src/screens/v2/FfFbsSupplyWorkspace.test.ts` —
  **зелёный**: `1 passed`, `3 tests passed`.
- `npm run test:unit -- src/screens/v2/FfFbsSupplyWorkspace.test.ts src/utils/metaStatus.test.ts`
  — **зелёный**: `2 passed`, `12 tests passed`.
- `npx eslint src/screens/v2/FfFbsSupplyWorkspace.tsx tests-e2e/ff-fbs-supply.spec.ts`
  — **зелёный**, код выхода 0.
- `npx playwright test tests-e2e/ff-fbs-supply.spec.ts --grep 'S-03-TC-018' --list`
  — **зелёный**: найден ровно один сценарий
  `S-03-TC-018: failed workspace refresh closes WB delivery`.
- `npx playwright test tests-e2e/ff-fbs-supply.spec.ts --grep 'S-03-TC-018'`
  — **красный до запуска сценария**: Playwright-managed backend не смог открыть
  локальный порт `127.0.0.1:18000`, ОС вернула `operation not permitted`.
  Ни один assertion теста не исполнялся и не падал.

Рабочий каталог корневых команд:
`/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen`.

- `python3 scripts/ui/ui_guard.py` — **красный** из-за двух уже
  закоммиченных нарушений вне атома:
  `src/components/WbProductPickerDialog.tsx: экран-монолит 0 → 646` и
  `src/screens/v2/SellerInboundDraftScreen.tsx: экран-монолит 1111 → 1169`.
  Изменённый `FfFbsSupplyWorkspace.tsx` нового нарушения не создаёт: в нём 2492
  строки при базовой границе 2493; гейт отмечает улучшение своей кнопки `37 → 36`.
- `git diff --exit-code HEAD -- frontend/src/components/WbProductPickerDialog.tsx frontend/src/screens/v2/SellerInboundDraftScreen.tsx`
  — **зелёный**, код выхода 0: оба красных пункта `ui_guard.py` не изменялись
  этим атомом.
- `git diff --check` — **зелёный**, ошибок пробелов и маркеров конфликта нет.
- `git add -- frontend/src/screens/v2/FfFbsSupplyWorkspace.tsx frontend/tests-e2e/ff-fbs-supply.spec.ts night/volna-9-recovery/cards/02-verdikt-screen/DEV.md && git diff --cached --check && git diff --cached --stat && git commit -m "fix(fbs): fail closed on workspace refresh errors"`
  — **красный до индексирования**: Git не смог создать
  `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-2-02-verdikt-screen1/index.lock`,
  ОС вернула `Operation not permitted`. Коммит не создан.

Полные frontend/backend-регрессы не запускались по прямому ограничению
атомарной проверки. Выполнены только тесты экрана, зависимого словаря и
назначенный e2e-кейс.

## Не реализовано

- Пунктов контракта, пропущенных в коде, нет.
- Исполняемый прогон `S-03-TC-018` не завершён из-за запрета среды на открытие
  локального порта Playwright. Сам тест обнаруживается конфигурацией, TypeScript
  и ESLint зелёные, но это не заменяет браузерный прогон.
- Два чужих нарушения `ui_guard.py` не исправлялись: их файлы не названы в
  атоме, не относятся к экрану S-03 и запрещены для правки ролью `screen-dev`.
  Базовая линия `ui_guard.py` не обновлялась.
- Результат записан в назначенную рабочую копию, но не сохранён в Git: среда
  запрещает создать `index.lock`, поэтому восстанавливаемого commit SHA нет.

## Находки

- Находок по данным, утечкам или персональным данным в разрешённых файлах нет.
  Секреты, ключи, токены, `.env`, кабинеты учётных данных, живой Wildberries и
  production `194.87.96.144` не читались и не затрагивались.
