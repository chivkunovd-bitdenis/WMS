## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend/src/screens/ff/FfReportsPage.tsx`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend/tests-e2e/ff-reports.spec.ts`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend/tests-e2e/seller-reports.spec.ts`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/docs/blockers/S-33.md`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/night/volna-9-recovery/cards/07-reporting/DEV.md`

Экран использует календарную дату Москвы для пресетов, передаёт серверу исключающую верхнюю границу следующего дня и автоматически ограничивает срез единственным складом. При смене общего среза прежние показатели и строки очищаются; при отсутствии базы сравнения показано «—» с предусмотренным пояснением. Ошибка сводки заменяет верхний блок и не оставляет старые значения видимыми. В этом атоме усилена e2e-проверка: обе группировки, серверная вторая страница, неизменность сводки и CSV с MIME `text/csv`.

## Гейты

- ЗЕЛЁНЫЙ: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend && npx tsc --noEmit -p tsconfig.app.json`
- ЗЕЛЁНЫЙ: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend && npm run test:unit -- --run src/screens/ff/FfReportsPage.tsx`
- КРАСНЫЙ, вне файлов атома: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting && python3 scripts/ui/ui_guard.py` сообщает новые нарушения в `frontend/src/App.tsx`, `frontend/src/components/WbProductPickerDialog.tsx`, `frontend/src/screens/v2/FfFbsSupplyWorkspace.tsx`, `frontend/src/screens/v2/SellerInboundDraftScreen.tsx`. Базовая линия не обновлялась.
- ЗЕЛЁНЫЙ: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend && npx playwright test tests-e2e/ff-reports.spec.ts tests-e2e/seller-reports.spec.ts`
- Дополнительно: `npm run test:e2e -- tests-e2e/ff-reports.spec.ts tests-e2e/seller-reports.spec.ts` не запускает Playwright в этой рабочей копии (`error: unknown command 'test'`); целевой набор успешно выполнен прямой командой `npx playwright test` выше.
- ЗЕЛЁНЫЙ: `git diff --check`
- Не сохранено commit: `git add ... && git commit ...` не может создать `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-1-07-reporting1/index.lock` (`Operation not permitted`). Метаданные Git worktree находятся вне разрешённой на запись области этой сессии; SHA для результата отсутствует.

## Не реализовано

В рамках экранного атома 11 не менялись серверные формулы, миграция, API, маршрутизация и источники данных из находок 1–13 `REVIEW.md`: это другие файлы и слои. Тест экрана закрывает находку 14 в разрешённом слое: обе группировки, серверную вторую страницу, неизменность сводки, пустую выгрузку и MIME `text/csv`.

## Находки

Для двух явных запретов экрана добавлен обязательный реестр блокировок `docs/blockers/S-33.md`: пустой CSV-срез и период длиннее 366 дней.
