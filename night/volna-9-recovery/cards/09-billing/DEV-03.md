# 09-billing · screen-dev · атом 3

Роль: `screen-dev`. Реализован только атом «Зафиксировать сетку таблицы “По исполнителям”» из `FEATURES.md` и относящаяся к нему находка R-09 из `DESIGN-REVIEW.md`.

В режиме «По исполнителям» все пять колонок получили фиксированные ширины `220 / 150 / 150 / 120 / 120 px`. Длинное имя исполнителя ограничено через общий `TextCell` и показывается с многоточием и штатной подсказкой, поэтому не раздвигает услугу, расчёт и числовые колонки. «Количество» и «Документов» сохранили правое выравнивание. Денежные колонки в режим не добавлялись.

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend/src/screens/ff/FfBillingScreen.tsx`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend/tests-e2e/billing-ledger.spec.ts`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/night/volna-9-recovery/cards/09-billing/DEV.md`

`frontend/tests-e2e/billing-ledger.spec.ts` сохраняет трассировку `S-31-TC-005`: заглушка возвращает длинное имя, сценарий переключает UI в режим «По исполнителям», проверяет все пять заголовков и их ширины, фактическое переполнение имени с многоточием, значения услуги и расчёта, правое выравнивание двух числовых ячеек и отсутствие «Ставки»/«Суммы».

## Гейты

- **Красный, существующий долг ветки** — точная команда `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend && npx tsc --noEmit -p tsconfig.app.json`, код возврата 2. В `FfBillingScreen.tsx` остаются прежние ошибки типизации условного `DataTable` и MUI-пропсов на строках 310–311; также воспроизводятся прежние ошибки в `FfSettingsScreen.tsx`, `SellersScreen.tsx` и `PeriodPicker.tsx`. Добавленные свойства `width`, `TextCell width` и E2E-сценарий отдельных новых ошибок TypeScript не дали. Исправление этого долга потребовало бы затронуть поведение и файлы вне атома.
- **Красный, существующий храповик ветки** — точная команда `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing && python3 scripts/ui/ui_guard.py`, код возврата 1. Повторены четыре ранее зафиксированные записи: `WbProductPickerDialog.tsx` `0 → 646`, `FfSettingsScreen.tsx` `701 → 795`, `FfFbsSupplyWorkspace.tsx` `2493 → 2498`, `SellerInboundDraftScreen.tsx` `1111 → 1169`; `App.tsx` отмечен как улучшившийся `3492 → 3491`. Базовая линия не обновлялась. Текущий атом не увеличил `FfBillingScreen.tsx` и не создал нового отклонения.
- **Зелёный** — точная команда `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend && task_temp_dir=$(mktemp -d /private/tmp/wms-billing-unit.XXXXXX) && TMPDIR="$task_temp_dir" npm run test:unit -- src/screens/ff/FfBillingScreen.test.ts --pool=threads --maxWorkers=1 --minWorkers=1`: 1 файл, 4 теста пройдены.
- **Красный по среде** — точная атомарная команда `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend && task_temp_dir=$(mktemp -d /private/tmp/wms-billing-e2e.XXXXXX) && TMPDIR="$task_temp_dir" npx playwright test tests-e2e/billing-ledger.spec.ts --grep "billing ledger performer mode keeps fixed columns and hides money"`, код возврата 1. Playwright поднял приложение до шага привязки API, но среда запретила bind `127.0.0.1:18000` с `operation not permitted`; сам браузерный кейс не стартовал. Конфигурация и порты ради обхода не менялись.
- **Зелёный** — точная команда `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend && npx playwright test tests-e2e/billing-ledger.spec.ts --grep "billing ledger performer mode keeps fixed columns and hides money" --list`: найден ровно 1 кейс атома в 1 файле.
- **Зелёный** — точная команда `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend && git diff --check`: замечаний нет.
- **Красный по правам среды** — точная команда `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing && git add -- frontend/src/screens/ff/FfBillingScreen.tsx frontend/tests-e2e/billing-ledger.spec.ts night/volna-9-recovery/cards/09-billing/DEV.md && git diff --cached --name-status && git diff --cached --check && git commit -m "fix(billing): stabilize performer table columns"`, код возврата 128. Git не смог создать `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-3-09-billing1/index.lock`: `Operation not permitted`. Ничего не попало в индекс; проверенного commit SHA нет. Чужое изменение `night/volna-9-recovery/JOURNAL.md` в команду не включалось.

Полный backend `pytest`, `pytest -q`, `ruff check .` и `mypy .` не запускались в соответствии с запретом атомарной проверки.

## Не реализовано

Пунктов контракта атома 3, которые не удалось реализовать буквально в коде, нет. Живой Playwright-прогон не выполнен только из-за запрета среды на локальный порт; он не подменён изменением тестовой конфигурации.

Код и отчёт локально реализованы, но не сохранены в Git из-за запрета записи в служебный каталог зарегистрированного worktree. До внешнего коммита результат остаётся уязвимым как незакоммиченный diff.

Находки `DESIGN-REVIEW.md` про колонки детализации счёта, короткую подпись повторного формирования и безопасное отображение неизвестных кодов относятся к атомам 4–6 и намеренно не затрагивались.

## Находки

`FfBillingScreen.tsx` и маршрут `/app/ff/billing` отсутствуют в `frontend/screens.registry.json`; существующий идентификатор `S-31` в реестре принадлежит `SellerProductsStockScreen`, хотя биллинговые тесты уже размечены `S-31-TC-*`. Реестр не входит в разрешённые файлы атома, поэтому не изменялся.

Секреты, ключи, токены, `.env`, кабинеты учётных данных, живой кабинет Wildberries и боевой прод `194.87.96.144` не открывались и не затрагивались. Новых находок по данным, утечкам или персональным данным в границах атома нет.
