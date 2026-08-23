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
