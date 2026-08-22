# UI-критика · 02-verdikt-screen

ВЕРДИКТ: НАХОДКИ 1

## Находки

| Правило | Файл:строка | Что теряет оператор | Как чинить |
|---|---|---|---|
| R-11 → R-35 | `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/frontend/src/screens/v2/FfFbsSupplyWorkspace.tsx:1911,1922-1928` | Положительный серверный WB-вердикт повторно выделяет всю строку зелёной заливкой и границей, помимо `StatusChip` в зоне «ЧЗ». Оператор получает второй визуальный сигнал той же сущности, а зелёная строка нарушает закреплённое значение заливки строки — только расхождение по количеству. | Не связывать `bgcolor` и `borderLeftColor` с `metadata.verdict.delivery_allowed`: оставить для строки только уже существующие состояния активности/печати, а WB-вердикт показывать единственным `StatusChip` в зоне «ЧЗ». |

## Проверено и нормально

Сверены контракт и макет из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/night/volna-9-recovery/cards/02-verdikt-screen/CONTRACT.md` и `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/night/volna-9-recovery/cards/02-verdikt-screen/MOCKUP.html`, а также файлы S-03 из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/frontend/screens.registry.json`.

В обоих затронутых местах использован согласованный `StatusChip`; словарь фиксирует контрактные подписи WB, а причина отказа выводится через `TextCell` без технического кода. Для основного действия применяется `PrimaryAction` с объяснением недоступности. Новых колонок, вкладок, локального компонента статуса или новых названий статусов не обнаружено.

`python3 scripts/ui/ui_guard.py`: новые отступления есть, но только вне границы карточки — в `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/frontend/src/components/WbProductPickerDialog.tsx` и `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/frontend/src/screens/v2/SellerInboundDraftScreen.tsx`. Для целевых файлов guard фиксирует улучшения и не сообщает нового отступления.

`python3 scripts/ui/ui_inventory.py`: выполнен успешно; реальные подписи WB проверены по исходному коду, придуманных колонок или статусов в реализации нет.
