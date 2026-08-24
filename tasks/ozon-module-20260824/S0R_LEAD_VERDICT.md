# Вердикт ведущего по replacement S0R

**Дата:** 24 августа 2026 года
**Call:** `11-ozon-reuse-replacement-prototype`
**Вердикт:** `PRODUCT_REWORK_REQUIRED` — продуктовый diff не коммитить как принятый результат.

## Находка S0R-LEAD-001: reuse-first соблюдён по путям файлов, но нарушен по фактическому UI

Prototype заменяет существующий FBS render ранним `return <OzonQueueFixture>` и существующий FBS workspace ранним `return <OzonFbsWorkspaceFixture>`. Это два параллельных интерфейса, спрятанных внутри разрешённых файлов. Они не проверяют, как Ozon действительно укладывается в текущую таблицу, выбор, существующие четыре стадии и WB-регрессию.

В `FfSuppliesShipmentsPage` добавлен отдельный Ozon-only modal document с собственной шапкой, полями, декоративными вкладками и футером. Он имитирует существующий документ вместо расширения его настоящих create/header/tabs/packaging/footer зон.

Эта находка ломает основную операторскую работу: зелёный prototype не доказывает, что один и тот же FBS/FBO процесс обслужит WB и Ozon без переключения на параллельный UI. Это именно тот продуктовый дефект, из-за которого владелец отклонил предыдущий S0.

## Находка S0R-LEAD-002: machine gate даёт ложноположительный результат

`check_ozon_reuse_scope.py` проверяет разрешённые пути файлов и строки новых routes, но пропускает:

- раннюю полную замену существующего screen/workspace по `ozonPrototype`;
- новый Ozon-named component, который возвращает весь screen/workspace;
- новый Ozon-only modal document с собственной копией tabs/header/footer.

Self-test обязан отдельно доказывать, что каждый из этих трёх паттернов отклоняется. Пока это не сделано, gate не является требуемым машинным ограничением reuse-first.

## Находка S0R-LEAD-003: заявленная полнота не подтверждена

FBO tabs имеют фиксированное `value={0}` и не переключают реальные существующие зоны. Returns report прямо называет полноценную проверку возврата «next bounded fixture slice». Поэтому обязательные click paths из `ARCH.md` фактически не завершены.

## Обязательный результат rework

1. Удалить `OzonQueueFixture`, `OzonFbsWorkspaceFixture` и любые ранние `return`-подмены по prototype-флагу.
2. Подать fixture-данные и состояния в существующий render и существующие обработчики/зоны FBS; WB row остаётся в той же таблице и текущий workspace остаётся тем же компонентом.
3. Удалить Ozon-only shipment modal. Prototype должен выбрать Ozon в текущем create block и показать условные Ozon-поля в настоящей шапке, настоящих трёх tabs, packaging zone и footer существующего документа.
4. Завершить реальные clickable paths для FBO и returns, не заявлять будущую slice как выполненную.
5. Усилить gate и его self-test тремя отрицательными паттернами выше.
6. Не расширять scope: каталог и settings остаются в существующих action/dialog/card patterns; новых surface нет.

## Результат correction round 1 (`12-ozon-reuse-prototype-correction`)

Структурная часть S0R-LEAD-001 исправлена: ранние подмены удалены, FBO действительно перенесён в state/header/tabs/packaging/footer существующего документа, return — в очередь и строку существующей приёмки. Усиленный gate теперь ловит прежние параллельные UI-паттерны.

### Находка S0R-LEAD-004: FBS остался некликабельной декорацией вместо обязательного процесса

`createOzonFixtureWorkspace()` сразу создаёт состояние `handoff_prep` с прогрессом picked/packed `3/3` и единственным order/product, в чьё имя записан текст «2 товара / 3 шт». Это не демонстрирует две реальные товарные линии и три единицы. `scanLocation`, KIZ/exemplar, print/label и часть box-действий всё ещё идут в настоящие backend-функции либо недоступны из-за финального fixture state. Обязательные переходы unmapped mapping → scans → rejected/corrected exemplar → partial package → label pending/ready/applied → one-by-one handover отсутствуют.

Отчёт ослабил исходное требование до «click all four existing stages», хотя `ARCH.md` требует выполнить конкретные действия и увидеть их результаты. Это не принимается.

### Обязательный результат correction round 2

Внутри существующего `FfFbsSupplyWorkspace` добавить локальную fixture-state machine, не отдельный workspace:

1. Начальное состояние — `composition`, две товарные линии и три unit/order projections, одна линия unmapped.
2. Подтверждение fixture mapping разблокирует существующий переход в подбор.
3. `scanLocation` и `scanProduct` в fixture mode меняют только локальный workspace и никогда не вызывают API; нужны три подтверждённые единицы по двум линиям.
4. В существующей packing zone показать rejected exemplar, его correction и partial package 2/3; переход к boxes только после исправления.
5. В существующей boxes/print zone провести label `pending → ready → applied`, показать box/package relation, выбрать discovered one-by-one handover и получить честное pending confirmation сообщение.
6. Сохранить один настоящий render, STAGES, dialog и stage navigation; WB path без query не менять.
7. Browser report обязан перечислять исходный полный click path, а не только просмотр вкладок.
