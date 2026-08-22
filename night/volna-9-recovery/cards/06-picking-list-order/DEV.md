# Фича 1

# DEV · 06-picking-list-order · атом 1

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/frontend/src/ui-kit/ModalFrame.tsx` — `busy` теперь явно блокирует Escape; длинное тело модального документа имеет ограниченную высоту и прокрутку.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/frontend/src/ui-kit/FilterBar.tsx` — `ChoiceFilter` получил недоступное состояние с объясняющей подсказкой и корректным `aria-disabled`.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/frontend/src/ui-kit/Cells.tsx` — причина блокировки `CheckCell` доступна через подсказку на обёртке, которая принимает события у disabled-контрола.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/frontend/src/ui-kit/UiKitShowcase.tsx` — витрина показывает недоступный фильтр с причиной; при `busy` кнопка закрытия получает причину и блокируется.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/night/volna-9-recovery/cards/06-picking-list-order/DEV.md` — отчёт этого атома.

`PrintAction` со значением `стикеры заказов` и экспорты `ModalFrame`, `ChoiceFilter`, `CheckCell` уже присутствовали в разрешённых файлах и не требовали изменений в этой переделке.

## Гейты

- `npx tsc --noEmit -p tsconfig.app.json` — красный: локального `tsc` нет; `npx` не смог скачать пакет из-за недоступности `registry.npmjs.org` (`ENOTFOUND`).
- `python3 scripts/ui/ui_guard.py` — красный только из-за двух существующих нарушений вне атома: `frontend/src/components/WbProductPickerDialog.tsx` и `frontend/src/screens/v2/SellerInboundDraftScreen.tsx`. Базовая линия не менялась.
- `npm run test:unit` — красный: локальный `vitest` отсутствует (`sh: vitest: command not found`).
- `git diff --check` — зелёный.

## Не реализовано

- Находки 1–5 из `REVIEW.md` относятся к `FfFbsPickList.tsx`, `FbsPrintPreviewDialog.tsx`, API, backend-сервису и тестам экрана. Эти файлы вне слоя и границы атома 1, поэтому не менялись.
- Изолированный unit-тест нового примитива не добавлен: в данной рабочей копии нет установленного раннера `vitest`, а ревьюер не назвал тест ui-kit как разрешённый дополнительный файл.

## Находки

- Секреты, ключи, токены, `.env` и кабинеты учётных данных не читались.

# Фича 2

# Backend Dev · 06-picking-list-order · атом 2

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/backend/tests/test_fbs_supply_assembly.py` — расширена интеграционная проверка загрузки поставки: заказы с одинаковым `wb_order_id`, вставленные в обратном порядке, возвращаются по `order.id`.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/backend/app/models/fbs_supply.py` — без изменений в этом проходе: relationship уже задан как `order_by="(FbsOrder.wb_order_id, FbsOrder.id)"`.

## Гейты

- `ruff check .` (из `backend/`) — не пройден: 82 существующие ошибки вне изменённого атома; `ruff check tests/test_fbs_supply_assembly.py` — пройден.
- `mypy .` (из `backend/`) — не пройден: 21 существующая ошибка в 6 посторонних файлах.
- `pytest` (из `backend/`) — начат, собрано 821 тестов; среда вернула поток без финального итога. Целевой прогон `pytest tests/test_fbs_supply_assembly.py -k 'orders_are_returned_in_stable_order or relationship_orders_by_wb_id_then_internal_id'` — пройден, 2 passed.
- `python3 scripts/ci/back_guard.py` — не запущен: файл отсутствует в этой рабочей копии.
- `python3 scripts/ci/check_migrations.py` — не запущен: файл отсутствует в этой рабочей копии.
- `git diff --check` — пройден.

## Не реализовано

- Нет. Находки `REVIEW.md` относятся к печати, API-валидации и фронтенду следующих атомов; этот атом покрывает только стабильный порядок relationship поставки.

## Находки

- Для одного селлера одинаковый `wb_order_id` защищён производственным уникальным ограничением. Тест развязки использует двух селлеров одной организации, не отключая ограничение, и проверяет фактическую загрузку relationship через endpoint поставки.

# Фича 3

# DEV · 06-picking-list-order · атом 3

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/backend/tests/test_fbs_supply_assembly.py` — расширен API-сценарий `S-03-TC-009`: две позиции без товарных признаков образуют одну каноническую строку `№ 1–2`, а полный `order_ids` отсортирован по `wb_order_id`; запрос повторяется с идентичным ответом.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/night/volna-9-recovery/cards/06-picking-list-order/DEV.md` — отчёт backend-разработки по атому 3.

Существующая реализация в `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/backend/app/services/fbs_supply_service.py` и `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/backend/app/api/fbs_supplies.py` уже возвращает канонический порядок `(article, sku_code, size, product_name)`, непрерывные диапазоны и полный `order_ids`; изменений в ней не потребовалось.

## Гейты

- `ruff check tests/test_fbs_supply_assembly.py` — PASS.
- `ruff check .` — FAIL: 82 существующие несвязанные нарушения в backend; изменённый тест в них не указан.
- `mypy .` — FAIL: 21 существующая ошибка в 6 несвязанных файлах; атом 3 их не меняет.
- `pytest tests/test_fbs_supply_assembly.py` — PASS: `18 passed`.
- `pytest` — не завершён: после `61 passed` за 178 секунд остановлен вручную; до остановки ошибок не было.
- `python3 scripts/ci/back_guard.py` — NOT RUN: файл `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/scripts/ci/back_guard.py` отсутствует.
- `python3 scripts/ci/check_migrations.py` — NOT RUN: файл `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/scripts/ci/check_migrations.py` отсутствует.
- `git diff --check` — PASS.

## Не реализовано

- Миграций нет: атом 3 меняет вычисление и выдачу листа, не схему данных.
- Находки `REVIEW.md` о физической печати, popup, Честном знаке и предпросмотре относятся к frontend и слою ленты, не к серверной выдаче листа этого атома.

## Находки

- Нет.

# Фича 4

# Backend development report · 06-picking-list-order · atom 4 rework

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/backend/app/services/fbs_order_tape_print_service.py` — полная лента (`include_order_qr=true`) теперь принимает только актуальный полный состав поставки, по одному ID каждого заказа; построчная печать (`include_order_qr=false`) сохраняет прежний режим подмножества.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/backend/app/api/fbs_supplies.py` — неполный состав полной ленты возвращает `409 full_supply_order_set_required`; PNG-ассеты заказа отдают `order_id`, `wb_order_id` и канонический `order_number` для предпросмотра и физической пары WB → WMS № K.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/backend/tests/test_fbs_supply_assembly.py` — проверка точного полного множества ID, включая перемешанный порядок и дубликат.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/backend/tests/test_fbs_packaging_integration.py` — endpoint-регресс: неполный состав отклоняется, перемешанный полный состав сохраняет канонические номера; QR-ассеты несут номер и WB ID.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/night/volna-9-recovery/cards/06-picking-list-order/DEV.md` — отчёт этого прохода.

## Миграции

Нет: изменены правила валидации и API-представление существующих данных.

## Тесты

- `tests/test_fbs_supply_assembly.py -k fbs_order_tape` — 4 passed: канонический порядок, номер подмножества для старого режима, внешний ID и полный набор ID.
- `tests/test_fbs_packaging_integration.py -k tape_covers_every_order_and_matches_picking_list` — 1 passed: полный состав в перемешанном порядке, стабильная повторная печать, отказ для неполного состава и метаданные ассета.

## Гейты

- `ruff check .` — не пройден: 82 существующие диагностики вне изменённых файлов; точечный `ruff check` четырёх изменённых backend-файлов пройден.
- `mypy .` — не пройден: 21 существующая ошибка в 6 других файлах; затронутые сервис и API среди ошибок отсутствуют.
- `pytest` — полный запуск не дал финального отчёта в среде запуска (вывод остановился после первых тестов без диагностик); обязательные целевые тесты пройдены, как указано выше.
- `python3 scripts/ci/back_guard.py` — не запущен: `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/scripts/ci/back_guard.py` отсутствует.
- `python3 scripts/ci/check_migrations.py` — не запущен: `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/scripts/ci/check_migrations.py` отсутствует.
- `git diff --check` — пройден.
- `git commit` — не выполнен: среда запретила создание `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-3-06-picking-list-order/index.lock` (`Operation not permitted`); изменения остаются незакоммиченными в этой рабочей копии.

## Не реализовано

- Frontend-находки ревью о печати кодов Честного знака и popup относятся к UI-слою и не менялись в роли `backend-dev`.
- Новые маршруты и миграции не нужны.

## Находки

- Рабочее дерево уже содержало несвязанные изменения в `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/night/volna-9-recovery/JOURNAL.md`; они не изменялись.
- Git-метаданные общего worktree недоступны для записи, поэтому commit SHA не создан.

# Фича 5

## Изменённые файлы

- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/frontend/src/screens/v2/FfFbsSupplyWorkspace.tsx
- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/night/volna-9-recovery/cards/06-picking-list-order/DEV.md

## Гейты

- `npx tsc --noEmit -p tsconfig.app.json` (из `frontend/`) — зелёный.
- `python3 scripts/ui/ui_guard.py` (из корня) — зелёный.
- `npm run test:unit` (из `frontend/`) — красный: в рабочей копии нет локального `vitest` (`sh: vitest: command not found`).
- `git diff --check` — зелёный.

## Не реализовано

- Находки 1 и 2 относятся к `/frontend/src/screens/v2/FfFbsPickList.tsx`, который не входит в атом 5; они требуют отдельной доработки печатного окна и состава ленты с Честным знаком.
- Находка 3 относится к серверной проверке полного состава в `/backend/app/services/fbs_order_tape_print_service.py`; этот backend-слой не входит в атом 5.
- Находка 4 уже устранена серверным атомом 4: endpoint `print-assets` возвращает `wb_order_id` и `order_number`, которые существующий `FbsPrintPreviewDialog.tsx` показывает и использует для служебной этикетки. В этом атоме новых правок для него не потребовалось.
- Находка 5 требует Playwright-сценариев и относится к следующему атому 6; автоматический unit-gate сейчас не запускается из-за отсутствующего `vitest`.

# Фича 6

# Реализация · 06-picking-list-order

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/frontend/src/screens/v2/FfFbsPickList.tsx`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/frontend/src/screens/v2/FfFbsPickList.test.ts`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/night/volna-9-recovery/cards/06-picking-list-order/DEV.md`

В окне печати, созданном непосредственно жестом оператора, лента теперь сохраняет напечатанные коды «Честного знака», затем этикетку WB и служебную этикетку WMS с постоянным номером. При блокировке всплывающего окна операция на сервер не запускается, а оператор видит понятную ошибку.

## Гейты

- `npx tsc --noEmit -p tsconfig.app.json` из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/frontend` — зелёный.
- `npm run test:unit -- --run src/screens/v2/FfFbsPickList.test.ts` из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/frontend` — зелёный.
- `python3 scripts/ui/ui_guard.py` из корня — красный только на уже существующих чужих экранах: `src/components/WbProductPickerDialog.tsx` (экран-монолит `0 → 646`) и `src/screens/v2/SellerInboundDraftScreen.tsx` (экран-монолит `1111 → 1169`). Базовую линию не менял.
- `git diff --check` — зелёный.

## Не реализовано

- Прямые Playwright-сценарии `S-03-TC-001…007` не добавлены: `FfFbsPickList` не импортируется и не монтируется ни одним файлом в `frontend/src`, а подключение модалки требует правки `FfFbsSupplyWorkspace.tsx`, которого нет в разрешённом списке атома. Текущий unit-тест покрывает исправленную физическую последовательность ленты с кодом маркировки.
- Серверная проверка «клиент передал полный актуальный состав поставки» из замечания ревью относится к `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/backend/app/services/fbs_order_tape_print_service.py` и не входит в роль screen-dev.
- Исправление общего предпросмотра из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/frontend/src/screens/v2/FbsPrintPreviewDialog.tsx` не выполнено: это отдельный прямо названный ревьюером файл, но он не включён в ограниченный список текущего атома.

## Находки

Нет.
