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
