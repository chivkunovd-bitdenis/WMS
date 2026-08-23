# Фича 1

# DEV · 02-verdikt-screen · атом 1 · повторное исправление

## Что реализовано

- Эндпоинты: новых и изменённых эндпоинтов нет; контракт API не менялся.
- Сервис: `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/backend/app/services/fbs_marking_service.py` сохраняет маркер старта WB-проверки отдельной короткой транзакцией до ожидания WB; ответ раннего запроса больше не может записать операторский вердикт после старта более нового запроса.
- Сервис: блокировка текущего состояния продолжает возвращать уже загруженные связи `order.markings` и `marking_code`, поэтому повторно проверенные сценарии замены ЧЗ не выполняют ленивое async-чтение.

## Миграции

Нет.

## Тесты

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/backend/tests/test_fbs_marking.py::test_fbs_marking_sync_does_not_apply_stale_response` проверяет оба порядка завершения запросов A и B. При завершении A первым его устаревший `filled` не открывает сдачу, а итог B сохраняет `uinBadStatus` и `metadata_delivery_allowed = false`.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/backend/tests/test_fbs_kiz.py` проверяет три прямо названные регрессии замены ЧЗ и согласованное ожидание успешного WB-ответа: сохранение предыдущего кода, отсутствие двойного счётчика и выбор активной строки.

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/backend/app/services/fbs_marking_service.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/backend/tests/test_fbs_marking.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/backend/tests/test_fbs_kiz.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/night/volna-9-recovery/cards/02-verdikt-screen/DEV.md`

## Гейты

- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/backend && python3 -m ruff check app/services/fbs_marking_service.py tests/test_fbs_marking.py tests/test_fbs_kiz.py` — `All checks passed!`.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/backend && python3 -m mypy --follow-imports=silent app/services/fbs_marking_service.py` — `Success: no issues found in 1 source file`.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/backend && python3 -m pytest -q tests/test_fbs_marking.py::test_fbs_marking_sync_does_not_apply_stale_response tests/test_fbs_kiz.py::test_fbs_kiz_commit_success_creates_records_event_and_counter tests/test_fbs_kiz.py::test_fbs_kiz_commit_confirmed_replaces_old_kiz_and_voids_code tests/test_fbs_kiz.py::test_fbs_kiz_pool_to_external_replacement_does_not_double_count_unit tests/test_fbs_kiz.py::test_fbs_marking_readers_prefer_active_row_over_newer_rejected_row` — `6 passed in 10.29s`.
- `back_guard.py` не запускался: атом не добавляет и не меняет роуты.
- `check_migrations.py` не запускался: миграций нет.
- Полный backend-регресс, `ruff check .` и `mypy .` не запускались по правилу атомарного шага.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen && git add -- backend/app/services/fbs_marking_service.py backend/tests/test_fbs_marking.py backend/tests/test_fbs_kiz.py night/volna-9-recovery/cards/02-verdikt-screen/DEV.md` — не выполнена: Git не смог создать `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-2-02-verdikt-screen1/index.lock`, `Operation not permitted`.

## Не реализовано

- Находки 4–6 из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/night/volna-9-recovery/cards/02-verdikt-screen/REVIEW.md` относятся к frontend-слою и не входят в роль backend-dev или этот атом.
- Новые роуты, модели, колонки и миграции не добавлялись: атом реализует защиту порядка существующих проверок WB без изменения API и схемы данных.

## Находки

Нет новых находок по данным, утечкам, секретам или персональным данным. Секреты, ключи, токены, `.env`, кабинеты учётных данных, живой Wildberries и production `194.87.96.144` не читались и не затрагивались.

## Блокеры

Git-сохранение блокируется правами среды на служебный каталог зарегистрированного worktree: нельзя создать `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-2-02-verdikt-screen1/index.lock`. Реализация и DEV-артефакт присутствуют локально, но новый восстанавливаемый commit SHA не создан.

# Фича 2

# DEV · 02-verdikt-screen · атом 2 · повторная проверка

## Что реализовано

- Эндпоинты: новых и изменённых эндпоинтов нет; API-контракт не менялся.
- Сервис: `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/backend/app/services/fbs_marking_service.py` при блокировке актуального состояния заранее загружает `FbsOrderMarking.marking_code` и восстанавливает `order.markings` из полученного набора без ленивого async-чтения. Подтверждённая замена ЧЗ после ответа WB больше не завершается `MissingGreenlet`.

## Миграции

Нет.

## Тесты

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/backend/tests/test_fbs_kiz.py::test_fbs_kiz_commit_confirmed_replaces_old_kiz_and_voids_code` проверяет штатную замену и погашение прежнего ЧЗ.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/backend/tests/test_fbs_kiz.py::test_fbs_kiz_pool_to_external_replacement_does_not_double_count_unit` проверяет, что замена пулового ЧЗ внешним сохраняет счётчик в одну единицу.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/backend/tests/test_fbs_kiz.py::test_fbs_marking_readers_prefer_active_row_over_newer_rejected_row` проверяет выбор активной строки при доступных загруженных связях.

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/backend/app/services/fbs_marking_service.py` — реализация атома сохранена в существующем commit `06b62a2dd400962db56b6cfd36605055caaceb04`.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/night/volna-9-recovery/cards/02-verdikt-screen/DEV.md` — отчёт повторной проверки.

## Гейты

- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/backend && python3 -m pytest -q tests/test_fbs_kiz.py::test_fbs_kiz_commit_confirmed_replaces_old_kiz_and_voids_code tests/test_fbs_kiz.py::test_fbs_kiz_pool_to_external_replacement_does_not_double_count_unit tests/test_fbs_kiz.py::test_fbs_marking_readers_prefer_active_row_over_newer_rejected_row` — `3 passed in 2.59s`.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/backend && python3 -m ruff check app/services/fbs_marking_service.py tests/test_fbs_kiz.py` — `All checks passed!`.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/backend && python3 -m mypy --follow-imports=silent app/services/fbs_marking_service.py` — `Success: no issues found in 1 source file`.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen && git diff --check -- backend/app/services/fbs_marking_service.py backend/tests/test_fbs_kiz.py night/volna-9-recovery/cards/02-verdikt-screen/DEV.md` — замечаний нет.
- `back_guard.py` не запускался: атом не добавляет и не меняет роуты.
- `check_migrations.py` не запускался: миграций нет.
- Полный backend-регресс, `ruff check .` и `mypy .` не запускались по правилу атомарного шага.

## Не реализовано

- Находка 1 повторного ревью относится к отдельному атомарному пункту 1 и уже сохранена в commit `16bbe667`; в этом атоме не менялась.
- Находка 3 относится к отдельному пункту 3 из `FEATURES.md`; она не входит в текущий атом 2.
- Находки 4–6 относятся к frontend-слою и не входят в роль backend-dev.

## Находки

Нет новых находок по данным, утечкам, секретам или персональным данным. Секреты, ключи, токены, `.env`, кабинеты учётных данных, живой Wildberries и production `194.87.96.144` не читались и не затрагивались.

## Блокеры

Повторное сохранение DEV-артефакта отдельным commit недоступно: команда `git add -- night/volna-9-recovery/cards/02-verdikt-screen/DEV.md` не смогла создать `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-2-02-verdikt-screen1/index.lock` (`Operation not permitted`). Реализация сервиса уже сохранена в commit `06b62a2dd400962db56b6cfd36605055caaceb04`; текущий DEV-артефакт существует локально в этой рабочей копии.

# Фича 3

# DEV · 02-verdikt-screen · атом 3

## Что реализовано

- Эндпоинты: новых и изменённых нет.
- Сервис: не менялся. Проверка закрепляет существующий серверный контракт успешного ответа WB.
- Тест: `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/backend/tests/test_fbs_kiz.py::test_fbs_kiz_commit_success_creates_records_event_and_counter` использует `_patch_wb_acceptance`, проверяет `metadata.verdict.delivery_allowed is True` и подпись `WB: принято`; ожидания `Нет ответа WB` в сценарии нет. Изменение теста уже сохранено в commit `16bbe667ce810bca05717e4c7c1232fa60d59082` и в этом атоме подтверждено точечным запуском.

## Миграции

Нет.

## Тесты

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/backend/tests/test_fbs_kiz.py::test_fbs_kiz_commit_success_creates_records_event_and_counter` — явный ответ WB `accepted` даёт оператору серверный вердикт «WB: принято» и разрешает сдачу.

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/night/volna-9-recovery/cards/02-verdikt-screen/DEV.md` — отчёт атома 3.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/backend/tests/test_fbs_kiz.py` — целевая проверка уже находится в сохранённом commit `16bbe667ce810bca05717e4c7c1232fa60d59082`; повторная правка не требовалась.

## Гейты

- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/backend && python3 -m pytest -q tests/test_fbs_kiz.py::test_fbs_kiz_commit_success_creates_records_event_and_counter` — `1 passed in 0.99s`.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/backend && python3 -m ruff check tests/test_fbs_kiz.py` — `All checks passed!`.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/backend && python3 -m mypy --follow-imports=silent tests/test_fbs_kiz.py` — `3 errors`; все три в существующих строках 1199, 1442 и 1810, вне атома 3. Целевая проверка на строках 1348–1349 диагностик не имеет.
- `back_guard.py` не запускался: атом не добавляет и не меняет роуты.
- `check_migrations.py` не запускался: миграций нет.
- Полный backend-регресс, `ruff check .` и `mypy .` не запускались по правилу атомарного шага.

## Не реализовано

- Не менялись API, сервисы, модели, роуты и миграции: атом ограничен проверкой уже работающего успешного ответа WB.
- Находки 1–2 относятся к атомам 1–2, а находки 4–6 — к frontend-слою; они не входят в этот атом backend-dev.

## Находки

- Mypy целевого тестового модуля сообщает три ранее существовавшие ошибки вне целевой проверки (строки 1199, 1442, 1810). Секреты, ключи, токены, `.env`, кабинеты учётных данных, живой Wildberries и production `194.87.96.144` не читались и не затрагивались.

## Блокеры

- Продуктовых и кодовых блокеров нет. Отчёт атома существует локально, но отдельный commit для него не создан: `git add -- night/volna-9-recovery/cards/02-verdikt-screen/DEV.md` не может создать `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-2-02-verdikt-screen1/index.lock` (`Operation not permitted`). Поэтому этот артефакт пока не восстановим из нового SHA; целевое исправление теста уже сохранено в `16bbe667ce810bca05717e4c7c1232fa60d59082`.

# Фича 4

# DEV · 02-verdikt-screen · атом 4

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/frontend/src/screens/v2/FfFbsSupplyWorkspace.tsx`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/frontend/tests-e2e/ff-fbs-supply.spec.ts`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/night/volna-9-recovery/cards/02-verdikt-screen/DEV.md`

## Гейты

- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/frontend && npx tsc --noEmit -p tsconfig.app.json` — зелёный, exit 0.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen && python3 scripts/ui/ui_guard.py` — красный, exit 1: новая проверка не относит `FfFbsSupplyWorkspace.tsx` к нарушениям; остаются чужие изменения вне разрешённых файлов атома: `src/components/WbProductPickerDialog.tsx` (`0 → 646`) и `src/screens/v2/SellerInboundDraftScreen.tsx` (`1111 → 1169`). Базовая линия не менялась.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/frontend && npm run test:unit` — зелёный: 20 test files, 148 tests passed; в том числе `src/screens/v2/FfFbsSupplyWorkspace.test.ts`.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/frontend && npx playwright test tests-e2e/ff-fbs-supply.spec.ts --grep 'stale successful refresh preserves fail-closed WB error'` — не запущен: web-server не смог привязать `127.0.0.1:18000` (`operation not permitted`) до запуска теста. Секреты, `.env`, внешний WB и production не читались и не затрагивались.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/frontend && npx playwright test tests-e2e/ff-fbs-supply.spec.ts --grep 'stale successful refresh preserves fail-closed WB error|failed workspace refresh closes WB delivery' --list` — зелёный: обнаружены ровно два относящихся сценария, включая новый сценарий гонки refresh.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen && git diff --check -- frontend/src/screens/v2/FfFbsSupplyWorkspace.tsx frontend/tests-e2e/ff-fbs-supply.spec.ts` — зелёный.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen && git add -- frontend/src/screens/v2/FfFbsSupplyWorkspace.tsx frontend/tests-e2e/ff-fbs-supply.spec.ts night/volna-9-recovery/cards/02-verdikt-screen/DEV.md && git commit -m 'fix(fbs): keep newer refresh failure fail-closed'` — не выполнен: Git не может создать `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-2-02-verdikt-screen1/index.lock` (`Operation not permitted`). Изменения существуют только локально в этой рабочей копии, нового восстанавливаемого SHA нет.

## Не реализовано

Нет. Атом 4 реализован буквально: запрос workspace получает номер поколения, и устаревший успешный ответ не может очистить более свежий fail-closed запрет. Следующие атомы 5–6 из `FEATURES.md` не менялись.

## Находки

Новых находок по данным, утечкам, секретам или персональным данным нет. Секреты, ключи, токены, `.env`, кабинеты учётных данных, живой Wildberries и production `194.87.96.144` не читались и не затрагивались.

# Фича 5

# DEV · 02-verdikt-screen · атом 5

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/frontend/tests-e2e/ff-fbs-supply.spec.ts` — сценарий `S-03-TC-004` передаёт pending-вердикт `WB: проверяет` с тоном `neutral` и ожидает подсказку `WB ещё не подтвердил код`.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/night/volna-9-recovery/cards/02-verdikt-screen/DEV.md` — обязательный артефакт этого атома.

## Гейты

- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/frontend && npx tsc --noEmit -p tsconfig.app.json` — зелёный, exit 0.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen && python3 scripts/ui/ui_guard.py` — красный, exit 1. Новые нарушения относятся не к этому атому и лежат вне разрешённого e2e-файла: `src/components/WbProductPickerDialog.tsx` (`экран-монолит 0 → 646`) и `src/screens/v2/SellerInboundDraftScreen.tsx` (`экран-монолит 1111 → 1169`). Базовая линия не менялась.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/frontend && npm run test:unit -- src/utils/metaStatus.test.ts` — зелёный, 1 файл / 9 тестов, exit 0.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/frontend && npx playwright test tests-e2e/ff-fbs-supply.spec.ts --grep 'pending WB verdict blocks delivery' --list` — зелёный, обнаружен ровно один сценарий `S-03-TC-004`, exit 0.
- Полный запуск Playwright не выполнялся: он поднимает Vite и backend, которые могут неявно загрузить `.env`; читать `.env` запрещено ролью. Другие e2e- или backend-наборы не запускались — это запрещено границами атома.

## Не реализовано

Все пункты атома 5 реализованы буквально. Находки ревью №1–4 и №6 относятся к другим атомам и файлам; они намеренно не изменялись.

## Находки

- Секреты, ключи, токены, `.env`, кабинеты учётных данных, живой Wildberries и production `194.87.96.144` не читались и не затрагивались.

# Фича 6

## Изменённые файлы

- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/frontend/tests-e2e/ff-fbs-supply.spec.ts
- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/night/volna-9-recovery/cards/02-verdikt-screen/DEV.md

## Гейты

- Зелёный: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/frontend && npx tsc --noEmit -p tsconfig.app.json`.
- Красный вне атома: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen && python3 scripts/ui/ui_guard.py` сообщил новые нарушения в неразрешённых для карточки файлах: `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/frontend/src/components/WbProductPickerDialog.tsx` и `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/frontend/src/screens/v2/SellerInboundDraftScreen.tsx`. Базовую линию не обновлял и чужие экраны не менял.
- Не выполнен из-за ограничения среды до старта тестов: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/frontend && npx playwright test tests-e2e/ff-fbs-supply.spec.ts --grep 'S-03-TC-018|stale successful refresh'`. Playwright не смог запустить web-server: `operation not permitted` при bind `127.0.0.1:18000`.
- Зелёный статический отбор атома и регрессии: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/frontend && npx playwright test tests-e2e/ff-fbs-supply.spec.ts --grep 'S-03-TC-018|stale successful refresh' --list` — найдены ровно два сценария.
- Зелёный связанный unit-регресс: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/frontend && npm run test:unit -- src/utils/metaStatus.test.ts` — 1 файл, 9 тестов.
- Коммит не создан: `git add ... && git commit ...` не смог создать `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-2-02-verdikt-screen1/index.lock` (`Operation not permitted`). Изменения остаются незакоммиченными в этой рабочей копии.

## Не реализовано

- Функциональных пунктов атома нет. TC-018 теперь закрывает рабочее место, моделирует сохранённый на сервере отказ WB, возвращает оператора в поставку и подтверждает отображение `WB не принял` с человеческой причиной, отсутствие диалога передачи и отсутствие запроса `/deliver`.
- Динамический запуск двух назначенных Playwright-сценариев не подтверждён из-за запрета среды на локальный порт; код и тест не изменялись за пределами разрешённого E2E-файла.

## Находки

- Секреты, ключи, токены, `.env`, кабинеты учётных данных, живой Wildberries и production `194.87.96.144` не читались и не затрагивались.
