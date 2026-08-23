# 09-billing · screen-dev · атом 1

Роль: `screen-dev`. Проверен и сохранённый ранее в ветке атом «Сделать переключатель разделов настроек настоящими вкладками» из `FEATURES.md`. Его реализация находится в commit `5c02a5065a509300f1ebe3a78edfd20a645b0cd6` (`night(09-billing): atom 1/6`).

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend/src/screens/ff/FfSettingsScreen.tsx` — семантические MUI `Tabs`/`Tab` с текущим состоянием через `aria-selected`; вкладка «Тарифы ФФ» остаётся доступной только администратору.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend/tests-e2e/billing-tariffs.spec.ts` — пользовательский сценарий `S-19-TC-001`: переход в «Тарифы ФФ» и возврат к блоку склада и сотрудников.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/night/volna-9-recovery/cards/09-billing/DEV.md` — артефакт повторной проверки.

В этом повторном проходе исходники не менялись: реализация первого атома уже совпадает с контрактом и макетом. Находки R-31 о формате денег и истории ставок относятся к атому 2 и не менялись.

## Гейты

Выполненные команды:

- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend && npx tsc --noEmit -p tsconfig.app.json` — **красный**, код 2. Ошибки находятся вне первого атома: `FfBillingScreen.tsx`, уже существующая тарифная часть `FfSettingsScreen.tsx` (атом 2), `SellersScreen.tsx` и `PeriodPicker.tsx`. В `Tabs`/`Tab` ошибок нет.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing && python3 scripts/ui/ui_guard.py` — **красный**, код 1. Ратчет показывает уже существующие монолиты `WbProductPickerDialog.tsx`, `FfSettingsScreen.tsx`, `FfFbsSupplyWorkspace.tsx` и `SellerInboundDraftScreen.tsx`. Базовая линия не обновлялась.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend && npm run test:unit -- src/screens/ff/FfSettingsScreen.test.ts` — **зелёный**, 1 файл и 1 тест пройдены.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend && npx playwright test tests-e2e/billing-tariffs.spec.ts --grep "admin switches between settings tabs" --list` — **зелёный**, найден ровно 1 сценарий в 1 файле.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend && npx playwright test tests-e2e/billing-tariffs.spec.ts --grep "admin switches between settings tabs"` — **красный по среде**. Тест не начался: web-server не смог привязаться к `127.0.0.1:18000` (`operation not permitted`). Конфигурация теста не менялась.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing && git diff --check` — **зелёный**.

## Не реализовано

Нет пунктов контракта первого атома, которые нельзя было реализовать буквально. Полный живой Playwright-прогон не выполнен только из-за запрета локального порта в среде.

## Находки

Секреты, ключи, токены, `.env`, кабинеты учётных данных и боевой прод не читались и не затрагивались. Новых находок в границах атома нет.
