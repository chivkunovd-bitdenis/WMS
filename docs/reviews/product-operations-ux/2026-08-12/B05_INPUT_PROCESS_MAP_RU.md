# Батч 05. Карта процесса остатков, движений и инвентаризации

## Граница и исходное состояние

B05 проверяет только FF-каталог остатков, адресный справочник складов/ячеек, журнал движений, форму внутренних перемещений и раздел инвентаризации на Railway staging. Упаковка, MP/FBS, Честный знак и B06 не открываются как рабочие процессы.

Исходный synthetic fixture передан из B04 и до первого клика считается гипотезой, которую надо перечитать глазами:

- request `41823675-2b08-4714-97b6-8782486c4dda`, №`000007`, seller `B01 UX Seller 960724`, status `done`/`Оприходовано`;
- товар A: total `3`, Sorting `0`, cells `3`, available `3`;
- товар B: total `2`, Sorting `0`, cells `2`, available `2`;
- warehouse `FBS WB 1155120`, cell `A 1.1`, barcode `LOC-36F984B31C3D`;
- per-cell A/B balance в B04 через UI не читался.

Shared/foreign warehouses, cells, products и WB/external state не мутируются. В exact warehouse доказана только одна storage cell, поэтому реальное перемещение не выполняется: нет второй изолированной synthetic cell, а обратимость через тот же UI до начала действия не доказана. Background-сводка допустима как read-only расчёт журнала, если UI не затрагивает stock.

## Роли и физические задачи

| Роль | Физическая ситуация | Вопрос, на который система должна ответить | Нужный результат |
|---|---|---|---|
| Кладовщик | Стоит у товара/ячейки со сканером | Где лежит SKU и сколько можно взять? | SKU/barcode → склад → ячейка → on hand/reserved/available без ручного сведения экранов |
| Старший смены | Разбирает расхождение по полке | Почему остаток изменился? | Время, документ/причина, откуда/куда, delta, сотрудник и итоговый баланс |
| Инвентаризатор | Идёт по адресам с ТСД | Что считать, сколько ожидалось и как зафиксировать факт? | Задание/ячейка → scan SKU → факт → расхождение → безопасное подтверждение/recovery |
| Администратор FF | Настраивает адреса и контролирует остатки | Какие склады/ячейки существуют и чем заполнены? | Фильтр/поиск, occupancy, SKU/qty и безопасные row actions |

## Сквозные AS-IS задачи

### 1. Найти доступный остаток

Открыть `Каталог` → найти SKU/barcode/название → связать строку identity с колонками `На складе`, `В сортировке`, `В ячейках`, `Доступно` → при необходимости прокрутить таблицу по горизонтали. Проверяются поиск, seller filter, сортировки, zero/no-result, reload и one-glance на 1280/wide.

### 2. Найти физический адрес товара

Из строки товара попытаться открыть location breakdown → перейти в `Ячейки` → выбрать warehouse → найти cell → попытаться доказать SKU и количество в ней. Если перехода/связи/наполнения нет, это process gap, а не пропущенный сценарий.

### 3. Объяснить изменение остатка

Из товара попытаться открыть движение → открыть `/app/ops/movements` → найти exact SKU → определить время, причину, документ, откуда/куда и итог. Проверяются refresh, reload, row affordance, поиск/фильтр/сортировка/пагинация, raw terms и связь transfer-pair.

### 4. Инициировать и выполнить инвентаризацию

Открыть `Инвентаризация` → найти CTA/задание → выбрать warehouse/cell → scan product → внести факт → увидеть delta → подтвердить → reload/read-back. Placeholder adjudicated как наблюдаемый разрыв всего процесса; отсутствующие шаги получают `FAIL_PROCESS`, а не `NOT_RUN`.

### 5. Внутреннее перемещение как соседний recovery-path

Открыть `/app/ops/transfers` → оценить поля `откуда/куда/товар/количество`, scanner/keyboard path, warehouse identity и последствия. Реальная проводка разрешена только при двух exact synthetic storage cells того же склада и заранее доказанном обратном пути; текущий fixture этому условию не соответствует.

## Инвентарь экранов и действий

- `/app/ff/products`: loading/error, seller filter, search по SKU/name/vendor barcode, clear/no-result, сортировка name/quantity, горизонтальная таблица, exact A/B, row/keyboard affordance, barcode/ТЗ secondary actions, reload/back/wide, отсутствие pagination/column chooser/location/movement drill-down.
- `/app/catalog`: warehouses, exact warehouse, storage/system cells, select/reload, row/keyboard affordance, print dialog, отсутствие search/sort/pagination/occupancy/SKU/qty, отсутствие scanner lookup.
- `/app/ops/movements`: direct route discoverability, populated list, refresh, background summary, exact SKU/delta/type, raw terminology, missing timestamp/location/document/seller/actor/balance, row/keyboard affordance, search/filter/sort/pagination, reload/back/wide.
- `/app/ops/transfers`: direct route discoverability, source/destination/product/qty controls, flat cell names, disabled/validation states, scanner/keyboard path, consequence/confirm/recovery; no stock mutation without safe fixture.
- `/app/ff/inventory`: navigation, placeholder, reload/back/forward/wide, отсутствие create/count/scan/delta/confirm/history/recovery.

## Твёрдые правила verdict

1. `Доступно` не равно `На складе`; интерфейс обязан объяснять Sorting/reserved/packed и не заставлять оператора выводить формулу самостоятельно.
2. Адрес считается доказанным только когда product identity, warehouse, cell и quantity видны в одном связанном пути. Наличие cell code отдельно недостаточно.
3. Movement объясняет delta только если различимы time, type/reason, document, source/destination, actor и relation pair; raw enum не считается операторским объяснением.
4. Search/filter/sort оцениваются по видимому результату и recovery после clear/reload; отсутствие control фиксируется отдельно.
5. Scanner-first путь нужен для поиска товара, ячейки, transfer и count. Mouse-only dropdown не доказывает складскую пригодность.
6. Инвентаризация-placeholder является подтверждённым process gap по всем обязательным шагам, а не пустым экраном вне scope.
7. Любое stock-changing действие требует exact isolated source/destination, preview consequence, duplicate protection, reload/read-back и доказанный reverse path. Иначе mutation не выполняется.
8. Каждый сохранённый PNG лично открывается; runtime metrics и file dimensions фиксируются отдельно. Имя файла не доказывает viewport.

## Протокол измерения

Для четырёх типовых jobs считаются: clicks/taps, keyboard entries/Enter, scanner events, scroll gestures, attention shifts между товаром/экраном/мышью/клавиатурой/сканером и не объяснённые решения. Минимальный flow предлагается в существующих сущностях: один universal search/scan → одна строка с available и cell → drill-down движения/адреса → понятный count/transfer, без нового workflow engine и тотального redesign.

