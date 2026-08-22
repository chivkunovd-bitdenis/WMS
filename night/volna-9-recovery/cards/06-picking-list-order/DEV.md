# Screen development report · 06-picking-list-order · атом 6 · переделка по REVIEW

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/frontend/screens.registry.json` — `FfFbsPickList.tsx` зарегистрирован в `files` экрана `S-03`, поэтому модалка теперь входит в разрешённую границу экранного конвейера; это исправляет находку 1 ревью.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/night/volna-9-recovery/cards/06-picking-list-order/DEV.md` — записан обязательный отчёт текущего атома.

Остальные находки ревью уже исправлены предыдущими атомарными коммитами этой же ветки: совместимость MUI — `e5230651`, устранение дубля ошибки WB — `a21180bf`, согласованность снимка листа и ленты, запрет выборочной печати/копий и браузерные регрессии — `4e98a155`.

## Гейты

- `npx tsc --noEmit -p tsconfig.app.json` из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/frontend` — **зелёный**, код 0.
- `npm run test:unit -- src/ui-kit/PickingListPrimitives.test.ts src/screens/v2/FfFbsPickList.test.ts src/screens/v2/FbsPrintPreviewDialog.test.ts src/screens/v2/FfFbsSupplyWorkspace.test.ts` из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/frontend` — **зелёный**, прошли 4 файла и 18 тестов.
- `python3 scripts/ui/ui_guard.py` из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order` — **красный только вне границ атома**: существующие нарушения `src/components/WbProductPickerDialog.tsx: экран-монолит 0 → 646` и `src/screens/v2/SellerInboundDraftScreen.tsx: экран-монолит 1111 → 1169`. Для файлов карточки новых нарушений нет; guard отмечает улучшения `FfFbsPickList.tsx` по собственной таблице, кнопкам и чипам и `FfFbsSupplyWorkspace.tsx` по размеру монолита. Baseline не обновлялась.
- `npx playwright test tests-e2e/ff-fbs-supply.spec.ts --grep 'S-03-TC-00[1-8]'` из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/frontend` — **красный по ограничению среды до запуска кейсов**: Playwright API дошёл до старта, но sandbox запретил bind `127.0.0.1:18000` (`operation not permitted`).
- `npx playwright test tests-e2e/ff-fbs-supply.spec.ts --grep 'S-03-TC-00[1-8]' --list` из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/frontend` — **зелёный**: найдены 8 целевых тестов в одном файле, включая `S-03-TC-001`, `S-03-TC-002`, `S-03-TC-003`, `S-03-TC-004`, `S-03-TC-005`, `S-03-TC-006`, `S-03-TC-007`, `S-03-TC-008`.
- `python3 -m json.tool frontend/screens.registry.json >/dev/null` из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order` — **зелёный**, реестр остаётся валидным JSON.
- `git diff --check` из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order` — **зелёный**, код 0 до записи отчёта.
- `git add -- frontend/screens.registry.json night/volna-9-recovery/cards/06-picking-list-order/DEV.md && git diff --cached --check && git diff --cached --stat && git commit -m 'fix(fbs): register picking list screen'` из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order` — **красный по ограничению среды**: Git не смог создать `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-3-06-picking-list-order/index.lock`, `Operation not permitted`; индекс не изменён, коммит не создан.

## Не реализовано

- Пункты контракта и все шесть находок ревью в коде ветки закрыты; буквальных пропусков в разрешённом слое нет.
- Живое выполнение Playwright-сценариев не подтверждено из-за запрета sandbox на локальный порт. Проверено только обнаружение всех восьми целевых сценариев; это ограничение проверки, а не замена browser product review.
- Изменение реестра и этот отчёт находятся в постоянной рабочей копии, но не сохранены отдельным Git-коммитом из-за read-only доступа к общей Git-метапапке. Последний сохранённый `HEAD` — `4e98a155db61`; он содержит исправления находок 2–6, но не текущую регистрацию экрана из находки 1.

## Находки

- Секреты, ключи, токены, `.env` и кабинеты учётных данных не читались и не изменялись.
- Несвязанное изменение `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/night/volna-9-recovery/JOURNAL.md` сохранено без изменений и в коммит атома не включается.
