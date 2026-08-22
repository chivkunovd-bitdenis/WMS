# DEV · 03-no-distribution-mode

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-03-no-distribution-mode/frontend/tests-e2e/ff-fbs-supply.spec.ts` — mock workspace теперь содержит `boxes_without_distribution`, а тест переключения моделирует отдельный toggle API и сохраняет включённый режим до создания коробов.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-03-no-distribution-mode/docs/blockers/S-03.md` — B-09 описывает блокировку только при наличии назначений и показывает операторскую подсказку.

## Гейты

- `npx tsc --noEmit -p tsconfig.app.json` — красный: `npx` попытался скачать пакет `tsc` из npm, но сеть недоступна (`ENOTFOUND registry.npmjs.org`).
- `python3 scripts/ui/ui_guard.py` — красный: guard сообщил новые относительно текущей базы нарушения в `src/components/WbProductPickerDialog.tsx`, `src/screens/v2/FfFbsSupplyWorkspace.tsx` и `src/screens/v2/SellerInboundDraftScreen.tsx`; базовую линию не обновлял.
- `npm run test:unit` — красный: локальная зависимость `vitest` отсутствует (`vitest: command not found`).

## Не реализовано

- Backend-находки 1–2 из `REVIEW.md` не менялись: они находятся вне роли screen-dev и вне разрешённого экранного слоя.
- Каноническая OpenAPI-схема уже содержит маршрут `/operations/fbs-supplies/{supply_id}/boxes-without-distribution` и поле `boxes_without_distribution`, поэтому изменений в ней не потребовалось.
