ФИЧ: 2

## Фичи

### 1. Каркас модального листа и переключатель фильтра

Оператор получает одинаковый каркас для «Листа подбора»: заголовок, прокручиваемое
тело, действия внизу и блокировка закрытия во время подготовки печати. Над таблицей
он выбирает один из существующих фильтров с заметным выбранным состоянием и
клавиатурным фокусом. Это отдельный frontend ui-kit-атом и он намеренно идёт до
любых экранных работ.

Файлы:

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/frontend/src/ui-kit/ModalFrame.tsx`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/frontend/src/ui-kit/FilterBar.tsx`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/frontend/src/ui-kit/PickingListPrimitives.test.ts`

Зависимости: нет.

Как проверить: unit-тестом открыть `ModalFrame`, убедиться, что при `busy` нельзя
закрыть его ни крестиком, ни Escape, а `ChoiceFilter` меняет только выбранное
значение и доступен с клавиатуры. В `UiKitShowcase` вручную проверить длинное
прокручиваемое тело и видимый фокус фильтра.

### 2. Ячейка локальной отметки и действие печати

Оператор видит единообразные отметки «Собрал» и «Упаковал»: их можно включать
клавиатурой, а заблокированная отметка объясняет причину. Главное действие печати
называет документ «стикеры заказов», показывает подготовку и не допускает
повторного запуска до ответа. Это второй независимый frontend ui-kit-атом; нового
экрана и режима выборочной печати он не добавляет.

Файлы:

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/frontend/src/ui-kit/Cells.tsx`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/frontend/src/ui-kit/Actions.tsx`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/frontend/src/ui-kit/PickingListPrimitives.test.ts`

Зависимости: нет; может выполняться параллельно с фичей 1, потому что продуктовые
файлы не пересекаются.

Как проверить: unit-тестом переключить `CheckCell`, проверить aria-подпись и
недоступное состояние с причиной; отдельным тестом передать в `PrintAction`
значение `стикеры заказов` и увидеть корректную подпись, индикатор занятости и
запрет повторного нажатия.

## Порядок

1. Сначала выполнить фичу 1: это требуемый отдельный frontend ui-kit-слой, без
   которого экранная работа не может считаться атомарной.
2. Фича 2 независима от фичи 1 и может выполняться параллельно; обе ui-kit-фичи
   должны быть завершены до каких-либо новых изменений `S-03`.
3. Единственная незакрытая находка из
   `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/night/volna-9-recovery/cards/06-picking-list-order/JUDGE.md`
   закрывается не разработкой: после доступности стенда product browser review
   повторно проходит `S-03-TC-001` … `S-03-TC-013` и сохраняет снимки в
   `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/docs/evidence/06-picking-list-order/`.
   Серверный порядок, модалки `S-03` и лента, уже принятые ревью, в этот план
   повторно не включены.

## Что осталось за бортом

- В `JUDGE.md` нет доказанного дефекта кода: отсутствие живого browser-прогона и
  снимков остаётся задачей продуктовой приёмки, а не третьей dev-фичей.
- Секреты, ключи, токены, `.env` и кабинеты учётных данных не читались.
