# Фича 1

# Backend-dev · 02-verdikt-screen · переделка атома 1

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/backend/app/services/fbs_marking_service.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/backend/tests/test_fbs_marking.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/night/volna-9-recovery/cards/02-verdikt-screen/DEV.md`

## Что реализовано

- `GET /operations/fbs-orders/{order_id}/metadata` — синхронизирует ответ WB и для заказа без локальных строк `FbsOrderMarking`, если WB запросил обязательные или необязательные метаданные; возвращает единый серверный вердикт и состояние необязательного требования.
- `POST /operations/fbs-orders/{order_id}/markings/sync` — больше не пропускает синхронизацию заказа без локальной маркировки, когда у заказа есть запрос метаданных WB.
- `_sync_order_meta_from_wb` — сохраняет свежие `metaDetails` на уровне заказа, включая `optional`/`notRequired` без локального кода, и не теряет их при объединении с локальными маркировками.
- `_wb_order_verdict` — читает сохранённый ответ WB на уровне заказа, сохраняет приоритет причины и блокеров и принимает совместимое историческое решение `accepted` как проходное.
- `build_order_metadata` — передаёт оба источника S-03 один и тот же вердикт и серверное состояние необязательного требования без технической подписи вместо продуктового текста.

## Миграции

Нет.

## Тесты

- `backend/tests/test_fbs_marking.py::test_fbs_metadata_preserves_optional_wb_decision_without_local_marking[False]` — S-03-TC-002: заказ только с необязательным требованием и без единой локальной маркировки получает `optional`, разрешение передачи и состояние с источником WB.
- `backend/tests/test_fbs_marking.py::test_fbs_metadata_preserves_optional_wb_decision_without_local_marking[True]` — S-03-TC-002/S-03-TC-007: `filled` обязательного кода вместе с `optional` без локальной строки агрегируются в проходной вердикт.
- Повторно пройден весь целевой `backend/tests/test_fbs_marking.py`, покрывающий S-03-TC-001…007, отсутствие/неизвестность ответа, приоритет причины и блокера.
- Повторно пройдён названный ревьюером `backend/tests/test_fbs_kiz.py::test_fbs_marking_readers_prefer_active_row_over_newer_rejected_row`: исторический `decision="accepted"` снова разрешает передачу.

## Гейты

- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/backend && pytest -q tests/test_fbs_marking.py tests/test_fbs_kiz.py::test_fbs_marking_readers_prefer_active_row_over_newer_rejected_row` — PASS, `32 passed in 7.96s`.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/backend && ruff check app/services/fbs_marking_service.py tests/test_fbs_marking.py` — PASS, `All checks passed!`.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/backend && mypy app/services/fbs_marking_service.py` — целевой изменённый модуль без ошибок; команда завершилась FAIL из-за четырёх предсуществующих ошибок в импортируемых соседних файлах `wildberries_credentials_service.py:167`, `fbs_stock_sync_service.py:617`, `fbs_warehouse_binding_service.py:23,291`.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/backend && mypy --follow-imports=skip --disable-error-code=no-any-return app/services/fbs_marking_service.py` — PASS, `Success: no issues found in 1 source file`; это изолированная проверка изменённого модуля, не подмена результата обычного целевого mypy выше.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/backend && git diff --check -- backend/app/services/fbs_marking_service.py backend/tests/test_fbs_marking.py` — PASS, ошибок пробелов нет.
- `back_guard.py` не запускался: новый роут не добавлялся.
- `check_migrations.py` не запускался: миграций нет.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen && git add -- backend/app/services/fbs_marking_service.py backend/tests/test_fbs_marking.py night/volna-9-recovery/cards/02-verdikt-screen/DEV.md` — BLOCKED средой: Git не смог создать `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-2-02-verdikt-screen1/index.lock`, `Operation not permitted`.

## Не реализовано

- Находка REVIEW №2 в `frontend/src/screens/v2/FfFbsSupplyWorkspace.tsx` не реализована: это UI-слой и отдельный атом роли `screen-dev`; backend-dev фронтенд не меняет.
- `backend/app/api/fbs_marking.py` не менялся: существующие response model и роуты уже содержат `verdict`; исправление потребовалось в вызываемом сервисе и покрыто реальным API-тестом.
- Следующие фичи из `FEATURES.md`, включая серверный запрет передачи поставки, не затрагивались: выполнен только атом 1.

## Находки

- Обычный целевой mypy красный только на четырёх ошибках в трёх соседних, не изменённых этим атомом сервисах; в `fbs_marking_service.py` ошибок после исправления нет.

## Блокеры

- Изменения локально реализованы и проверены, но не сохранены в Git-коммите: sandbox разрешает запись в рабочую копию, однако запрещает запись в общий служебный каталог `.git`, где расположен index этого зарегистрированного worktree. Commit SHA получить в этой сессии невозможно.

# Фича 2

# Backend-dev · 02-verdikt-screen · переделка атома 2

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/backend/tests/test_fbs_shipment_deliver_gate_unit.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/night/volna-9-recovery/cards/02-verdikt-screen/DEV.md`

## Что реализовано

- Эндпоинты: новых нет; существующий серверный путь передачи поставки повторно выполняет `_build_delivery_checks` и возвращает привязанный к заказу `marking_not_allowed`, поэтому прямой запрос не обходит WB-вердикт.
- Сервисы: производственное правило в `_build_delivery_checks` уже читает единый `_wb_order_verdict`; зависимая фича 1 в текущем `HEAD` уже сохраняет ответ `optional`/`notRequired` без локальной строки маркировки и поддерживает ранее сохранённый `accepted`, поэтому дополнительная правка сервиса после ревью не потребовалась.

## Миграции

Нет.

## Тесты

- В `backend/tests/test_fbs_shipment_deliver_gate_unit.py` добавлена регрессия S-03-TC-002: обязательный `sgtin=filled` существует локально, необязательный `imei=optional` существует только в агрегированных данных заказа, и финальный серверный gate разрешает передачу.
- Параметризованный тест проходных решений расширен ранее сохранённым `accepted`; `filled`, `optional` и `notRequired` без причины по-прежнему проходят.
- Целевой прогон включает весь unit-файл атома и два прямо названных ревью-регресса: сохранение необязательного ответа без локальной строки и чтение активной строки с `accepted`.

## Гейты

- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/backend && ruff check app/services/fbs_shipment_service.py tests/test_fbs_shipment_deliver_gate_unit.py` — PASS, `All checks passed!`.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/backend && mypy app/services/fbs_shipment_service.py app/services/fbs_marking_service.py` — FAIL на 4 предсуществующих ошибках в импортируемых соседних файлах `wildberries_credentials_service.py`, `fbs_stock_sync_service.py` и `fbs_warehouse_binding_service.py`; в двух целевых сервисах ошибок этим прогоном не найдено.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/backend && mypy --follow-imports=skip app/services/fbs_shipment_service.py app/services/fbs_marking_service.py` — FAIL на 11 предсуществующих `no-any-return` в самих сервисах; изменённый тест новых mypy-ошибок не добавляет.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/backend && pytest -q tests/test_fbs_shipment_deliver_gate_unit.py tests/test_fbs_marking.py::test_fbs_metadata_preserves_optional_wb_decision_without_local_marking tests/test_fbs_kiz.py::test_fbs_marking_readers_prefer_active_row_over_newer_rejected_row` — PASS, `23 passed in 2.74s`.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen && git diff --check` — PASS.
- `back_guard.py` не запускался: атом не добавляет роут.
- `check_migrations.py` не запускался: атом не добавляет миграцию.

## Не реализовано

- Frontend-находка ревью о зелёной заливке строки не исправлялась: она находится вне роли `backend-dev` и вне файлов backend-атома.
- Новые роуты, сервисные ветки и миграции не добавлялись: производственные исправления обеих backend-находок ревью уже находятся в зависимой фиче 1 текущего `HEAD`; этот проход закрыл недостающую регрессию именно на финальном shipment-gate.
- Полный backend-регресс не запускался по прямому запрету атомарного задания.

## Находки

- Целевой `mypy` остаётся красным на ранее существовавших ошибках, перечисленных в секции «Гейты»; тестовый и производственный код этого атома их не создаёт.
- Секреты, ключи, токены, `.env`, кабинеты учётных данных, живой Wildberries и production `194.87.96.144` не читались и не затрагивались.

## Блокеры

Нет.

# Фича 3

# Screen-dev · 02-verdikt-screen · переделка атома 3

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/frontend/src/screens/v2/fbsApi.test.ts`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/frontend/src/utils/metaStatus.test.ts`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/night/volna-9-recovery/cards/02-verdikt-screen/DEV.md`

`frontend/src/screens/v2/fbsApi.ts` и `frontend/src/utils/metaStatus.ts` проверены по контракту и замечаниям ревью. Их производственный код уже содержит серверный `readonly delivery_allowed`, шесть фиксированных подписей, контрактные тоны, русские причины и безопасный блокирующий fallback, поэтому повторная правка не потребовалась.

Добавлена регрессия клиентской границы для обоих ответов S-03: worklist и workspace сохраняют полученный серверный вердикт, а отсутствующее поле превращается в `Нет ответа WB` с запретом передачи. Типовой тест через `@ts-expect-error` закрепляет запрет присваивать новое значение серверному `delivery_allowed`. Словарь дополнительно проверен на приоритет непустой причины и безопасную обработку отсутствующей или неизвестной подписи.

## Гейты

- `npx tsc --noEmit -p tsconfig.app.json` из `frontend/` — зелёный.
- `python3 scripts/ui/ui_guard.py` из корня — красный на предсуществующих отклонениях вне файлов атома 3: `src/components/WbProductPickerDialog.tsx` (`экран-монолит 0 → 646`), `src/screens/v2/FfFbsSupplyWorkspace.tsx` (`экран-монолит 2493 → 2497`) и `src/screens/v2/SellerInboundDraftScreen.tsx` (`экран-монолит 1111 → 1169`). Базовая линия не обновлялась; эти файлы не исправлялись, потому что текущий атом разрешает только клиентский API, словарь и тесты этого слоя.
- `npm run test:unit` из `frontend/` — зелёный: 20 файлов, 149 тестов прошли.
- Целевая проверка сценариев ревью `pytest -q tests/test_fbs_marking.py::test_fbs_marking_sync_clears_stale_filled_verdict tests/test_fbs_shipment_deliver_gate_unit.py::test_delivery_sync_error_invalidates_stale_filled_verdict` из `backend/` — зелёная: 3 теста прошли (параметры пустого batch и ошибки WB плюс сбой синхронизации перед передачей).

## Не реализовано

- Зелёный `ui_guard.py` получить в границах атома 3 нельзя: каждое показанное нарушение находится в соседнем экранном коде, который контракт этого запуска запрещает менять. Базовую линию флагом `--update` не сдвигал.
- Backend-находки ревью не переписывались ролью `screen-dev`: они уже исправлены зависимыми атомами в текущем `HEAD` и подтверждены тремя целевыми регрессионными тестами.

## Находки

- Секреты, ключи, токены, `.env`, кабинеты учётных данных, живой Wildberries и production `194.87.96.144` не читались и не затрагивались.

# Фича 4

# DEV · 02-verdikt-screen · атом 4

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/night/volna-9-recovery/cards/02-verdikt-screen/DEV.md` — записан итог повторной проверки атома после `REVIEW.md`.

Исходники атома повторно не менялись: требуемый вывод одного `StatusChip` и
`TextCell` уже находится в текущей ветке, а обе находки ревью исправлены до этого
прохода в коммитах `32c38f9e50ddf7703cc3b70fa619c30b4835bac6` и
`dade3f19431846e6717749969355c317f5527a60`. Первый сохраняет серверный
`metadata.verdict` в реальном API-ответе и сбрасывает устаревший зелёный вердикт
при пустом или ошибочном свежем ответе WB. Второй закрывает тот же fail-closed
путь (безопасный запрет при ошибке) для прямой передачи поставки.

## Гейты

- `npx tsc --noEmit -p tsconfig.app.json` из `frontend/` — зелёный.
- `python3 scripts/ui/ui_guard.py` из корня — красный на общем состоянии ветки:
  новые превышения базовой линии найдены в
  `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/frontend/src/components/WbProductPickerDialog.tsx`,
  `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/frontend/src/screens/v2/FfFbsSupplyWorkspace.tsx` и
  `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/frontend/src/screens/v2/SellerInboundDraftScreen.tsx`.
  Для целевого
  `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/frontend/src/screens/v2/FfFbsOrdersScreen.tsx`
  guard сообщает улучшение: `свой-чип 2 → 1`, `экран-монолит 1587 → 1572`.
  Базовая линия не обновлялась; чужие и соседние файлы в этом атоме не правились.
- `npm run test:unit` из `frontend/` — зелёный: 20 файлов, 149 тестов.
- Узкие unit-тесты `fbsApi.test.ts` и `metaStatus.test.ts` — зелёные: 16 тестов.
- Backend-регрессии реального API и сброса устаревшего вердикта — зелёные:
  4 теста в `test_fbs_marking.py`, `test_fbs_shipment_deliver_gate_unit.py` и
  `test_fbs_worklist_query_count.py`.
- Playwright для S-03-TC-001, S-03-TC-002, S-03-TC-003 и S-03-TC-006 — не
  запущен до сценария: webServer не смог занять `127.0.0.1:18000`, среда вернула
  `[Errno 1] operation not permitted`. Сам сценарий остался без изменений и
  проверяет открытие списка через UI, четыре видимых вердикта, русскую причину,
  отсутствие `uinBadStatus` и текст `Сдача пока недоступна`.
- `git diff --check 31cd2f5f..HEAD` — зелёный.
- Новый коммит этого отчёта создать не удалось: Git попытался создать
  `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-2-02-verdikt-screen1/index.lock`,
  но файловая песочница разрешает этому пути только чтение и вернула
  `Operation not permitted`. Артефакт существует в рабочем дереве, однако его
  ещё должен сохранить в Git оркестратор с доступом к общему git-dir.

## Не реализовано

- Буквально не выполнен только живой Playwright-прогон названных сценариев:
  локальный HTTP-порт запрещён средой до запуска браузерного шага. Пункты
  контракта в коде и тесте реализованы; технические поля WB на странице не
  выводятся.
- Отчёт `DEV.md` локально записан, но не закоммичен из-за read-only доступа к
  общему git-dir этой зарегистрированной рабочей копии.

## Находки

- Новых продуктовых находок в файлах атома нет.

# Фича 5

# DEV · 02-verdikt-screen · переделка атома 5

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/frontend/src/screens/v2/FfFbsSupplyWorkspace.tsx`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/frontend/tests-e2e/ff-fbs-supply.spec.ts`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/night/volna-9-recovery/cards/02-verdikt-screen/DEV.md`

Исправлена находка 2 из `REVIEW.md`, относящаяся к фронтенд-слою этого атома. Сохранённый
хвост ЧЗ теперь окрашивает строку в зелёный цвет только при положительном
серверном `metadata.verdict.delivery_allowed`. При блокирующем вердикте строка больше
не показывает зелёную заливку и границу по одному лишь `value_tail`.

S-03-TC-007 усилен: обе строки имеют сохранённый код, но только проходная строка
имеет зелёные фон и границу. Тест сравнивает вычисленные браузером стили и падает
на прежней реализации.

## Гейты

- `npx tsc --noEmit -p tsconfig.app.json` из `frontend/` — зелёный, exit code 0.
- `npm run test:unit` из `frontend/` — зелёный: 20 файлов, 149 тестов прошли.
- `python3 scripts/ui/ui_guard.py` из корня — общий гейт красный, exit code 1, только из-за
  соседних `frontend/src/components/WbProductPickerDialog.tsx` (`экран-монолит 0 → 646`) и
  `frontend/src/screens/v2/SellerInboundDraftScreen.tsx` (`экран-монолит 1111 → 1169`). Целевой
  `FfFbsSupplyWorkspace.tsx` нового нарушения не добавил; храповик показал улучшение `своя-кнопка 37 → 36`.
  Базовая линия не обновлялась.
- `npx playwright test tests-e2e/ff-fbs-supply.spec.ts --grep 'pending WB verdict blocks delivery|required WB verdict explains missing code|one blocked order prevents whole-supply delivery'`
  из `frontend/` — браузерный прогон не начался: Playwright webServer получил `[Errno 1] operation not permitted`
  при попытке занять `127.0.0.1:18000`; exit code 1.
- `npx playwright test tests-e2e/ff-fbs-supply.spec.ts --grep 'pending WB verdict blocks delivery|required WB verdict explains missing code|one blocked order prevents whole-supply delivery' --list`
  из `frontend/` — зелёный: найдены ровно S-03-TC-004, S-03-TC-005 и S-03-TC-007, всего 3 теста в 1 файле.
- `git diff --check` — зелёный.
- `git add -- frontend/src/screens/v2/FfFbsSupplyWorkspace.tsx frontend/tests-e2e/ff-fbs-supply.spec.ts night/volna-9-recovery/cards/02-verdikt-screen/DEV.md && git diff --cached --check && git commit -m "fix(s03): respect verdict in marking row"`
  из корня — коммит не создан: Git не смог создать `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-2-02-verdikt-screen1/index.lock`,
  среда вернула `Operation not permitted`. Чужой `JOURNAL.md` в команду не включался.

## Не реализовано

- Живой прогон S-03-TC-004, S-03-TC-005 и S-03-TC-007 не выполнен из-за запрета среды на локальный
  HTTP-порт. Конфигурация тестов корректно находит все три сценария.
- Общий `ui_guard.py` нельзя сделать зелёным в границах этой роли: оба оставшихся нарушения
  находятся в файлах соседних экранов, которые контракт запрещает менять.
- Изменения локально реализованы, но не сохранены Git-коммитом из-за запрета песочницы на запись
  в общий Git-dir. Оркестратору нужно закоммить три файла из секции «Изменённые файлы».

## Находки

- Секреты, ключи, токены, `.env`, кабинеты учётных данных, живой Wildberries и production `194.87.96.144` не читались и не затрагивались.
