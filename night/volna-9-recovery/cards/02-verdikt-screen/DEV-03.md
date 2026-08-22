# Screen Dev · 02-verdikt-screen · feature 3

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/frontend/src/screens/v2/fbsApi.ts`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/frontend/src/utils/metaStatus.ts`

Добавлен тип неизменяемого серверного вердикта WB и единый словарь его показа:
фиксированные подписи и тоны, русские переводы известных причин, безопасный показ
неизвестной причины и `disabledReason` для блокирующих состояний.

## Гейты

- `npx tsc --noEmit -p tsconfig.app.json` — FAIL: локальные зависимости отсутствуют, `npx` попытался скачать пакет `tsc`, но сеть недоступна (`ENOTFOUND registry.npmjs.org`). Ошибок компиляции получить не удалось.
- `python3 scripts/ui/ui_guard.py` — FAIL: три новые относительно baseline записи в чужих/смежных файлах: `src/components/WbProductPickerDialog.tsx`, `src/screens/v2/FfFbsSupplyWorkspace.tsx`, `src/screens/v2/SellerInboundDraftScreen.tsx`. Файлы этой атомарной правки не затрагивались; baseline не обновлялся.
- `npm run test:unit` — FAIL: `vitest: command not found`, локальные зависимости frontend не установлены.

## Не реализовано

- Компоненты экранов не подключались: это следующий атомарный кусок контракта, а текущая карточка ограничена типом API и словарём отображения.
- Полная проверка TypeScript и unit-тесты требуют установленных зависимостей; установка из сети невозможна в текущем окружении.
