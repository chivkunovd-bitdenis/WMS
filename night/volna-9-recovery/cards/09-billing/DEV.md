# Фича 1

# 09-billing · screen-dev · атом 1

Роль: `screen-dev`. Реализован только атом «Сделать переключатель разделов настроек настоящими вкладками» из `FEATURES.md`.

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend/src/screens/ff/FfSettingsScreen.tsx`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend/src/screens/ff/FfSettingsScreen.test.ts`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend/tests-e2e/billing-tariffs.spec.ts`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/night/volna-9-recovery/cards/09-billing/DEV.md`

`FfSettingsScreen` теперь использует семантические MUI-вкладки `Tabs`/`Tab`. У выбранной вкладки есть штатный нижний индикатор и `aria-selected="true"`; доступ к «Тарифам ФФ» по-прежнему есть только у администратора. Содержимое разделов не менялось. Добавлены узкий unit-тест начального выбранного состояния и пользовательский Playwright-сценарий `S-19-TC-001` с переходом в «Тарифы ФФ» и обратно.

## Гейты

- **Красный** — `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend && npx tsc --noEmit -p tsconfig.app.json`. Код возврата 2. Компиляцию блокируют уже существующие ошибки вне строк этого атома: типы таблиц и MUI-пропсы в `FfBillingScreen.tsx`, старые `inputProps`/`SelectProps`/`InputLabelProps` и неиспользуемый `EmptyState` в тарифной части `FfSettingsScreen.tsx`, `inputProps` в `SellersScreen.tsx` и `PeriodPicker.tsx`. В добавленных `Tabs`/`Tab` ошибок TypeScript нет.
- **Красный** — `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing && python3 scripts/ui/ui_guard.py`. Код возврата 1. Храповик воспроизводит существующие отклонения: `WbProductPickerDialog.tsx` 0 → 646, `FfSettingsScreen.tsx` 701 → 795, `FfFbsSupplyWorkspace.tsx` 2493 → 2498, `SellerInboundDraftScreen.tsx` 1111 → 1169. Базовая линия не обновлялась. Физический размер `FfSettingsScreen.tsx` до и после атома одинаковый: 794 строки, поэтому вкладки не добавили нового роста монолита.
- **Зелёный** — `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend && npm run test:unit -- src/screens/ff/FfSettingsScreen.test.ts`. Один файл и один тест пройдены.
- **Красный по среде** — `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend && npx playwright test tests-e2e/billing-tariffs.spec.ts --grep "admin switches between settings tabs"`. Playwright не смог запустить локальный webServer: привязка `127.0.0.1:18000` запрещена средой с ошибкой `operation not permitted`; сам тест не стартовал.
- **Зелёный** — `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend && npx playwright test tests-e2e/billing-tariffs.spec.ts --grep "admin switches between settings tabs" --list`. Найден ровно один требуемый кейс в одном файле.
- **Зелёный** — `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing && git diff --check`.
- **Красный по среде** — `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing && git add -- frontend/src/screens/ff/FfSettingsScreen.tsx frontend/src/screens/ff/FfSettingsScreen.test.ts frontend/tests-e2e/billing-tariffs.spec.ts night/volna-9-recovery/cards/09-billing/DEV.md && git diff --cached --name-status && git diff --cached --check && git commit -m "fix(settings): use semantic billing tabs"`. Git не смог создать `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-3-09-billing1/index.lock`: `Operation not permitted`. Коммит не создан.

Перед проверками зависимости установлены строго из lock-файла командой `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend && npm ci --prefer-offline --no-audit --no-fund`; `package-lock.json` не изменён.

## Не реализовано

Пунктов контракта, которые не удалось реализовать буквально в коде атома, нет. Не выполнен только живой прогон Playwright-сценария из-за запрета локального порта в среде; это не заменено изменением тестовой конфигурации или обходом проверки.

Находка R-31 про одиночную кнопку «Закрыть» в истории ставок относится к следующему атому из `FEATURES.md` и намеренно не исправлялась здесь. Остальные находки `DESIGN-REVIEW.md` относятся к `FfBillingScreen.tsx` и также находятся вне этого атома.

## Находки

Секреты, ключи, токены, `.env`, кабинеты учётных данных и боевой прод не читались и не затрагивались. Новых находок по данным, утечкам или персональным данным в границах атома нет.

## Блокеры

Изменения локально реализованы и артефакт записан, но не сохранены в Git: среда запрещает запись в служебный каталог зарегистрированного worktree. Проверенного commit SHA нет. Кроме того, обязательные `tsc` и `ui_guard.py` остаются красными на перечисленных выше существующих отклонениях, а живой Playwright-прогон не стартует из-за запрета локального порта.

# Фича 2

# 09-billing · screen-dev · атом 2

Роль: `screen-dev`. Реализован только атом «Показывать ставки единым денежным форматом и историю в диалоге» из `FEATURES.md` с исправлением относящихся к нему находок R-08 и R-31 из `DESIGN-REVIEW.md`.

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend/src/screens/ff/FfSettingsScreen.tsx`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend/tests-e2e/billing-tariffs.spec.ts`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/night/volna-9-recovery/cards/09-billing/DEV.md`

В действующей таблице и в версиях истории ставка теперь выводится общим `MoneyCell`: всегда два знака после запятой и неразрывный пробел перед `₽`. История открывается в штатном MUI-диалоге, поддерживает стандартный `onClose` и закрывается крестиком `IconAction` с подсказкой; отдельной слабой кнопки «Закрыть» больше нет. Playwright-сценарии используют дробные ставки `45.5` и `50.25`, проверяют точные строки `45,50 ₽` и `50,25 ₽`, обе версии в диалоге и неизменность действующего тарифа после закрытия.

## Гейты

- **Красный, существующий долг ветки** — точная команда `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend && npx tsc --noEmit -p tsconfig.app.json` выполнена после финальной правки, код возврата 2. Ошибки остаются в `FfBillingScreen.tsx`, старых MUI-пропсах и неиспользуемом импорте тарифной части `FfSettingsScreen.tsx`, `SellersScreen.tsx` и `PeriodPicker.tsx`; тот же набор был зафиксирован в `DEV-01.md`. Ошибок на добавленных `MoneyCell`, `Dialog`, `DialogContent`, `DialogTitle` и строках истории после исправления нет.
- **Красный, существующий храповик ветки** — точная команда `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing && python3 scripts/ui/ui_guard.py`, код возврата 1. Повторены четыре уже известные записи: `WbProductPickerDialog.tsx` `0 → 646`, `FfSettingsScreen.tsx` `701 → 795`, `FfFbsSupplyWorkspace.tsx` `2493 → 2498`, `SellerInboundDraftScreen.tsx` `1111 → 1169`. Базовая линия не обновлялась. `git show HEAD:frontend/src/screens/ff/FfSettingsScreen.tsx | wc -l` и `wc -l < frontend/src/screens/ff/FfSettingsScreen.tsx` оба дали 794: атом 2 не увеличил экран-монолит.
- **Зелёный** — точная команда `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend && task_temp_dir=$(mktemp -d /private/tmp/wms-billing-unit.XXXXXX) && TMPDIR="$task_temp_dir" npm run test:unit -- src/screens/ff/FfSettingsScreen.test.ts --pool=threads --maxWorkers=1 --minWorkers=1`: 1 файл, 1 тест пройдены.
- **Зелёный** — точная относящаяся к денежному формату регрессия `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend && task_temp_dir=$(mktemp -d /private/tmp/wms-billing-unit.XXXXXX) && TMPDIR="$task_temp_dir" npm run test:unit -- src/screens/ff/FfSettingsScreen.test.ts src/ui-kit/Cells.test.ts --pool=threads --maxWorkers=1 --minWorkers=1`: 2 файла, 2 теста пройдены.
- **Красный по среде** — точная команда `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend && task_temp_dir=$(mktemp -d /private/tmp/wms-billing-e2e.XXXXXX) && TMPDIR="$task_temp_dir" npx playwright test tests-e2e/billing-tariffs.spec.ts --grep "admin creates (an active FF tariff|a later tariff version)"`, код возврата 1. Локальный webServer не смог привязать `127.0.0.1:18000`: `operation not permitted`; тесты не стартовали. Конфигурация не менялась и обход проверки не добавлялся.
- **Зелёный** — точная команда `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend && npx playwright test tests-e2e/billing-tariffs.spec.ts --grep "admin creates (an active FF tariff|a later tariff version)" --list`: обнаружены ровно 2 кейса атома в 1 файле.
- **Зелёный** — точная команда `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing && git diff --check`, замечаний нет.

Первый unit-запуск точной командой `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend && npm run test:unit -- src/screens/ff/FfSettingsScreen.test.ts` остановился до выполнения теста с `ENOSPC` в системном temp-каталоге. Повтор с отдельным каталогом в `/private/tmp` дал зелёный результат, приведённый выше. Полный backend `pytest`, `ruff check .` и `mypy .` не запускались по запрету атомарной проверки.

## Не реализовано

Пунктов контракта атома 2, которые не удалось реализовать буквально в коде, нет. Не выполнен только живой Playwright-прогон из-за запрета среды на локальный порт; это не подменено правкой конфигурации. Находки `DESIGN-REVIEW.md` в `FfBillingScreen.tsx` относятся к атомам 3–6 и намеренно не затрагивались.

## Находки

Новых находок по данным, утечкам или персональным данным в границах атома нет. Секреты, ключи, токены, `.env`, кабинеты учётных данных и боевой прод `194.87.96.144` не читались и не затрагивались.

## Блокеры

Изменения локально реализованы и артефакт записан, но среда не позволила сохранить их в Git. Точная команда `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing && git add -- frontend/src/screens/ff/FfSettingsScreen.tsx frontend/tests-e2e/billing-tariffs.spec.ts night/volna-9-recovery/cards/09-billing/DEV.md && git diff --cached --name-status && git diff --cached --check && git commit -m "fix(settings): show tariff history in dialog"` завершилась кодом 128: Git не смог создать `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-3-09-billing1/index.lock` (`Operation not permitted`). Проверенного commit SHA нет; `night/volna-9-recovery/JOURNAL.md` остаётся отдельным чужим изменением и в команду индексации не включался.

# Фича 3

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

# Фича 4

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

# Фича 5

# 09-billing · screen-dev · атом 5

Роль: `screen-dev`. Реализован только атом «Сократить подпись повторного формирования счёта» из `FEATURES.md` и относящаяся к нему находка R-32 из `DESIGN-REVIEW.md`.

Когда администратор выбирает селлера без действующих причин блокировки, пояснение «Причины устранены — повторите формирование» остаётся отдельным текстом панели, а `PrimaryAction` теперь имеет короткую подпись «Повторить формирование». Алгоритм запроса и отображение результата формирования не менялись.

В `billing-invoices.spec.ts` добавлен пользовательский сценарий `S-31-TC-006`: администратор выбирает селлера, видит отдельное пояснение и короткую подпись кнопки, запускает повторное формирование и после прежнего POST видит выставленный счёт в таблице. Тест отдельно подтверждает, что длинная фраза больше не является доступным именем кнопки и что запрос формирования отправлен один раз.

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend/src/screens/ff/FfBillingScreen.tsx`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend/tests-e2e/billing-invoices.spec.ts`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/night/volna-9-recovery/cards/09-billing/DEV.md`

## Гейты

- **Красный, существующий долг ветки** — точная команда `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend && npx tsc --noEmit -p tsconfig.app.json` выполнена дважды, в том числе после финальной правки; код возврата 2. Финальный запуск повторил прежние ошибки типизации условного `DataTable`, старого `alignItems` в строках проблем, MUI-пропсов и `testId` у `DangerAction` в `FfBillingScreen.tsx`, а также прежние ошибки в `FfSettingsScreen.tsx`, `SellersScreen.tsx` и `PeriodPicker.tsx`. Добавленный в первой итерации `alignItems` у новой панели дал отдельную ошибку и был удалён до финального запуска; в финальном выводе этой новой ошибки больше нет.
- **Красный, существующий храповик ветки** — точная команда `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing && python3 scripts/ui/ui_guard.py` выполнена дважды, в том числе после финальной правки; код возврата 1. Повторены четыре ранее зафиксированные записи: `WbProductPickerDialog.tsx` `0 → 646`, `FfSettingsScreen.tsx` `701 → 795`, `FfFbsSupplyWorkspace.tsx` `2493 → 2498`, `SellerInboundDraftScreen.tsx` `1111 → 1169`; `App.tsx` отмечен как улучшившийся `3492 → 3491`. `FfBillingScreen.tsx` не появился в списке новых отступлений, базовая линия не обновлялась.
- **Зелёный** — точная команда `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend && task_temp_dir=$(mktemp -d /private/tmp/wms-billing-unit.XXXXXX) && TMPDIR="$task_temp_dir" npm run test:unit -- src/screens/ff/FfBillingScreen.test.ts --pool=threads --maxWorkers=1 --minWorkers=1` выполнена дважды, в том числе после финальной правки: 1 файл, 4 теста пройдены.
- **Красный по среде** — точная атомарная команда `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend && task_temp_dir=$(mktemp -d /private/tmp/wms-billing-e2e.XXXXXX) && TMPDIR="$task_temp_dir" npx playwright test tests-e2e/billing-invoices.spec.ts --grep "billing invoice retry uses a short action label and keeps the visible formation result"`, код возврата 1. Playwright создал тестовую схему, но локальный API не смог привязать `127.0.0.1:18000`: `operation not permitted`; браузерный кейс не стартовал. Конфигурация и порты ради обхода не менялись.
- **Зелёный** — точная команда `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend && task_temp_dir=$(mktemp -d /private/tmp/wms-billing-e2e.XXXXXX) && TMPDIR="$task_temp_dir" npx playwright test tests-e2e/billing-invoices.spec.ts --grep "billing invoice retry uses a short action label and keeps the visible formation result" --list` выполнена дважды, в том числе после финальной правки: найден ровно 1 кейс атома в 1 файле.
- **Зелёный** — точная команда `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing && git diff --check`: замечаний нет.
- **Красный по правам среды** — точная команда `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing && git add -- frontend/src/screens/ff/FfBillingScreen.tsx frontend/tests-e2e/billing-invoices.spec.ts night/volna-9-recovery/cards/09-billing/DEV.md && git diff --cached --name-status && git diff --cached --check && git commit -m "fix(billing): shorten invoice retry action"`, код возврата 128. Git не смог создать `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-3-09-billing1/index.lock`: `Operation not permitted`. Ничего не попало в индекс; проверенного commit SHA нет. Чужое изменение `night/volna-9-recovery/JOURNAL.md` в команду не включалось.

Полный backend `pytest`, `pytest -q`, `ruff check .` и `mypy .` не запускались в соответствии с запретом атомарной проверки. Полный frontend E2E-регресс также не запускался.

## Не реализовано

Пунктов контракта атома 5, которые не легли буквально в код, нет. Живой Playwright-прогон не выполнен только из-за запрета среды на локальный порт; он не подменён правкой тестовой конфигурации.

Изменения локально реализованы и артефакт записан, но среда не позволила сохранить их в Git. До внешнего коммита результат остаётся уязвимым как незакоммиченный diff.

Находка R-30 про безопасное отображение неизвестных кодов относится к следующему атому 6 и намеренно не затрагивалась. Находки в `FfSettingsScreen.tsx` и сетках таблиц относятся к предшествующим атомам и также не входят в границы атома 5.

## Находки

`FfBillingScreen.tsx` и маршрут `/app/ff/billing` отсутствуют в `frontend/screens.registry.json`; существующий идентификатор `S-31` в реестре принадлежит другому экрану, хотя биллинговые тесты размечены `S-31-TC-*`. Реестр не входит в разрешённые файлы атома, поэтому не изменялся.

Секреты, ключи, токены, `.env`, кабинеты учётных данных, живой кабинет Wildberries и боевой прод `194.87.96.144` не открывались и не затрагивались. Новых находок по данным, утечкам или персональным данным в границах атома нет.

# Фича 6

# 09-billing · screen-dev · атом 6

Роль: `screen-dev`. Реализован только атом «Не выводить неизвестные коды биллинга в интерфейс» из `FEATURES.md` и относящаяся к нему находка R-30 из `DESIGN-REVIEW.md`.

Неизвестные `service_code` и `unit` теперь отображаются безопасным знаком «—» в строках начислений, режиме «По исполнителям», строках открытого счёта и печатном представлении того же счёта. Над журналом начислений и внутри диалога счёта появляется отдельный `ErrorNotice` с понятным оператору описанием ошибки; исходные технические значения в сообщения не подставляются.

E2E-заглушки возвращают неизвестные услугу и единицу отдельно для начисления и строки счёта. Сценарии проверяют обычный режим начислений, режим «По исполнителям», открытый счёт и печатный вид: в каждом месте видны «—», а исходные строки API отсутствуют в интерфейсе.

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend/src/screens/ff/FfBillingScreen.tsx`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend/tests-e2e/billing-ledger.spec.ts`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend/tests-e2e/billing-invoices.spec.ts`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/night/volna-9-recovery/cards/09-billing/DEV.md`

## Гейты

- **Красный, существующий долг ветки** — точная команда `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend && npx tsc --noEmit -p tsconfig.app.json`, код возврата 2. В `FfBillingScreen.tsx` воспроизведены прежние ошибки типизации условного `DataTable`, старых MUI-пропсов и `testId` у `DangerAction`; также воспроизведены ранее зафиксированные ошибки в `FfSettingsScreen.tsx`, `SellersScreen.tsx` и `PeriodPicker.tsx`. На добавленных безопасных подстановках, вычислении признака неизвестных кодов и `ErrorNotice` отдельных новых ошибок TypeScript нет.
- **Красный, существующий храповик ветки** — точная команда `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing && python3 scripts/ui/ui_guard.py`, код возврата 1. Повторены четыре ранее зафиксированные записи: `WbProductPickerDialog.tsx` `0 → 646`, `FfSettingsScreen.tsx` `701 → 795`, `FfFbsSupplyWorkspace.tsx` `2493 → 2498`, `SellerInboundDraftScreen.tsx` `1111 → 1169`; `App.tsx` отмечен как улучшившийся `3492 → 3491`. `FfBillingScreen.tsx` не появился в списке новых отступлений, базовая линия не обновлялась.
- **Зелёный** — точная команда `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend && task_temp_dir=$(mktemp -d /private/tmp/wms-billing-unit.XXXXXX) && TMPDIR="$task_temp_dir" npm run test:unit -- src/screens/ff/FfBillingScreen.test.ts --pool=threads --maxWorkers=1 --minWorkers=1`: 1 файл, 4 теста пройдены.
- **Зелёный** — точная команда обнаружения атомарных E2E и связанных регрессий `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend && task_temp_dir=$(mktemp -d /private/tmp/wms-billing-e2e.XXXXXX) && TMPDIR="$task_temp_dir" npx playwright test tests-e2e/billing-ledger.spec.ts tests-e2e/billing-invoices.spec.ts --grep "billing (ledger (hides unknown service and unit codes in both modes|uses the canonical storage service code)|invoice (hides unknown service and unit codes|opens, reveals documents and starts print))" --list`: найдены ровно 4 кейса в 2 файлах — два сценария атома и две связанные регрессии канонического кода хранения и печати счёта.
- **Красный по среде** — та же атомарная Playwright-команда без `--list`, код возврата 1. Локальный API дошёл до запуска приложения, но не смог привязать `127.0.0.1:18000`: `operation not permitted`; браузерные шаги не стартовали. Конфигурация, порты и тестовые данные ради обхода не менялись.
- **Зелёный** — точная команда `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing && git diff --check`: замечаний нет.
- **Красный по правам среды** — точная команда `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing && git add -- frontend/src/screens/ff/FfBillingScreen.tsx frontend/tests-e2e/billing-ledger.spec.ts frontend/tests-e2e/billing-invoices.spec.ts night/volna-9-recovery/cards/09-billing/DEV.md && git diff --cached --name-status && git diff --cached --check && git commit -m "fix(billing): hide unknown billing codes"`, код возврата 128. Git не смог создать `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-3-09-billing1/index.lock`: `Operation not permitted`. Ничего не попало в индекс; проверенного commit SHA нет. Чужое изменение `night/volna-9-recovery/JOURNAL.md` в команду не включалось.

Полный backend `pytest`, `pytest -q`, `ruff check .` и `mypy .` не запускались в соответствии с запретом атомарной проверки. Полный frontend E2E-регресс также не запускался.

## Не реализовано

Пунктов контракта атома 6, которые не легли буквально в код, нет. Не выполнен только живой Playwright-прогон двух новых сценариев и двух связанных регрессий из-за запрета среды на локальный порт; это не подменено правкой конфигурации.

Обязательные общие `tsc` и `ui_guard.py` остаются красными на существующих отклонениях ветки, перечисленных выше. Исправление соседних ошибок и монолитов не входит в разрешённые файлы и границы атома 6.

Изменения локально реализованы и артефакт записан, но среда не позволила сохранить их в Git. До внешнего коммита результат остаётся уязвимым как незакоммиченный diff.

## Находки

`FfBillingScreen.tsx` и маршрут `/app/ff/billing` отсутствуют в `frontend/screens.registry.json`; существующий идентификатор `S-31` в реестре принадлежит другому экрану, хотя биллинговые тесты уже размечены `S-31-TC-*`. Реестр не входит в разрешённые файлы атома, поэтому не изменялся.

Секреты, ключи, токены, `.env`, кабинеты учётных данных, живой кабинет Wildberries и боевой прод `194.87.96.144` не читались и не затрагивались. Новых находок по данным, утечкам или персональным данным в границах атома нет.
