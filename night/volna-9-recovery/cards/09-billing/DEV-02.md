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
