ВЕРДИКТ: НАХОДКИ 2

# UI-критика исполнения · 07-reporting

## Находки

| Правило → файл:строка | Что теряет оператор | Как чинить |
|---|---|---|
| R-09 → /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend/src/screens/ff/FfReportsPage.tsx:290–293 | Числовые колонки товарной группировки не имеют зафиксированной ширины. При смене данных или роли их границы могут сдвигаться, и оператор хуже считывает показатели по столбцам. Это также расходится с контрактом: 130/110/110/100 px. | Передать `width` для «Остаток сейчас» (130), «Приход» (110), «Расход» (110) и «Нетто» (100), как задано контрактом. |
| R-31 → /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend/src/screens/ff/FfReportsPage.tsx:302 | Переходы страниц «Назад» и «Вперёд» оформлены как заполненные `PrimaryAction`, хотя главным действием панели является «Скачать CSV». Равный визуальный вес нескольких главных действий мешает оператору сразу выделить основное действие. | Оформить пагинацию как отдельный согласованный навигационный контрол, не конкурирующий с главным `PrimaryAction`; сохранить короткие подписи и объяснения у недоступных переходов. |

## Проверено и нормально

- Экран зарегистрирован как S-33 в /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend/screens.registry.json; проверены все файлы этого экрана из поля `files` и непосредственные UI-kit-компоненты отчёта.
- Каркас соответствует R-02, R-03 и R-04: стандартная шапка, отдельный `FilterBar` над данными и `DataTable` на `Paper variant="outlined"`.
- Таблица использует единый `DataTable`, плотность `small`, липкую шапку, выравнивание чисел вправо и отсутствие заливки строк вне расхождения количества: R-04, R-05, R-07, R-08, R-11.
- Подписи, статусы и состояния проверены относительно контракта, макета и /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/docs/product/ui-inventory.json: несоответствий названий колонок или статусов, подпадающих под R-10, не найдено. Ошибки выводятся через `ErrorNotice`, а пустое и загрузочное состояния дают оператору понятное объяснение: R-21, R-22, R-23.
- Палитра и типографика соблюдают R-13–R-16: график использует закреплённые цвета, легенду и не превращает состояние в цвет строки; предупреждения — единым `WarningNotice`.

## ui_guard.py

Новые отступления есть в общем выводе `python3 scripts/ui/ui_guard.py`, но только вне границ этой карточки: `src/App.tsx`, `src/components/WbProductPickerDialog.tsx`, `src/screens/v2/FfFbsSupplyWorkspace.tsx` и `src/screens/v2/SellerInboundDraftScreen.tsx`. В пределах /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend/src/screens/ff/FfReportsPage.tsx новых отступлений нет; guard отдельно сообщает об улучшениях: «своя-кнопка 1 → 0» и «своя-таблица 1 → 0».
