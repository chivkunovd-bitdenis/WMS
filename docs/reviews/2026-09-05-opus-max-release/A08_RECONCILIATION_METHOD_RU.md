# WMS-375 / A08 — сверка преобразования поштучного выделения

Дата: 06.09.2026. Это методика исследования данных, а не исправление количеств.
Прочитаны миграция `20260905_0252_fbs_available_stock.py`, старый сервис
`fbs_stock_units_service.py` из `c0dfaecae5985ac7a0597dc2acf56901ee242fe4`,
старый `split_amounts`, арбитраж A08 и локальные сведения о резервных копиях.
Первоначально была подготовлена только методика. Затем оркестратор восстановил
выбранные таблицы в отдельную локальную базу для A08; результаты выполненного
сравнения приведены в конце. Продуктивная база и секреты не использовались,
этот исполнитель не выполнял SSH, внешних вызовов или миграций.

## Какой снимок нужен: первоначальный поиск

Нужен согласованный снимок непосредственно перед 0252, где сохранились
`products.fbs_units_mode`, `fbs_binding_stock_pools.allocated_at`, исходные
`pool.quantity` и `fbs_stock_pool_debits`. Восстановление такого снимка —
отдельная операция в изолированную локальную базу, без автозапуска приложения
и миграций; в рамках этой задачи не выполнялось.

В `docs/KANONICHESKIY_BACKLOG.md` в записи выпуска 05.09 зафиксирован кандидат:
`/opt/wms/.deploy-backups/ozon-20260905-4306fa7e/wms.dump`.
Это **прочитанная локальная запись о серверном дампе**, не свежая проверка его
наличия, контрольной суммы или ревизии. Локальная копия этого дампа не найдена
в просмотренных `.deploy-backups`, `scratchpad` и `~/wms-backups`.

Локально найден `/Users/deniscivkunov/wms-backups/wms-20260825-150000-before-sku-unique.dump`:
395800458 байт, файловая дата изменения 25.08.2026 18:07:24. Содержимое не
восстанавливалось. `scripts/deploy/rollback-sku-unique-20260825.sh` описывает его
как снимок ревизии `20260823_0100`. Он не восстанавливает состояние 05.09:
поля `fbs_units_mode` и `allocated_at` добавлены только миграцией 0251.

Существующий `scripts/deploy/probe-migrations.sh` создаёт/удаляет пробную базу
и запускает миграции; rollback-скрипт также умеет менять код и восстанавливать
базу. **Оба не являются готовым read-only сравнением A08 и здесь не запускались.**

## Две точные формулы

Старый расход пула:

```text
cutoff_old = allocated_at OR updated_at OR created_at
spent_old = SUM(debit.quantity_debited)
  по debit.pool_id = pool.id с JOIN orders по debit.order_id;
  orders.created_at >= cutoff_old;
  status != 'cancelled' ИЛИ существует ledger.shipment_movement_id IS NOT NULL.
available_old = max(0, pool.quantity - spent_old)
```

Миграция рассматривает **все пулы товара с `fbs_units_mode=true`**, без
фильтра `active/served/sync`. Для каждого из них:

```text
spent_0252 = COUNT(orders), только если allocated_at IS NOT NULL
  и binding.marketplace = 'wb' (именно это буквальное значение в миграции);
  совпадают tenant_id, seller_id, product_id, wb_warehouse_id;
  orders.created_at >= allocated_at;
  условие отмены/проведённой передачи то же.
Иначе spent_0252 = 0.
desired_0252 = max(0, pool.quantity - spent_0252)
converted_quantity = min(desired_0252, remaining_physical)
remaining_physical -= converted_quantity
```

Здесь используется **`orders.created_at`**, не `created_at_wb`, не время записи
debit. В COUNT миграции нет фильтра `orders.marketplace`; воспроизводя её,
нельзя незаметно добавить его или заменить COUNT суммой количества позиций.
Старый расчёт привязан к `pool.id`, а новый COUNT — к перечисленным полям заказа.

## Запрос первого сравнения: только чтение

Запускать после проверки схемы **на восстановленном снимке до 0252**. Запрос
показывает различие расхода и доступности **до физического ограничителя**.
Это список кандидатов, а не число испорченных миграцией строк. `BEGIN ... READ
ONLY` запрещает запись в таблицы в этой транзакции; `ROLLBACK` завершает её.

```sql
BEGIN TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY;
SET LOCAL statement_timeout = '60s';

SELECT version_num FROM alembic_version;
SELECT table_name, column_name
FROM information_schema.columns
WHERE table_schema = 'public'
  AND ((table_name = 'fbs_binding_stock_pools'
        AND column_name IN ('allocated_at', 'quantity', 'updated_at', 'created_at'))
    OR (table_name = 'products' AND column_name = 'fbs_units_mode')
    OR (table_name = 'fbs_stock_pool_debits'
        AND column_name IN ('pool_id', 'order_id', 'quantity_debited')))
ORDER BY table_name, column_name;

WITH eligible AS (
  SELECT pool.id, pool.tenant_id, pool.binding_id, pool.product_id,
         pool.quantity, pool.allocated_at, pool.updated_at, pool.created_at,
         b.seller_id, b.marketplace, b.wms_warehouse_id, b.wb_warehouse_id,
         COALESCE(pool.allocated_at, pool.updated_at, pool.created_at) AS cutoff_old,
         COUNT(*) OVER (
           PARTITION BY pool.product_id, b.wms_warehouse_id, b.wb_warehouse_id
         ) AS migration_sort_peers
  FROM fbs_binding_stock_pools pool
  JOIN products p ON p.id = pool.product_id
  JOIN fbs_warehouse_bindings b ON b.id = pool.binding_id
  WHERE p.fbs_units_mode = true
), compared AS (
  SELECT e.*,
    COALESCE((
      SELECT SUM(d.quantity_debited)
      FROM fbs_stock_pool_debits d
      JOIN fbs_orders o ON o.id = d.order_id
      WHERE d.pool_id = e.id AND o.created_at >= e.cutoff_old
        AND (o.status != 'cancelled' OR EXISTS (
          SELECT 1 FROM fbs_shipment_reversal_ledger l
          WHERE l.fbs_order_id = o.id AND l.shipment_movement_id IS NOT NULL
        ))
    ), 0) AS spent_old,
    CASE WHEN e.allocated_at IS NOT NULL AND e.marketplace = 'wb' THEN (
      SELECT COUNT(*) FROM fbs_orders o
      WHERE o.tenant_id = e.tenant_id AND o.seller_id = e.seller_id
        AND o.product_id = e.product_id AND o.wb_warehouse_id = e.wb_warehouse_id
        AND o.created_at >= e.allocated_at
        AND (o.status != 'cancelled' OR EXISTS (
          SELECT 1 FROM fbs_shipment_reversal_ledger l
          WHERE l.fbs_order_id = o.id AND l.shipment_movement_id IS NOT NULL
        ))
    ) ELSE 0 END AS spent_0252
  FROM eligible e
), remainders AS (
  SELECT c.*,
         GREATEST(0, quantity - spent_old) AS available_old,
         GREATEST(0, quantity - spent_0252) AS desired_0252
  FROM compared c
)
SELECT *, desired_0252 - available_old AS delta_before_physical_cap
FROM remainders
WHERE spent_old != spent_0252 OR allocated_at IS NULL OR migration_sort_peers > 1
ORDER BY product_id, wms_warehouse_id, wb_warehouse_id, id;

ROLLBACK;
```

Для полной сводки надо убрать последний WHERE: физический ограничитель может
изменить пул и при одинаковом `spent`. Отдельно сохранять снимок результатов
с идентификатором/контрольной суммой исходного дампа; не публиковать данные
селлеров или содержимое таблиц учётных данных в документ ревью.

## Как получить точное значение после физического ограничителя

На том же снимке для каждой пары `(product_id, wms_warehouse_id)` рассчитать
начальное `max(0, physical - reserved)` **буквально по SELECT миграции 0252**:

| Слагаемое | Нужные таблицы и фильтр |
|---|---|
| Физический остаток | `inventory_balances.quantity`, связь `storage_location_id → storage_locations.warehouse_id`, tenant/product. |
| Резервы заказов ФБС | Суммы `fbs_order_reservations.quantity` и `fbs_order_product_reservations.quantity`, tenant/product/warehouse. |
| Именованные направления | Сумма `stock_directions.quantity` по tenant/product. Миграция вычитает её в каждой физической группе; не менять это в воспроизведении. |
| Обычные отгрузки | `inventory_reservations → outbound_shipment_lines → outbound_shipment_requests`; статусы `draft/submitted`; склад из location либо warehouse_id при NULL location. |
| Отгрузки на МП | `marketplace_unload_reservations → marketplace_unload_lines → marketplace_unload_requests`; статусы `submitted/confirmed/collecting`, tenant/product/warehouse. |

Обработать все пулы по `ORDER BY product_id, wms_warehouse_id, wb_warehouse_id`
и применять `min(desired_0252, remaining)` последовательно. При одинаковом
ключе сортировки миграция не задаёт порядка `marketplace` или `pool.id`:
`migration_sort_peers > 1` отмечает эту границу. При недостаточном общем
остатке нельзя назвать точное распределение внутри такой группы без результата
самого применения/дополнительного доказательства. Добавленный в запросе `id`
лишь стабилизирует показ и **не доказывает порядок исполнения миграции**.

Раздельно вывести: старую доступность по журналу, новый расчёт до ограничителя,
результат ограничителя, разницу и причину. Старая публикация также ограничивала
сумму физически свободным остатком в `split_amounts`: разница сырых квот не
равна автоматически разнице внешнего предложения. Оценка внешнего ущерба
требует подтверждённого запроса/ответа маркетплейса, не только арифметики базы.

Текущее `pool.quantity` уже мог изменить оператор, резерв, отмена или
инвентаризация. Оно не заменяет снимок сразу после применения. Не выполнять
UPDATE по полученной дельте, не переписывать уже применённую миграцию и не
запускать downgrade: он не восстанавливает исходные значения.

## Выполненная сверка на локальной копии, 06.09.2026

Оркестратор отдельно проверил серверный кандидат: размер 401283980 байт,
время 05.09.2026 18:02 UTC, сохранённая ревизия `20260904_0251`. Он извлёк
только 18 таблиц для сравнения и **специально для этой задачи создал локальную
базу `wms375_a08_pre0252`**. Таблицы секретов, доступов и пользователей в неё
не включались. Это не подключение к production и не изменение production.

В рамках продолжения я непосредственно прочитал локальную ревизию, список
18 таблиц, схему пулов/привязок и журнал восстановления. Ошибок `ERROR/FATAL`
в журнале `/tmp/wms375-a08-restore.log` не найдено. Выбранный SQL восстановления
`/tmp/wms375-a08-snapshot.sql` имеет размер 17558908 байт; его данные в Git
не включаются.

Воспроизводимый расчёт: [a08_reconcile_snapshot.py](a08_reconcile_snapshot.py).
Он вызывает только `psql` через локальный Unix socket `/tmp`, с явно заданными
локальными базой и пользователем. Вся выборка выполняется в одной транзакции
`REPEATABLE READ READ ONLY`; проверены `transaction_read_only=on` и ревизия
0251. Числа вычисляются в памяти Python, таблицы не меняются. Импорт приложения,
автозапуск миграций и внешние вызовы отсутствуют. Команда воспроизведения:

```sh
python3 docs/reviews/2026-09-05-opus-max-release/a08_reconcile_snapshot.py
```

В выборке **82 товара, 206 пулов**. Пустых `allocated_at` — **0**; совпадений
полного ключа сортировки миграции — **0**. Проверки несовпадения tenant у
остатка/резерва и связанной ячейки также дали ноль. Поэтому на этом снимке
не возникло перечисленных выше неоднозначностей воспроизведения.

| Сравнение на одном исходном снимке | Различающиеся пулы | Суммы, шт. |
|---|---:|---:|
| Старый расход по журналу против COUNT миграции, до физического ограничения | 1, уменьшение на 1 | 2424 → 2423 |
| Оба расхода с **одинаковым физическим ограничителем и порядком 0252** | **0** | **2423 → 2423** |
| Буквальная публикация baseline через active/served и старый порядок привязок против количества после 0252 | **0 из 206** | **2423 → 2423** |
| Исходное сохранённое `pool.quantity` против результата 0252 | 80, уменьшение на 233 | 2656 → 2423 |

Во втором сравнении заменяется только источник расхода: старый SUM либо новый
COUNT; физические резервы, общий оставшийся остаток и очередь пулов одинаковы.
В третьем дополнительно воспроизведена область старого `publish_amounts_for_binding`:
активные обслуживаемые привязки селлера, сортировка по числовому ID, свободный
остаток физического склада текущей привязки и выключатель товара. Старый код
не сужал список привязок до этого физического склада; скрипт сохраняет это
поведение. Все 206 выбранных пулов на этом снимке попали в сравнение публикации.

**На проверенном предмиграционном снимке различие SUM/COUNT не изменило итог
ни одного пула после физического ограничителя.** Сырое расхождение на одну
единицу этим ограничителем поглощается. Уменьшение сохранённых значений
на 233 единицы нельзя называть новым ущербом A08: прежняя вычисленная
публикуемая доступность уже составляла те же 2423 единицы.

Это арифметическое сравнение одного снимка. Оно не устанавливает ответы
маркетплейса и не сверяет состояние сразу после применения с текущей базой.
Общая ошибка формулы, обнаруженная арбитром, этим не опровергается: на других
данных она остаётся достижимой, в частности при NULL `allocated_at`.
Оснований для автоматической компенсации количеств этот результат не даёт.
Компенсация не выполнялась.
