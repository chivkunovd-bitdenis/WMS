# DEV · 01-catalog-box-lookup · атом 1

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/catalog-box-lookup-20260823/lane-1-01-catalog-box-lookup/frontend/screens.registry.json` — в список файлов `S-16` добавлен локальный владелец блока коробов: `src/screens/v2/FfCatalogInboundPackages.tsx`.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/catalog-box-lookup-20260823/lane-1-01-catalog-box-lookup/night/catalog-box-lookup-20260823/cards/01-catalog-box-lookup/DEV.md` — отчёт роли `screen-dev` для атома 1.

## Гейты

- Зелёный: `node --input-type=module -e "import fs from 'node:fs'; const registry = JSON.parse(fs.readFileSync('frontend/screens.registry.json', 'utf8')); const screen = registry.screens?.find((item) => item.id === 'S-16' && item.route === '/app/ff/products'); const expected = 'src/screens/v2/FfCatalogInboundPackages.tsx'; if (!screen || !screen.files?.includes(expected)) throw new Error('S-16 owner is missing'); console.log('registry JSON parsed; S-16 owns ' + expected);"` — JSON разбирается, `S-16` владеет требуемым файлом.
- Зелёный: `git diff --check -- frontend/screens.registry.json` — ошибок пробелов нет; diff содержит ровно одно добавление файла в `S-16`.
- Красный, ограничение окружения: `npx tsc --noEmit -p tsconfig.app.json` и `npx --no-install tsc --noEmit -p tsconfig.app.json` из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/catalog-box-lookup-20260823/lane-1-01-catalog-box-lookup/frontend` не выполнились: локальный `frontend/node_modules/.bin/tsc` отсутствует; `npm exec --offline` подтвердил отсутствие TypeScript в кэше (`ENOTCACHED`).
- Красный, вне границы атома: `python3 scripts/ui/ui_guard.py` сообщил новые нарушения в не затронутых этим атомом файлах `frontend/src/components/WbProductPickerDialog.tsx`, `frontend/src/screens/v2/FfFbsSupplyWorkspace.tsx`, `frontend/src/screens/v2/FfProductsCatalogScreen.tsx`, `frontend/src/screens/v2/SellerInboundDraftScreen.tsx`. Базовая линия не менялась, а эти файлы не правились, так как атом разрешает только реестр.
- Красный, ограничение окружения: `npm run test:unit` из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/catalog-box-lookup-20260823/lane-1-01-catalog-box-lookup/frontend` завершился с `sh: vitest: command not found`; локальный `node_modules` отсутствует. Для декларативного изменения реестра отдельного unit-теста в репозитории нет.
- Не сохранено в Git: `git add frontend/screens.registry.json night/catalog-box-lookup-20260823/cards/01-catalog-box-lookup/DEV.md` не смог создать `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-1-01-catalog-box-lookup/index.lock` (`Operation not permitted`). Поэтому отдельный commit SHA получить в этом окружении нельзя.

## Не реализовано

- Все пункты контракта, относящиеся к UI и поведению, намеренно не изменялись: этот проход ограничен только атомом 1 из `FEATURES.md` — регистрацией владельца файла в `S-16`.
- Находки ревью 2–8 не относятся к файлу и слою атома 1; они остаются следующими отдельными атомами из `FEATURES.md` и в этом проходе не затрагивались.

## Находки

Нет находок о данных, секретах или персональных данных.
