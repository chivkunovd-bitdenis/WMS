# UI-критика карточки 04

Проверены зарегистрированные файлы S-03 из
`/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/zadachi-2026-08-21-20260821-r04/lane-4-04/frontend/screens.registry.json` и артефакты карточки. В рабочем дереве нет изменений целевых UI-файлов карточки 04; поэтому ниже зафиксировано отступление, уже присутствующее в коде экрана, а не выдуманная оценка реализации.

## Находки

| Правило | Файл:строка | Что теряет оператор | Как чинить |
|---|---|---|---|
| R-31 | `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/zadachi-2026-08-21-20260821-r04/lane-4-04/frontend/src/screens/v2/FfFbsSupplyWorkspace.tsx:1660` | Кнопка печати листа подбора стоит отдельно от главного действия как контурная. В рабочем месте физического подбора она выглядит слабой и не имеет заданного каноном отношения к главному действию, из-за чего оператору сложнее быстро отличить действие печати от второстепенного просмотра. | В панели этого блока задать один главный сценарий и размещать контурную кнопку только рядом с ним; если печать остаётся самостоятельным действием, дать ей предусмотренный для самостоятельного действия вес в отдельной согласованной панели. |

## Проверено и нормально

- В диалоге создания сохранена каноническая подпись «Склад WMS» без переименования: `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/zadachi-2026-08-21-20260821-r04/lane-4-04/frontend/src/screens/v2/FbsSupplyCreateDialog.tsx:228` (R-10).
- Диалог показывает ошибки в теле через `Alert severity="error"`, без технических кодов: `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/zadachi-2026-08-21-20260821-r04/lane-4-04/frontend/src/screens/v2/FbsSupplyCreateDialog.tsx:237` (R-23, R-30).
- Главное действие создания — заполненная кнопка с короткой подписью «Создать поставку»: `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/zadachi-2026-08-21-20260821-r04/lane-4-04/frontend/src/screens/v2/FbsSupplyCreateDialog.tsx:256` (R-31, R-32).
- `python3 /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/zadachi-2026-08-21-20260821-r04/lane-4-04/scripts/ui/ui_inventory.py` завершился успешно; он не выявил придуманных этой карточкой названий колонок или статусов.
- Результат `ui_guard.py`: новые отступления есть. Скрипт сообщил об экране-монолите в `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/zadachi-2026-08-21-20260821-r04/lane-4-04/frontend/src/screens/v2/FfFbsSupplyWorkspace.tsx` (2493 → 2498 строк), а также в двух файлах вне S-03. Это результат храповика, но не отдельная находка: у него нет номера правила R-XX, а роль не приписывает ему номер задним числом.
