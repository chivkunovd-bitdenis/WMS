# WMS-669: независимая проверка 43cdb021 — FAIL

Дата: 06.10.2026. Проверен точный продуктовый commit
`43cdb021fe9e205be7731c86bdf4d878992aae71` относительно замороженного контракта
`d7f4633912b066f740efdb2ce1ecabfba356755d`.

**Вердикт: FAIL — два воспроизведённых дефекта соответствия SQL существующему
обогащению карточек.** Основные автоматические сценарии проходят, но они не
покрывают приведённые ниже варианты исходного JSON. Нужны локальные исправления
SQL-выражений, без новой схемы или источника данных. Ручная C11 не проводилась
и не является основанием FAIL.

Запрошенный профиль ревью — Astra HIGH. Метаданные текущей сессии не позволяют
независимо удостоверить её точную модель и effort; этот документ подтверждает
выполненные проверки, а не удостоверяет запуск Astra HIGH. Другие модели,
вложенные агенты и навыки не запускались; effort не повышался.

## F1 · P2: SQL сортирует по иной категории, чем показывает строка

Место: `backend/app/services/seller_fulfillment_catalog_service.py:537`;
использование результата в группировке — строки 647–666, 748–755.
Нарушено R5: категория → артикул → размер должны образовывать последовательные
группы до пагинации.

Новый SQL берёт необработанное `raw_json["subjectName"]`. Между тем существующий
`subject_name_from_card()` в `wb_card_enrichment.py:41` удаляет наружные пробелы
и поддерживает запасное поле `subject_name`. Именно этот helper формирует
категорию товарной строки и импортированной карточки, которую группирует экран.

В собственной SQLite созданы три WB-карточки одного селлера с одним артикулом
`review-spaces` и размером 48. Значения `subjectName` соответственно:
`" Футболки "`, `"Пуховики"`, `"Футболки"`. Запрос сервиса с
`article="review-spaces", group_by="category_article_size"` вернул показанные
категории **Футболки → Пуховики → Футболки**. На экране одна категория окажется
двумя отдельными группами. Это воспроизводится на строковых данных с обычными
наружными пробелами, без неверных типов JSON.

Второй воспроизведённый вариант: первая карточка хранит
`{"subject_name":"Футболки"}`, две следующие — обычный `subjectName` с
Пуховиками и Футболками. Результат тот же:

```text
CATEGORY_ORDER [('wb:669901', 'Футболки'), ('wb:669902', 'Пуховики'), ('wb:669903', 'Футболки')] total 3
PAGINATION_STABLE True
CANONICAL_CATEGORY_SPACES [('wb:669911', 'Футболки'), ('wb:669912', 'Пуховики'), ('wb:669913', 'Футболки')]
```

Уникальные ключи и повторяемость страниц в этом примере сохранены; дефект —
именно порядок отображаемых групп, а не потеря строк. Минимальное исправление:
строить SQL-категорию по семантике уже существующего helper и использовать её
для порядка. Прежнюю проблему фильтра категории этот вывод не объявляет новой:
замечание относится к добавленному порядку группировки.

## F2 · P2: SQL принимает числовой techSize, который отображение отвергает

Место: `backend/app/services/seller_fulfillment_catalog_service.py:475–478`.
Нарушены R2/R6: фильтр размера должен соответствовать размеру, реально показанному
у карточки, включая существующий fallback с techSize на wbSize.

Модель `SellerWildberriesImportedCard.raw_json` хранит исходный JSON без схемы
вложенных полей. Существующие `_size_label()` и `_size_label_from_entry()` принимают
только непустые строки: числовой techSize игнорируется и используется строковый
wbSize. Новый SQL преобразует techSize в текст без проверки типа и останавливает
`coalesce` на этом значении.

Воспроизведение: одна импортированная карточка `wb:669904`, артикул
`review-numeric`, исходные размеры `[{"techSize":148,"wbSize":"48"}]`.
Чтение без фильтра возвращает `sizes=["48"]`. Однако фильтр 48 исключает карточку
из page и keys, а фильтр 148 возвращает её с по-прежнему показанным размером 48:

```text
NUMERIC_SIZE None [('wb:669904', ['48'])] keys ['wb:669904']
NUMERIC_SIZE 48 [] keys []
NUMERIC_SIZE 148 [('wb:669904', ['48'])] keys ['wb:669904']
```

Это проверка неполного/некорректно типизированного сырого поля, которое прежнее
отображение уже умеет обрабатывать; наличие такой карточки в production не
утверждается. Дефект воспроизведён на SQLite. В PostgreSQL SQL также не содержит
проверки строкового типа, но новый прогон PostgreSQL здесь не выполнялся.
Минимальное исправление: повторить существующий выбор строкового techSize/wbSize
в SQL; не менять отображаемое значение или требования под SQL.

## Как повторить оба дефекта без правки тестового контракта

Из `backend` проверяемого checkout выполнить следующий код установленным Python
окружения проекта. `conftest` создаёт собственную SQLite с PID в имени; рабочие
базы не используются. Вызывать только с очищенными переменными выбора тестовой
базы: `env -u WMS_TEST_DATABASE_URL -u WMS_TEST_DATA_DIR <python> -`.
Код использует существующую подготовку данных и реальные сервисы напрямую,
без HTTP-порта и внешних API. Чужие файлы и зафиксированные тесты не меняются.

```python
import asyncio
from tests import conftest
from tests.wms669_catalog_fixtures import catalog
from app.db.session import SessionLocal, engine
from app.models.seller_wildberries_imported_card import SellerWildberriesImportedCard as Card
from app.services.seller_fulfillment_catalog_service import (
    list_seller_catalog_page as page,
    list_seller_catalog_keys as keys,
)

async def main():
    await conftest._reset_database()
    c = await catalog.__wrapped__(None)
    async with SessionLocal() as s:
        for nm, subject in [(669911, ' Футболки '),
                            (669912, 'Пуховики'), (669913, 'Футболки')]:
            s.add(Card(tenant_id=c.tenant, seller_id=c.seller, nm_id=nm,
                       vendor_code='review-spaces', raw_json={
                           'subjectName': subject, 'sizes': [{'techSize': '48'}]}))
        s.add(Card(tenant_id=c.tenant, seller_id=c.seller, nm_id=669904,
                   vendor_code='review-numeric', raw_json={
                       'sizes': [{'techSize': 148, 'wbSize': '48'}]}))
        await s.commit()
        rows, _, _, _ = await page(s, c.tenant, c.seller,
            article='review-spaces', group_by='category_article_size')
        print('categories:', [r['category'] for r in rows])
        for size in [None, '48', '148']:
            args = dict(article='review-numeric', size=size)
            rows, _, _, _ = await page(s, c.tenant, c.seller, **args)
            print('size:', size, [(r['key'], r['sizes']) for r in rows],
                  'keys:', await keys(s, c.tenant, c.seller, **args))
    await engine.dispose()
    conftest._TEST_DB_PATH.unlink(missing_ok=True)

asyncio.run(main())
```

## Что независимо проверено и что осталось за границей

Прочитаны AGENTS.md и полный текст owner-cases.md/failure-cases.md из
`docs/reviews/2026-09-11-analyst-draft`, требования WMS-669 и тестовая передача.
После `git fetch origin etalon` актуальный etalon —
`0f1460b023700a99f17b504d6af3934a02bc68cc`; его AGENTS.md совпадает с локальным.
Дифф от тестового SHA до продуктового содержит только API каталога, сервис
каталога и SellerProductsStockScreen. Требования, тесты, фикстуры, тестовая
передача и guards не изменены. Исходный RED сохранён тестировщиком до реализации;
старый код повторно здесь не запускался.

Независимый целевой прогон из backend:

```sh
env -u WMS_TEST_DATABASE_URL -u WMS_TEST_DATA_DIR /Users/deniscivkunov/Projects/WMS/backend/.venv/bin/python -m pytest -n 1 tests/test_wms669_seller_catalog_contract.py tests/test_wms669_seller_catalog_once.py tests/test_wms548_seller_catalog_page.py tests/test_seller_wb_catalog_isolation.py -q --tb=short
```

Результат: **36 passed, 1 skipped**, 23.67 s. Один worker, собственная SQLite;
пропуск — только PostgreSQL C10. Проверено пересечение точных фильтров, quantity
до count/limit/offset, полностью зарезервированный положительный остаток,
совпадение page/keys, границы организации/селлера/магазина/площадки и отсутствие
изменений балансов, резервов, лимитов и карточек при чтении.

Независимый целевой прогон из frontend:

```sh
npm run test:unit -- src/screens/v2/Wms669SellerCatalog.dom.test.tsx src/screens/v2/SellerCatalogAsync.dom.test.tsx
```

Результат: **32 passed**, два файла, 13.97 s. Настоящий компонент с подменённым
HTTP-транспортом: сохранение выбора, сброс страницы, группы без товарных ключей,
поздние ответы поиска/фильтра/селлера, очистка прежних строк и остатков.
Дополнительно прочитаны проверки актуальности ответа до и после JSON/error body.

Дополнительные прямые проверки SQL на собственной SQLite: товар с пустым
`wb_size` и карточкой 46/48 находится только по своему штрихкоду варианта 48,
не по 46 или 148; тот же результат при запасном штрихкоде из ProductBarcode.
Разворачивание JSON коррелировано с карточкой, соединение карточки ограничено
tenant/seller/nmID. Набор из 12 размеров с повтором сохраняет исходный порядок
уникальных подписей. Серверный порядок заканчивается kind/raw_key; страницы
с limit=1 стабильны и не дублируют строки. Новый источник остатка, схема или
пишущее действие в проверяемом диффе не добавлены.

Заявленные разработчиком **31 PostgreSQL PASS**, ruff, mypy по 551 файлу,
tsc/build PASS здесь не повторялись и не выдаются за независимый новый прогон.
Остановленный PostgreSQL не запускался, новый не устанавливался. Браузер,
Chrome, live DB/API, кабинеты/значения секретов, Telegram и деплой не использованы.
C11 визуально не проверена; полный CI, приёмка аналитиком, merge и выпуск не
заявляются. Ревью изменяет только этот документ; исправления остаются исполнителю.
