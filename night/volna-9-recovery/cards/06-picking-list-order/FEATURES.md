ФИЧ: 6

## Фичи

### 1. Переиспользуемые элементы модального листа

Оператор получает единые элементы интерфейса для модального документа, выбора фильтра, отметки в ячейке и печати стикеров заказов: они имеют состояния обычное, отключённое с причиной, занятое и клавиатурный фокус. Это не меняет сам лист подбора и может быть проверено в изоляции.

Файлы:

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/frontend/src/ui-kit/ModalFrame.tsx`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/frontend/src/ui-kit/FilterBar.tsx`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/frontend/src/ui-kit/Cells.tsx`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/frontend/src/ui-kit/Actions.tsx`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/frontend/src/ui-kit/index.ts`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/frontend/src/ui-kit/UiKitShowcase.tsx`

Зависимости: нет.

Проверка: в showcase открываются `ModalFrame`, `ChoiceFilter`, `CheckCell` и `PrintAction` со значением «стикеры заказов»; у отключённых действий есть понятное объяснение, а `busy` не позволяет закрыть модалку.

### 2. Стабильный базовый порядок заказов поставки

Оператор больше не зависит от случайной выдачи базы: relationship поставки возвращает заказы в стабильном порядке `wb_order_id`, затем внутренний `order.id`. Это базовая гарантия для чтений, которые не строят специальную последовательность листа.

Файлы:

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/backend/app/models/fbs_supply.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/backend/tests/test_fbs_supply_assembly.py`

Зависимости: нет.

Проверка: тест создаёт заказы с перемешанным порядком вставки и одинаковым `wb_order_id`; при загрузке поставки они приходят в предсказуемом порядке с развязкой по `order.id`.

### 3. Серверная последовательность листа с диапазонами и составом печати

Оператор получает лист, в котором товарные строки уже отсортированы по `(article, sku_code, size, product_name)`, а каждый диапазон `№` и полный список `order_ids` вычислены сервером. Пустые товарные признаки и совпадающие признаки не делают результат недетерминированным; диапазоны начинаются с 1, непрерывны и согласованы с количеством строки.

Файлы:

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/backend/app/services/fbs_supply_service.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/backend/app/api/fbs_supplies.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/backend/tests/test_fbs_supply_assembly.py`

Зависимости: 2.

Проверка: API листа для поставки из нескольких товарных групп возвращает отсортированные строки с одиночными номерами или диапазонами и канонический полный `order_ids`; повторный запрос даёт те же данные.

### 4. Каноническая лента и служебный номер заказа

При полной печати сервер принимает только полный состав поставки и сам приводит его к последовательности листа, а не доверяет порядку клиента. Для каждого заказа он возвращает его постоянный номер; отсутствующий WB-стикер становится ошибкой именно этого номера и не сдвигает следующие. Контракт печати дополнительно гарантирует одну WMS-этикетку с `№ K` после неизменённого PNG Wildberries, включая макеты без обычной собственной этикетки.

Файлы:

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/backend/app/services/fbs_order_tape_print_service.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/backend/app/api/fbs_supplies.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/backend/tests/test_fbs_supply_assembly.py`

Зависимости: 2, 3.

Проверка: запрос с теми же ID в перемешанном порядке возвращает ленту в каноническом порядке с номерами 1..N; повторная печать не меняет номера, а ошибка получения одного PNG сохраняет его номер и следующий номер не уплотняет.

### 5. Единый запуск и предпросмотр полной ленты из рабочего места

Оператор, запускающий печать в существующем рабочем месте, всегда отправляет серверный полный набор ID, а не `workspace.orders`. Предпросмотр показывает пары «стикер WB → служебная этикетка WMS № K» в ответном порядке и выводит `ErrorNotice` для пропущенного стикера без технического HTTP-текста.

Файлы:

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/frontend/src/screens/v2/fbsApi.ts`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/frontend/src/screens/v2/FfFbsSupplyWorkspace.tsx`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/frontend/src/screens/v2/FbsPrintPreviewDialog.tsx`

Зависимости: 3, 4.

Проверка: из рабочего места печать поставки с перемешанным `workspace.orders` открывает предпросмотр в серверном порядке; рядом с каждым WB-стикером видна отдельная служебная этикетка с тем же номером, а неполученный стикер показан как «Заказ WB №…: стикер не получен».

### 6. Модалка листа подбора с постоянными номерами и полной печатью

Оператор видит существующий «Лист подбора» в новом каркасе: колонку `№`, канонические диапазоны, неизменные остальные колонки и локальные отметки. Поиск, фильтры и отметки меняют лишь видимые строки, не номера и не полный состав печати. Загрузка, ошибка, пустая поставка и пустой результат фильтра объясняются текстом контракта; во время подготовки печати повторный запуск и закрытие блокируются.

Файлы:

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/frontend/src/screens/v2/FfFbsPickList.tsx`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/frontend/src/screens/v2/FfFbsPickList.test.ts`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/frontend/tests-e2e/ff-fbs-supply.spec.ts`

Зависимости: 1, 3, 4, 5.

Проверка: Playwright-сценарий `S-03-TC-001` открывает лист, видит диапазоны и правильный порядок; `S-03-TC-002` скрывает строки фильтром и меняет локальную отметку без перенумерации; `S-03-TC-003`, `S-03-TC-006`, `S-03-TC-007` покрывают соответственно печать полной поставки при пустом фильтре, пустую поставку и защиту от двойной печати/закрытия во время подготовки.

## Порядок

Фичи 1 и 2 независимы и могут выполняться параллельно: первая создаёт только frontend ui-kit, вторая — только базовое правило модели на backend. После них строго последовательно идут 3 (серверный контракт листа), 4 (серверная лента), 5 (существующий frontend-путь печати) и 6 (итоговая модалка и пользовательская e2e-проверка). Такой порядок не оставляет фронтенду необходимости придумывать номера или сортировку самостоятельно.

## Что осталось за бортом

- Выборочная печать видимых или отмеченных строк со своей отдельной нумерацией: контракт прямо исключает этот режим.
- Оптимизация маршрута подбора по складским ячейкам: контракт сохраняет товарный порядок и не задаёт маршрут обхода.
- Точная политика при изменении состава поставки во второй вкладке между загрузкой листа и печатью не описана контрактом; кейс `S-03-TC-008` требует не смешивать старые диапазоны с новым составом, но способ проверки актуальности должен быть закреплён продуктом до разработки соответствующей защиты.
