# WMS-662 F6: PostgreSQL RED до исправления порядка блокировок

Проверено 06.10.2026 отдельным тестировщиком, без skills и subagents.
Ownership: только новый `backend/tests/test_wms662_cancellation_lock_order.py`
и этот handoff. Исходный код, legacy tests, guards и требования не менялись.
AGENTS.md прочитан; origin/etalon обновлён, его правила прочитаны.
По прямому поручению владельца тестируется существующий c36, а не новая
продуктовая задача от etalon.

Business base **c36b8abee120e57b27e50d3358cfdc533cd411eb**. Отдельный постоянный
checkout `.worktrees/wms662-f6-testwriter`, ветка `codex/wms662-f6-testwriter`.
Прочитан независимый отчёт
`../wms662-review-c36b8ab/docs/reviews/wms662-663-priority/astra-review-c36b8ab.md`,
опубликованный review commit `7019ac731`.

## Результат и реальное последствие

Все четыре комбинации дали **RED с настоящим SQLSTATE 40P01**. Это не
source grep, не SQLite и не тайм-аут окружения. Исполнялись реальные функции
передачи, синхронизации, отмены, склада и биллинга на PostgreSQL 16.14.
Проверена независимая PostgreSQL-сессия каждого worker, её PID записан в trace.

| Отмена B | Передача A | Результат |
|---|---|---|
| `_lock_order` → `_finish_local_cancellation` | `deliver_supply` | 40P01 |
| `_lock_order` → `_finish_local_cancellation` | `sync_ozon_order_statuses` → `conduct_supply` | 40P01 |
| `_lock_order` → `_apply_status(cancelled)` | `deliver_supply` | 40P01 |
| `_lock_order` → `_apply_status(cancelled)` | `sync_ozon_order_statuses` → `conduct_supply` | 40P01 |

В завершённых RED-прогонах жертвой стала передача A. Её
`charge_handed_over_orders` проглотил исключение внутри savepoint, обе
операции вернули `None` и сделали внешний commit. Новая сессия увидела:
остаток **12 → 11**, резерв **2 → 0**, A=`in_delivery`, B=`cancelled`,
начисление A **0 вместо 1800**, баланс B после сторно **0**.
Тест ловит SQLSTATE даже при проглоченной ошибке; внешний успех не скрывает
потерянное начисление. Выбор жертвы PostgreSQL не является ожиданием теста:
другая жертва также должна нарушить контракт успешного завершения обеих операций.

## Достижимое расписание и точность fixture

Два разных заказа одного tenant/seller/product. A находится в своей передаваемой
поставке, B не прикреплён к поставке. У B осталась настоящая mapped позиция Ozon
на тот же товар и настоящий резерв. Нет общего order/supply lock, который
подменял бы конкуренцию seller/product. B имеет старые начисления сборки и
упаковки, записанные настоящим `record_operational_charge`, по 1000 и 800.
HTTP fake возвращает данные только A; настоящие сетевые обращения запрещены.

У B `external_order_id=None`, поэтому полный observed poll A не захватывает
B в своей общей пачке заказов. Для отмены используется настоящий локальный
обработчик статуса, а не второй seller-wide poll, который заранее запер бы A.
У B также `product_id=None`, но **не** `product_positions.product_id`:
действующий Ozon-расчёт резерва использует mapped позицию. Nullable основной
указатель поддерживается моделью. Это явно ограниченный вариант Ozon-данных,
а не утверждение, что любой заказ с заполненным основным указателем даёт
тот же цикл: его audit status INSERT получает дополнительный FK KEY SHARE
по Product раньше явного Seller lock и может изменить расписание.
Аудит, внешние ключи и бизнес-функции не отключались и не подменялись.

Барьер ставится **после исполненного** первого Seller/Product lock отмены B.
Передача A затем запускается отдельной сессией. Когда A пытается взять ресурс,
который удерживает B, барьер отпускает B. На c36 это даёт:

```text
B acquired sellers FOR NO KEY UPDATE
A acquired products FOR UPDATE
A attempts sellers FOR NO KEY UPDATE → releases B barrier
B attempts products FOR UPDATE
PostgreSQL: deadlock detected / SQLSTATE 40P01
```

При едином порядке второй worker запросит первую общую блокировку сразу;
барьер отпустит первого, и PostgreSQL сможет сериализовать операции.
Тест не требует, чтобы оба worker одновременно получили первую блокировку,
что само по себе сделало бы исправленный порядок невыполнимым.
Нет sleep, определяющего расписание. Ограничения ожидания служат только
защитой стенда; даже проглоченный timeout барьера отдельно фиксируется как
HARNESS, а не F6. Коды 57014/55P03 также не выдаются за business RED.

Trace записывает PID для каждой acquisition/commit/rollback. Rollback
независимого reader из fake HTTP callback не обрывает внешний writer в
проверке порядка. Успешные savepoint не считаются внешними commit.

## Неизменяемые ожидания после исправления

Нужны успешные внешние commit обеих операций без SQL errors; одинаковый
относительный порядок Product/Seller внутри их внешних транзакций; расход
ровно одной штуки A, все резервы сняты, B не списан; A начислен ровно 1800,
B полностью сторнирован с сохранением исходных строк. Повтор обоих путей
не меняет headers денег, IDs движений, фактов или операций. Повтор обычной
передачи не повторяет fake HTTP мутацию.

**PASS на исправленном product SHA пока не заявляется.** На c36 проверка
останавливается на настоящем 40P01; последующие успешные assertions должны
быть исполнены разработчиком и перепроверены на его исправленном SHA.
Это контракт тестов и RED, не приёмка, CI или разрешение выпуска.

## Изолированный PostgreSQL и воспроизведение

Свой сервер: loopback `127.0.0.1:55466`, пользователь `wms_test`, БД
`wms_test_662_f6`. Существующие PG разработчика/других задач не использованы.
Кластер `/private/tmp/wms662-f6-pg-55466/cluster`, журнал
`/private/tmp/wms662-f6-pg-55466/postgres.log`, test-data в том же собственном
каталоге. Сервер оставлен работающим для GREEN; не нужно убивать чужие PG.

Команды первоначального создания собственного сервера (повторно initdb
на существующем кластере не запускать):

```sh
initdb -D /private/tmp/wms662-f6-pg-55466/cluster -U wms_test --auth=trust --no-locale -E UTF8
pg_ctl -D /private/tmp/wms662-f6-pg-55466/cluster \
  -l /private/tmp/wms662-f6-pg-55466/postgres.log \
  -o '-h 127.0.0.1 -p 55466 -k /private/tmp/wms662-f6-pg-55466 -c deadlock_timeout=100ms -c statement_timeout=12000' start
createdb -h 127.0.0.1 -p 55466 -U wms_test wms_test_662_f6
```

Из backend нужного точного product checkout, **без xdist**:

```sh
WMS_TEST_DATABASE_URL=postgresql+asyncpg://wms_test@127.0.0.1:55466/wms_test_662_f6 \
WMS_TEST_DATA_DIR=/private/tmp/wms662-f6-pg-55466/test-data \
PYTHONDONTWRITEBYTECODE=1 \
/Users/deniscivkunov/Projects/WMS/backend/.venv/bin/python -m pytest \
  -q -p no:cacheprovider tests/test_wms662_cancellation_lock_order.py \
  --tb=short --show-capture=no
```

На SQLite файл намеренно SKIP: это не PG PASS. Основной сохранённый RED
получен на реальном PostgreSQL; все четыре упали с 40P01 примерно за 4 секунды.
`ruff check` нового файла и `git diff --check` прошли.
Полные проверки backend, legacy regression и CI не запускались этим тестировщиком.
Production DB, marketplace writes, main и etalon не менялись.

Первые пробы harness с заполненным `product_id` остановились на FK-ожидании
и timeout барьера; они **не** использованы как доказательство F6. Итоговый
сценарий выше воспроизвёл 40P01 без timeout. Исходный полный stdout последнего
RED локально: `/private/tmp/wms662-f6-pg-55466/red.txt`; восстановимая защита,
описание расписания и инструкция запуска сохранены в Git, а не только в /tmp.
