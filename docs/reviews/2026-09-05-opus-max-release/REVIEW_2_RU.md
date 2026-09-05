# WMS-374 — независимое ревью 2

Модель: `claude-opus-5`, запрошенный effort: `max`.
Целевой production: `ed72c8888a6e383f5101e0c1bd96d3793810e4fc`.

Ниже полный финальный ответ CLI без редакторских правок.

---

Проверки закончил. Ниже полный отчёт.

---

# WMS-374. Второе независимое перекрёстное ревью релиза

**Модель:** Claude Opus 5 Max (CLI). **Граница диффа:** `c0dfaeca` → `ed72c888`, 146 коммитов, 263 файла, +29 368/−14 782 (проверено `git rev-list --count` и `git diff --shortstat`). Рабочее дерево по `backend/`, `frontend/`, `scripts/`, `.github/` совпадает с целевым SHA байт в байт (`git diff ed72c888 -- …` пуст), поэтому чтение файлов с диска — это чтение замороженного релиза.

**Независимость соблюдена.** Ни один артефакт первого ревью не открывался: ни `REVIEW_1_RU.md`, ни `REVIEW_1_HISTORY.jsonl`, ни `REVIEW_1_METADATA.json`, ни брифы арбитра. Выводы ниже получены чтением кода, базовой версии через `git show c0dfaeca:…` и существующих тестов.

**Браузером не пользовался.** Ни один экран руками не проверялся, живых вызовов к WB и Ozon не делал, в базу не ходил. Всё, что ниже, — статический разбор кода; утверждать «на бою работает» я не имею права и не утверждаю.

---

## Вердикт по риску текущего прода

**Продакшн работоспособен по вайлдберрисовской части и по передаче поставок, но по публикации остатков в Ozon содержит дефект первого класса тяжести — тот самый тип аварии, который описан во втором главном правиле проекта (случай с 335 штуками).**

Коротко суть: путь публикации остатков в Ozon отправляет в кабинет `stock: 0` **на каждый товар продавца, у которого есть активная связка с карточкой Ozon, но не настроено правило ФБС**. Вайлдберрисовский путь в такой ситуации товар не трогает вообще — это записано в коде явным комментарием. Озоновский путь этого правила не соблюдает. Срабатывает автоматически: каждые пять минут по расписанию и дополнительно после каждого движения по складу.

Ущерб реализуется ровно тогда, когда у продавца есть обслуживаемый Ozon-склад и импортированный каталог Ozon. Есть ли такой продавец на бою — я не знаю и проверить не мог (в базу не ходил); запрос для проверки приведён в разделе «Что требует живой проверки». Если такой продавец есть, его ненастроенные товары уже показываются на Ozon с нулём.

Три ранее найденные проблемы (перепубликация выше физического остатка, зависшая передача после рестарта, невозможность повторить `ship_failed`) я перепроверил независимо — **все три действительно закрыты**, подробности в последнем разделе. Починка beat-расписания (именованная функция вместо lambda) тоже на месте.

---

## Находки

### P0-1. Ozon обнуляет остаток каждого товара, у которого есть связка с карточкой, но нет правила ФБС

**Где:** `backend/app/services/ozon_fbs_sync_service.py:354–396`, решающая строка — 385.

**Что происходит.** Функция `sync_ozon_stocks` выбирает **все** товары продавца и приклеивает к ним связку с карточкой Ozon левым присоединением:

```python
select(Product, ProductMarketplaceLink)
  .outerjoin(ProductMarketplaceLink, and_(… marketplace == "ozon", is_active))
  .where(Product.tenant_id == tenant_id, Product.seller_id == seller_id)   # 368
```

Дальше она просит посчитать, сколько публиковать, и берёт число так:

```python
amounts = await publish_amounts_for_binding(session, binding, products)   # 376
…
"stock": amounts.get(product.id, 0),                                      # 385
```

`amounts` — это словарь, и он **намеренно не содержит товаров без правила**. Так написано в самом расчёте, `backend/app/services/fbs_stock_rule_service.py:713–724`:

> «Товар без правила в ответ не попадает вовсе. Если правило настроено, но публикация выключена, в ответе остаётся осознанный ноль».

```python
publishable = [p for p in products if p.fbs_percent is not None or p.fbs_units_mode]  # 720
```

То есть отсутствие ключа означает «мы про этот товар ничего не решали», а `.get(product.id, 0)` превращает это молчание в приказ «поставь ноль».

**Вайлдберрисовский путь делает ровно наоборот** — `backend/app/services/fbs_stock_sync_service.py:259–262`:

```python
if product.id not in publish_quantities:
    # Нет рассчитанного количества — публикация выключена либо доля не
    # настроена. Товар не трогаем и ноль в WB не отправляем.
    continue
```

Там же, на 629–646, стоит «сторож нуля» (`ERROR_UNSAFE_ZERO_BLOCKED`): ноль без явного признака «это осознанный ноль» до WB не доходит вовсе. На озоновском пути такого сторожа нет; счётчик `result.products_zeroed` на строке 399 нули считает, но ни на что не влияет.

**Это новый регресс, а не старый дефект.** В базовой версии (`git show c0dfaeca:backend/app/services/ozon_fbs_sync_service.py`) цикл шёл не по товарам продавца, а по строкам пула именно этой привязки — `select(FbsBindingStockPool, ProductMarketplaceLink).where(FbsBindingStockPool.binding_id == binding.id)` — и публиковал `"stock": max(int(pool.quantity), 0)`. Товар без выделенного пула в выборку не попадал физически, обнулить его было нечем.

**Сценарий с числами.** У продавца импортирован каталог Ozon: `import_ozon_product_cards` (`ozon_product_import_service.py:494–606`) тянет все карточки и на каждую заводит `ProductMarketplaceLink` (строка 462). Пусть карточек 500, а правило ФБС оператор настроил у 20 товаров. Ozon-склад обслуживаемый (`served=True`, `stock_sync_enabled=True` — их ставит вместе `configure_seller_warehouse`, `fbs_warehouse_binding_service.py:421–423`). Тогда в кабинет уезжает пакет из 500 строк, где 20 несут реальные числа, а **480 несут ноль**.

**Путь вызова целиком, оба входа:**

1. По расписанию: `celery_app.py:48–51` (`fbs-stock-reconcile`, период `settings.fbs_stock_reconcile_interval_sec`, по умолчанию 300 секунд — `settings.py:216–227`) → `reconcile_fbs_stocks_all_sellers` (`fbs_autopoll_service.py:755–829`) → `sync_marketplace_stocks_for_target` (там же, 500–521) → `sync_ozon_stocks`.
2. По событию: любое движение по складу зовёт `schedule_seller_stock_publish` → после коммита `publish_seller_stocks_now` (`fbs_stock_publish_service.py:33–80`) → тот же `sync_marketplace_stocks_for_target` по всем площадкам продавца.

Цели опроса для Ozon берутся только по наличию действующего аккаунта (`fbs_autopoll_service.py:142–153`), никакой дополнительной защиты между расписанием и обнулением нет.

**Последствие для оператора, товара и денег.** Товары перестают предлагаться покупателям на Ozon, причём молча: экран синхронизации покажет привязку в состоянии «ошибка» (см. P2-3), но не скажет, что кто-то обнулил четыреста восемьдесят карточек. Восстановление — только вручную, настройкой правила на каждый товар.

**Какое принятое требование нарушено.** Правило «в кабинет уезжает `min(что задал оператор, свободный остаток)`»: у товара без правила оператор не задавал ничего, и трогать его нельзя ни в какую сторону. Плюс прямое указание владельца из брифа — искать не только перепубликацию, но и необоснованное обнуление.

**Минимальное исправление, не меняющее принятых правил.** Одна строка, зеркально вайлдберрисовской: перед формированием строки остатка пропускать товар, которого нет в `amounts`.

```python
for product, link in rows:
    if product.id not in amounts:
        continue
```

Ни новых сущностей, ни флагов, ни таблиц. Как вариант — сузить саму выборку до `publishable`, но проверка по `amounts` надёжнее: она опирается на тот же единственный источник числа.

**Чем закрыть.** Тест на продавца с двумя товарами: у первого `fbs_percent = 50`, у второго только `ProductMarketplaceLink` без правила. Ожидаем `transport.published_stocks` ровно из одной строки. Существующий тест `backend/tests/test_fbs_ozon_lane.py:484–587` дыру увидеть не может: в нём заведён ровно один товар, и он настроен (`product.fbs_percent = 50`, строка 562), поэтому `products_targeted == 1` выполняется и при правильном, и при сломанном поведении.

---

### P1-2. Одна отвергнутая строка отменяет публикацию всех следующих сотен

**Где:** `backend/app/services/ozon_marketplace_transport.py:562–612`.

Публикация режется на пакеты по сто строк (`STOCK_BATCH_SIZE = 100`), и любая неподтверждённая строка внутри пакета поднимает исключение:

```python
for start in range(0, len(items), STOCK_BATCH_SIZE):     # 580
    …
    confirmed, failures = _reconcile_stock_rows(batch, rows)   # 599
    if failures:
        raise MarketplaceProviderError(… code="ozon_stock_rejected")   # 602
```

Цикл прерывается, и **пакеты со второго по последний не отправляются вообще**. Неотвеченная строка считается провалом (`_reconcile_stock_rows`, 251–308: молчание Ozon по строке — это `OZON_ROW_MISSING`), а поводов для молчания у Ozon хватает — например, ограничение на частоту изменения остатка по одной карточке, о котором фронт уже честно предупреждает в подписи к ошибке `ozon_stock_rejected` (`frontend/src/screens/v2/FfFbsStockSyncScreen.tsx`).

**Само по себе это защитное поведение и оно осмысленно** — приписывать себе неподтверждённый успех нельзя. Проблема во взаимодействии с P0-1: пока в пакет попадали только настроенные товары, их было десятки и они помещались в первую сотню. После расширения выборки до всего каталога настроенные товары могут оказаться во втором, третьем, пятом пакете, а сорвать публикацию способна любая из четырёхсот ненужных нулевых строк в первом.

**Регресс:** новый по последствиям, потому что размер пакета вырос из-за P0-1. Сам транспорт в релизе появился целиком (файл новый, 648 строк), сравнивать с базовой линией нечего.

**Последствие:** товар, у которого правило настроено, месяцами едет со старым числом в кабинете, а оператор видит «ошибка» и не может понять, какая именно строка виновата.

**Исправление:** сначала закрыть P0-1 — этого достаточно, чтобы пакет вернулся к прежнему размеру. Отдельно менять политику «первая ошибка — отказ» я не предлагаю: она защищает от ложного «опубликовано».

**Чем закрыть:** тест на 150 строк, где неподтверждённой оказывается строка из первой сотни; проверить, что вызовов `POST /v2/products/stocks` было ровно один, а не два.

---

### P2-3. Привязка Ozon навсегда красится в «ошибка», даже когда Ozon подтвердил всё

**Где:** `backend/app/services/ozon_fbs_sync_service.py:379–382, 400–404, 431–433`.

Каждый товар продавца без активной связки с карточкой Ozon увеличивает счётчик `missing_links`:

```python
if link is None or (not link.external_offer_id and not link.external_sku):
    missing_links += 1
    continue
```

и дальше любой ненулевой `missing_links` жёстко ставит `binding.last_sync_status = "error"`, `last_error_code = "product_mapping_missing"`, а ветка успеха закрыта условием `if not missing_links:` (431). У продавца, торгующего не только на Ozon (а это норма), товаров без озоновской связки всегда больше нуля, поэтому статус «ошибка» становится вечным.

**Последствие:** экран синхронизации показывает «Не найден товар для выгрузки» постоянно, и настоящая ошибка — истёкший ключ, отвергнутый пакет — в этом шуме не видна. Оператор перестаёт смотреть на индикатор, который всегда красный.

**Регресс:** новый. В базовой версии выборка шла по строкам пула, товаров без связки в ней не было по построению.

**Исправление:** считать `missing_links` только по товарам, у которых есть настроенное правило (то есть после фикса P0-1 — только по тем, что остались в `amounts`). Отсутствие связки у товара, который мы и не собирались публиковать, — не ошибка синхронизации.

**Чем закрыть:** тест «продавец с одним настроенным Ozon-товаром и одним товаром без связки → `last_sync_status == "confirmed"`».

---

### P2-4. На озоновском пути не проверяется признак «обслуживаем склад»

**Где:** `backend/app/services/ozon_fbs_sync_service.py:322–338` против `backend/app/services/fbs_stock_rule_service.py:723`.

Выборка привязок в `sync_ozon_stocks` фильтрует по `is_active` и `stock_sync_enabled`, но **не по `served`**. Вайлдберрисовский путь проверяет признак явно и выходит сразу: `fbs_stock_sync_service.py:590` — `if not binding.is_active or not binding.stock_sync_enabled or not binding.served: return FbsStockSyncResult()`.

Если у Ozon-привязки окажется `served=False` при `stock_sync_enabled=True`, то `publish_amounts_for_binding` вернёт пустой словарь (строка 723: `if not publishable or not binding.served: return {}`), а `amounts.get(product.id, 0)` превратит пустоту в **ноль по всему каталогу разом**.

**Достижимость.** Через экран — нет: `configure_seller_warehouse` двигает оба признака вместе (`fbs_warehouse_binding_service.py:421–423`), а фронт на второй ручке площадку не передаёт вовсе (`frontend/src/screens/v2/fbsApi.ts:1332–1348`, тело запроса — только `wms_warehouse_id` и `stock_sync_enabled`). Через API — да: `upsert_binding` (`fbs_warehouse_binding_service.py:289–301`) присваивает `existing.stock_sync_enabled` и **не трогает `existing.served`**, а ручка `PUT /{seller}/warehouse-bindings/{wb_id}` принимает `marketplace` в теле (`backend/app/api/fbs_sellers.py:382–391`).

Поэтому это не P0, а взведённая мина: сегодня к ней ведёт только прямой вызов API, завтра — первая же кнопка на фронте, которая начнёт передавать площадку.

**Исправление:** добавить `FbsWarehouseBinding.served.is_(True)` в условие выборки на 326–332, как на вайлдберрисовской стороне. После фикса P0-1 последствие исчезает само, но проверка всё равно должна стоять симметрично.

---

### P2-5. Совпадение номеров складов WB и Ozon ловится только при сохранении правила

**Где:** `backend/app/services/fbs_stock_rule_service.py:486–504` (проверка) против `269–292` (публикация).

Правило в режиме штук хранится словарём «номер склада → сколько штук», и номер — единственное, чем правило различает склады: `split_amounts` берёт `rule.units_by_warehouse.get(int(binding.wb_warehouse_id), 0)` (строка 281). Список привязок продавца намеренно не фильтруется по площадке. Поэтому при сохранении правила стоит проверка на входе, и её комментарий формулирует опасность точно: «На совпадении одно и то же число легло бы сразу на две площадки, и доля Wildberries молча уехала бы на Ozon».

Но проверка стоит **только** в `set_rule_for_products`. Заведение склада идёт другой дорогой — `configure_seller_warehouse` (`fbs_warehouse_binding_service.py:343–431`), и там такой проверки нет. Значит порядок «сначала правило, потом новый Ozon-склад с совпавшим номером» проходит мимо сторожа, и на публикации число оператора применится дважды.

**Последствие ограничено:** `split_amounts` всё равно режет сумму общим свободным остатком (`amount = min(share, remaining)`, 289), так что физического перевыпуска не будет. Но оператор задал десять штук на склад, а в кабинеты уехало двадцать на два разных, и он об этом не узнает.

**Регресс:** сама механика единого списка привязок в релизе новая, значит и дыра новая.

**Исправление:** та же проверка на входе в `configure_seller_warehouse` — не давать завести склад с номером, который уже занят у этого продавца на другой площадке. Ограничение на вводе, ровно как требует второе главное правило.

---

### P2-6. Разовая миграция `0252` считает израсходованное не той формулой, что снятый ею код

**Где:** `backend/alembic/versions/20260905_0252_fbs_available_stock.py:72–88`.

Миграция переводит старое «выделено оператором» в новое «доступно», и расход считает так:

```python
if row["allocated_at"] is not None and row["marketplace"] == "wb":
    spent = COUNT(*) по fbs_orders (продавец, товар, склад WB, created_at >= allocated_at, …)
available = min(max(0, int(row["quantity"]) - spent), remaining[key])
```

Снятый ею рантайм считал иначе — `git show c0dfaeca:backend/app/services/fbs_stock_units_service.py`, функция `_consumed_stmt`: `SUM(FbsStockPoolDebit.quantity_debited)` с присоединением журнала списаний по `pool_id`. Отличий два, и оба доказуемы по коду:

1. Миграция считает **все** заказы, подходящие по продавцу, товару и номеру склада, а не только те, по которым в журнале была строка расхода этого пула. Заказ, до которого журнал не добрался, теперь тоже съедает квоту.
2. У пула с пустым `allocated_at` миграция ставит расход в ноль, тогда как старый код в этом случае откатывался к `updated_at`/`created_at` (`_allocated_since`) — специально, потому что первые пулы заливались SQL-ом до появления экрана.

**Насколько это опасно.** Обе стороны ограничены сверху вычисленным свободным физическим остатком (`remaining[key] = max(0, physical - reserved)`, строка 71), поэтому завысить публикацию миграция не может ни при каком раскладе. Занизить — может: доступность у части товаров могла оказаться меньше, чем оператор видел до релиза, и никакого сигнала об этом ему не показали.

**Статус:** миграции на боевой базе накатаны до `0254`, то есть **это уже произошло**. Канонический бэклог фиксирует (`docs/KANONICHESKIY_BACKLOG.md:466–469`), что перенос обкатывался только на изолированной базе.

**Что делать:** переписывать миграцию поздно и не нужно. Нужна сверка на бою — запрос приведён в разделе «Что требует живой проверки»; расхождения оператор поправляет тем же экраном, которым задаёт число.

---

### P2-7. Публикация по событию идёт без блокировки, а общая блокировка передачи видна оператору как «уже выполняется»

**Где:** `backend/app/services/fbs_stock_publish_service.py:33–80` против `backend/app/services/fbs_autopoll_service.py:768–785`.

Ночной и пятиминутный проходы берут сеансовую блокировку в PostgreSQL — `marketplace_seller_lock(session, target.seller_id, target.marketplace)`, — и, не взяв её, пропускают продавца. А публикация по событию (`publish_seller_stocks_now`) вызывает ровно ту же `sync_marketplace_stocks_for_target` **без всякой блокировки**. Вайлдберрисовская ветка защищена собственной арендой на привязку (`_try_acquire_lease`, поле `lease_until`), у озоновской нет ни аренды, ни блокировки.

Практический эффект: сорок движений по складу за минуту дают сорок параллельных публикаций одному продавцу в Ozon, и в кабинет по одной карточке прилетает залп изменений — при живом ограничении Ozon на частоту это гарантированный `ozon_stock_rejected`, а с ним и P1-2.

Вторая сторона той же медали: ключ блокировки — пара (продавец, площадка), и его же берёт передача поставки в Ozon (`fbs_shipment_service._deliver_ozon_supply`, 1845–2155). Значит идущая в этот момент пятиминутная сверка остатков может вернуть оператору 503 «Передача в Ozon уже выполняется», хотя никакой передачи не идёт. Это не блокер навигации (правило про рабочее пространство WB FBS не нарушено), но текст ошибки вводит в заблуждение.

**Исправление:** брать ту же `marketplace_seller_lock` в `publish_seller_stocks_now` и, не взяв её, тихо выходить — сверка через пять минут всё равно догонит. Никаких новых сущностей: механизм уже есть и уже используется рядом.

---

## Известные ограничения и бэклог — не дефекты

Перечисляю, чтобы отделить от находок:

- **WMS-352** — автоматический фильтр импорта отправлений: продуктовое ограничение, чинить сейчас не надо (побочные эффекты я смотрел, отдельных находок нет).
- **WMS-369, WMS-371, WMS-372** — записаны в бэклог и намеренно не исправлены.
- **WMS-010, 011, 012, 013, 021, 025** — частичные/открытые.
- **`label_template_enabled = False`** на бою — сознательное решение.
- **Окно отсечки ±30 дней** — намеренное.
- **`set-postings` у Ozon не вызывается** — намеренно.
- **Доверительная приёмка, `containers_count`, ярлыки грузомест, Ozon на ТСД** — вне объёма.
- **`FbsShipmentReversalLedger`** — не журнал-сущность, а рецепт списания и ключ идемпотентности (`shipment_movement_id`); удалять из-за названия нельзя, и я не предлагаю.
- **Уменьшение `FbsBindingStockPool.quantity` на приход заказа** (`inventory_service.py:224–225`) — я едва не записал это в нарушение правила «число оператора не уменьшается никогда», но таблица в WMS-060 (`docs/KANONICHESKIY_BACKLOG.md:562–580`) описывает это поведение как принятое: 200 → заказ → 199, отмена до передачи → 200. Не дефект.
- **ФБО не вычитает резервы ФБС-заказов в процентном режиме** (`marketplace_unload_service.py:475–487`, `unit_reserve = reserved_fbs if product.fbs_units_mode else 0`) — проверил по базовой линии: там в этой ветке `reserved_fbs` не вычитался **вообще**, а `allocated_fbs` не существовал. Релиз строго консервативнее прежнего. Не регресс.

---

## Конфликты требований

Один, и он существенный для понимания P0-1.

С одной стороны — расчёт публикации, `backend/app/services/fbs_stock_rule_service.py:716–718`:

> «Товар без правила в ответ не попадает вовсе. Если правило настроено, но публикация выключена, в ответе остаётся осознанный ноль: WB не должен хранить последнее положительное значение после выключения товара.»

И вайлдберрисовский потребитель, `backend/app/services/fbs_stock_sync_service.py:260–262`:

> «Нет рассчитанного количества — публикация выключена либо доля не настроена. Товар не трогаем и ноль в WB не отправляем.»

С другой стороны — озоновский потребитель того же расчёта, `backend/app/services/ozon_fbs_sync_service.py:385`:

```python
"stock": amounts.get(product.id, 0),
```

Два потребителя одного контракта читают отсутствие ключа противоположным образом: WB — как «не трогать», Ozon — как «обнулить». Правильная сторона — вайлдберрисовская: так написан контракт в самом расчёте, и так требует правило про необоснованное обнуление. Это не вопрос вкуса, а расхождение в трактовке одного и того же значения, и оно порождает P0-1.

---

## Что покрыто этим ревью

**Публикация остатков — прочитано целиком:** `fbs_stock_rule_service.py` (правило, разбиение, `set_rule_for_products` с блокировкой товара и проверками на вводе, `publish_amounts_for_binding`), `fbs_stock_availability_service.py` (разложение на три числа, резервы, выделенное), `fbs_stock_sync_service.py` (аренда, сторож нуля, явный ноль), `ozon_fbs_sync_service.py` (публикация, импорт отправлений, статусы, требования маркировки), `ozon_marketplace_transport.py` (пакеты, сверка построчно, идентификаторы), `fbs_stock_publish_service.py`, `fbs_autopoll_service.py` (цели опроса, сверка, блокировка), `fbs_warehouse_binding_service.py`, `api/fbs_sellers.py`, `celery_app.py`, `core/settings.py` в части интервалов, миграция `0252`, базовые версии всего перечисленного через `git show`.

**Передачи и повторы — прочитано:** `fbs_shipment_service._deliver_ozon_supply` / `_deliver_ozon_supply_locked` / `_fail_ozon_deliver_operation` / `_finish_ozon_delivery` / `_write_off_delivered_orders_once`, `marketplace_seller_lock_service.py`, `ozon_box_assembly_service.py` (восстановление после `ship_failed`), `ozon_fbs_process_service._apply_posting_readback`, `fbs_ozon_packaging_service.prepare_shipment_sources` и `write_off_order`.

**Внутренняя доступность и резервы — прочитано:** `inventory_service.update_fbs_order_reservation`, `lock_stock_product`, `_order_stock_pool`, `_deduct_inventory_from_fbs`, `marketplace_unload_service` в части доступности, `wb_marketplace_orders_service._try_reserve_order` / `_release_reservation` (и их базовые версии), `fbs_stock_availability_service` целиком.

**Границы и контракты — прочитано:** `marketplace_scope.py`, `ozon_product_import_service.import_ozon_product_cards`, `product_merge_service.py`, `ozon_fbs_marking_gate_service.py`, `fbs_order_import_scope_service.py`, `models/fbs_warehouse_binding.py`.

**Деньги и фон — прочитано выборочно:** `storage_daily_charge_service.py` (идемпотентность суток, добор пропусков, доначисление отдельной строкой), `tasks/billing_tasks.py`, расписание beat.

**Тесты — прочитаны:** `test_fbs_ozon_lane.py:484–690`, `test_ozon_box_assembly.py:352–377`, `test_fbs_stock_rule_service.py:1079–1100`. Полный набор не запускал, как и требовал бриф.

**Что я не открывал вовсе** (перечисляю честно, там могут быть дефекты, которых я не искал): `billing_invoice_v2_service.py`, `billing_ledger_service.py`, `billing_seller_report_service.py` (624 строки изменений), `billing_tariff_matrix_service.py`, `storage_statement_service.py`, `reporting_service.py`, `inventory_count_service.py` (279 строк) и `api/inventory_counts.py`, `inventory_movement_report_service.py`, `operation_fact_service.py`, `print_template_service.py`, `fbs_print_asset_service.py`, `fbs_print_asset_storage.py`, `fbs_kiz_service.py`, `fbs_marking_service.py`, `api/marking_codes.py`, `api/storage.py`, `api/reports.py`, `fbs_order_history_service.py`, `fbs_packing_box_service.py`, `fbs_picking_service.py`, `fbs_workspace_service.py`, `fbs_worklist_service.py`, `fbs_supply_service.py`, `fbs_supply_reconcile_service.py`, `fbs_shipment_pvz_service.py`, `ozon_return_service.py`, `catalog_service.py`, `scan_resolver_service.py`, `seller_wb_catalog_service.py`, `inbound_intake_service.py`, `warehouse_map_service.py`, `docker-compose.prod.yml`, `.github/workflows/ci.yml`, а также большая часть фронта, кроме экранов остатков и каталога.

---

## Что требует живой проверки

Я не ходил в базу и не открывал браузер, поэтому масштаб P0-1 и последствия миграции `0252` может подтвердить только запрос к боевым данным.

**1. Есть ли уже пострадавшие от P0-1** — сколько товаров уедет с нулём при ближайшей сверке:

```sql
SELECT b.seller_id, b.external_warehouse_id, COUNT(*) AS zeroed_products
FROM fbs_warehouse_bindings b
JOIN product_marketplace_links l
  ON l.tenant_id = b.tenant_id AND l.seller_id = b.seller_id
 AND l.marketplace = 'ozon' AND l.is_active
JOIN products p ON p.id = l.product_id
WHERE b.marketplace = 'ozon' AND b.is_active AND b.stock_sync_enabled
  AND p.fbs_percent IS NULL AND p.fbs_units_mode IS NOT TRUE
GROUP BY 1, 2;
```

Ноль в ответе означает, что мина взведена, но ещё не сработала. Любое положительное число — уже сработала.

**2. Последствия миграции `0252`** — у каких пулов доступность стала нулём:

```sql
SELECT b.seller_id, b.marketplace, pool.product_id, pool.quantity
FROM fbs_binding_stock_pools pool
JOIN fbs_warehouse_bindings b ON b.id = pool.binding_id
JOIN products p ON p.id = pool.product_id
WHERE p.fbs_units_mode AND pool.quantity = 0;
```

Сверить с тем, что оператор видел на экране до релиза.

**3. Проверка руками в браузере, которую я не делал.** Экран синхронизации остатков ФБС по продавцу с подключённым Ozon: какой статус у Ozon-привязки, и стоит ли на ней вечное «Не найден товар для выгрузки» (P2-3). Экран настройки доли: совпадает ли показанная доступность с тем, что было до релиза (P2-6).

**4. Журнал воркера** за сутки: сколько раз в час срабатывает `publish_stocks` по Ozon и как часто он падает в `ozon_stock_rejected` (P1-2 и P2-7).

---

## Прежние P1 — что подтверждено исправленным

Все три перепроверил независимо, по коду и по базовой линии.

**Перепубликация выше физического остатка — закрыто.** `fbs_stock_rule_service.split_amounts:269–292`: обе ветки, и штучная, и процентная, сходятся в одну строку `amount = min(share, remaining)` с уменьшением `remaining` после каждой привязки. Раньше штучный режим отдавал заданное оператором число мимо потолка. Дополнительно потолок сужен до одного физического склада в `publish_amounts_for_binding:730–732`, а на вводе стоит перепроверка свободного остатка внутри транзакции (`set_rule_for_products`, проверка `units_sum_exceeded`).

**Зависшая передача Ozon после рестарта — закрыто.** `fbs_shipment_service._deliver_ozon_supply:1845+` берёт сеансовую блокировку PostgreSQL на отдельном соединении (`AsyncSession(bind=session.bind)`), а `pg_try_advisory_lock` снимается автоматически при смерти соединения (`marketplace_seller_lock_service.py`). Внутри `_deliver_ozon_supply_locked` попытка в состоянии `PENDING` переиспользуется, если живого владельца блокировки нет, — причём даже когда браузер прислал новый ключ повтора, но при несовпадении отпечатка запроса возвращается 409 `idempotency_key_reused`. То есть рестарт больше не оставляет операцию запертой навсегда.

**Невозможность повторить `ship_failed` — закрыто.** `ozon_fbs_process_service._apply_posting_readback:708–758` поднимает `ozon_ship_failed` при `substatus == "ship_failed"` **безусловно**, независимо от `require_shipped`. В `ozon_box_assembly_service:130–309` ключ сборки снимается и этикетка гасится **до** чтения, исключение ловится, изменения коммитятся, оператор получает 409 — и следующее же сканирование отправляет `/ship` заново. Я сначала прочитал это как мёртвый код (локальная переменная `assembly` не обнуляется) и ошибся; поведение подтверждено существующим тестом `test_ozon_box_assembly.py:352–377`, который проверяет ровно один `/ship` после отказа и второй — на следующем действии оператора.

**Дополнительно: lambda в расписании beat — закрыто.** `backend/app/celery_app.py:15–17` — именованная функция `moscow_now()` с комментарием про переживание сериализации, она же используется в `crontab(hour=0, minute=0, nowfun=moscow_now)` на строке 57. Анонимная функция, которая ломала сохранение расписания, из кода ушла.

---

## Итог

Из накопленного релиза одна находка требует правки до того, как продавцы начнут пользоваться Ozon всерьёз, — обнуление ненастроенных товаров (P0-1), и она чинится одной строкой по образцу вайлдберрисовского пути. Следом за ней сами уходят P1-2 и P2-3. Остальное — либо взведённые, но пока недостижимые с фронта мины (P2-4, P2-5), либо разовое последствие миграции, которое нужно сверить с базой (P2-6), либо отсутствие блокировки на событийной публикации (P2-7).

Прежние три P1 закрыты по-настоящему, а не переименованы: в каждом случае я нашёл конкретную строку, которая делает исправление, и там, где было можно, — тест, который его держит.


---

# Незавершённая дочитка второго ревью — сохранённая история

Оркестратор остановил дополнительный проход SIGINT после вопроса владельца о сроках и повторного чтения уже просмотренных зон. Основное ревью выше завершено успешно; у дочитки **нет финального заключения**. Ниже только видимые промежуточные сообщения автора без редакторской подмены. Все команды и результаты сохранены в REVIEW_2_HISTORY.jsonl; вынесенные CLI результаты — в REVIEW_2_OUTPUTS/.

**Граница независимости:** основной отчёт был закончен до доступа к первому. В дочитке широкий grep дважды вывел фрагменты REVIEW_1_RU.md; автор сам отметил это в сообщениях. Поэтому дополнение нельзя считать полностью слепым к первому ревью. Отдельная CLI-сессия не равна файловой изоляции. Промежуточные утверждения о найденных ошибках не являются проверенным финальным вердиктом.

## Видимые сообщения дочитки в порядке появления

I'll start by reading the brief and my own prior report to understand what was already covered.

Tree confirmed identical to target SHA for all code paths. Now let me size up the unreviewed areas.

Starting with the FBS operator flow — the highest-risk area per the owner. `fbs_workspace_service` has the largest rewrite and is where navigation blockers would live.

Box service reviewed. Now the picking/worklist/supply group.

Now the print subsystem — owner flagged печать/ЧЗ as sensitive.

Now the frontend print path — I need to identify which dialog is actually mounted.

The brief's file list doesn't match the actual diff. Let me verify precisely.

I made a working-directory error — an earlier `cd frontend` persisted. Correcting and re-verifying.

I'll resume with absolute paths, starting with the mounted frontend print path.

Print path mapped. Now the billing/money block.

Reports covered. Moving to inventory counts.

I'll continue the assigned coverage with the remaining services and APIs.

I'll continue the coverage: `fbs_order_history_service.py` and the remaining FBS frontend screens.

I'll continue with the money paths — reading the remaining billing and reporting diffs.

Note: that grep surfaced two lines from `REVIEW_1_RU.md`; I did not open it and will scope further searches to `backend/`/`frontend/` only. Continuing with the packing-charge callers.

Full changed-file inventory captured (155 files). Now the reports/storage API surface.

R2-A1 is now proven on both sides. Reading the new movements report.

Reports block done — found a search-scope mismatch. Now the print/marking block.

Correcting an earlier item: that `?? meta.sku_code` fallback was already dead code. Now the marking print dialog.

Print block verified: with the build flag off, no printed label changes. Now the remaining FBS services.

I'll continue with the remaining FBS services from the brief's list.

I'll finish the inventory-deduction verification first, then continue down the brief's list.

On-disk code matches the production target exactly. Now the deduction ordering.

The arithmetic is self-consistent only if the intermediate balance writes are flushed. Checking the session factory.

Arithmetic is self-consistent — balance writes are Core UPDATEs in the same transaction, so each recursive slice sees the previous one. Now how the deductions reach the operator.

Zero rows are filtered at api/inventory_counts.py:915. Let me check what `pool.quantity` represents relative to the operator's number.

`fbs_stock_pool_debit.py` still exists as a model — checking whether the removed journal left a live table behind.

The debit table/model survives with no production reader. Now the operator's number in `fbs_stock_rule_service`.

`pool.quantity` is both the operator's saved number (written line 653, read back line 258) and a live counter. Let me verify what decrements it and what publishes from it.

Confirmed: `pool.quantity` is decremented on reserve (line 225) and on count shortfall (line 306). Now the publication formula and the release boundary.

Migration 0251 (`fbs_units_mode`) predates the release. Let me read the model diff and migration 0252.

Migration 0252 overwrites the operator's saved number with a computed availability figure. Reading the publication formula.

This is a strong lead. Let me verify how the operator's form loads and re-posts these numbers.

The form seeding is unchanged, so that ratchet is pre-existing — not a release regression. Let me record the migration-0252 mechanism and move to the unread list, starting with infra.

CI adds a backlog gate; prod compose adds only the Ozon flag. Let me check the label-template flag and the backlog script.

Note: that grep leaked `REVIEW_1_RU.md` content again despite the exclude glob — I'll disclose it. Checking the backlog gate's base ref.

CI triggers only on `pull_request`/`workflow_dispatch`, and `origin/etalon` exists — the fallback is sound. Now the real print path and the label-template panel.

The label panel renders nothing when the flag is off — clean. `ProductBarcodePrintDialog` is mounted only in the seller portal; the FF path is the provider. Reading it.

Print path is flag-gated and byte-identical with the flag off. Moving to the billing cluster.

The ledger fix is sound. Critical question: do all reversal callers pass `service_code` where a document now carries two charges?

`order_work_moment` back-dates FBS charges to the work date. Let me check whether an invoice already issued for that period would then miss them.

Two proven billing findings so far. Let me size the remaining FBS and misc services.

I'll read the completed storage_statement_service diff, then continue down the brief's remaining list.

R2-A1 now has hard evidence. Let me confirm the divergent side — how the seller report and invoice read the same rows.

Storage divergence (R2-A1) is now proven on both sides. Moving to the reporting layer.

The reports screen was restructured substantially. Let me verify what happened to the warning banners and the integrity guard.

This looks like a real regression. Let me verify every call path before claiming it.

Verified at the component level. Let me check the screen's own test file for any contradicting assertion.

CSV regression confirmed — the test doesn't assert enablement, so it can't contradict. Now the highest-risk area: the FBS workspace navigation rule.
