# DESIGN REVIEW · 07-reporting · ui-critic

ВЕРДИКТ: НАХОДКИ 1

## Находки

| Правило → файл:строка | Что теряет оператор | Как чинить |
|---|---|---|
| R-30 → `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend/src/screens/ff/FfReportsPage.tsx:104` | Предупреждение для ФФ показывает технический термин «legacy-данные». Оператор не понимает, что именно в отчёте требует внимания, и вынужден переводить внутренний термин в складской смысл. | Заменить текст на понятное описание факта без технического жаргона, например: «В отчёте есть исторические записи, восстановленные по доступным связям: …». |

## Проверено и нормально

- Экран `S-33` в `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend/screens.registry.json` включает оба маршрута и ограничивает набор файлов экраном и его ролевой обвязкой.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend/src/screens/ff/FfReportsPage.tsx:270` использует стандартную `ScreenHeader`: только `h5` с названием и одну строку назначения (R-02). Фильтры находятся в `FilterBar` над данными (R-03).
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend/src/screens/ff/FfReportsPage.tsx:294` собирает обе группировки через `DataTable`: `Paper outlined`, липкая шапка, плотность `small`, фиксированные ширины, правое выравнивание количеств и отсутствие заливок строк соблюдают R-04, R-05, R-07, R-08, R-09 и R-11. Заголовки не переносятся (R-36).
- Канонические названия «Артикул продавца», «ШК», «SKU» и «Селлер» сохранены на `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend/src/screens/ff/FfReportsPage.tsx:271` и `:297–299`; сверка с реальным `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/docs/product/ui-inventory.json` не выявила придуманной замены сущностей (R-10).
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend/src/ui-kit/ReportMetricStrip.tsx` и `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend/src/ui-kit/MovementFlowChart.tsx` являются согласованными компонентами `ui-kit`, указанными в контракте, а не локальными заменами. Палитра, бумага и табличная типографика соответствуют R-13; ошибки и предупреждения используют корректные `Alert` (R-16, R-23).
- Пагинация на `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend/src/screens/ff/FfReportsPage.tsx:312` собрана из `ActionGroup`: кнопки имеют одинаковую минимальную ширину, не переносят подписи и объясняют недоступность (R-20, R-32, R-36).

## ui_guard.py

Новые отступления есть: скрипт сообщил о монолитах в `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend/src/App.tsx`, `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend/src/components/WbProductPickerDialog.tsx`, `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend/src/screens/v2/FfFbsSupplyWorkspace.tsx` и `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend/src/screens/v2/SellerInboundDraftScreen.tsx`. Это не новые локальные элементы отчёта; три последних файла вне границы `S-33`, а `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend/src/screens/ff/FfReportsPage.tsx` скрипт отметил как улучшенный: своих таблицы и кнопки больше нет.
