# DEV · 05-prod-slow · атом 6 · rework пагинации S-03

Исправлена находка №3 из `REVIEW.md`, относящаяся к этому атому. Асинхронный
обход курсоров по действию «Выбрать все» теперь фиксирует поколение запроса и
ключ фильтра. Если оператор во время обхода меняет вкладку, селлера или WB-склад,
поздний ответ старого фильтра не добавляет строки, не меняет курсор и не переносит
выбор в новую выдачу. Та же проверка не позволяет показать ошибку от уже
неактуального обхода.

В Playwright добавлен сценарий `S-03-TC-003 / S-03-TC-010`: вторая страница
старого WB-склада задерживается, оператор переключается на другой склад, после
чего старый ответ освобождается и проверяется отсутствие старых строк и выбора.

`frontend/src/screens/v2/fbsApi.ts` проверен и не изменён: его контракт `limit` и
`cursor` для этого исправления достаточен.

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/frontend/src/screens/v2/FfFbsOrdersScreen.tsx`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/frontend/tests-e2e/ff-fbs-orders.spec.ts`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/night/volna-9-recovery/cards/05-prod-slow/DEV.md`

## Гейты

- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/frontend && npx tsc --noEmit -p tsconfig.app.json` — **зелёный**, ошибок TypeScript нет.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow && python3 scripts/ui/ui_guard.py` — **красный** на накопленном превышении baseline: `MarkingPrintDialog.tsx` 1687 → 1750, `WbProductPickerDialog.tsx` 0 → 646, `FfFbsOrdersScreen.tsx` 1587 → 1675, `FfFbsSupplyWorkspace.tsx` 2493 → 2498, `SellerInboundDraftScreen.tsx` 1111 → 1169. Baseline флагом `--update` не менялась; четыре соседних файла находятся вне границы атома, а несвязанный рефакторинг экрана запрещён контрактом.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/frontend && npm run test:unit` — **зелёный**, 20 файлов и 142 теста.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/frontend && npx playwright test tests-e2e/ff-fbs-orders.spec.ts --list` — **зелёный**, файл собран, обнаружено 15 сценариев, включая новый сценарий гонки.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/frontend && npx playwright test tests-e2e/ff-fbs-orders.spec.ts --grep 'list, tabs and empty state|cursor pagination preserves rows and selection|first page shows a table skeleton|empty new list explains automatic WB loading|failed continuation preserves rows and retries|changing warehouse does not merge a previous page|changing warehouse discards an in-flight old continuation|polling preserves the loaded tail and pauses while hidden|select all includes every cursor page|changing warehouse discards an in-flight select all'` — **красный до запуска сценариев**: Playwright webServer не смог открыть `127.0.0.1:18000`, `operation not permitted`.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow && git diff --check` — **зелёный**.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow && git add -- frontend/src/screens/v2/FfFbsOrdersScreen.tsx frontend/tests-e2e/ff-fbs-orders.spec.ts night/volna-9-recovery/cards/05-prod-slow/DEV.md && git diff --cached --check && git commit -m "fix(fbs): discard stale select-all pages"` — **красный до изменения индекса**: Git не смог создать `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-2-05-prod-slow/index.lock`, `Operation not permitted`; новый commit SHA не создан.

## Не реализовано

- Буквальный браузерный прогон `S-03-TC-001`–`S-03-TC-007` и
  `S-03-TC-010`–`S-03-TC-012` не состоялся: среда запретила локальному API
  занять тестовый порт до старта Playwright. Сценарии корректно компилируются и
  перечисляются командой `--list`.
- `ui_guard.py` нельзя сделать зелёным в границе этого атома без несвязанного
  сокращения существующего экрана, правки четырёх запрещённых соседних файлов
  или запрещённого обновления baseline.
- Находки №1–2 и №4–6 из `REVIEW.md` относятся к backend, слою фоновой печати и
  документации блокеров. В атоме пагинации S-03 эти файлы намеренно не менялись.
- Изменения локально реализованы в постоянной рабочей копии, но не сохранены
  отдельным Git-коммитом из-за запрета среды на запись в служебный индекс
  worktree. До появления commit SHA атом нельзя считать сохранённым или готовым.

## Находки

- Секреты, ключи, токены, `.env` и кабинеты учётных данных не читались.
- Боевой production `194.87.96.144` и живой кабинет Wildberries не затрагивались.
