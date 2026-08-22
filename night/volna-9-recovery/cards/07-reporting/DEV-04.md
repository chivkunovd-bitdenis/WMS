## Изменённые файлы

Атом `ReportMetricStrip` и его экспорт уже присутствуют в рабочей копии и соответствуют разрешённому набору файлов:

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend/src/ui-kit/ReportMetricStrip.tsx`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend/src/ui-kit/index.ts`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend/src/ui-kit/ReportMetricStrip.test.tsx`

В рамках переделки по `REVIEW.md` относящихся к этому ui-kit-атому находок нет, поэтому исходный код этих файлов не изменялся.

## Гейты

- `npx tsc --noEmit -p tsconfig.app.json` — красный: локальный `tsc` отсутствует; `npx` попытался скачать пакет, но сеть недоступна (`ENOTFOUND registry.npmjs.org`).
- `python3 scripts/ui/ui_guard.py` — красный из-за новых нарушений в чужих файлах: `frontend/src/App.tsx`, `frontend/src/components/WbProductPickerDialog.tsx`, `frontend/src/screens/v2/FfFbsSupplyWorkspace.tsx`, `frontend/src/screens/v2/SellerInboundDraftScreen.tsx`. В разрешённых файлах атома нарушений не выявлено; базовую линию не обновлял.
- `npm run test:unit -- src/ui-kit/ReportMetricStrip.test.tsx` — красный: локальный `vitest` отсутствует (`vitest: command not found`).

## Не реализовано

Нет пунктов контракта, относящихся к `ReportMetricStrip`, которые не легли буквально. Находки `REVIEW.md` относятся к другим слоям и файлам карточки и не исправлялись в рамках этого атомарного куска.

