# WMS-349 · Сериализация merge_products с движениями остатка

Дата: 2026-09-10. Ветка: `feat/wms349-merge-service`. Работа выполнена по прямому
поручению владельца в порядке WMS-415, пятый параллельный Opus-исполнитель.

## Постановка

Аудит WMS-414 зафиксировал: `merge_products` читает и обновляет `products` и
`inventory_balances` без `FOR UPDATE`. Штатный writer остатка
`inventory_service.record_movement_and_adjust_balance` — с `FOR UPDATE` через
`lock_stock_product`. Между этими двумя путями нет общей блокировки, поэтому
конкурентное движение может пройти между `SELECT` и `UPDATE` внутри merge, и
merge запишет сумму из прежнего снимка. Границей проверки был явно очерчен код;
факт реальной потери на бое не утверждался и в этой задаче не устанавливается.

Запись владельца в handoff WMS-415 §2а п.2: «объединение карточек должно брать
существующие блокировки Product в стабильном порядке до чтения балансов; гонка
доказана чтением путей, фактическая потеря на production не утверждается».

Ссылка: `docs/KANONICHESKIY_BACKLOG.md#wms-349` — статус до правки был
`ЧАСТИЧНО: ОБЪЕДИНЕНИЕ ЕСТЬ, НЕТ СЕРИАЛИЗАЦИИ С ДВИЖЕНИЯМИ ОСТАТКА`.

## Как было (bc7f760c11b032fbb94376f042bb6d0f2dd7c13b)

`backend/app/services/product_merge_service.py:206–226`, до правки:

```python
async def merge_products(session, tenant_id, product_ids):
    ids = list(dict.fromkeys(product_ids))
    if len(ids) != 2:
        raise ProductMergeError("merge_needs_exactly_two")

    products = list(
        (
            await session.execute(
                select(Product)
                .options(selectinload(Product.seller))
                .where(Product.tenant_id == tenant_id, Product.id.in_(ids))
            )
        )
        .scalars()
        .all()
    )
```

`_sum_inventory_balances`, до правки: два обычных SELECT без `with_for_update`.

## Как стало

`backend/app/services/product_merge_service.py:206–252` — блокировки идут строго
до чтения балансов и по одной, в порядке возрастания `id`:

```python
locked_ids = sorted(ids)
locked: dict[uuid.UUID, Product] = {}
for product_id in locked_ids:
    row = (
        await session.scalars(
            select(Product)
            .where(Product.tenant_id == tenant_id, Product.id == product_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
    ).one_or_none()
    if row is None:
        raise ProductMergeError("product_not_found")
    locked[product_id] = row
```

`_sum_inventory_balances` теперь читает обе группы балансов с `with_for_update()`
(`backend/app/services/product_merge_service.py:132–170`).

Ни новой таблицы, ни журнала, ни счётчика заведено не было — используется тот
же самый механизм `SELECT ... FOR UPDATE`, что и в штатном writer'e остатков.
Совпадение порядка блокировок между двумя путями (Product по возрастанию `id`)
исключает встречный deadlock.

## Тестовое покрытие

Новый файл: `backend/tests/test_product_merge_service_wms349.py`. Пять тестов,
все зелёные:

1. `test_merge_takes_product_locks_in_ascending_id_order_input_forward`
2. `test_merge_takes_product_locks_in_ascending_id_order_input_reversed`
3. `test_merge_reads_balances_under_for_update_lock`
4. `test_merge_still_sums_stock_end_to_end_after_lock_change`
5. `test_merge_reports_missing_product_before_touching_balances`

Тесты 1 и 2 подтверждают ключевое: `SELECT ... FOR UPDATE` для каждого из двух
продуктов действительно уходит на драйвер (проверено перекомпилированием
захваченного ORM-выражения под PostgreSQL-диалект — SQLite в тесте вырезает
`FOR UPDATE` из физического SQL, но ORM-объект остаётся неизменным), их два, и
их bind-параметры равны `sorted([id₁, id₂])` независимо от порядка входа. Первый
`FOR UPDATE` идёт по позиции раньше любого чтения `inventory_balances`.

Тест 3 подтверждает, что оба SELECT в `inventory_balances` внутри
`_sum_inventory_balances` тоже уходят с `FOR UPDATE`.

Тест 4 — регресс-щит: конкретный merge с двумя карточками, у которых остаток
8 и 5 в одной ячейке, после исправления по-прежнему складывает их в 13.

Тест 5 сторожит поведение при отсутствующей карточке: `product_not_found`
поднимается на стадии блокировки, ни одного чтения `inventory_balances` до
этого не происходит.

Прогон:

```
cd backend && ../backend/.venv/bin/pytest -n auto tests/test_product_merge_service_wms349.py
# 5 passed, 45 warnings in 7.96s
```

Существующие merge-тесты в `backend/tests/test_products_ozon_catalog.py` (14
шт.) остались зелёными — правка не сломала прежнее поведение:

```
cd backend && ../backend/.venv/bin/pytest -n auto tests/test_products_ozon_catalog.py
# 14 passed, 45 warnings in 10.56s
```

Технический слой:

```
cd backend && ../backend/.venv/bin/ruff check app/services/product_merge_service.py tests/test_product_merge_service_wms349.py
# All checks passed!
cd backend && ../backend/.venv/bin/mypy app/services/product_merge_service.py
# Success: no issues found in 1 source file
```

## Граница проверки — честно

Тест-БД в проекте — SQLite (aiosqlite). У SQLite `FOR UPDATE` вырезается
диалектом на этапе компиляции и физически до драйвера не доходит. Поэтому:

* **Что доказано.** Сервис действительно строит SELECT с `with_for_update()` и
  делает это по одному, в возрастающем порядке `id`, до чтения балансов. Это —
  ровно та смена пути, которую требовал аудит. Проверка сделана на уровне
  ORM-выражений и перекомпиляции под PostgreSQL-диалект.
* **Что не проверено.** Физический deadlock и конкурентный сценарий против
  живого PostgreSQL здесь не проигрывались — нет ни отдельной PG-фикстуры под
  concurrency, ни воспроизведения реальной потери. Утверждать, что «на бою
  теперь всё точно сериализуется» — рано; правильное утверждение: «сервис
  теперь ходит тем же путём, что и штатный writer остатков; на PostgreSQL эти
  два пути выстраиваются в одну очередь блокировок».
* **Реальные клиентские карточки не объединялись** — сегодня, вчера, никогда.
  Тест работает на синтетических тенантах теста.

Гонка доказана чтением путей и наличием `FOR UPDATE` в компиляции ORM-выражений;
физическая потеря на production по-прежнему не утверждается.

## Что не менялось

* `backend/app/services/inventory_service.py` — не трогался, координация со
  stock-lane выдержана.
* Никаких новых таблиц, счётчиков, флагов или журналов — соблюдено «ВТОРОЕ
  ГЛАВНОЕ ПРАВИЛО» из `CLAUDE.md`/`AGENTS.md`.
* Фронт, чат, mobile, FBS-таблицы — не трогались.

## Ссылки

* Изменения кода: `backend/app/services/product_merge_service.py`
* Новый тест: `backend/tests/test_product_merge_service_wms349.py`
* Бэклог: `docs/KANONICHESKIY_BACKLOG.md` → `## WMS-349`
* Handoff: `docs/reviews/WMS_CLAUDE_HANDOFF_2026-09-09.md` §2а п.2
