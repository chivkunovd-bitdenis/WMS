## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/frontend/screens.registry.json`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/frontend/src/components/MarkingPrintDialog.tsx`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/frontend/src/utils/printMarkingCodeLabel.ts`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/frontend/tests-e2e/ff-marking-print-constructor.spec.ts`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/frontend/tests-e2e/ff-separate-marking-print.spec.ts`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/night/volna-9-recovery/cards/05-prod-slow/DEV.md`

Диалог сохраняет активную или готовую подготовку для тех же данных после закрытия и повторного открытия. Повтор в состояниях ошибки и истечения запускает только новую подготовку уже выбранных кодов, не повторяя операцию выдачи кодов. Состояния собраны из `StatusChip`, `ErrorNotice`, `ActionGroup`, `PrimaryAction` и `SecondaryAction`; PDF запрашивается только после явного действия «Открыть для печати». Реестр экранов фиксирует общий характер двух файлов для S-03/S-09/S-14/S-15 и закрывает находку ревью о границе владения.

## Гейты

- `npx tsc --noEmit -p tsconfig.app.json` из `frontend/` — зелёный.
- `npm run test:unit` из `frontend/` — зелёный: 20 файлов, 142 теста.
- `npx eslint src/components/MarkingPrintDialog.tsx src/utils/printMarkingCodeLabel.ts tests-e2e/ff-marking-print-constructor.spec.ts tests-e2e/ff-separate-marking-print.spec.ts` — зелёный.
- `npx playwright test --list --grep "S-03 marking tape" ...` — зелёный: обнаружены два теста, покрывающие `S-03-TC-008`, `S-03-TC-009`, `S-03-TC-014` и `S-03-TC-015`.
- `npm run test:e2e -- --grep "S-03 marking tape" ...` — красный до выполнения сценариев: Playwright webServer не смог открыть локальный `127.0.0.1:18000`, среда вернула `[Errno 1] operation not permitted`. Это ограничение запуска среды, а не падение тестового шага в браузере.
- `python3 scripts/ui/ui_guard.py` из корня — красный на ранее существующих отклонениях: `MarkingPrintDialog.tsx` (baseline 1687, сейчас 1750 строк; до этой правки в HEAD было 1752), `WbProductPickerDialog.tsx`, `FfFbsOrdersScreen.tsx`, `FfFbsSupplyWorkspace.tsx`, `SellerInboundDraftScreen.tsx`. Baseline не обновлялся; текущая правка размер `MarkingPrintDialog.tsx` не увеличила.
- `git diff --check` — зелёный.
- `git commit -m "fix(print): preserve background tape dialog state"` — красный: sandbox запретил создать `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-2-05-prod-slow/index.lock` (`Operation not permitted`). Изменения локально реализованы, но не сохранены новым commit SHA.

## Не реализовано

- Буквальных пропусков в разрешённом frontend-слое атома нет.
- Браузерное выполнение `S-03-TC-008`, `S-03-TC-009`, `S-03-TC-014`, `S-03-TC-015` не подтверждено в этой среде из-за запрета на bind локального порта; тесты добавлены и проходят обнаружение Playwright.
- Результат не удалось сохранить отдельным Git-коммитом из-за запрета sandbox на служебный `index.lock` зарегистрированного worktree; восстановление пока зависит от текущего рабочего дерева.
- Backend- и deployment-находки ревью, а также находки по `FfFbsOrdersScreen.tsx`, не менялись: они относятся к другим атомам и запрещены границами роли `screen-dev`.

## Находки

- Секреты, ключи, токены, `.env`, кабинеты учётных данных, боевой production и живой кабинет Wildberries не читались и не затрагивались.
