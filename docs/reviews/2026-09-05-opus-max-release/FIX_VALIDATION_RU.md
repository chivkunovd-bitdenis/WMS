# WMS-375 — фактическая проверка исправлений

06.09.2026. Рабочая ветка `feat/ozon-merge-staging-20260905`.
Это протокол проверки, не отдельный бэклог и не заявление о готовности production.

## Первый объединённый прогон

15 файлов backend: Ozon transport/lane/delivery/sources/cleanup, FBS stock rules,
FBO availability, warehouse bindings, event publication, reports, storage,
WB delivery/gates/autopoll/stock sync. `pytest -n 4`: 263 passed, 9 failed,
24.39 секунды. Все девять падений разобраны:

- 3 сценария FBO: новый тест не передал обязательный `is_fbs=False`;
  после исправления 3 passed, 37 deselected.
- Ozon delivery/sources: неверное имя поля движения `delta` вместо
  `quantity_delta`; fixture нехватки оставлял quantity_packed=1 при quantity=0.
  Исходные данные исправлены, ожидаемый минус сохранён. Два файла: 10 passed.
- 2 сценария связей отчёта: запрос movements не задавал обязательную группу;
  добавлено `operation=FBS`, API не ослаблен. Весь файл reports_movements: 9 passed.

`ruff check .` прошёл; `mypy .`: 421 source files, без ошибок.
Frontend: FfReportsPage.test.tsx — 3 passed; `npm run build` прошёл.
Предупреждения сборки о размере chunks и тестовые Swig deprecations сохранены
как ограничения инструментов, не выданы за функциональные дефекты.

## PostgreSQL

Отдельная локальная БД `wms375_lock_20260906`, PostgreSQL 17.10, драйвер psycopg.
Первый запуск с asyncpg не стартовал: драйвер отсутствует, использован драйвер
из pyproject. Новый тест реального пути событийной публикации прошёл:
после двух внутренних commit конкурент не получает тот же seller/Ozon lock;
`ozon-delivery` доступен; после завершения stock lock снова доступен.

Две существующие проверки конкурентной сборки WB первоначально не смогли
создать схему: в ORM Product отсутствовал уникальный ключ (tenant_id,id),
который уже создан миграцией 0111 и используется FK billing_ledger_lines.
Наличие этого ключа на production подтверждено чтением pg_indexes.
Метаданные приведены в соответствие существующей миграции, новой миграции нет.
После исправления: 2 passed, 12 deselected — параллельное создание поставки
из одного заказа и конкурентное добавление заказа в поставку.

## Текущие границы

Сервер проверен чтением: `/opt/wms` HEAD
`ed72c8888a6e383f5101e0c1bd96d3793810e4fc`; api, worker, beat, web работают.
Исправления на сервер пока не выкладывались. Новые browser/printer/внешние
подтверждения публикации не получены. A07 редактор коллизий и WMS-369/371
дорабатываются отдельно; указанный выше build не проверяет их будущий diff.
A08 остаётся исследованием снимка, количества в production не менялись.
