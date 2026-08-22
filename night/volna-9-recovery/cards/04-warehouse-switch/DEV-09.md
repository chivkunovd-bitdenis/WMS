# DEV · 04-warehouse-switch · переделка атома 9

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend/src/screens/v2/FbsSupplyCreateDialog.tsx`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend/src/screens/v2/FbsSupplyCreateDialog.test.ts`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend/tests-e2e/ff-fbs-supply.spec.ts`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/night/volna-9-recovery/cards/04-warehouse-switch/DEV.md`

Диалог больше не приписывает весь межскладской дефицит одному складу. Количество рядом с известным складом ограничено фактическим `source_warehouse.available`, а оставшаяся часть честно показана как количество из других складов. Агрегированное предупреждение суммирует одинаковые источники. Кнопка создания при локальной нехватке остаётся доступной после актуального preflight; во время повторной проверки она заблокирована с причиной, старое объяснение остаётся видимым, а запоздавший ответ отменённого запроса не заменяет актуальное состояние.

## Гейты

- `npx tsc --noEmit -p tsconfig.app.json` из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend` — **красный вне файлов атома**. Единственная оставшаяся причина: `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend/src/ui-kit/WarehouseContextSwitch.test.tsx` импортирует отсутствующий в `package.json` пакет `@testing-library/react` и его DOM-matchers. Ошибок TypeScript в файлах атома 9 нет.
- `python3 scripts/ui/ui_guard.py` из корня — **красный вне файлов атома**: новые нарушения остаются в `WbProductPickerDialog.tsx`, `FfFbsOrdersScreen.tsx`, `FfFbsStockSyncScreen.tsx`, `FfFbsSupplyWorkspace.tsx` и `SellerInboundDraftScreen.tsx`. Изменённый `FbsSupplyCreateDialog.tsx` отмечен guard-ом как улучшение (`своя-кнопка 3 → 2`); базовая линия не менялась.
- `npm run test:unit -- src/screens/v2/FbsSupplyCreateDialog.test.ts` из frontend — **зелёный**, 3/3 теста.
- `npx playwright test tests-e2e/ff-fbs-supply.spec.ts --grep "create supply from selected orders" --list` — **зелёный**, найден один целевой сценарий.
- Живой запуск того же Playwright-сценария — **красный по ограничению среды**: webServer не получил разрешение открыть `127.0.0.1:18000` (`Errno 1 operation not permitted`).
- `git diff --check` — **зелёный**.
- Отдельный commit — **красный по ограничению среды**: Git не смог создать `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-1-04-warehouse-switch/index.lock` (`Operation not permitted`). Изменения атома не проиндексированы, commit SHA отсутствует; чужой `JOURNAL.md` не захватывался.

## Не реализовано

- Backend preflight по-прежнему возвращает для товарной строки только один известный `source_warehouse`, хотя общий остаток может быть собран с нескольких складов. Фронтенд больше не показывает ложное количество для этого склада и явно обозначает остаток как `другие склады`, но назвать каждый дополнительный склад буквально невозможно без расширения backend-контракта вне разрешённого экранного слоя этого атома.
- Живой E2E-прогон не завершён из-за системного запрета bind порта, описанного в гейтах; тест собран и обнаруживается Playwright.
- Результат локально реализован, но не сохранён в Git: песочница запрещает запись в служебный каталог worktree, поэтому восстановимого commit SHA нет.

## Находки

- Исправлена относящаяся к атому 9 находка №1 из `REVIEW.md`: UI теперь использует фактическое доступное количество источника и не даёт невыполнимое указание забрать весь дефицит с одного склада.
- Секреты, ключи, токены, `.env` и кабинеты учётных данных не читались и не изменялись.
