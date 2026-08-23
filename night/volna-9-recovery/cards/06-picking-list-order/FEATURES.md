ФИЧ: 8

## Фичи

### 1. Передавать и проверять снимок порядка листа подбора

Оператор печатает только тот полный порядок, который увидел в открытом листе. Сервер
возвращает вместе со строками непрозрачный снимок канонического порядка, а при печати
сверяет его с текущими атрибутами группировки и отклоняет устаревший снимок до создания
ленты. Изменение товара во второй вкладке поэтому не сопоставит номер на этикетке с
другой строкой.

Файлы:

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/backend/app/services/fbs_supply_service.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/backend/app/services/fbs_order_tape_print_service.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/backend/app/api/fbs_supplies.py`

Зависимости: нет.

Как проверить: backend-тестом получить лист, изменить один из атрибутов канонической
группировки без изменения состава `order_ids`, затем отправить печать со старым снимком.
Ожидаем контрактный отказ без созданной ленты; неизменённый снимок по-прежнему
принимается и сохраняет его номера.

### 2. Выделить безопасный серверный режим печати из листа

Обычная кнопка `Печать стикеров` в листе подбора запрашивает только пары WB → WMS.
Этот режим не выбирает, не выпускает и не перепечатывает коды маркировки, не синхронизирует
их с Wildberries и не зависит от макета маркировки. Существующий режим печати маркировки
остаётся отдельным, чтобы не менять упаковочные операции.

Файлы:

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/backend/app/services/fbs_order_tape_print_service.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/backend/app/api/fbs_supplies.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/backend/tests/test_fbs_order_tape_print.py`

Зависимости: фича 1.

Как проверить: backend-тестом напечатать полную поставку с товаром, требующим маркировку,
через явный режим листа подбора. В ответе есть только готовый WB-asset и служебный номер,
нет `printed_codes`, записей о выпуске/перепечати и вызова синхронизации WB. Отдельный
старый запрос печати маркировки сохраняет прежний контракт.

### 3. Подключить лист к безопасной печати и вернуть упаковочную кнопку

Оператор из листа передаёт серверный снимок и явный безопасный режим печати. В зоне
упаковки кнопка `Печать всего` снова открывает существующий конструктор с выбранным
макетом, `allow_partial` (разрешением неполной печати) и подтверждением большой партии,
а не подменяется печатью ленты из листа.

Файлы:

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/frontend/src/screens/v2/fbsApi.ts`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/frontend/src/screens/v2/FfFbsSupplyWorkspace.tsx`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/frontend/tests-e2e/ff-fbs-supply.spec.ts`

Зависимости: фичи 1 и 2.

Как проверить: e2e-сценарием нажать `Печать стикеров` из открытого листа и проверить
тело запроса: полный `order_ids`, снимок порядка и безопасный режим. Отдельно нажать
`Печать всего` в упаковке и увидеть стандартный конструктор, включая выбранный макет и
защитное подтверждение; лента листа подбора не открывается.

### 4. Не добавлять номера листа в общий API assets

Обычные QR-заказы, QR-короба, грузоместа и поставки сохраняют прежний ответ
`/print-assets`: без номера листа подбора. Номер передаётся только в результате
специальной печати ленты, поэтому общий API не меняет физический комплект соседних
действий.

Файлы:

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/backend/app/api/fbs_supplies.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/backend/tests/test_fbs_print_assets.py`

Зависимости: фича 2.

Как проверить: backend-тестом запросить обычные `order_sticker`, `box_qr`, `cargo_place_qr`
и `supply_qr` через `/print-assets` и убедиться, что у assets нет `order_number`.
Ответ специальной ручки ленты всё ещё содержит номер только для своей пары.

### 5. Изолировать предпросмотр ленты и печатать ровно пару WB → WMS

В специальном режиме листа подбора предпросмотр и печать создают для каждого заказа ровно
две страницы: неизменённый PNG WB 40×58 мм и одну WMS-этикетку `№ K`. PNG печатается в
фиксированном размере без поля, масштабирования или выбора пользовательского формата.
Обычный предпросмотр QR не добавляет WMS-страницу и сохраняет подходящую подпись действия.

Файлы:

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/frontend/src/screens/v2/FbsPrintPreviewDialog.tsx`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/frontend/src/screens/v2/FbsPrintPreviewDialog.test.ts`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/frontend/tests-e2e/ff-fbs-supply.spec.ts`

Зависимости: фичи 2 и 4.

Как проверить: unit-тестом построить HTML специальной ленты для заказа с обязательной
маркировкой и получить только WB-страницу и WMS-страницу, без кода маркировки. Проверить
CSS печати 40×58 мм без padding и `max-*`; e2e-сценарием напечатать обычный QR и убедиться,
что WMS `№` не показывается, а текст кнопки соответствует QR-документу.

### 6. Запретить физическую печать неполной ленты

Когда хотя бы один заказ не получил PNG или вернул ошибку, оператор видит честные счётчики
`Готово`, `Не получено` и `Ошибок`, а главное действие печати недоступно с понятной
причиной. Готовые пары и `ErrorNotice` остаются видимыми для диагностики, но укороченная
лента не печатается.

Файлы:

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/frontend/src/screens/v2/FbsPrintPreviewDialog.tsx`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/frontend/tests-e2e/ff-fbs-supply.spec.ts`

Зависимости: фича 5.

Как проверить: e2e-сценарием вернуть один готовый PNG и ошибку следующего заказа.
В диалоге видны реальные счётчики и складской `ErrorNotice`, а `Печать стикеров`
заблокирована; при полном ответе кнопка снова доступна.

### 7. Сделать загрузку листа устойчивой к смене поставки и ошибке

Оператор при быстрой смене поставки видит только последний ответ: устаревший запрос
отменяется либо игнорируется. Пока идёт загрузка, остаются каркас, фильтры, заголовки и
скелетон счётчиков; при ошибке показывается фиксированное складское сообщение без ложного
текста о пустой поставке и без технического текста браузера.

Файлы:

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/frontend/src/screens/v2/FfFbsPickList.tsx`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/frontend/src/screens/v2/FfFbsPickList.test.ts`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/frontend/tests-e2e/ff-fbs-supply.spec.ts`

Зависимости: нет; не пересекается по продуктовым файлам с фичами 1–6 и может выполняться
параллельно с ними.

Как проверить: e2e-сценарием задержать ответ поставки A, переключиться на B и вернуть B
раньше A — в модалке остаются строки B и печать отправляет только их. Отдельно вернуть
ошибку загрузки и проверить фиксированный текст, отсутствие пустого состояния и видимый
скелетон в начале запроса.

### 8. Мигрировать старые локальные отметки листа

Оператор после обновления видит свои ранее сохранённые отметки `Собрал` и `Упаковал`.
При чтении localStorage старый ключ `article::size` сопоставляется с единственной
подходящей строкой нового ключа; новые записи продолжают использовать точный ключ.
Неоднозначные старые записи не назначаются произвольно.

Файлы:

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/frontend/src/screens/v2/FfFbsPickList.tsx`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/frontend/src/screens/v2/FfFbsPickList.test.ts`

Зависимости: фича 7.

Как проверить: unit-тестом положить в localStorage старую запись для единственной строки
товара, открыть лист и увидеть обе восстановленные отметки по новому ключу. Для двух
строк с одинаковыми старыми `article::size` проверить, что отметка не переносится на
случайный товар.

## Порядок

1. Сначала фича 1: она вводит проверяемый серверный снимок, от которого зависит запрос
   из листа.
2. Затем фича 2, чтобы специальный серверный режим был безопасен до подключения кнопки.
3. После неё можно выполнять фичу 3; она связывает UI только с уже существующим
   контрактом и одновременно возвращает границу упаковочной операции.
4. Затем фича 4, так как она отделяет ответ общего API от специальной ленты.
5. После фич 2 и 4 выполнить фичу 5, а затем фичу 6: сначала точный состав и размер
   страниц, затем запрет печати неполного состава.
6. Фича 7 независима по продуктовым файлам от фич 1–6 и может идти параллельно с их
   серверной частью. Фича 8 следует за фичей 7, потому что использует тот же путь загрузки
   строк и локальных отметок.

## Что осталось за бортом

- Принятые ui-kit-атомы `ModalFrame`, `ChoiceFilter`, `CheckCell` и `PrintAction` не
  возвращены в разработку: в `REVIEW.md` для них нет незакрытой находки.
- Повторный живой browser product review и снимки всех `S-03-TC-001` … `S-03-TC-013`
  обязательны после этих фич, но это приёмка, а не дополнительная dev-фича.
- Секреты, ключи, токены, `.env` и кабинеты учётных данных не читались.
