# Фича 1

# Backend-dev · 02-verdikt-screen · rework

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/backend/app/services/fbs_workspace_service.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/backend/tests/test_fbs_marking.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/night/volna-9-recovery/cards/02-verdikt-screen/DEV.md`

## Что реализовано

- Сервис workspace: `_metadata_ready` теперь принимает сохранённый `metadata_delivery_allowed` как единый серверный вердикт, включая явный `False`; fallback к прежним статусам применяется только для старых записей без этого признака.
- Тест: S-03-TC-003 подтверждает, что `filled + reason=uinBadStatus` с техническим `accepted` не повышает готовность workspace; legacy-запись без серверного признака сохраняет прежний fallback.

## Миграции

Нет.

## Тесты

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/backend/tests/test_fbs_marking.py`: добавлена регрессия server-verdict → workspace progress для S-03-TC-003.

## Гейты

- `ruff check app/services/fbs_marking_service.py app/services/fbs_workspace_service.py tests/test_fbs_marking.py` — PASS.
- `ruff check .` — FAIL: 81 предсуществующая ошибка вне изменённых файлов.
- `mypy .` — FAIL: 21 предсуществующая ошибка в 6 файлах вне изменённых файлов.
- `pytest -q tests/test_fbs_marking.py` — PASS: 27 passed.
- `pytest` — FAIL/прерван после первого падения: `tests/test_fbs_kiz.py::test_fbs_marking_readers_prefer_active_row_over_newer_rejected_row`, 167 passed, 3 skipped. Фикстура ожидает разрешение при WB `decision=accepted`, которое не является допустимым положительным decision контракта этого атома; изменённый workspace-сервис в traceback не участвует.
- `python3 scripts/ci/back_guard.py` — BLOCKED: `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/scripts/ci/back_guard.py` отсутствует.
- `python3 scripts/ci/check_migrations.py` — BLOCKED: `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/scripts/ci/check_migrations.py` отсутствует.

## Не реализовано

- Frontend-находки 1 и 3 из REVIEW.md не входят в роль backend-dev и не менялись.
- Полные repo-гейты не зелёные по указанным предсуществующим проблемам вне атома.

## Блокеры

Нет.

# Фича 2

# Backend-dev · 02-verdikt-screen · фича 2/5

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/backend/app/services/fbs_shipment_service.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/backend/tests/test_fbs_shipment_deliver_gate_unit.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/night/volna-9-recovery/cards/02-verdikt-screen/DEV.md`

## Что реализовано

- Сервис передачи поставки: финальная серверная проверка повторно применяет единый WB-вердикт заказа и при блокировке возвращает исходный `DeliveryCheck` с понятным сообщением, идентификатором заказа и HTTP 400; прямой запрос не может отбросить этот результат.
- Сервис workspace: находка REVIEW.md о `accepted` вместе с WB reason уже исправлена в текущем HEAD (`298542a5`): явный сохранённый `metadata_delivery_allowed=False` имеет приоритет над legacy fallback.

## Миграции

Нет.

## Тесты

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/backend/tests/test_fbs_shipment_deliver_gate_unit.py`: S-03-TC-003 проверяет, что `filled` с причиной, `pending`, `required` и неизвестное решение останавливают доставку; ошибка финальной проверки сохраняет сообщение и идентификатор конкретного заказа.
- Целевой прогон `tests/test_fbs_shipment_deliver_gate_unit.py tests/test_fbs_marking.py`: PASS, 44 passed.

## Гейты

- `ruff check app/services/fbs_shipment_service.py tests/test_fbs_shipment_deliver_gate_unit.py` — PASS.
- `ruff check .` — FAIL: 81 предсуществующее нарушение вне изменённых файлов.
- `mypy .` — FAIL: 21 предсуществующее нарушение в 6 файлах вне атома.
- `pytest` — INCOMPLETE: среда прервала полный прогон без итоговой сводки; целевой прогон PASS, 44 passed.
- `python3 scripts/ci/back_guard.py` — BLOCKED: файла `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/scripts/ci/back_guard.py` нет в рабочей копии.
- `python3 scripts/ci/check_migrations.py` — BLOCKED: файла `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/scripts/ci/check_migrations.py` нет в рабочей копии.

## Не реализовано

- Frontend-находки 1 и 3 из REVIEW.md не входят в слой backend-dev и не менялись.
- Полные repo-гейты не стали зелёными из-за перечисленных предсуществующих нарушений вне атома.

## Блокеры

- Git commit не выполнен: песочница запретила создать `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-2-02-verdikt-screen1/index.lock`; итог существует только как локальный diff рабочей копии.

# Фича 3

# Реализация · 02-verdikt-screen · атом 3

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/frontend/src/screens/v2/fbsApi.ts`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/frontend/src/utils/metaStatus.ts`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/frontend/src/utils/metaStatus.test.ts`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/frontend/tests-e2e/ff-fbs-orders.spec.ts`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/night/volna-9-recovery/cards/02-verdikt-screen/DEV.md`

`uinBadStatus` переводится в `неверный статус УИН`; экранный сценарий теперь использует это реальное значение WB. Тип тона вердикта ограничен контрактными `neutral`, `ok` и `stop`. Unit-тест покрывает все шесть фиксированных подписей, реальную причину WB и безопасный fallback для неизвестной причины.

## Гейты

- `npx tsc --noEmit -p tsconfig.app.json` — не запущен до результата: в `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/frontend` отсутствует `node_modules`, локального `tsc` нет; `npx --no-install` в этом окружении не завершился.
- `python3 scripts/ui/ui_guard.py` — красный по не относящимся к атому файлам: `src/components/WbProductPickerDialog.tsx` (экран-монолит `0 → 646`) и `src/screens/v2/SellerInboundDraftScreen.tsx` (экран-монолит `1111 → 1169`). Затрагивать их роль не разрешает.
- `npm run test:unit` — красный: `sh: vitest: command not found`, потому что зависимости frontend не установлены.
- `git diff --check` — зелёный.

## Не реализовано

В атоме 3 не осталось нереализованных пунктов контракта. Находки 2 и 3 из `REVIEW.md` относятся соответственно к серверному workspace и `FfFbsSupplyWorkspace.tsx`, то есть к другим атомам; по ограничениям этой роли они не менялись.

Коммит не создан: Git не смог создать `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-2-02-verdikt-screen1/index.lock` из-за отсутствия права записи на метаданные общего репозитория. Итог сохранён только как локальный diff этой рабочей копии.

# Фича 4

# DEV · 02-verdikt-screen · атом 4

## Изменённые файлы

- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/frontend/src/screens/v2/FfFbsOrdersScreen.tsx — существующая зона «Статус» выводит серверный вердикт через `StatusChip`; при отказе и отсутствии ответа рядом остаётся понятный `TextCell` без технических полей.
- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/frontend/src/utils/metaStatus.ts — `uinBadStatus` переведён в «неверный статус УИН».
- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/frontend/tests-e2e/ff-fbs-orders.spec.ts — S-03-TC-001, S-03-TC-002, S-03-TC-003 и S-03-TC-006 используют реальный `uinBadStatus` и проверяют видимый русский текст.

Исправление первого пункта REVIEW.md уже присутствует в текущей ветке (commit `e8a5ee45`). Пункты 2–3 относятся к backend/workspace и не входят в разрешённый атом списка S-03; их не менял.

## Гейты

- `npx tsc --noEmit -p tsconfig.app.json` — не запущен до компиляции: в `frontend/node_modules` нет TypeScript, `npx` попытался скачать пакет из npm и завершился `ENOTFOUND` (сеть недоступна).
- `python3 scripts/ui/ui_guard.py` — красный только из-за новых нарушений в чужих файлах `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/frontend/src/components/WbProductPickerDialog.tsx` и `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/frontend/src/screens/v2/SellerInboundDraftScreen.tsx`. В `FfFbsOrdersScreen.tsx` храповик сообщает улучшение; базовую линию не обновлял.
- `npm run test:unit` — красный: `vitest: command not found`, зависимости frontend отсутствуют.
- `npx playwright test tests-e2e/ff-fbs-orders.spec.ts --grep 'shows the server WB verdict'` — не запущен: Playwright отсутствует, `npx` завершился `ENOTFOUND` при попытке скачать пакет из npm.

## Не реализовано

- Нет. Для этого атома все пункты контракта уже представлены в текущем коде списка: один `StatusChip` в существующей зоне статуса, `TextCell` с русской причиной при отказе, `Нет ответа WB` с «Сдача пока недоступна», без новой колонки и без технических WB-полей.

## Находки

- REVIEW.md, находки 2–3: единый серверный признак в workspace и локальная готовность строки требуют отдельной работы в backend/workspace; они находятся вне данного атома списка и его разрешённых файлов.

# Фича 5

# DEV · 02-verdikt-screen

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/frontend/src/screens/v2/FfFbsSupplyWorkspace.tsx`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/frontend/tests-e2e/ff-fbs-supply.spec.ts`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/night/volna-9-recovery/cards/02-verdikt-screen/DEV.md`

Рабочая строка теперь считает отметку о напечатанном ЧЗ только по серверному
`verdict.delivery_allowed`. Поэтому ответ WB `filled + reason=uinBadStatus` не
даёт одновременно зелёную галочку и блокирующий вердикт. Сценарий S-03-TC-007
воспроизводит именно этот ответ WB и проверяет отсутствие галочки, понятную
причину и блокировку передачи всей поставки.

## Гейты

- `npx tsc --noEmit -p tsconfig.app.json` — не запущен: локального `tsc` нет,
  а `npx` не смог скачать пакет из-за недоступности `registry.npmjs.org`
  (`ENOTFOUND`).
- `python3 scripts/ui/ui_guard.py` — красный только из-за новых нарушений в
  чужих файлах
  `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/frontend/src/components/WbProductPickerDialog.tsx`
  и
  `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/frontend/src/screens/v2/SellerInboundDraftScreen.tsx`.
  Изменённый S-03 улучшил свои счётчики, новых отступлений в нём нет.
- `npm run test:unit` — не запущен: отсутствует `vitest` в
  `frontend/node_modules` (`sh: vitest: command not found`).
- Целевые Playwright S-03-TC-004, S-03-TC-005 и S-03-TC-007 — не запущены:
  `frontend/node_modules/.bin/playwright` отсутствует. Сценарий S-03-TC-007
  обновлён статически для реального блокирующего ответа WB.
- `git diff --check` — зелёный.

## Не реализовано

- Находка ревью №2 в
  `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/backend/app/services/fbs_workspace_service.py`
  не менялась: это серверный сервис вне разрешённых файлов роли `screen-dev`.
  Она требует отдельной атомарной backend-правки, чтобы серверный
  `progress.metadata_ready` также не принимал `filled + reason`.

## Находки

- В текущей копии
  `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/frontend/src/utils/metaStatus.ts`
  уже содержит перевод `uinBadStatus` в «неверный статус УИН»; новый S-03-TC-007
  закрепляет реальный код в проверке рабочего места.
