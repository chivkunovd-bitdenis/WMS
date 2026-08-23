# UI-критика исполнения · 08-storage

ВЕРДИКТ: НАХОДКИ 4

## Находки

| Правило | Файл:строка | Что теряет оператор | Как чинить |
|---|---|---|---|
| R-20 | /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/frontend/src/screens/ff/FfStoragePage.tsx:261 | Будущий месяц отсекается только атрибутом `max` нативного поля без видимого объяснения. Оператор не понимает, почему период недоступен, хотя контракт S-11 требует объяснить ограничение. | Рядом с полем или через доступную подсказку показать короткую причину: «Будущие месяцы недоступны: расчёт ещё не начался». |
| R-09 | /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/frontend/src/screens/ff/FfStoragePage.tsx:297 | У таблицы истории габаритов не заданы фиксированные ширины колонок. При длинном имени автора или источника столбцы сместятся, и оператору сложнее сопоставить дату, объём и применённую версию. | Указать `width` для всех колонок `DataTable` истории, как уже сделано в сводной и SKU-таблицах. |
| R-09 | /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/frontend/src/screens/ff/FfStoragePage.tsx:298 | В печатном предпросмотре нет фиксированных ширин колонок. Длинный артикул способен сдвинуть числовые значения, из-за чего сверка суммы перед печатью становится ненадёжной. | Задать `width` для каждой колонки печатной `DataTable` и оставить числовые колонки справа. |
| R-10 | /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/frontend/src/screens/ff/FfStoragePage.tsx:298 | В A4-предпросмотре отсутствует «Ставка, ₽/л·день», хотя этот реквизит предусмотрен контрактом и показан в SKU-детализации. Оператор не может проверить, из какой ставки получилась напечатанная сумма. | Добавить в печатную таблицу колонку с тем же названием «Ставка, ₽/л·день» и значением `rate_snapshot`, выровненным вправо. |

## Проверено и нормально

- Шапка, фильтры и обе рабочие таблицы собраны из согласованного ui-kit: `ScreenHeader`, `FilterBar`, `DataTable`, `StatusChip`, `PrimaryAction`, `SecondaryAction`, `IconAction` и `PrintAction`; локальных таблиц, чипов и цветов на S-11 нет.
- Сводная и SKU-таблицы используют плотный `DataTable` с липкой шапкой, фиксированными ширинами, правым выравниванием чисел и без заливки проблемных строк. Статусы и подписи соответствуют контракту: «Черновик», «Требует исправления», «Зафиксирован», «Рассчитано», «Нет габаритов».
- Иконки раскрытия, истории и печати имеют подсказки; печать в строке остаётся иконкой, а в панели предпросмотра названа «Печать накладной». Кнопки укладываются в лимит R-32 и не переносят подпись.
- `python3 /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/scripts/ui/ui_inventory.py` выполнился: 15 chips, 27 statuses, 18 buttons, 23 alerts. Названия экрана сверены с кодом, контрактом и макетом; выдуманных названий колонок или статусов не найдено.

## ui_guard.py

Новые отступления есть: `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/scripts/ui/ui_guard.py` сообщил о трёх экран-монолитах вне S-11: `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/frontend/src/components/WbProductPickerDialog.tsx`, `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/frontend/src/screens/v2/FfFbsSupplyWorkspace.tsx`, `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/frontend/src/screens/v2/SellerInboundDraftScreen.tsx`. Они не относятся к карточке 08-storage и в число находок выше не включены. Для S-11 новых отступлений сторож не сообщил.
