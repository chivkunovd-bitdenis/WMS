# DEV · 05-prod-slow · атом 6 · пагинация S-03 · rework

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/frontend/src/screens/v2/FfFbsOrdersScreen.tsx`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/frontend/tests-e2e/ff-fbs-orders.spec.ts`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/night/volna-9-recovery/cards/05-prod-slow/DEV.md`

`/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/frontend/src/screens/v2/fbsApi.ts`
проверен и не изменён: используемый экраном `fetchFbsWorklist` уже передаёт контрактные
`limit` и `cursor`.

Закрыты находки 8 и 9 из `REVIEW.md`, относящиеся к слою этого атома. Догрузка
фиксирует номер актуального запроса и ключ фильтра; ответ старого селлера, склада
или вкладки больше не добавляется к новой выдаче. Фоновый тик принимает новый
`next_cursor` первой порции, поэтому вставка заказа сверху не оставляет старую
границу пагинации. Выбор сместившейся строки сохраняется, а повторный обход нового
курсора возвращает её без дублей и без очистки ранее догруженного хвоста.

В разрешённый Playwright-файл добавлена гонка «летящая догрузка → смена склада →
старый ответ» и усилен `S-03-TC-006` с реальным сдвигом границы: новая строка
вставляется сверху, заказ № 50 возвращается по обновлённому курсору и остаётся
выбранным.

## Гейты

- `npx tsc --noEmit -p tsconfig.app.json` из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/frontend` — **красный** только на существующей ошибке вне границы атома: `src/components/MarkingPrintDialog.tsx:3` импортирует отсутствующий `beginPrintUserGesture` из `@mui/material`. Три ранее существовавшие ошибки в разрешённом `FfFbsOrdersScreen.tsx` устранены; других ошибок команда не выдаёт.
- `python3 scripts/ui/ui_guard.py` из корня — **красный** на уже накопленных превышениях baseline: `MarkingPrintDialog.tsx` 1687 → 1753, `WbProductPickerDialog.tsx` 0 → 646, `FfFbsOrdersScreen.tsx` 1587 → 1668, `FfFbsSupplyWorkspace.tsx` 2493 → 2498, `SellerInboundDraftScreen.tsx` 1111 → 1169. Baseline флагом `--update` не менялась; четыре соседних файла запрещены границей роли.
- `npm run test:unit` из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/frontend` — **зелёный**, 20 файлов и 142 теста.
- `npm run test:e2e -- tests-e2e/ff-fbs-orders.spec.ts` — **красный до запуска тестов**: Playwright webServer не получил разрешение среды на bind `127.0.0.1:18000` (`operation not permitted`). Production, внешний WB и сеть не затрагивались.
- `npx playwright test tests-e2e/ff-fbs-orders.spec.ts --list` — **зелёный**: файл корректно собран и обнаружены 14 сценариев, включая оба новых/усиленных сценария rework.
- `git diff --check` — **зелёный**.
- `git add frontend/src/screens/v2/FfFbsOrdersScreen.tsx frontend/tests-e2e/ff-fbs-orders.spec.ts night/volna-9-recovery/cards/05-prod-slow/DEV.md && git commit -m "fix(fbs): guard paginated worklist refreshes"` — **красный до изменения индекса**: Git не смог создать `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-2-05-prod-slow/index.lock`, `Operation not permitted`. Новый commit SHA не создан.

## Не реализовано

- Буквально выполнить браузерный прогон `S-03-TC-001`–`S-03-TC-007` и
  `S-03-TC-010`–`S-03-TC-012` не удалось: среда запрещает локальному API занять
  тестовый порт до старта Playwright. Сами сценарии собираются и перечисляются.
- Получить зелёные общие `tsc` и `ui_guard.py` в границах атома невозможно без
  изменения прямо запрещённого соседнего `MarkingPrintDialog.tsx` и нескольких
  соседних экранов либо без запрещённого обновления baseline.
- Находка 10 ревью про `S-03-TC-008`, `009`, `013`, `014`, `015` относится к
  следующему атому фоновой печати и общему `MarkingPrintDialog`, а не к пагинации
  этого атома; она намеренно не реализовывалась здесь.
- Изменения локально реализованы в постоянной рабочей копии, но не сохранены
  отдельным Git-коммитом из-за запрета среды на запись в служебный индекс worktree.

## Находки

- Секреты, ключи, токены, `.env` и кабинеты учётных данных не читались.
- Боевой production `194.87.96.144` и живой кабинет Wildberries не затрагивались.
