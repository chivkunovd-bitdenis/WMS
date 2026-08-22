# DEV · 02-verdikt-screen · атом 4

## Изменённые файлы

- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/frontend/src/screens/v2/FfFbsOrdersScreen.tsx — существующая зона «Статус» выводит серверный вердикт через `StatusChip`; при отказе и отсутствии ответа рядом остаётся понятный `TextCell` без технических полей.
- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/frontend/src/utils/metaStatus.ts — `uinBadStatus` переведён в «неверный статус УИН».
- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/frontend/tests-e2e/ff-fbs-orders.spec.ts — S-03-TC-001, S-03-TC-002, S-03-TC-003 и S-03-TC-006 используют реальный `uinBadStatus` и проверяют видимый русский текст.

Исправление первого пункта REVIEW.md уже присутствует в текущей ветке (commit `e8a5ee45`). Пункты 2–3 относятся к backend/workspace и не входят в разрешённый атом списка S-03; их не менял.

## Гейты

- `npx tsc --noEmit -p tsconfig.app.json` — не запущен до компиляции: в `frontend/node_modules` нет TypeScript, `npx` попытался скачать пакет из npm и завершился `ENOTFOUND` (сеть недоступна).
- `python3 scripts/ui/ui_guard.py` — красный только из-за новых нарушений в чужих файлах `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/frontend/src/components/WbProductPickerDialog.tsx` и `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/frontend/src/screens/v2/SellerInboundDraftScreen.tsx`. В `FfFbsOrdersScreen.tsx` храповик сообщает улучшение; базовую линию не обновлял.
- `npm run test:unit` — красный: `vitest: command not found`, зависимости frontend отсутствуют.
- `npx playwright test tests-e2e/ff-fbs-orders.spec.ts --grep 'shows the server WB verdict'` — не запущен: Playwright отсутствует, `npx` завершился `ENOTFOUND` при попытке скачать пакет из npm.

## Не реализовано

- Нет. Для этого атома все пункты контракта уже представлены в текущем коде списка: один `StatusChip` в существующей зоне статуса, `TextCell` с русской причиной при отказе, `Нет ответа WB` с «Сдача пока недоступна», без новой колонки и без технических WB-полей.

## Находки

- REVIEW.md, находки 2–3: единый серверный признак в workspace и локальная готовность строки требуют отдельной работы в backend/workspace; они находятся вне данного атома списка и его разрешённых файлов.
