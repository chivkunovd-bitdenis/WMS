# WMS-445: backend/API и учебный контур, 13.09.2026

Это передача реализации исполнителю UI и на ревью. Приёмка WMS-445 не объявлена;
Android, браузерный проход, физическая печать и настоящие площадки этим отчётом не проверены.
Требования WMS-445 не менялись. Ветка codex/wms445-tsd включает отдельно разрешённые
зависимости WMS-444 (2978eea8, ecf01356) и WMS-443 (cda86f14).

## Что изменилось

Скан без order_id выбирает старейший ещё не подобранный заказ по created_at_wb,
при равенстве — deadline_at и ID. Это относится к WB и Ozon; ячейку выбирает
оператор, автоматический FIFO источников не вводился. Контрактный тест ставит
старому заказу более поздний срок и проверяет его выбор, второй физический скан,
повтор HTTP и сохранение результата.

Preflight summary сохраняет уже рассчитанные marketplace и delivery_route.
Список поставок возвращает delivery_type/delivery_route, workspace.supply —
delivery_route. Большой Ozon warehouse ID больше не передаётся в WB int4 справочник
при чтении списка поставок. positions[].packed_quantity читается из существующих
active FbsPackagingFulfillment units; складские движения не создаются.

Повтор последней упаковки узнаётся по существующему PackagingTaskEvent до
проверки остатка/статуса. Сохранены tenant-wide ключ, проверка количества, строки,
оператора и действия из WMS-444; для FBS проверяется также конкретный заказ.
Замки идут в существующем порядке supply → task → lines. Нового журнала или
колонки нет. После done повтор читает факт, другой quantity/order возвращает409.

Отказ локального завершения Ozon после внешнего успеха раньше терялся:
после rollback обращение к operation.id запускало недопустимый неявный SQL
(MissingGreenlet). ID теперь сохраняется до rollback; ошибка записывается
существующей операцией. Это обнаружено настоящим запросом к isolated API,
когда учебный barcode ошибочно оказался PDF; fake исправлен на PNG.

## Контракт для Android

- /operations/fbs-orders/worklist?marketplace=...&sort=oldest: seller{id,name},
  wms_warehouse{id,name}, wb_warehouse{id,name}, delivery_route, can_pvz,
  selection_blockers и positions доступны. Новое поле positions[].packed_quantity.
- /operations/fbs-supplies/preflight: summary.marketplace и summary.delivery_route.
  Площадку, селлера, оба склада и маршрут показывать до сохранения.
- /operations/fbs-supplies/worklist: добавлены delivery_type/delivery_route,
  can_add_orders и seller/warehouse refs уже были. IDs необходимо сохранять.
- /operations/fbs-supplies/{id}/workspace: supply.delivery_route плюс существующие
  площадка, селлер, склад, task ID, состав и прогресс. Для Ozon внутреннее
  planned_delivery_type=warehouse_sc не должно называться выбором WB «Склад/СЦ».
- Retry одной попытки сохраняет idempotency_key; новый физический scan/pack
  получает новый. Старейший заказ выбирает сервер, если order_id не задан.
- Никаких новых запретов упаковки/выбора вкладок или status assembling→picking
  эта реализация не добавляет.

## Проверки

На собственной PostgreSQL wms445_tests (без общей БД), после включения WMS-443:
`pytest -n 0 tests/test_wms445_fbs_contract.py tests/test_pack_progress_idempotency.py tests/test_wms445_local_emulators.py` — 20 passed.
Это включает конкуренцию обычной упаковки WMS-444, FBS quantities/retry/rollback,
большой warehouse ID, маршруты, запрет внешнего HTTP и redirect, Ozon formed.

Ранее целевые SQLite-наборы упаковки дали38passed/3skipped (три PostgreSQL проверки
затем прошли выше), read/picking набор дал32passed; неподходящие проверке всего
проекта тесты не запускались. Последние `ruff check .` и `mypy .` — пройдены,
451 source files. Нового общего статуса задачи из этих технических проверок не следует.

В собственной wms445_fixture/API18084/WB19094/Ozon19093 seed создан и повторён:
18заказов,3селлера,2ячейки,4товара×2источника×20ед,8реальных inbound движений.
A/B имеют тарифы444, C не имеет тарифа; сотрудник Иван Учебный Сотрудник,
должность Кладовщик, ставка7руб. WB assembling создан действующим from-orders→start-work.
`done`/`delivered` не выставлялись seed-скриптом.

Реальный API smoke прошёл Ozon from-orders→start-work→pick3→pack3→box→QR assembly
→label→deliver→тот же deliver→workspace. После исправления неверного MIME barcode
тот же внешний результат восстановлен: одна carriage445001, один ship, один
create, один approve, статус formed. База: fbs_shipment2движения на-3ед;
ledger fbs_order3×4000=12000коп и packing3×3000=9000коп. Повтор не добавил расход.
Доказательства: [manifest](artifacts/wms445-backend-20260913/manifest.json),
[финальные HTTP шаги](artifacts/wms445-backend-20260913/ozon-smoke.json),
[сводка БД и HTTP](artifacts/wms445-backend-20260913/ozon-wire-summary.json).
Финальный HTTP список записан повторным запуском после сборки короба;
первый проход до коробов подтверждён исполнением, но полный сетевой trace не сохранён.

## Запуск в общем учебном контуре

Координатор сначала подключает source и разрешает использование shared API/БД.
У API должны совпадать локальные JWT/Fernet настройки с процессом seed; реальные
.env и кабинеты секретов не нужны. Настройки API: WMS_OZON_LIVE_API=true,
WMS_OZON_SELLER_API_BASE=http://127.0.0.1:19093; WB marketplace/supplies/content
base все направлены в http://127.0.0.1:19092. Во избежание случайных запросов
других интеграционных endpoints API запускается фабрикой
`tools.wms445_local_http:create_app --factory`; она запрещает любой HTTP вне
перечисленных loopback портов, включая redirect. Seed устанавливает ту же защиту.

Из backend, отдельный Ozon fake запускается так:

```sh
WMS445_OZON_STATE=/absolute/path/ozon445-shared.json python -m uvicorn tools.wms445_ozon_emulator:app --host 127.0.0.1 --port 19093 --no-access-log
```

Для shared нужен НОВЫЙ файл состояния: изолированный smoke уже использовал
445-a-0, его состояние нельзя переносить в учебный tenant другой БД.
Остальные данные fake/неподдерживаемые endpoints не считаются реальным Ozon:
неизвестный маршрут возвращает501. ЧЗ/exemplar API и multi-box split этим
эмулятором пока не реализованы и требуют расширения до соответствующей приёмки.

Из корня checkout (python — используемая backend/.venv/bin/python):

```sh
PYTHONPATH=.:backend python -m tools.wms445_seed --database-url postgresql+psycopg://deniscivkunov@localhost:5432/wms_tsd_20260913 --api-base http://127.0.0.1:18082 --wb-base http://127.0.0.1:19092 --wb-db /absolute/path/shared-wb-emulator.sqlite --manifest /absolute/path/wms445-manifest.json
```

WB файл принимает только445xxxxxx order IDs и не перезаписывает существующие;
Ozon fake seed не перезаписывает состояния существующих posting IDs.
Операции над synthetic аккаунтами выполняются локальными services,
без credential-validation HTTP и без фоновых catalog imports. Причина ограничения:
исходный validator Ozon имеет жёсткий внешний URL и игнорирует base override;
он был обнаружен при первом synthetic smoke, после чего исключён из seed.
Никакого onboarding ремонта в445 нет.

Входы учебные: wms445-admin@example.com и wms445-staff@example.com;
пароль обоих Wms445-demo-only. Они существуют только в созданной fixture БД.
Скрипт не печатает JWT и не записывает их в manifest.

Optional server smoke (он действительно изменит собственную Ozon445-a-0 поставку):

```sh
cd backend
python -m tools.wms445_smoke --api-base http://127.0.0.1:18082 --manifest /absolute/path/wms445-manifest.json --report /absolute/path/wms445-smoke.json
```

До сквозной независимой приёмки остаются Android UI, WB оба полных маршрута,
маркировка, split коробов, выдача всех вариантов печати, отказ до создания и
выход/возврат после сетевых отказов. Эти проверки не выданы за пройденные.
