# DESIGN REVIEW · 07-reporting · ui-critic

ВЕРДИКТ: ЧИСТО

## Находки

Нарушений не найдено.

## Проверено и нормально

- Экран `S-33` в `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend/screens.registry.json` содержит оба согласованных маршрута и ограничивает экранный набор файлов его ролевой обвязкой.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend/src/screens/ff/FfReportsPage.tsx:270` применяет стандартную `ScreenHeader`: заголовок `h5` и одну строку назначения (R-02). Поиск и фильтры собраны через `FilterBar` над данными (R-03).
- Обе группировки на `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend/src/screens/ff/FfReportsPage.tsx:294` используют `DataTable`: `Paper outlined`, липкая шапка, плотность `small`, фиксированные ширины, правое выравнивание количеств и отсутствие цветной заливки строк соблюдают R-04, R-05, R-07, R-08, R-09 и R-11. Подписи колонок и действий не переносятся (R-36).
- Подписи «Артикул продавца», «ШК», «SKU» и «Селлер» сверены с реальным `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/docs/product/ui-inventory.json`; придуманной замены сущностей нет (R-10).
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend/src/ui-kit/ReportMetricStrip.tsx` и `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend/src/ui-kit/MovementFlowChart.tsx` — предусмотренные контрактом компоненты `ui-kit`, а не локальные замены. Бумага, палитра и типографика соответствуют R-13; ошибки и предупреждения используют `Alert`, а строковый статус — короткий `StatusChip` (R-14, R-16, R-23).
- Предупреждение о восстановленной истории на `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend/src/screens/ff/FfReportsPage.tsx:104` говорит складским языком, без внутреннего термина `legacy` (R-30).
- Пагинация на `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend/src/screens/ff/FfReportsPage.tsx:312` использует `ActionGroup`: второстепенные действия одной ширины, а недоступные кнопки объясняют причину (R-20, R-31, R-32, R-36).

## ui_guard.py

Новые отступления есть: `python3 scripts/ui/ui_guard.py` сообщил об экранах-монолитах в `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend/src/App.tsx`, `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend/src/components/WbProductPickerDialog.tsx`, `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend/src/screens/v2/FfFbsSupplyWorkspace.tsx` и `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend/src/screens/v2/SellerInboundDraftScreen.tsx`. Это не находки данного UI-ревью: три последних файла вне `S-33`, а в `FfReportsPage.tsx` скрипт зафиксировал улучшение — собственных таблицы и кнопки больше нет.
