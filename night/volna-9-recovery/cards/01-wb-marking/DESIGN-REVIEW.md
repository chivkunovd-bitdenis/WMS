# DESIGN REVIEW · 01-wb-marking

ВЕРДИКТ: ЧИСТО

## Находки

Нарушений по границе карточки не найдено. Карточка меняет только backend-данные маркировки; по `CONTRACT.md` экранные зоны S-03, S-14 и S-15, их таблицы, статусы, подписи, чипы и действия не меняются. В `git diff -- frontend` изменений нет, а среди коммитов относительно `origin/etalon` нет изменений файлов экранов этой карточки.

| Правило | Файл:строка | Что теряет оператор | Как чинить |
|---|---|---|---|
| — | — | — | Не требуется: пользовательское представление в карточке не менялось. |

## Проверено и нормально

Проверены файлы S-03 из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/frontend/screens.registry.json` и границы из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/night/volna-9-recovery/cards/01-wb-marking/CONTRACT.md`: новых экранов, колонок, чипов, кнопок, фильтров, сообщений, статусов или локальных UI-компонентов карточка не создаёт. Поэтому R-01–R-16 и R-31–R-36 не нарушены; существующие формулировки также сверены с `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/docs/product/ui-inventory.json`.

`python3 scripts/ui/ui_inventory.py` завершился успешно: `chips: 15`, `statuses: 27`, `buttons: 18`, `alerts: 23`.

## ui_guard.py

Новые отступления есть в общем снимке храповика: `src/components/WbProductPickerDialog.tsx` (экран-монолит 0 → 646), `src/screens/v2/FfFbsSupplyWorkspace.tsx` (2493 → 2498) и `src/screens/v2/SellerInboundDraftScreen.tsx` (1111 → 1169). Они не входят в продуктовую правку карточки 01: в текущей ветке нет frontend-диффа, а последний коммит каждого из этих экранных файлов — `d706a37` из базовой истории. По ограничению текущей карточки они не оформлены как её находки и не менялись.
