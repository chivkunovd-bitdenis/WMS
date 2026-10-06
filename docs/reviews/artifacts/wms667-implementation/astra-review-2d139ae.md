# WMS-667: независимое ревью 2d139ae

**Product review: PASS.** В проверенном объёме R1–R5 подтверждённых дефектов,
блокирующих реализацию, не найдено. Это заключение о коде и выполненных
изолированных проверках, не финальная приёмка задачи и не разрешение на выпуск.
**C10: НЕ ПРОВЕРЕНО** — авторизованный каталог в браузере недоступен;
читаемость на узком экране и длинное имя селлера требуют ручной приёмки.
Настоящие DOM-проверки не выданы за визуальный PASS.

Дата: 06.10.2026. Ревью выполнено самостоятельно в текущей сессии,
без skills и дочерних агентов. Продуктовый SHA:
`2d139aee43464ff799fe64d1cbf05b043ff88007`.
Именованная ветка: `codex/wms667-stock-filter`.

## Основа и сохранность контракта

Перед ревью выполнен `git fetch origin etalon`; полностью прочитаны
`origin/etalon:AGENTS.md` на `0f1460b023700a99f17b504d6af3934a02bc68cc`,
`docs/reviews/2026-09-11-analyst-draft/owner-cases.md` (104 строки),
`failure-cases.md` (359 строк), `docs/requirements/WMS-667.md` и оба README
контракта/реализации. Исторические случаи применены как направления проверки,
без переноса чужих требований или блокировок.

Контракт `463b03825dec5fdca43a39c117e7afc4080c0508` — непосредственный родитель
проверенного продукта. Между ними нет изменений backend/tests, DOM-контракта,
guards или требований. Прочитаны исходные тесты, не только отчёт разработчика.
Сохранённые RED-результаты тестировщика относятся к этапу до реализации;
повторный прогон старого продукта в этом ревью не выполнялся.

Единственное изменение ревью — этот файл. Исходные чужие untracked-файлы
`urgent667_analyst-result.txt` и `urgent667_tester-result.txt` не открывались,
не менялись и не включаются в коммит. Продукт, тесты, требования и guards
остаются на точном проверенном SHA по содержимому.

## Вывод по реализации

API принимает булев `has_stock`, по умолчанию false. В сервисе каталога
условие входит в тот же набор SQL-фильтров, который применяется перед
`count`, сортировкой и `limit/offset`. Проверено отсутствие локального отбора
только внутри уже загруженной страницы. `scope_total` и категории сохраняют
прежние области расчёта.

Новый SQL-конструктор содержит прежнюю сумму `InventoryBalance.quantity`
по организации и товару. Он не вычитает резерв и не ограничивает расположение.
Существующий `_organization_on_hand_by_product` добавляет к этому запросу
прежнее ограничение по product_ids. Результаты для пустого списка, подмножеств,
повторённого ID, отсутствующего товара и другой организации сопоставлены
с исходным SQL-выражением до выделения общей функции. Расхождений нет.
Остальные части расчёта резерва/доступного и его потребители не менялись.

Фильтр сохраняет положительный остаток при полном резерве и отрицательном
доступном количестве; нулевая сумма положительных/отрицательных строк не
попадает в результат. Границы организации и существующий отказ сотруднику
без прав подтверждены контрактом. Зависимость проверки прав API не изменена.
Сочетания селлера, площадки, категории, поиска и передачи остатков проверены
через настоящий API и БД.

В интерфейсе использованы существующие Checkbox/FormControlLabel внутри
текущего блока фильтров. Переключение сбрасывает страницу в том же обработчике;
остальные выбранные условия остаются. Состояние выбора строк очищается прежним
механизмом смены фильтров. Прочитаны оба места проверки отменённого запроса:
после ответа каталога и после ответа сводки. Дополнительные DOM-пробы подтвердили,
что оба вида позднего успешного ответа не заменяют новую выборку и счётчик.

Настройки публикации и лимиты не меняются от GET. Сохранность правила
`min(лимит оператора, свободный остаток)` и независимости WB/Ozon проверена
существующим guard через подменённый внешний транспорт. Изменений публикации
в diff нет. Документа/отдельного контракта WMS-670 на проверенном SHA нет;
это подтверждение сохранности существующего поведения, не отдельная приёмка WMS-670.

## Независимое выполнение

Создан новый PostgreSQL 17 cluster во временном каталоге ревью. Порт выбран
через успешный bind на loopback, затем сервер успешно запущен на `127.0.0.1:64363`.
До тестов `pg_stat_activity` показал 0 других клиентских соединений.
База: `wms_test667_review`. Ни 51756, ни 6517, ни 56767 не использовались
для подключения или остановки. Кластер разработчика не переиспользован.
Параметры: max_locks_per_transaction=1024, shared_buffers=16MB,
max_connections=10; единый session asyncio loop согласно фикстурам проекта.
Все изменения данных выполнялись только в созданной тестовой БД.
После прогонов собственный кластер остановлен через pg_ctl; повторное
подключение к 64363 отклонено. Чужие процессы не останавливались.

| Независимый прогон | Результат |
|---|---|
| PostgreSQL: WMS-667 + WMS-418 | 17 PASS |
| PostgreSQL: WMS-530 + WMS-538 | 14 PASS |
| PostgreSQL: test_fbs_stock_availability.py | 7 PASS |
| PostgreSQL: guards/test_guard_stock_publication.py | 1 PASS |
| Суммарный PostgreSQL-прогон выше | **39 passed**, 65.13 s |
| Дополнительная матрица API и сопоставление старого/выделенного SQL | **2 passed** |
| Замороженный DOM-контракт + соседний seller URL filter | **6 passed** |
| Дополнительные поздние ответы каталога и сводки, настоящий компонент | **2 passed** |
| `git diff --check` | PASS |

Матрица ревью: 18 товаров, по три строки расположения, отрицательные/нулевые/
положительные суммы, резерв 20, раздельные WB/Ozon-флаги и legacy null для Ozon.
Для десяти сочетаний фильтров сопоставлены полный обычный результат и страницы
по 3 строки с `has_stock=true`, включая последнюю пустую страницу, total,
scope_total и категории. Отдельно проверены `false`, `0` и отказ 422 для
`has_stock=unknown`. Дополнительные пробы сохранены ниже для воспроизведения;
опубликованные тесты не менялись.

Внешние HTTP-вызовы запрещены фикстурой каталога; guard публикации использует
тестовый транспорт. Ни production, ни живой учёт, ни Telegram не затронуты.
Секреты и кабинеты учётных данных не использовались и не менялись.

Первый запуск временного DOM-harness потребовал исправить путь `/var` на
канонический `/private/var` и явно включить automatic JSX в отдельном config.
Эти ошибки окружения до выполнения сценариев не являются дефектами продукта.
Итоговые две пробы прошли на неизменённом компоненте.

SQLite 17 PASS, ruff/mypy, tsc/build — результаты разработчика из README;
ревьюер не выдаёт их за свой повторный прогон. Полный CI, приёмка аналитика,
C10 и деплой этим ревью не подтверждены. Main/etalon не изменяются.

## Команды основного прогона

Из backend, с Python `/Users/deniscivkunov/Projects/WMS/backend/.venv/bin/python`,
`WMS_TEST_DATABASE_URL` указывает только на созданную loopback-базу,
`WMS_TEST_DATA_DIR` — во временный каталог ревью:

```sh
python -m pytest -n 0 \
  -o asyncio_default_fixture_loop_scope=session \
  -o asyncio_default_test_loop_scope=session \
  tests/test_wms667_catalog_has_stock_contract.py \
  tests/test_wms418_catalog_publication_filter.py \
  tests/test_wms530_single_stock.py tests/test_wms538_ff_catalog_batch.py \
  tests/test_fbs_stock_availability.py \
  tests/guards/test_guard_stock_publication.py --tb=short -q
```

Из frontend:

```sh
npm run test:unit -- \
  src/screens/v2/FfProductsCatalogScreen.hasStock.wms667.dom.test.tsx \
  src/screens/v2/FfProductsCatalogScreen.sellerUrlFilter.dom.test.tsx
```

## Воспроизводимые дополнительные пробы

Следующий Python-код сохранён во временном `test_review.py` вне checkout.
Запуск из backend: те же переменные изолированной БД и параметры asyncio,
`python -m pytest -p tests.conftest -n 0 -o asyncio_mode=auto ... /ABS/test_review.py`.
Импортирована только готовая фикстура каталога; существующие assertions не изменены.

```python
import uuid
import pytest
from sqlalchemy import select, func
from tests.test_wms667_catalog_has_stock_contract import catalog
from app.db.session import SessionLocal
from app.models.inventory_balance import InventoryBalance
from app.models.product import Product
from app.services.fbs_stock_availability_service import _organization_on_hand_by_product

@pytest.mark.asyncio
async def test_review_matrix(catalog):
    expected = []
    for i in range(18):
        quantities = [i % 5 - 2, (i * 3) % 7 - 3, (i * 7) % 9 - 4]
        pid = await catalog.add(f'P{i:02d}', quantities[0], seller=i % 2,
            category='X' if i % 3 else 'Y', ozon=True, reserved=20)
        async with SessionLocal() as session:
            product = await session.get(Product, uuid.UUID(pid))
            product.fbs_stock_sync_enabled = bool(i % 2)
            product.fbs_ozon_stock_sync_enabled = [None, False, True][i % 3]
            session.add_all([InventoryBalance(tenant_id=catalog.tenant,
                product_id=uuid.UUID(pid), storage_location_id=catalog.locations[j],
                quantity=quantities[j]) for j in [1, 2]])
            await session.commit()
        if sum(quantities) > 0: expected.append(pid)
    summary = await catalog.summary()
    assert {pid for pid, row in summary.items() if row['quantity'] > 0} == set(expected)
    assert all(summary[pid]['available'] < 0 for pid in expected)
    for extra in [{}, {'marketplace':'ozon'}, {'seller_id':str(catalog.sellers[0])},
                  {'category':'X'}, {'search':'P0'},
                  *[{'stock_publication':value} for value in ['wb','ozon','both','any','none']]]:
        base = await catalog.page(limit=200, **extra)
        wanted = [row['id'] for row in base['items'] if row['id'] in expected]
        actual = []
        for offset in range(0, len(wanted) + 3, 3):
            page = await catalog.page(has_stock=True, limit=3, offset=offset, **extra)
            assert page['total'] == len(wanted)
            assert page['scope_total'] == base['scope_total']
            assert page['categories'] == base['categories']
            assert [row['id'] for row in page['items']] == wanted[offset:offset+3]
            actual.extend(row['id'] for row in page['items'])
        assert actual == wanted
    for value in ['false','0']:
        page = await catalog.page(has_stock=value, limit=200)
        assert page['total'] == 18
    invalid = await catalog.client.get('/products/ff-catalog-page', headers=catalog.headers,
        params={'has_stock':'unknown'})
    assert invalid.status_code == 422

@pytest.mark.asyncio
async def test_review_extraction_matches_original_for_subsets(catalog):
    pids = [uuid.UUID(await catalog.add(f'S{i}', qty)) for i, qty in enumerate([5, -2, 0, None])]
    async with SessionLocal() as session:
        for subset in [[], pids, pids[:1], pids[1:], [pids[0],pids[0]], [uuid.uuid4()]]:
            original = select(InventoryBalance.product_id,
                func.coalesce(func.sum(InventoryBalance.quantity), 0)).where(
                InventoryBalance.tenant_id == catalog.tenant,
                InventoryBalance.product_id.in_(subset)).group_by(InventoryBalance.product_id)
            oracle = {pid: int(qty or 0) for pid, qty in (await session.execute(original)).all()}
            assert await _organization_on_hand_by_product(session, catalog.tenant, subset) == oracle
            assert await _organization_on_hand_by_product(session, uuid.uuid4(), subset) == {}
```

Для DOM-проб использована начальная часть замороженного файла
`FfProductsCatalogScreen.hasStock.wms667.dom.test.tsx` до первого `it('c8_`:
тот же mount, фикстуры HTTP и helpers. Импорт компонента заменён абсолютным
путём к проверенному checkout; ниже добавлены только новые сценарии.
Временный каталог использует node_modules проекта, config:
`{ esbuild: { jsx: 'automatic' }, test: { environment: 'jsdom', include: ['race.test.tsx'] } }`.
Запуск: `vitest run --root /ABS/TEMP --config /ABS/TEMP/vitest.config.mjs`.
Задержанный транспорт намеренно разрешает старый Promise даже после abort,
чтобы проверить защиту самого компонента.

```tsx
it.each(['catalog', 'summary'])('review late %s response cannot replace newer checkbox selection', async (stage) => {
  await mount()
  const delegate = globalThis.fetch
  let release!: (value: Response) => void
  let heldSignal: AbortSignal | null | undefined
  vi.stubGlobal('fetch', vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
    const url = new URL(String(input), 'http://test')
    const hold = stage === 'catalog'
      ? url.pathname.endsWith('/products/ff-catalog-page') && url.searchParams.get('has_stock') === 'true'
      : url.pathname.endsWith('/operations/inventory-balances/summary') && url.searchParams.getAll('product_id').includes('late-positive')
    if (hold) {
      heldSignal = init?.signal
      return new Promise<Response>((resolve) => { release = resolve })
    }
    return delegate(input, init)
  }))
  await toggleStock()
  expect(release).toBeTypeOf('function')
  await toggleStock()
  expect(heldSignal?.aborted).toBe(true)
  expect(host.querySelector('[data-testid="ff-product-row"]')?.textContent).toContain('ordinary-zero')
  await act(async () => release(response(stage === 'catalog'
    ? { items: [row('late-positive')], total: 1, scope_total: 999, categories: ['STALE'] }
    : [{ product_id: 'late-positive', quantity: 999, reserved: 0, available: 999 }])))
  await settle()
  expect(host.querySelector('[data-testid="ff-catalog-filter-count"]')?.textContent).toBe('Найдено: 101 из 120')
  expect(host.querySelector('[data-testid="ff-product-row"]')?.textContent).toContain('ordinary-zero')
  expect(host.textContent).not.toContain('late-positive')
  expect(host.querySelector<HTMLInputElement>('[data-testid="ff-catalog-has-stock-filter"] input')?.checked).toBe(false)
})
```
