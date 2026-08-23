# 09-billing · screen-dev · атом 1

Роль: `screen-dev`. Проверен и восстановлен артефакт только для атома «Сделать переключатель разделов настроек настоящими вкладками» из `FEATURES.md`.

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/night/volna-9-recovery/cards/09-billing/DEV.md`

Реализация атома уже присутствовала в зафиксированном состоянии ветки (`5c02a506`):

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend/src/screens/ff/FfSettingsScreen.tsx`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend/src/screens/ff/FfSettingsScreen.test.ts`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend/tests-e2e/billing-tariffs.spec.ts`

Экран использует семантические MUI-вкладки `Tabs`/`Tab`: первоначально выбраны «Склад и сотрудники», для администратора доступна «Тарифы ФФ», а `aria-selected` однозначно отражает активный раздел. Содержимое складского блока, сотрудников и тарифов не менялось.

## Гейты

- **Красный** — `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend && npx tsc --noEmit -p tsconfig.app.json` (код 2). Ошибки уже есть в `FfBillingScreen.tsx`, прежней тарифной форме `FfSettingsScreen.tsx`, `SellersScreen.tsx` и `PeriodPicker.tsx`; проверяемые `Tabs`/`Tab` ошибок не дают.
- **Красный** — `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing && python3 scripts/ui/ui_guard.py` (код 1). Храповик сообщает уже существующие экран-монолиты: `WbProductPickerDialog.tsx` `0 → 646`, `FfSettingsScreen.tsx` `701 → 795`, `FfFbsSupplyWorkspace.tsx` `2493 → 2498`, `SellerInboundDraftScreen.tsx` `1111 → 1169`. Базовая линия не изменялась.
- **Зелёный** — `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend && npm run test:unit -- src/screens/ff/FfSettingsScreen.test.ts`: 1 тест пройден.
- **Красный по среде** — `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend && npx playwright test tests-e2e/billing-tariffs.spec.ts --grep "admin switches between settings tabs"`: Playwright не начал сценарий, поскольку его webServer не смог привязать `127.0.0.1:18000` (`operation not permitted`). Конфигурация и сценарий не менялись для обхода ограничения.
- **Красный по среде** — `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing && git add -- night/volna-9-recovery/cards/09-billing/DEV.md && git diff --cached --check && git diff --cached --name-status && git commit -m "docs(night): record billing atom 1 verification"`: Git не смог создать `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-3-09-billing1/index.lock` (`Operation not permitted`), поэтому commit для обновлённого артефакта не создан.

## Не реализовано

Нет: требование атома уже реализовано буквально в существующем коммите. Находка R-31 о кнопке закрытия истории ставок относится к следующему атому, а остальные находки — к `FfBillingScreen.tsx`; они намеренно не затрагивались.

## Находки

Секреты, ключи, токены, `.env`, кабинеты учётных данных и боевой прод не читались и не затрагивались. Новых находок по данным, утечкам или персональным данным в пределах атома нет.

## Блокеры

Живой e2e-прогон недоступен из-за запрета среды на локальный порт. Обязательные `tsc` и `ui_guard.py` остаются красными на перечисленных существующих нарушениях вне исправляемой вкладочной навигации. Обновлённый артефакт существует локально, но не сохранён отдельным Git-коммитом из-за запрета записи в служебный каталог worktree.
