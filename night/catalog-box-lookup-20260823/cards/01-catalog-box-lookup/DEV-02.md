# DEV · Раскрываемый блок коробов и грузомест в каталоге

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/catalog-box-lookup-20260823/lane-1-01-catalog-box-lookup/frontend/src/screens/v2/FfCatalogInboundPackages.tsx`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/catalog-box-lookup-20260823/lane-1-01-catalog-box-lookup/frontend/src/screens/v2/FfProductsCatalogScreen.tsx`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/catalog-box-lookup-20260823/lane-1-01-catalog-box-lookup/night/catalog-box-lookup-20260823/cards/01-catalog-box-lookup/DEV.md`

Реализован только атом 2 из `FEATURES.md`: под таблицей каталога появился свёрнутый
раздел с ленивым read-only списком, адресным поиском через существующее поле и
состояниями состава, пустоты и ошибки. Адресный результат и ошибка ленивого списка
держатся независимо; повторный скан не позволяет позднему ответу открыть старый объект.

## Гейты

- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/catalog-box-lookup-20260823/lane-1-01-catalog-box-lookup/frontend && npx tsc --noEmit -p tsconfig.app.json` — зелёный.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/catalog-box-lookup-20260823/lane-1-01-catalog-box-lookup && python3 scripts/ui/ui_guard.py` — зелёный, новых нарушений нет.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/catalog-box-lookup-20260823/lane-1-01-catalog-box-lookup/frontend && npx vitest run --passWithNoTests src/screens/v2/FfCatalogInboundPackages.tsx src/screens/v2/FfProductsCatalogScreen.tsx` — зелёный. В этом атоме нет выделенного unit-файла S-16; команда ограничена двумя затронутыми экранами и завершилась без найденных тестов.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/catalog-box-lookup-20260823/lane-1-01-catalog-box-lookup/frontend && npm run test:unit -- --passWithNoTests src/screens/v2/FfCatalogInboundPackages.tsx src/screens/v2/FfProductsCatalogScreen.tsx` — красный до запуска тестов: `sh: vitest: command not found`. Локальная зависимость `vitest` в этой рабочей копии недоступна из npm-скрипта; код и проверка через `npx vitest` выше не выявили ошибок.

Полные `pytest`, `ruff check .`, `mypy .` и общий frontend-регресс не запускались по
прямому ограничению атомарной проверки.

## Не реализовано

Нет. Реализован ровно атом 2. Новый e2e-сценарий и постоянная трассировка TC-ID относятся
к следующему атому 3 и не затрагивались.

## Находки

Секреты, ключи, токены, `.env` и кабинеты учётных данных не открывались. Боевой сервер
`194.87.96.144` не использовался.
