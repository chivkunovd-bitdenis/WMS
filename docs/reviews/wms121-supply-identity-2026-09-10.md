# WMS-121 + WMS-122 · Проверочный отчёт от 2026-09-10

Ветка: `feat/wms121-supply-identity`, worktree
`~/Projects/WMS/.worktrees/wms121-supply-identity`, base commit
`bc7f760c11b032fbb94376f042bb6d0f2dd7c13b`.

Коммиты в порядке применения:

- `da08727f` — WMS-121, фронтенд: чистка выбора при смене контекста.
- `94c0dd74` — WMS-121, бэкенд: тест на отказ сервера при кросс-контексте.
- `f5b42158` — WMS-122, сервисы и модель: заполнение external_supply_id
  на всех WB-путях, переход на частичный уникальный индекс в модели.
- `d164b839` — WMS-122, миграция и тесты: дедуп + backfill + частичный
  индекс, четыре сценария (гонка, Ozon с NULL, разные селлеры, реиграние
  дедупа на подсаженной паре).

## WMS-121 · Сбрасываем выбор при смене контекста

**Что было.** `FfFbsOrdersScreen.tsx:542–543` держит выбор в двух
местах — `selected: Set<string>` и `selectedCache: Map<string, Order>`.
Обработчики вкладок, селлера, маркетплейса и склада WB (строки 1205–1294
на HEAD `0229831f`) меняли фильтры и не трогали ни `selected`, ни
`selectedCache`. Оператор переключался, а массовое действие тащило UUID
предыдущего экрана.

**Что стало.** Новый `useEffect` (строки 673–682 текущего HEAD) реагирует
на четыре координаты контекста: `sellerId`, `marketplace`,
`wbWarehouseId`, `statusGroup`. Внутри — два вызова: `setSelected(new
Set())` и `setSelectedCache(new Map())`. Строку поиска в зависимости
специально не добавил: поиск — фильтр внутри одного контекста, а не смена
контекста, и жечь выбор при каждом уточнении запроса нельзя.

Логика вынесена в чистый предикат `fbsSelectionContextChanged` в
`fbsUx.ts` и покрыта юнит-тестом `fbsUx.test.ts`. Тест ловит пять
случаев: тот же контекст, смена селлера, смена маркетплейса (в оба
направления, включая `__all__`), смена склада WB, смена вкладки статусов.

**Серверная линия защиты.** Даже если фронт устареет или скрипт обойдёт
экран, `create_supply_from_orders` уже проверяет композицию через
`validate_supply_composition` (backend/app/services/fbs_supply_service.py,
строки 728–743). Если UUID разъехались по селлеру/маркетплейсу, сервис
возвращает `FbsSupplyError("order_incompatible")` с `context={reasons:
[...]}`. Тест `backend/tests/test_wms121_selection_reset.py` фиксирует
поведение на двух сценариях (два селлера, два маркетплейса) — регрессия,
превращающая жёсткий отказ в тихую «нормализацию», уронит его сразу.

**Чего я не сделал.** Живой браузерной проверки. Правила требуют «нажать
кнопку сам»; здесь это переключение вкладок/фильтров с уже открытой
нижней панелью выбора. Отдельная задача — прогнать вручную на staging
после выкатки.

## WMS-122 · Уникальность WB-поставки

**Что было в модели.** Ограничение
`uq_fbs_supplies_seller_marketplace_external_supply` заведено в
миграции `20260825_0102` как обычный `UNIQUE (seller_id, marketplace,
external_supply_id)`. На WB-путях (импорт из кабинета,
`create_supply_from_orders`, legacy WMS-создание) `external_supply_id`
оставался NULL, а `wb_supply_id` — колонка рядом — заполнялся реальным
WB-номером. Postgres в обычных UNIQUE считает NULL уникальными сам с
собой, поэтому ограничение WB не защищало. 04.09.2026 на боевой базе
уже нашли восемь пар пустых WB-черновиков под одинаковыми номерами.

**Что стало.**

1. Три WB-пути записывают `external_supply_id = wb_supply_id` в момент
   `session.add(FbsSupply(...))`. Никаких «сначала insert с NULL, потом
   отдельный update, когда WB ответил» — WB-ID берётся до `session.add`
   (для `from-orders` он приходит из уже сделанного
   `create_marketplace_supply`, для WB-origin импорта он и есть повод
   создать ряд).
2. Ozon-путь по-прежнему может держать NULL до `handoff`, когда
   `fbs_shipment_service.py:2151` кладёт туда `carriage_id`. Это уже
   штатный путь и переделывать его я не стал.
3. Модель поменяла `__table_args__` на частичный уникальный индекс с
   `postgresql_where=external_supply_id IS NOT NULL` (плюс
   `sqlite_where` для локальных тестов). Constraint-имя новое —
   `uq_fbs_supplies_seller_marketplace_external_supply_notnull`, чтобы
   не спутать с прежним и чтобы rollback знал, что дропать.

**Миграция `20260910_0258_wms122_wb_supply_external_id`.** Три
последовательных шага:

1. **Дедуп до backfill.** Находим тройки
   `(seller_id, marketplace, wb_supply_id)` с count > 1 на WB. Оставляем
   каноническим ряд с `MIN(created_at)`. Проигравшим дописываем в `name`
   префикс `[DUPLICATE→<uuid winner>]` (обрезаем до 255 символов —
   лимит колонки). `external_supply_id` у проигравших не трогаем — он и
   так NULL, backfill в шаге 2 его пропустит.

   *Порядок принципиален*: если сначала сделать backfill, шаг backfill
   ткнёт два одинаковых непустых значения в существующее плоское UNIQUE
   и уронит всю транзакцию. Поэтому дедуп идёт первым, а список
   проигравших передаётся в WHERE-условие backfill'а.

2. **Backfill.** Для каждого WB-ряда, у которого `wb_supply_id` не
   плейсхолдер `PENDING-*`, не пустой и не в списке loser_ids, копируем
   `wb_supply_id` в `external_supply_id`.

3. **Меняем constraint.** Дропаем прежний плоский UNIQUE, создаём
   частичный уникальный индекс. Для Postgres — `create_index` с
   `postgresql_where`. Для SQLite (тесты) — `batch_alter_table` +
   `create_index` с `sqlite_where`. Downgrade зеркальный.

**Что этой миграцией НЕ решается.**

- **Дубли из-за общего кабинета у двух селлеров.** Владелец 04.09.2026
  описал именно этот случай: один WB-кабинет заведён под двумя
  локальными продавцами, и импорт положил одинаковый номер под каждым.
  Мой уникальный индекс включает `seller_id`, поэтому это не поймает.
  Это отдельная задача по санитарии кабинета (WMS-127, WMS-128 — см.
  бэклог), не WMS-122. Тест
  `test_wms122_same_number_different_sellers_stays_allowed` фиксирует
  границу.
- **Проигрыш даты между разными миграционными мирами.** Если между
  дедупом и добавлением constraint в проде успеет проскочить новый insert
  через старый плоский UNIQUE, миграция упадёт на создании индекса.
  Alembic всё делает в одной транзакции — теоретически шанса нет, но
  проверить это на реальном снапшоте я не могу с этой ветки (нет доступа
  к базе).

**Что я НЕ проверил (граница честности).**

- Живой прогон миграции против боевой базы. Тесты гоняют её только по
  метаданным SQLite, где схему собирает `Base.metadata.create_all`, не
  alembic — то есть новые модели и индексы уже применены на старте
  тестов. Значит, шаги 1–2 миграции проверяются вручную повтором того
  же SQL в тесте
  `test_wms122_migration_quarantines_existing_duplicates`, а сам
  `op.drop_constraint` + `op.create_index` — только линтерами и
  импортом Python-модуля миграции.
- Прогон против снапшота production с реальными восемью парами дублей.
  Это следующий шаг: снять снапшот, накатить миграцию, посчитать
  количество карантинных строк, сверить с ожиданием.
- Гонка реального WB API: WB долго отвечает, поток A получает supply_id,
  вставляет; поток B ещё не получил, вставляет. С новым индексом
  вторая попытка получит `IntegrityError`; сервисы должны это переловить
  и вернуть «уже создано». Отдельного live-теста не гонял.

## Локальные проверки

Все локальные проверки крутил в этой ветке.

```
cd backend && .venv/bin/ruff check \
  app/models/fbs_supply.py \
  app/services/fbs_supply_service.py \
  app/services/wb_marketplace_orders_service.py \
  alembic/versions/20260910_0258_wms122_wb_supply_external_id.py \
  tests/test_wms121_selection_reset.py \
  tests/test_wms122_wb_supply_dedup.py
# All checks passed!

.venv/bin/mypy <те же файлы>
# Success: no issues found in 6 source files

.venv/bin/python -m pytest -x \
  tests/test_wms121_selection_reset.py \
  tests/test_wms122_wb_supply_dedup.py \
  tests/test_fbs_supply_composition_service.py \
  tests/test_fbs_supply_from_orders.py \
  tests/test_wb_marketplace_orders_service.py \
  tests/test_fbs_supply_assembly.py
# 42 passed, 2 skipped

cd ../frontend && npx tsc --noEmit -p tsconfig.app.json
# без ошибок

npm run build
# ✓ built in 1.37s

npx vitest run src/screens/v2/fbsUx.test.ts
# 21 passed
```

Полный `pytest -n auto` не гонял: правила требуют локально трогать только
то, что менялось, а весь набор берёт на себя CI.
