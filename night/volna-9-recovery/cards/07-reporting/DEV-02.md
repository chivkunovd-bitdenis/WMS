# Screen-dev · 07-reporting · атом 2 · повторная доработка

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend/tests-e2e/ff-reports.spec.ts` — сценарий S-33-TC-015 закрепляет профиль сотрудника ФФ `cells=true, inventory=false`, прямой адрес `/app/ff/reports`, видимое состояние отказа, отсутствие пункта меню и всех блоков отчёта, а также отсутствие запросов `/api/reports/*`. Исправление уже находится в текущей ветке в commit `b4342ba84686299b315192316d2ac0bbcafab942`; в этом проходе содержимое файла не менялось повторно.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/night/volna-9-recovery/cards/07-reporting/DEV.md` — отчёт screen-dev по этому атому.

## Гейты

- ЗЕЛЁНЫЙ: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend && npx tsc --noEmit -p tsconfig.app.json` — код завершения 0.
- ЗЕЛЁНЫЙ: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend && npm run test:unit -- src/screens/ff/FfReportsPage.test.tsx` — `1 passed`, код завершения 0.
- КРАСНЫЙ, вне границ атома: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting && python3 scripts/ui/ui_guard.py` — обнаружены новые нарушения в `src/App.tsx`, `src/components/WbProductPickerDialog.tsx`, `src/screens/v2/FfFbsSupplyWorkspace.tsx` и `src/screens/v2/SellerInboundDraftScreen.tsx`. Все они вне разрешённого файла этого атома; базовая линия не обновлялась.
- НЕ ЗАПУЩЕН ДО КОНЦА из-за ограничений среды: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend && npx playwright test tests-e2e/ff-reports.spec.ts --grep 'cells access but without inventory access'` — Playwright не смог запустить API, так как bind `127.0.0.1:18000` завершился `operation not permitted`. Сам тест не начал выполнение.
- Полный `npm run test:e2e`, полный backend `pytest`, `ruff check .` и `mypy .` не запускались: они запрещены границами атомарной проверки.

## Не реализовано

- В коде нет нереализованных пунктов атома: требуемый тестовый профиль, маршрут, видимые проверки и контроль отсутствия отчётных запросов уже реализованы буквально.
- Живой e2e-прогон не подтверждён только из-за запрета среды на открытие локального порта; это не исправляется в разрешённом тестовом файле.

## Блокеры

- Отчёт не удалось сохранить отдельным commit: `git add night/volna-9-recovery/cards/07-reporting/DEV.md && git diff --cached --check && git commit -m "night(07-reporting): record screen atom gates"` завершилась ошибкой создания `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-1-07-reporting1/index.lock` (`Operation not permitted`). `DEV.md` сохранён в рабочем дереве, но не зафиксирован.

## Находки

- Секреты, ключи, токены, `.env`, кабинеты учётных данных, production `194.87.96.144` и живой кабинет Wildberries не читались и не затрагивались.
