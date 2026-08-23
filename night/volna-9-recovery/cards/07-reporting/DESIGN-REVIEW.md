# DESIGN REVIEW · 07-reporting · ui-critic

ВЕРДИКТ: НАХОДКИ 2

## Находки

| Правило → файл:строка | Что теряет оператор | Как чинить |
|---|---|---|
| R-31 → `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend/src/screens/ff/FfReportsPage.tsx:311` | Кнопки «Назад» и «Вперёд» рендерятся как два самостоятельных контурных `SecondaryAction`, рядом с которыми нет главного действия. У перехода между страницами нет предусмотренного каноном визуального веса, поэтому оператору приходится заново считывать одинаково слабые действия вместо понятного элемента навигации. | Не использовать самостоятельные контурные `SecondaryAction` для пагинации: заменить их согласованным контролом пагинации либо собрать панель действий по R-31, где второстепенное действие находится рядом с главным. |
| R-32 → `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend/src/screens/ff/FfReportsPage.tsx:311` | В одной панели две кнопки разной собственной ширины: простой `Stack` не задаёт им общий размер, в отличие от `ActionGroup`. Глаз каждый раз заново ищет переход вперёд и назад в разнокалиберной паре. | Если остаётся пара кнопок, оформить её через согласованный `ActionGroup` либо задать обеим одинаковую ширину и высоту в ui-kit-контроле пагинации. |

## Проверено и нормально

- Экран `S-33` из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend/screens.registry.json` зарегистрирован для `/app/ff/reports` и `/app/seller/reports`; его экранные файлы не используют legacy `src/ui/*`.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend/src/screens/ff/FfReportsPage.tsx:269` соблюдает R-02: шапка содержит только название и одну строку назначения; фильтры на строках 270–275 размещены в `FilterBar` по R-03.
- На строках 293–308 используется `DataTable`: это даёт `Paper outlined`, липкую шапку, плотность `small`, фиксированные ширины и правое выравнивание чисел по R-04, R-05, R-07, R-08 и R-09. Заливка строк не добавлена (R-11).
- Названия показателей, фильтров, группировок и колонок на строках 257–260 и 269–307 совпадают с `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/cards/07-reporting/CONTRACT.md`; переименований сущностей относительно его канонических подписей нет (R-10).
- Палитра и типографика реализованы через MUI-тему с каноническими значениями в `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend/src/mui/theme.ts`, а график использует primary `#5b21b6`; предупреждения и ошибки используют `WarningNotice` и `ErrorNotice`, не выдавая нейтральную информацию за статус (R-13, R-16).
- В таблице нет нового локального компонента вместо ui-kit: `ReportMetricStrip` и `MovementFlowChart` вынесены в `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend/src/ui-kit/` и заявлены контрактом.

## ui_guard.py

Новые отступления есть. `python3 /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/scripts/ui/ui_guard.py` сообщил о монолитах в `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend/src/App.tsx`, `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend/src/components/WbProductPickerDialog.tsx`, `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend/src/screens/v2/FfFbsSupplyWorkspace.tsx` и `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend/src/screens/v2/SellerInboundDraftScreen.tsx`. Три последних файла не относятся к `S-33` и не включены в текущую карточку, поэтому не включены в находки. Для `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend/src/screens/ff/FfReportsPage.tsx` контрол, наоборот, отметил улучшение: своих таблицы и кнопки больше нет.

`python3 /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/scripts/ui/ui_inventory.py` выполнен: в инвентаре нет самостоятельных записей нового отчётного экрана, а использованные в экране предметные подписи закреплены его контрактом; выдуманных замен канонических «Артикул продавца», «ШК», «SKU» и «Селлер» не обнаружено.
