# Фича 1

# 09-billing — screen-dev, атом 1

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend/src/screens/ff/FfSettingsScreen.tsx` — переключатель «Склад и сотрудники» / «Тарифы ФФ» реализован семантическими вкладками `Tabs`/`Tab`; текущий раздел получает `aria-selected="true"`.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend/tests-e2e/billing-tariffs.spec.ts` — добавлен пользовательский сценарий переключения вкладок и проверки обоих сохранённых блоков.

Код этого атома уже находится в истории рабочей ветки: `5c02a5065a509300f1ebe3a78edfd20a645b0cd6` (`night(09-billing): atom 1/6`). Повторная проверка после дизайн-ревью подтвердила исправление R-31: вкладки больше не являются парой второстепенных контурных действий.

## Гейты

- Зелёный: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend && npm run test:unit -- FfSettingsScreen.test.ts` — 1 test passed.
- Красный: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend && npx tsc --noEmit -p tsconfig.app.json` — ошибки уже есть в `FfBillingScreen.tsx`, `SellersScreen.tsx`, `PeriodPicker.tsx` и существующих частях `FfSettingsScreen.tsx`; это не изменения переключателя вкладок.
- Красный: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing && python3 scripts/ui/ui_guard.py` — храповик сообщает существующие отклонения: `FfSettingsScreen.tsx: экран-монолит 701 → 795`, а также три экрана вне атома. Базовую линию флагом `--update` не менял.
- Не запущен до браузерного сценария: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend && npx playwright test tests-e2e/billing-tariffs.spec.ts -g 'admin switches between settings tabs without losing their existing content'` — webServer не смог стартовать: sandbox запретил bind `127.0.0.1:18000` (`operation not permitted`). Сам тестовый файл и только кейс атома выбраны корректно; полный e2e не запускался.
- Не сохранено в новом коммите: `git commit -m 'night(09-billing): record screen-dev atom 1 verification'` не смог создать `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-3-09-billing1/index.lock` (`Operation not permitted`). Артефакт записан в рабочей копии, но недоступен как новый commit SHA; реализация атома остаётся восстановимой из ранее существующего `5c02a5065a509300f1ebe3a78edfd20a645b0cd6`.

## Не реализовано

- Ничего в пределах атома 1. По вердикту исправлены относящиеся к этому слою R-31 для вкладок, R-31 для закрытия истории ставок (штатный диалог с `IconAction`) и R-08 для денег (`MoneyCell`); последние два пункта уже зафиксированы в текущем состоянии ветки коммитом `b342da77` (атом 2) и не изменялись в этом атоме.
- Зелёный общий `tsc`, `ui_guard` и Playwright недостижимы в данной рабочей копии без выхода за границы атома: точные причины и команды приведены в разделе «Гейты».

## Находки

- Секреты, ключи, токены, `.env` и кабинеты учётных данных не открывались.

# Фича 2

# 09-billing — screen-dev, атом 2

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend/src/screens/ff/FfSettingsScreen.tsx` — действующая ставка и версии в истории выводятся общим `MoneyCell`; история открывается в штатном диалоге и закрывается иконкой закрытия с подсказкой.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend/tests-e2e/billing-tariffs.spec.ts` — сценарии проверяют дробную ставку в формате `45,50 ₽`, версии в диалоге и штатное закрытие без изменения списка.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/night/volna-9-recovery/cards/09-billing/DEV.md` — отчёт реализации и проверок этого атома.

Реализация двух экранных файлов уже сохранена в истории текущей ветки коммитом `b342da77` (`night(09-billing): atom 2/6`). В этой итерации повторно проверены все относящиеся к атому находки R-08 и R-31 из `DESIGN-REVIEW.md`.

## Гейты

- Зелёный: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend && npm run test:unit -- src/screens/ff/FfSettingsScreen.test.ts` — 1 test passed.
- Красный: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend && npx tsc --noEmit -p tsconfig.app.json` — ошибки находятся в уже затронутом соседними атомами `/frontend/src/screens/ff/FfBillingScreen.tsx`, а также в существующих частях `FfSettingsScreen.tsx`, `SellersScreen.tsx` и `PeriodPicker.tsx`; новая денежная ячейка и диалог истории ошибок TypeScript не добавили.
- Красный: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing && python3 scripts/ui/ui_guard.py` — новые записи храповика: экран-монолит `FfSettingsScreen.tsx: 701 → 795` и три экрана вне атома. Базовая линия флагом `--update` не менялась.
- Не запущен: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend && npx playwright test tests-e2e/billing-tariffs.spec.ts` — Playwright выбрал только сценарии этого атома и регрессию зависимости, но webServer не смог привязаться к `127.0.0.1:18000`: `operation not permitted`.

## Не реализовано

- Ничего в пределах атома 2: R-08 исправлен общим `MoneyCell`, R-31 — штатным диалогом и иконкой закрытия. Исправление экранного монолита `FfSettingsScreen.tsx` выходит за границы одного атома и не выполнялось.

## Находки

- Секреты, ключи, токены, `.env` и кабинеты учётных данных не открывались.

# Фича 3

# 09-billing — screen-dev, атом 3

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend/src/screens/ff/FfBillingScreen.tsx` — в текущем состоянии ветки режим «По исполнителям» уже использует фиксированную сетку `220 / 150 / 150 / 120 / 120 px`; длинное имя ограничено общим `TextCell`, а «Количество» и «Документов» выровнены вправо. Повторная проверка этого атома не потребовала новой правки исходника.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend/tests-e2e/billing-ledger.spec.ts` — в текущем состоянии ветки уже есть `S-31-TC-005`: сценарий с длинным именем проверяет пять заголовков и ширины, многоточие, правое выравнивание чисел и отсутствие денежных колонок. Повторная проверка не потребовала новой правки теста.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/night/volna-9-recovery/cards/09-billing/DEV.md` — восстановлен обязательный отчёт этого атома.

## Гейты

- Зелёный: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend && task_tmp_dir=$(mktemp -d /private/tmp/wms-billing-unit.XXXXXX) && TMPDIR="$task_tmp_dir" npm run test:unit -- src/screens/ff/FfBillingScreen.test.ts --pool=threads --maxWorkers=1 --minWorkers=1` — 1 файл, 4 теста пройдены.
- Красный, существующие ошибки ветки: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend && npx tsc --noEmit -p tsconfig.app.json` — код возврата 2. В `FfBillingScreen.tsx` остаётся несовместимость условного `DataTable` для `LedgerEntry`/`PerformerRow` и прежние MUI-пропсы; также ошибки уже есть в `FfSettingsScreen.tsx`, `SellersScreen.tsx` и `PeriodPicker.tsx`. Фикс сетки пяти колонок новых ошибок не добавил; исправление чужих частей не входит в этот атом.
- Красный, существующий храповик: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing && python3 scripts/ui/ui_guard.py` — код возврата 1. Зафиксированы только прежние экран-монолиты `WbProductPickerDialog.tsx` (`0 → 646`), `FfSettingsScreen.tsx` (`701 → 795`), `FfFbsSupplyWorkspace.tsx` (`2493 → 2498`) и `SellerInboundDraftScreen.tsx` (`1111 → 1169`); `FfBillingScreen.tsx` в выводе отсутствует. Базовая линия флагом `--update` не менялась.
- Зелёный выбор атомарного E2E: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend && task_tmp_dir=$(mktemp -d /private/tmp/wms-billing-e2e.XXXXXX) && TMPDIR="$task_tmp_dir" npx playwright test tests-e2e/billing-ledger.spec.ts --grep "billing ledger performer mode keeps fixed columns and hides money" --list` — найден ровно 1 кейс в 1 файле.
- Красный по ограничениям среды: та же команда без `--list` — Playwright не дошёл до браузерного сценария, поскольку API не смог привязаться к `127.0.0.1:18000` (`operation not permitted`). Конфигурация, порты и тестовые данные не менялись ради обхода.

Полный backend `pytest`, `ruff check .` и `mypy .` не запускались: они запрещены для атомарной проверки. Полный E2E-регресс также не запускался.

## Не реализовано

Пунктов контракта и находок `DESIGN-REVIEW.md`, относящихся к атому 3, не осталось: R-09 в таблице «По исполнителям» уже реализован буквально. Живой Playwright-прогон не выполнен только из-за запрета среды на локальный порт.

## Находки

- `FfBillingScreen.tsx` и маршрут `/app/ff/billing` отсутствуют в `frontend/screens.registry.json`; существующий `S-31` принадлежит другому экрану. Реестр не входит в разрешённые файлы атома и не изменялся.
- Секреты, ключи, токены, `.env`, кабинеты учётных данных, боевой прод `194.87.96.144` и живой кабинет Wildberries не открывались и не затрагивались.

# Фича 4

# 09-billing — screen-dev, атом 4

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend/src/screens/ff/FfBillingScreen.tsx` — закреплена сетка шести колонок детализации счёта: ширины 180/170/120/130/140/70, правое выравнивание «Количество», «Ставка» и «Сумма», центральное выравнивание узкой колонки «Детализация».
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend/tests-e2e/billing-invoices.spec.ts` — сценарий S-31-TC-007 проверяет ширины, выравнивание и доступность раскрытия документов/печати.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/night/volna-9-recovery/cards/09-billing/DEV.md` — этот отчёт.

Указанная реализация уже сохранена в истории текущей рабочей ветки коммитом `c83236776468fc9beb7bac70e0e152640baea781` (`night(09-billing): atom 4/6`); в этой проверке дублирующих изменений исходного кода не вносилось.

## Гейты

- КОМАНДА: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend && npx tsc --noEmit -p tsconfig.app.json`
  РЕЗУЛЬТАТ: КРАСНЫЙ. В `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend/src/screens/ff/FfBillingScreen.tsx` есть предшествующие атомы проблемы типизации условного `DataTable` для `LedgerEntry`/`PerformerRow` и несовместимые MUI-пропсы. Вне границ атома ошибки также есть в `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend/src/screens/ff/FfSettingsScreen.tsx`, `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend/src/screens/v2/SellersScreen.tsx` и `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend/src/ui-kit/PeriodPicker.tsx`. Атом 4 не разрешает исправлять их заодно.
- КОМАНДА: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing && python3 scripts/ui/ui_guard.py`
  РЕЗУЛЬТАТ: КРАСНЫЙ. Новые отступления: `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend/src/components/WbProductPickerDialog.tsx`, `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend/src/screens/ff/FfSettingsScreen.tsx`, `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend/src/screens/v2/FfFbsSupplyWorkspace.tsx`, `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend/src/screens/v2/SellerInboundDraftScreen.tsx`. Базовая линия не менялась.
- КОМАНДА: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend && npm run test:unit -- src/screens/ff/FfBillingScreen.test.ts`
  РЕЗУЛЬТАТ: ЗЕЛЁНЫЙ — 1 файл, 4 теста.
- КОМАНДА: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend && npx playwright test tests-e2e/billing-invoices.spec.ts --grep 'billing invoice retry uses a short action label and keeps the visible formation result|billing invoice opens, reveals documents and starts print|billing invoice hides unknown service and unit codes'`
  РЕЗУЛЬТАТ: КРАСНЫЙ ДО ВЫПОЛНЕНИЯ КЕЙСОВ. Playwright webServer не смог привязать `127.0.0.1:18000`: `operation not permitted`.

## Не реализовано

- По контракту атома 4 не осталось нереализованных пунктов: фиксированная сетка, правое выравнивание числовых колонок и центральная узкая колонка действия присутствуют.
- Зелёные общий `tsc` и `ui_guard.py` не получены из-за перечисленных выше существующих проблем ветки; базовую линию guard не обновлял.
- Адресные Playwright-кейсы не получили результат из-за ограничения среды на локальный порт, а не из-за результата проверок сценария.

## Находки

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend/screens.registry.json` не содержит маршрута `/app/ff/billing` или `FfBillingScreen`; реестр не входит в разрешённые файлы атома и не изменялся.
- Секреты, ключи, токены, `.env` и кабинеты учётных данных не читались.

# Фича 5

# 09-billing — screen-dev, атом 5

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend/src/screens/ff/FfBillingScreen.tsx` — действие повторного формирования имеет короткую подпись `Повторить формирование`, а объяснение `Причины устранены — повторите формирование` остаётся отдельным текстом рядом с ним.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend/tests-e2e/billing-invoices.spec.ts` — сценарий `S-31-TC-006` проверяет короткую подпись, один POST формирования и появление сформированного счёта.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/night/volna-9-recovery/cards/09-billing/DEV.md` — этот отчёт.

Изменения исходного кода и e2e уже сохранены в текущей ветке коммитом `5cab2f019f1ba10bd28e2ddafcd1c40f4c20ccdf` (`night(09-billing): atom 5/6`); при этой переделке дополнительный код не требовался.

## Гейты

- КОМАНДА: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend && npx tsc --noEmit -p tsconfig.app.json`
  РЕЗУЛЬТАТ: КРАСНЫЙ. В экране счетов есть существующие ошибки типизации условного `DataTable` для `LedgerEntry`/`PerformerRow` и несовместимые MUI-пропсы. Вне границ атома ошибки есть также в `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend/src/screens/ff/FfSettingsScreen.tsx`, `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend/src/screens/v2/SellersScreen.tsx` и `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend/src/ui-kit/PeriodPicker.tsx`. Атом 5 не разрешает исправлять их заодно.
- КОМАНДА: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing && python3 scripts/ui/ui_guard.py`
  РЕЗУЛЬТАТ: КРАСНЫЙ. Новые отступления: `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend/src/components/WbProductPickerDialog.tsx`, `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend/src/screens/ff/FfSettingsScreen.tsx`, `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend/src/screens/v2/FfFbsSupplyWorkspace.tsx`, `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend/src/screens/v2/SellerInboundDraftScreen.tsx`. Базовая линия не менялась.
- КОМАНДА: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend && npm run test:unit -- src/screens/ff/FfBillingScreen.test.ts`
  РЕЗУЛЬТАТ: ЗЕЛЁНЫЙ — 1 файл, 4 теста.
- КОМАНДА: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend && npm run test:e2e -- tests-e2e/billing-invoices.spec.ts --grep "billing invoice retry uses a short action label and keeps the visible formation result"`
  РЕЗУЛЬТАТ: КРАСНЫЙ ДО ВЫПОЛНЕНИЯ КЕЙСА. Playwright webServer не смог привязать `127.0.0.1:18000`: `operation not permitted`.

## Не реализовано

- Пункты атома реализованы буквально в уже сохранённом коммите `5cab2f019f1ba10bd28e2ddafcd1c40f4c20ccdf`: объяснение вынесено из подписи действия, сама кнопка называется `Повторить формирование`, а e2e подтверждает видимый сформированный счёт.
- Зелёные общий `tsc` и `ui_guard.py` не получены из-за перечисленных существующих проблем вне границ этого атома. Базовую линию guard не обновлял.
- Целевой Playwright-кейс не начал выполняться из-за запрета среды на локальный порт, а не из-за сценарной проверки.

## Находки

- Секреты, ключи, токены, `.env` и кабинеты учётных данных не читались.

# Фича 6

# 09-billing — screen-dev

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend/src/screens/ff/FfBillingScreen.tsx`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/night/volna-9-recovery/cards/09-billing/DEV.md`

Экран использует закрытые словари отображаемых услуг и единиц: неизвестные значения API показываются как «—». Для начислений (в обоих режимах) и строк открытого счёта выводится `ErrorNotice`; технические коды не передаются в видимый интерфейс или печатную форму. Дополнительно устранены ошибки типизации в том же экране, не меняющие видимое поведение: отдельная типизация таблиц режимов и корректные MUI-свойства.

## Гейты

- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend && npx tsc --noEmit -p tsconfig.app.json` — красный из-за файлов вне границ атома: `FfSettingsScreen.tsx`, `SellersScreen.tsx`, `ui-kit/PeriodPicker.tsx`. Ошибок в `FfBillingScreen.tsx` после исправления нет.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing && python3 scripts/ui/ui_guard.py` — красный из-за ранее существующих новых нарушений вне границ атома: `WbProductPickerDialog.tsx`, `FfSettingsScreen.tsx`, `FfFbsSupplyWorkspace.tsx`, `SellerInboundDraftScreen.tsx`. Базовая линия не менялась.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend && npm run test:unit -- src/screens/ff/FfBillingScreen.test.ts` — зелёный: 1 файл, 4 теста.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend && npm run test:e2e -- tests-e2e/billing-ledger.spec.ts --grep "hides unknown service and unit codes in both modes"` — не стартовал: sandbox запретил привязку web-server к `127.0.0.1:18000` (`operation not permitted`).
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend && npm run test:e2e -- tests-e2e/billing-invoices.spec.ts --grep "hides unknown service and unit codes"` — не стартовал по той же причине до выполнения сценария.

## Не реализовано

- Ничего в пределах атома 6 не оставлено. Точечные E2E-сценарии присутствуют в разрешённых файлах, но среда не разрешает поднять их локальный сервер.

## Находки

- Секреты, ключи, токены, `.env` и кабинеты учётных данных не открывались.
- Изменения не удалось сохранить отдельным Git-коммитом: Git не может создать `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-3-09-billing1/index.lock` из-за запрета среды (`operation not permitted`). Рабочее дерево содержит изменения экрана и этот артефакт; чужой `night/volna-9-recovery/JOURNAL.md` не добавлялся.
