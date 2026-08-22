# Фича 1

# Backend-dev · 02-verdikt-screen

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/backend/app/services/fbs_marking_service.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/backend/app/services/fbs_worklist_service.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/backend/tests/test_fbs_marking.py`

## Что реализовано

- Единый `_wb_order_verdict` теперь является источником `delivery_allowed` и `verdict` в metadata worklist.
- Старый `compute_delivery_allowed` делегирует тому же правилу, поэтому причина WB и decision больше не расходятся с финальной передачей.
- Отсутствующий или неизвестный ответ, включая незаполненное optional-требование, блокирует передачу; причина имеет приоритет, а отсутствие/неизвестность — приоритет над pending.
- Добавлены регрессии для причин, отсутствующего optional-ответа, конфликта отсутствия с pending и единого delivery gate.

## Миграции

Нет.

## Тесты

- `tests/test_fbs_marking.py`: S-03-TC-001…007 и регрессии агрегирования/совпадения API-гейта.

## Гейты

- `ruff check app/services/fbs_marking_service.py tests/test_fbs_marking.py` — PASS.
- `ruff check .` — FAIL: 83 существующие ошибки в репозитории; отдельная проверка изменённого сервиса и теста зелёная.
- `mypy .` — FAIL: 22 ошибки в 7 файлах, включая существующие ошибки; одна ошибка затрагивает тип `meta_details_json` в изменённом сервисе и требует отдельного общего типизационного прохода.
- `pytest -q tests/test_fbs_marking.py` — PASS, 26 passed.
- `pytest` — не завершён в доступное время; целевой набор зелёный.
- `python3 scripts/ci/back_guard.py` — BLOCKED: файл отсутствует в рабочей копии.
- `python3 scripts/ci/check_migrations.py` — BLOCKED: файл отсутствует в рабочей копии.

## Не реализовано

- Frontend-находки 1, 5 и 6 из `REVIEW.md` не реализованы: они относятся к `fbsApi.ts`, `FfFbsOrdersScreen.tsx` и `FfFbsSupplyWorkspace.tsx`, вне backend-dev атома.

## Блокеры

Нет продуктовых блокеров. Технические ограничения гейтов указаны выше.

# Фича 2

# Backend-dev · 02-verdikt-screen

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/backend/app/services/fbs_shipment_service.py` — передача проверяет единый `_wb_order_verdict`, а отказ содержит подпись, причину и UUID заказа.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/backend/tests/test_fbs_shipment_deliver_gate_unit.py` — unit-сценарии разрешённых и блокирующих WB-вердиктов.

## Гейты

- ruff: FAIL — 82 существующие ошибки в несвязанных backend-файлах.
- mypy: FAIL — существующие ошибки в `inventory_movement_report_service.py`, `wildberries_credentials_service.py`, служебных скриптах и stock/warehouse services; ошибок в изменяемом атоме нет.
- pytest: целевые тесты `43 passed`; полный прогон остановлен после `367 passed, 5 skipped` и показал 3 несвязанных падения (`test_fbs_kiz`, `test_fbs_stock_emulator_integration`, `test_fbs_supply_from_orders`).
- back_guard.py: BLOCKED — `scripts/ci/back_guard.py` отсутствует в этой рабочей копии.
- check_migrations.py: BLOCKED — `scripts/ci/check_migrations.py` отсутствует в этой рабочей копии.

## Не реализовано

- Нет: в рамках атома реализована только серверная проверка передачи поставки. Изменения списка и workspace относятся к другим атомам и не затрагивались.

## Блокеры

- Нет.

# Фича 3

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/frontend/src/screens/v2/fbsApi.ts`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/frontend/src/utils/metaStatus.ts`

В `fbsApi.ts` добавлена безопасная проверка серверного вердикта и нормализация
workspace после создания поставки и добавления заказов. Поэтому эти ответы больше
не обходят общий блокирующий fallback `Нет ответа WB`. В `metaStatus.ts`
неизвестная подпись также отображается только как блокирующее `Нет ответа WB`;
локальные поля заказа не используются для вывода разрешения.

## Гейты

- `npx tsc --noEmit -p tsconfig.app.json` — без диагностик; оболочка не вернула
  код завершения, поэтому числовой exit-код подтвердить не удалось.
- `python3 scripts/ui/ui_guard.py` — красный: новые нарушения обнаружены в
  несвязанных файлах `frontend/src/components/WbProductPickerDialog.tsx` и
  `frontend/src/screens/v2/SellerInboundDraftScreen.tsx`. Базовую линию не
  изменял.
- `npm run test:unit` — красный до запуска тестов: `vitest: command not found`
  (в рабочей копии отсутствует `frontend/node_modules`).

## Не реализовано

- Находки REVIEW, относящиеся к backend и экранным компонентам
  `FfFbsOrdersScreen.tsx`/`FfFbsSupplyWorkspace.tsx`, не исправлялись: они не
  входят в разрешённые файлы атома 3.

# Фича 4

# DEV · 02-verdikt-screen

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/frontend/src/screens/v2/FfFbsOrdersScreen.tsx`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/frontend/tests-e2e/ff-fbs-orders.spec.ts`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/night/volna-9-recovery/cards/02-verdikt-screen/DEV.md`

В существующей зоне статуса заказа сохранены единые `StatusChip` и `TextCell` для вердикта WB, включая русскую причину отказа и сообщение о недоступной сдаче. Дополнительно нейтрализован статус упакованной поставки: worklist поставок не содержит агрегированного WB-вердикта, поэтому экран больше не обещает «Готова к сдаче» до проверки заказов.

## Гейты

- `npx tsc --noEmit -p tsconfig.app.json` — не подтверждён: локальный `npx` не вернул диагностик или код завершения в доступное время, поэтому зелёным не считаю.
- `python3 scripts/ui/ui_guard.py` — красный из-за двух новых нарушений в несвязанных файлах `frontend/src/components/WbProductPickerDialog.tsx` и `frontend/src/screens/v2/SellerInboundDraftScreen.tsx`; для изменённого `FfFbsOrdersScreen.tsx` новых нарушений нет, показатели улучшились.
- `npm run test:unit` — красный: `vitest: command not found`, frontend-зависимости отсутствуют.
- Целевые Playwright-сценарии — не запущены: локальная Playwright-зависимость/стенд не доступна в этом окружении.
- `git diff --check` — без ошибок форматирования.

## Не реализовано

- Находки 1–4 из `REVIEW.md` относятся к backend и исправляются в соответствующих доменных слоях; они не входят в разрешённые файлы этого экранного атома.
- Находка 6 относится к `FfFbsSupplyWorkspace.tsx` и не входит в разрешённые файлы этого атома.
- Полный агрегированный WB-вердикт для строк поставок не может быть добавлен буквально: тип `FbsSupplyWorklistItem` и API-файлы находятся вне разрешённой границы. Поэтому исправлен только ложноположительный текст `Готова к сдаче`.

# Фича 5

# DEV · 02-verdikt-screen

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/frontend/src/screens/v2/FfFbsSupplyWorkspace.tsx`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/night/volna-9-recovery/cards/02-verdikt-screen/DEV.md`

## Гейты

- `npx tsc --noEmit -p tsconfig.app.json` (из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/frontend`) — не завершён: локальный `npx` зависает при попытке разрешить отсутствующую зависимость; команда остановлена после ожидания.
- `python3 scripts/ui/ui_guard.py` (из корня) — красный из-за существующих нарушений вне этого атома: `frontend/src/components/WbProductPickerDialog.tsx` и `frontend/src/screens/SellerInboundDraftScreen.tsx`. Для `FfFbsSupplyWorkspace.tsx` новых нарушений не обнаружено; показатель «своя-кнопка» улучшился с 37 до 36.
- `npm run test:unit -- --run src/screens/v2/FfFbsSupplyWorkspace.test.ts` (из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/frontend`) — не завершён вследствие отсутствующих frontend-зависимостей; локальный `npx`/тестовый раннер недоступен.
- Playwright S-03-TC-004, S-03-TC-005 и S-03-TC-007 — не запускались по той же причине отсутствующих frontend-зависимостей.
- Commit не создан: Git не смог создать `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-2-02-verdikt-screen1/index.lock` из-за ограничения доступа к служебному каталогу worktree.

## Не реализовано

- Находки REVIEW.md по backend-файлам и `FfFbsOrdersScreen.tsx` не изменялись: они относятся к другим слоям/файлам и не входят в границы этого атома.
- Исправление найдено в пределах `FfFbsSupplyWorkspace.tsx`: ответы workspace после операций нормализуются тем же безопасным правилом, что и начальная загрузка; открытый диалог и обработчик передачи повторно учитывают актуальный `deliveryBlocker`.

## Находки

- В рабочем дереве до этой правки уже были несвязанные изменения `night/volna-9-recovery/JOURNAL.md`; они не затрагивались.
