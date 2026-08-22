# Фича 1

# Backend-dev · 02-verdikt-screen · переделка атома 1

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/backend/app/api/fbs_orders.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/backend/app/services/fbs_marking_service.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/backend/tests/test_fbs_marking.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/backend/tests/test_fbs_worklist_query_count.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/backend/tests/test_fbs_kiz.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/night/volna-9-recovery/cards/02-verdikt-screen/DEV.md`

## Что реализовано

- `GET /operations/fbs-orders/worklist` — схема ответа сохраняет серверный объект `metadata.verdict` с подписью, тоном, причиной и разрешением передачи.
- `GET /operations/fbs-supplies/{supply_id}/workspace` — наследуемая схема заказа также сохраняет тот же `metadata.verdict`; Pydantic больше не вырезает его из реального ответа.
- `_reset_stale_wb_verdict` — перед свежим запросом WB очищает прежние `decision` и `reason`, переводит затронутые требования в неизвестное состояние и закрывает передачу.
- `_sync_order_meta_from_wb` — пустой batch, отсутствующая строка заказа, пустой `metaDetails` и ошибка WB больше не оставляют прежний зелёный `filled`; подавленная при финальной синхронизации ошибка остаётся fail-closed (передача запрещена).

## Миграции

Нет.

## Тесты

- `backend/tests/test_fbs_marking.py` — добавлена параметризованная регрессия S-03-TC-006/012 на переход `filled → пустой batch` и `filled → ошибка WB`; оба варианта очищают старое решение и запрещают передачу.
- `backend/tests/test_fbs_worklist_query_count.py` — реальный `GET /operations/fbs-orders/worklist` проверяет, что серверный положительный вердикт доезжает без вырезания схемой ответа.
- `backend/tests/test_fbs_kiz.py` — реальный workspace проверяет наличие и содержание серверного вердикта в `metadata` заказа.
- Целевой прогон — `31 passed`.
- Полный прогон — `842 passed, 5 skipped, 2 failed`; падения предсуществующие: `test_fbs_marking_readers_prefer_active_row_over_newer_rejected_row` ожидает разрешение для не входящего в контракт положительного набора решения `accepted`, а `test_fbs_cutoff_autoplans_supply_manual_date_and_calendar` использует прошедшую дату и получает `deadline_passed`.

## Гейты

- `ruff check .` — FAIL: 79 предсуществующих ошибок вне изменённого атома; целевой `ruff` по пяти изменённым Python-файлам — PASS.
- `mypy .` — FAIL: 21 предсуществующая ошибка в 6 файлах вне изменённого атома; новых ошибок реализации в полном выводе нет.
- `pytest` — FAIL: 842 passed, 5 skipped, 2 предсуществующих падения; целевой прогон атома — PASS, 31 passed.
- `python3 scripts/ci/back_guard.py` — BLOCKED: файл `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/scripts/ci/back_guard.py` отсутствует.
- `python3 scripts/ci/check_migrations.py` — BLOCKED: файл `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/scripts/ci/check_migrations.py` отсутствует.
- `git diff --check` — PASS.

## Не реализовано

- Новых роутов и миграций нет: контракт этого атома их не требует.
- `backend/app/api/fbs_marking.py` не менялся: его отдельный endpoint метаданных уже объявляет `verdict` и не содержит находку ревью.
- `backend/app/services/fbs_shipment_service.py` не менялся: его подавление ошибки теперь безопасно, потому что вызываемый marking-сервис до выброса ошибки очищает старый вердикт в текущей транзакции; соседнюю продуктовую логику передачи не расширял.

## Находки

- Секреты, токены, персональные данные и утечки не читались и не исследовались.

## Блокеры

- Git-коммит технически невозможен в текущей песочнице: `git add` не может создать `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-2-02-verdikt-screen1/index.lock` (`Operation not permitted`). Изменения и артефакт находятся в постоянной рабочей копии, но не сохранены коммитом.

# Фича 2

# Backend-dev · 02-verdikt-screen · переделка атома 2

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/backend/app/services/fbs_shipment_service.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/backend/tests/test_fbs_shipment_deliver_gate_unit.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/night/volna-9-recovery/cards/02-verdikt-screen/DEV.md`

## Что реализовано

- Эндпоинты: новых нет; существующая финальная передача поставки продолжает вызывать серверный preflight и не получает отдельного пути обхода.
- `_sync_supply_orders_from_wb`: любой `FbsMarkingError`, в том числе возникший до запроса метаданных WB, теперь явно сбрасывает прежний положительный вердикт заказа и сохраняет блокирующее неизвестное состояние.
- `_build_delivery_checks` / `_validate_checks_pass`: после сбоя свежей синхронизации возвращают `Нет ответа WB` с идентификатором конкретного заказа и отклоняют прямой запрос на передачу HTTP 400.

## Миграции

Нет.

## Тесты

- `backend/tests/test_fbs_shipment_deliver_gate_unit.py`: добавлен S-03-TC-006/012 на переход `filled → ошибка свежей синхронизации`; старое решение очищается, передача блокируется, а результат содержит конкретный `order_id`.
- Существующий параметризованный тест подтверждает, что `filled`, `optional` и `notRequired` без причины проходят, а `filled` с причиной, `pending`, `required` и неизвестное решение WB останавливают передачу.
- Целевой прогон `tests/test_fbs_shipment_deliver_gate_unit.py tests/test_fbs_marking.py`: PASS, 47 passed.
- Полный прогон: 843 passed, 5 skipped, 2 failed. Оба падения предсуществующие и вне атома: `test_fbs_marking_readers_prefer_active_row_over_newer_rejected_row` ожидает разрешение для неконтрактного решения `accepted`; `test_fbs_cutoff_autoplans_supply_manual_date_and_calendar` использует прошедшую дату и получает `deadline_passed`.

## Гейты

- `ruff check .` — FAIL: 79 предсуществующих нарушений вне изменённого атома; целевой `ruff check app/services/fbs_shipment_service.py tests/test_fbs_shipment_deliver_gate_unit.py` — PASS.
- `mypy .` — FAIL: 21 предсуществующая ошибка в 6 файлах вне изменённого атома; изменённые файлы в полном выводе отсутствуют.
- `pytest` — FAIL: 843 passed, 5 skipped, 2 предсуществующих падения вне атома; целевой прогон — PASS, 47 passed.
- `python3 scripts/ci/back_guard.py` — BLOCKED: файл `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/scripts/ci/back_guard.py` отсутствует.
- `python3 scripts/ci/check_migrations.py` — BLOCKED: файл `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/scripts/ci/check_migrations.py` отсутствует.
- `git diff --check` — PASS.

## Не реализовано

- Новые роуты и миграции не добавлялись: контракт атома их не требует.
- Находка ревью о схеме `metadata.verdict` и сброс при пустом batch уже исправлена зависимой фичей 1 в текущем HEAD; соседние UI-задачи не менялись.

## Находки

- Секреты, ключи, токены, `.env`, кабинеты учётных данных, живой WB и production `194.87.96.144` не читались и не затрагивались.

## Блокеры

- Реализация и целевые тесты завершены локально, но результат не сохранён коммитом: песочница запретила создать `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-2-02-verdikt-screen1/index.lock` (`Operation not permitted`). Риск: изменения пока существуют только в рабочем дереве этой постоянной рабочей копии.
- Незелёные и отсутствующие общие гейты перечислены выше; они не относятся к изменённому атому.

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

Рабочее место уже читало готовность строки и доступность действия только из
серверного `metadata.verdict.delivery_allowed`. В переделке сохранено это
поведение и убрано новое превышение храповика размера целевого экрана без
изменения разметки или интерфейса.

Тестовый ответ workspace теперь считает серверный `progress.metadata_ready`
по тому же `verdict.delivery_allowed`, а сценарии S-03-TC-004, S-03-TC-005 и
S-03-TC-007 дополнительно проверяют, что `pending`, `required` и один
отклонённый заказ не сосуществуют с оптимистичным полным прогрессом готовности.
S-03-TC-007 по-прежнему проверяет видимую русскую причину, отсутствие зелёной
галочки для заблокированного заказа и `disabledReason` с номером заказа.

Обе находки `REVIEW.md` уже исправлены в зависимом серверном слое текущего
`HEAD`: реальный API сохраняет `metadata.verdict`, а свежий пустой или ошибочный
ответ WB сбрасывает прежний зелёный вердикт. Их регрессии повторно проверены.

## Гейты

- `npx tsc --noEmit -p tsconfig.app.json` из `frontend/` — зелёный.
- `npm run test:unit` из `frontend/` — зелёный: 20 файлов, 149 тестов прошли.
- `python3 scripts/ui/ui_guard.py` из корня — общий гейт красный только на
  соседних файлах `frontend/src/components/WbProductPickerDialog.tsx` и
  `frontend/src/screens/v2/SellerInboundDraftScreen.tsx`. Целевой
  `frontend/src/screens/v2/FfFbsSupplyWorkspace.tsx` больше не нарушает
  храповик и улучшил счётчики: `экран-монолит 2493 → 2492`, `своя-кнопка 37 → 36`.
  Базовая линия не обновлялась.
- Playwright S-03-TC-004, S-03-TC-005 и S-03-TC-007 — исполнение заблокировано
  до браузерного шага: webServer не может занять `127.0.0.1:18000`, среда
  возвращает `[Errno 1] operation not permitted`. `playwright --list` зелёный и
  обнаруживает все три целевых теста.
- Серверные регрессии находок ревью — зелёные: 4 теста прошли, 6 отфильтрованы.
- `git diff --check` — зелёный.

## Не реализовано

- Буквально не выполнен живой прогон трёх Playwright-сценариев: запуск
  останавливает запрет среды на локальный HTTP-порт до открытия браузера.
- Общий `ui_guard.py` нельзя сделать зелёным в границах атома: два оставшихся
  нарушения находятся в соседних файлах, которые роль `screen-dev` и контракт
  запрещают менять.
- Результат локально реализован, но не сохранён Git-коммитом: песочница не даёт
  создать `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-2-02-verdikt-screen1/index.lock`
  (`Operation not permitted`). Оркестратору с доступом на запись к общему
  git-dir нужно закоммитить три файла из секции «Изменённые файлы».

## Находки

- Секреты, ключи, токены, `.env`, кабинеты учётных данных, живой Wildberries и
  production `194.87.96.144` не читались и не затрагивались.
