# Screen Dev · 07-reporting · фича 10

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend/src/screens/ff/FfReportsPage.tsx`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/night/volna-9-recovery/cards/07-reporting/DEV.md`

Экран переведён на контрактную шапку, `FilterBar`, единый запрос сводки и таблицы, `ReportMetricStrip`, `MovementFlowChart`, freshness/warning и частичные ошибки. Старые числа сбрасываются в loading-состояние при смене фильтра. Seller-фильтр рендерится только для ФФ-контекста с переданным списком селлеров.

## Гейты

- `npx tsc --noEmit -p tsconfig.app.json` из `frontend/` — GREEN (команда завершилась без диагностик).
- `python3 scripts/ui/ui_guard.py` из корня — RED из-за существующих/несвязанных нарушений: `frontend/src/components/WbProductPickerDialog.tsx`, `frontend/src/screens/v2/FfFbsSupplyWorkspace.tsx`, `frontend/src/screens/v2/SellerInboundDraftScreen.tsx`. Для `FfReportsPage.tsx` стало лучше: ручные кнопка и таблица устранены.
- `npm run test:unit` из `frontend/` — НЕ ЗАПУЩЕН: отсутствует локальный бинарник `vitest` (`vitest: command not found`, exit 127).

## Не реализовано

- Seller e2e-файл не добавлялся: в рабочем checkout отсутствует доступный seller fixture/сценарий авторизации, а разрешённые файлы карточки не включают общие seller helpers. Сам экран скрывает seller-фильтр при пустом списке `sellers`.
- Серверный export CSV и переключатель группировки не добавлены в эту атомарную фичу: они относятся к последующим пунктам FEATURES.md.
