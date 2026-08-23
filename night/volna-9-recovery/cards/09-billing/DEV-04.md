# 09-billing · screen-dev · атом 4

Роль: `screen-dev`. Изменён только атом «Выровнять и закрепить колонки детализации счёта» из `FEATURES.md` и относящиеся к нему находки R-08 и R-09 из `DESIGN-REVIEW.md`.

В диалоге выставленного счёта таблица строк получила фиксированную сетку шести колонок: `180 / 170 / 120 / 130 / 140 / 70 px`. Заголовки и значения «Количество», «Ставка» и «Сумма» выровнены вправо; узкая колонка «Детализация» и её действие выровнены по центру. Состав колонок, данные и действие «Показать документы» не менялись.

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend/src/screens/ff/FfBillingScreen.tsx`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend/tests-e2e/billing-invoices.spec.ts`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/night/volna-9-recovery/cards/09-billing/DEV.md`

`frontend/tests-e2e/billing-invoices.spec.ts` сохраняет трассировку `S-31-TC-007`: сценарий открывает выставленный счёт и проверяет все шесть заголовков и значений, фиксированные ширины, правое выравнивание трёх числовых колонок, центральное выравнивание детализации и прежнее раскрытие исходных документов.

## Гейты

- **Красный, существующий долг ветки** — точная команда `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend && npx tsc --noEmit -p tsconfig.app.json`, код возврата 2. В `FfBillingScreen.tsx` повторились прежние ошибки условного `DataTable`, старых MUI-пропсов и `testId` у `DangerAction`; также повторились ранее зафиксированные ошибки в `FfSettingsScreen.tsx`, `SellersScreen.tsx` и `PeriodPicker.tsx`. Добавленные `width` и `align` отдельных новых ошибок TypeScript не дали.
- **Красный, существующий храповик ветки** — точная команда `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing && python3 scripts/ui/ui_guard.py`, код возврата 1. Повторены четыре ранее зафиксированные записи: `WbProductPickerDialog.tsx` `0 → 646`, `FfSettingsScreen.tsx` `701 → 795`, `FfFbsSupplyWorkspace.tsx` `2493 → 2498`, `SellerInboundDraftScreen.tsx` `1111 → 1169`; `App.tsx` отмечен как улучшившийся `3492 → 3491`. `FfBillingScreen.tsx` не появился в списке новых отступлений, базовая линия не обновлялась.
- **Зелёный** — точная команда `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend && task_temp_dir=$(mktemp -d /private/tmp/wms-billing-unit.XXXXXX) && TMPDIR="$task_temp_dir" npm run test:unit -- src/screens/ff/FfBillingScreen.test.ts --pool=threads --maxWorkers=1 --minWorkers=1`: 1 файл, 4 теста пройдены.
- **Красный по среде** — точная атомарная команда `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend && task_temp_dir=$(mktemp -d /private/tmp/wms-billing-e2e.XXXXXX) && TMPDIR="$task_temp_dir" npx playwright test tests-e2e/billing-invoices.spec.ts --grep "billing invoice opens, reveals documents and starts print"`, код возврата 1. Playwright создал тестовую схему, но локальный API не смог привязать `127.0.0.1:18000`: `operation not permitted`; браузерный кейс не стартовал. Конфигурация и порты ради обхода не менялись.
- **Зелёный** — точная команда `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend && npx playwright test tests-e2e/billing-invoices.spec.ts --grep "billing invoice opens, reveals documents and starts print" --list`: найден ровно 1 кейс атома в 1 файле.
- **Зелёный** — точная команда `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing && git diff --check`: замечаний нет.
- **Красный по правам среды** — точная команда `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing && git diff --check && git add -- frontend/src/screens/ff/FfBillingScreen.tsx frontend/tests-e2e/billing-invoices.spec.ts night/volna-9-recovery/cards/09-billing/DEV.md && git diff --cached --name-status && git diff --cached --check && git commit -m "fix(billing): align invoice detail columns"`, код возврата 128. Git не смог создать `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-3-09-billing1/index.lock`: `Operation not permitted`. Ничего не попало в индекс; проверенного commit SHA нет. Чужое изменение `night/volna-9-recovery/JOURNAL.md` в команду не включалось.

Полный backend `pytest`, `pytest -q`, `ruff check .` и `mypy .` не запускались в соответствии с запретом атомарной проверки.

## Не реализовано

Пунктов контракта атома 4, которые не удалось реализовать буквально в коде, нет. Живой Playwright-прогон не выполнен только из-за запрета среды на локальный порт; он не подменён изменением тестовой конфигурации.

Изменения локально реализованы и артефакт записан, но среда не позволила сохранить их в Git. До внешнего коммита результат остаётся уязвимым как незакоммиченный diff.

Находки `DESIGN-REVIEW.md` про короткую подпись повторного формирования и безопасное отображение неизвестных кодов относятся к атомам 5–6 и намеренно не затрагивались. Находки в `FfSettingsScreen.tsx` относятся к уже предшествующим атомам и также не входят в границы атома 4.

## Находки

`FfBillingScreen.tsx` и маршрут `/app/ff/billing` отсутствуют в `frontend/screens.registry.json`; существующий идентификатор `S-31` в реестре принадлежит `SellerProductsStockScreen`, хотя биллинговые тесты уже размечены `S-31-TC-*`. Реестр не входит в разрешённые файлы атома, поэтому не изменялся.

Секреты, ключи, токены, `.env`, кабинеты учётных данных, живой кабинет Wildberries и боевой прод `194.87.96.144` не открывались и не затрагивались. Новых находок по данным, утечкам или персональным данным в границах атома нет.
