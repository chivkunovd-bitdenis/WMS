## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/backend/app/models/product.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/backend/app/models/product_dimension_event.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/backend/app/models/__init__.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/backend/alembic/versions/20260822_0095_product_dimension_events.py`

`Product` получил быстрый снимок действующего источника, времени и автора. Новая
`ProductDimensionEvent` хранит источник, аудитора, время наблюдения, размеры, объём,
основание объёма тары, fingerprint и признак действующей версии. Уникальные индексы
защищают от дублей и оставляют ровно одну действующую версию на товар.

## Миграции

- `20260822_0095_product_dimension_events` — добавляет три поля действующего источника
  в `products` и создаёт журнал `product_dimension_events` с FK, fingerprint-индексом и
  частичным уникальным индексом действующей версии.

## Гейты

- `ruff` — targeted checks новых файлов зелёные; полный `ruff check .` красный на 82
  существующих нарушениях базовой линии.
- `mypy` — красный: 21 существующая ошибка в 6 файлах; новых ошибок в изменённых моделях
  не выявлено.
- `pytest` — 32 passed, 63 ошибки и остановка полного запуска по таймауту/KeyboardInterrupt;
  ошибки относятся к существующему тестовому контуру.
- `back_guard.py` — не запущен: `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/scripts/ci/back_guard.py` отсутствует.
- `check_migrations.py` — не запущен: `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/scripts/ci/check_migrations.py` отсутствует.
- Metadata smoke test импорта моделей — зелёный.

## Не реализовано

- Сервис записи, переключения действующей версии и API истории не реализованы: они
  относятся к атомарным кускам 3–4 и намеренно не входят в этот backend-dev проход.
- Изменение Wildberries-импорта не выполнялось: оно также относится к куску 3.
- Найденные в рабочем дереве секреты, ключи, токены и `.env` не открывались.
