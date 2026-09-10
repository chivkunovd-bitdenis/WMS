# WMS-153 / WMS-156 — блокировки при проведении пересчёта с удалением тары

Исполнитель продолжил `feat/wms062-warehouse-docs` от
`db8f867f7251544b938937e6d38cfb807117edd7` в разрешённом worktree
`/Users/deniscivkunov/Projects/WMS/.worktrees/wms062-warehouse-docs`.
Полностью прочитан `review415-final-stock-transactions-result.md` координатора
в `docs/reviews/artifacts/wms415-astra-takeover-20260910/resumed/`.
Finding относится к frozen94fb6485; данный follow-up не переносит весь coord.
Предыдущее исправление stale empty_places сохраняется; его coord-аналог977bd21a.

## Реальный дефект до изменения

На собственной PostgreSQL17-базе `wms415_warehouse_astra_20260910` создан короб
с двумя разными товарами по3 единицы. A пересчитывает только P, B — только Q;
оба подтверждают короб пустым. Два отдельных AsyncSession держат разные Product,
после реальных движений синхронизируются перед удалением общей тары. Блокировки
и записи выполняет PostgreSQL; подменённые обёртки только задают порядок событий.
Никакой модели row locks в памяти или SQLite в этом воспроизведении нет.

До исправления новый тест упал: **OperationalError:40P01 + container_not_empty**.
Это реальный DeadlockDetected от PostgreSQL, не один лишь timeout тестового барьера.
Сохранена последовательность SHARE→UPDATE из finding. Клиентские данные не нужны.

## Решение и проверенный порядок

Прочитаны actual пути в inventory_service, inventory_container_service,
warehouse_map_service и pallet_service; они здесь не редактировались.
Обычное движение идёт Product→Container→Balance. Карта/палета могут уже держать
Container или Balance до запроса Product. Поэтому поздний блокирующий SELECT,
а также простой перенос блокирующего Container-lock раньше Balance, недостаточны.

В post_count Product берутся в прежнем стабильном порядке. Только если документ
содержит подтверждённую тару для удаления, до первого движения дополнительно
захватываются ресурсы операции с NOWAIT — отказом вместо ожидания:

1. Балансы затронутых товаров и товаров внутри подтверждённой тары, включая
   скрытые фильтром и нулевые строки, перечитываются под FOR UPDATE NOWAIT.
   Остатки скрытых товаров не обнуляются: они по-прежнему препятствуют удалению.
2. Подтверждённая тара и тара из этих строк заранее получают FOR UPDATE NOWAIT.
   Поэтому validate_container внутри движения больше не создаёт позднее повышение
   совместной блокировки до исключительной при удалении. Смежная тара тоже
   захватывается заранее: иначе два документа с разными confirmed/line-контейнерами
   могли бы ждать друг друга при очередном validate_container.
3. Для палеты тем же способом заранее захватываются места, которые существующий
   disband_pallet блокирует через joined balance query, и сортировочное место.
   Это учитывает перенос нулевых строк к существующему loose-балансу.

При SQLSTATE55P03 полностью откатывается транзакция и возвращается существующий
InventoryCountError(balance_changed_during_post); API уже отображает этот код
как409. Нового API-кода, UI, статуса или автоматического повтора не добавлено.
Другие DBAPI-ошибки откатываются и пробрасываются, DeadlockDetected не маскируется.
При обычном container_not_empty post_count теперь сам откатывает уже выполненные
движения: вызывающий сервис не может случайно сохранить их следующим commit.
Существующий publish-hook очищает отложенную публикацию на after_rollback;
внешних отправок тестовые товары без селлера не выполняли.

Операционный компромисс: при конкурирующей складской работе проведение может
вернуть существующий409 и потребовать повторного действия после обновления.
Дополнительные блокировки затрагивают балансы соответствующих товаров и тару,
а для палеты также места; вне проведения с удалением подтверждённой тары этот
предварительный захват не выполняется. Это не утверждение о закрытии всех
возможных гонок иных warehouse/map путей вне данного post_count.

## Узкие PostgreSQL проверки

Новый файл `backend/tests/test_wms153_count_post_concurrency.py`:

- Два одновременно проводимых filtered-count для box/cargo_place/pallet: вместо
  40P01 один получает balance_changed_during_post до записи движения, второй —
  container_not_empty; оба остаются draft, два остатка(3,3,0) сохранены, движений0,
  posted_delta не сохраняется. **3passed**.
- Встречные Container→Product и Balance→Product: writer сначала держит свой
  ресурс, post берёт Product, pg_blocking_pids подтверждает ожидание writer.
  Post отказывает NOWAIT и освобождает Product; writer заканчивает приход+1.
  Итог3+4, ровно одно движение+1, count остаётся draft. **2passed**.
- Обычный container_not_empty после выполненного движения откатывается до возврата
  из post_count; следующий commit вызывающего сервиса не сохраняет часть счёта.
  Остатки3+3, движений0, posted_delta=None. **1passed**.
- Полный пересчёт обоих товаров успешно проводит-3/-3 и удаляет/расформировывает
  box/cargo_place/pallet. **3passed**.

Новый файл: **9passed**,10.37s, один worker. До исправления первоначальный box-replay
дал1failed с указанным40P01, после исправления этот же replay дал1passed.

Команды из backend:

```sh
WMS_TEST_DATABASE_URL=postgresql+psycopg://deniscivkunov@localhost/wms415_warehouse_astra_20260910 \
.venv/bin/pytest -q tests/test_wms153_count_post_concurrency.py --tb=short
WMS_TEST_DATABASE_URL=postgresql+psycopg://deniscivkunov@localhost/wms415_warehouse_astra_20260910 \
.venv/bin/pytest -q tests/test_inventory_counts.py tests/test_wms156_discrepancy_concurrency.py \
-k 'post or empty or delete_container' --tb=short
.venv/bin/ruff check .
.venv/bin/mypy .
```

Регрессионный срез: **43passed,38deselected**,99.03s, включая прежние PG-проверки
двойного approve, stale balance и удаления тары при поступлении. Ruff PASS; mypy
PASS,438files. Итоговый `git diff --check` PASS. Полный pytest не запускался. Frontend не менялся, сборка и browser
повторно не запускались. Все данные — в собственной синтетической базе.

## Передача

Только три файла: inventory_count_service.py, новый scoped PG test и этот отчёт.
Канон, handoff, UI, inventory_service, WMS418 и соседние worktree не редактировались.
WMS111/112 остаются STOP, никаких работ по ним не выполнялось. Упаковка и потолки
не менялись. Новых сущностей, журналов, миграций и UX нет.

Это исправление конкретного P2 с PostgreSQL-доказательством; окончательное принятие
интегрированного кандидата требует независимого review. CI/deploy не выполнялись.

Перед commit перечитан актуальный конец takeover handoff координатора. Приоритет
быстрого выпуска не расширяет эту полосу: только заданный warehouse P2, без новых
аудитов или работ по418/111/112. Код после успешных проверок не менялся.
