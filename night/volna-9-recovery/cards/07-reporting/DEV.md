## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend/src/screens/ff/FfReportsPage.tsx`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend/tests-e2e/ff-reports.spec.ts`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend/tests-e2e/seller-reports.spec.ts`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/night/volna-9-recovery/cards/07-reporting/DEV.md`

Экран использует календарную дату Москвы для пресетов, передаёт серверу исключающую верхнюю границу следующего дня и автоматически ограничивает срез единственным складом. При смене общего среза прежние показатели и строки очищаются; при отсутствии базы сравнения показано «—» с предусмотренным пояснением. Ошибка сводки заменяет верхний блок и не оставляет старые значения видимыми. Исправлен сломанный FF e2e и добавлен сценарий селлерского маршрута без FF-фильтра и технического предупреждения.

## Гейты

- ЗЕЛЁНЫЙ: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend && npx tsc --noEmit -p tsconfig.app.json`
- ЗЕЛЁНЫЙ: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend && npx playwright test tests-e2e/ff-reports.spec.ts tests-e2e/seller-reports.spec.ts`
- ЗЕЛЁНЫЙ: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend && git diff --check`
- КРАСНЫЙ вне этого атома: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting && python3 scripts/ui/ui_guard.py` сообщает новые нарушения только в `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend/src/App.tsx`, `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend/src/components/WbProductPickerDialog.tsx`, `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend/src/screens/v2/FfFbsSupplyWorkspace.tsx`, `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend/src/screens/v2/SellerInboundDraftScreen.tsx`. Эти файлы не входят в разрешённый слой экрана.
- КРАСНЫЙ по окружению: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend && npm run test:unit` не стартует: `sh: vitest: command not found`.

## Не реализовано

- Находки ревью № 3–5, 7–12 требуют изменений в backend-сервисах, миграции, CSV и ui-kit и не входят в разрешённые файлы screen-dev. Они не исправлялись.
- Находка № 1 о передаче складов маршрутами уже не воспроизводится в этой рабочей копии: оба маршрута передают `warehouses`; экранный дефект единственного склада исправлен в `FfReportsPage.tsx`. Фильтрация только операционных складов остаётся обязанностью источника данных.
- Отдельный файл `docs/blockers/S-33.md`, запрошенный ревью для правил экспорта, не создавался: это документационный слой вне разрешённого списка файлов текущего атома.
