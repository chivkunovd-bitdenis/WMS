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
