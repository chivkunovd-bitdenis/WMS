# DESIGN-REVIEW · 04-warehouse-switch

ВЕРДИКТ: ЧИСТО

## Находки

Нарушений не найдено.

## Проверено и нормально

- Сверены контракт, `MOCKUP.html`, реестр затронутых экранов S-01, S-03, S-04, S-14, S-22, S-24, S-25, S-26, S-28 и S-29, а также разделы 1–3 `UX_CANON_RU.md` и инварианты R-31…R-36.
- R-23: `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend/src/screens/v2/FfFbsOrdersScreen.tsx:1015` передаёт ошибку только в `WarehouseContextSwitch`; прежний второй `Alert` удалён. Оператор видит одно понятное сообщение с действием «Обновите страницу».
- R-32 и R-36: `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend/src/screens/v2/FfFbsStockSyncScreen.tsx:773` содержит короткую подпись главной кнопки «Выгрузить остатки»; она не переносит ряд действий.
- `WarehouseContextSwitch` — согласованный компонент ui-kit. В нём показываются только названия складов, при одном варианте он не рендерится, а закрепление документа объяснено текстом причины. Контекст расположен под шапкой до зависимых фильтров, таблиц и сканера.
- В FBS-поставке предупреждение о подборе не блокирует действие, общая недостача показана через ошибку, числовые колонки выровнены вправо; в интерфейс не попадают служебные идентификаторы и внутренние остатки селлера.

## ui_guard.py

Новые отступления есть. `python3 scripts/ui/ui_guard.py` сообщил о росте экранов-монолитов в следующих файлах карточки:

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend/src/screens/v2/FfFbsOrdersScreen.tsx` (1587 → 1670);
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend/src/screens/v2/FfFbsStockSyncScreen.tsx` (1083 → 1121);
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend/src/screens/v2/FfFbsSupplyWorkspace.tsx` (2493 → 2605);
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend/src/screens/v2/SellerInboundDraftScreen.tsx` (1111 → 1267).

Сторож также вывел `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend/src/components/WbProductPickerDialog.tsx`; файл вне границ этой карточки и не включён в находки. Отступления храповика не получили номера правила R-XX, поэтому не входят в машинный вердикт ui-critic.

`python3 scripts/ui/ui_inventory.py` выполнен. Он обновил сгенерированный инвентарь для сверки фактических подписей, статусов и кнопок; эти побочные изменения были возвращены, чтобы не затронуть несвязанные файлы.
