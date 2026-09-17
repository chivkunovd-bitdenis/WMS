# Вердикт: PASS

Перекрёстное ревью Astra по WMS-437, 17.09.2026. Подтверждённых блокирующих дефектов в реализации WMS-456 не найдено. Вердикт относится к бэкенду коммита `17dacfb3d9f6aa67cd708c630f45fe665674d236` относительно `4474ac96`, а не к приёмке интерфейса, выпуску всего пакета или production.

Рабочий каталог: `/Users/deniscivkunov/Projects/WMS/.worktrees/wms456-night`, ветка `fix/wms456-ozon-publish`. Каталог, ветка и HEAD проверены командами `pwd`, `git branch --show-current`, `git rev-parse HEAD`. Перед работой `git status --short` был пуст. Код и тесты не изменялись, коммиты не создавались — по прямому поручению владельца результатом является только этот файл.

До проверки реализации целиком прочитаны `/Users/deniscivkunov/Projects/WMS/AGENTS.md`, обе библиотеки `owner-cases.md` и `failure-cases.md` из `docs/reviews/2026-09-11-analyst-draft/` основного проекта, а также `docs/requirements/WMS-454.md`, `WMS-456.md`, `WMS-457.md` рабочего каталога. WMS-454/457 использованы только как контекст. Исторические сведения из библиотек не считаются воспроизведением сегодняшнего production.

## Находки

### F1 — риск: конкурентное выполнение на PostgreSQL в этом ревью не проверено экспериментально

**Места:** `backend/app/services/fbs_stock_rule_service.py:692–717,849–857,883–918`; `backend/app/services/marketplace_seller_lock_service.py:49–61`; `backend/tests/test_wms351_publication_concurrency.py:25–33`.

В сохранении остались блокировки продавца в последовательности Ozon → WB, повторное чтение товаров с `FOR UPDATE` и запись под этими блокировками; новый запрос карточек Ozon находится после блокировки товаров. Публикация после сохранения использует существующую очередь до commit, а отправка начинается в `after_commit`: `backend/app/services/fbs_stock_publish_service.py:148–185`. Фоновая отправка берёт блокировку той же площадки продавца: там же, `55–80`. Объединение карточек также блокирует товары перед переносом связей: `backend/app/services/product_merge_service.py:325–341,363–365`. Нового механизма записи вне этих границ diff не добавляет.

Однако SQLite не исполняет PostgreSQL advisory lock: сервис возвращает ключ без захвата блокировки на строках `49–51`. Оба варианта `test_final_zero_serializes_wb_writers` были пропущены с условием `requires isolated PostgreSQL`. Поэтому успешный прогон не доказывает сериализацию конкурирующих запросов на PostgreSQL. Это ограничение доказательств по R5 и разделу 4 AGENTS.md, **не подтверждённый дефект и не блокировка данного ревью**: PostgreSQL прямо исключён из доступного ревьюеру контура.

**Как проверить:** на изолированной тестовой PostgreSQL выполнить `tests/test_wms351_publication_concurrency.py` с настроенным `WMS_TEST_DATABASE_URL`; проверка должна выполнить оба сценария, а не вернуть skip. Не использовать рабочую базу: `backend/tests/conftest.py:40–65` пересоздаёт/очищает тестовые таблицы. В этом ревью такая проверка не заявляется выполненной.

### F2 — замечание без блокировки: два HTTP-теста требуют установленный TypeScript, но не проверяют его наличие

**Места:** `backend/tests/test_wms417_stock_http_contract.py:31–34,110–118,256–264,326`; сравнение с `git show 4474ac96:backend/tests/test_wms417_stock_http_contract.py` подтвердило, что отсутствие проверки у сценария совпадающих номеров складов было и в базе.

В рабочем каталоге не установлен `frontend/node_modules/typescript`. Первые два теста файла в этой ситуации делают skip (`117–118`), а два варианта `test_colliding_wb_ozon_ids_survive_actual_frontend_http_edit` запускают Node без аналогичной проверки и падают до выполнения сформированного PUT. Отдельная команда `node -e 'console.log(require.resolve("typescript"))'` из frontend подтвердила `MODULE_NOT_FOUND: Cannot find module 'typescript'`.

Это проблема воспроизводимости тестового окружения, а не обнаруженная регрессия бэкенда WMS-456. Она не нарушает R1–R6 реализации. После предоставления Node уже установленного TypeScript из основного проекта через `NODE_PATH` оба упавших сценария прошли, без изменения исходников или установки зависимостей. Их результат можно учитывать как проверку HTTP-контракта второго маршрута, но не как браузерную приёмку.

**Как воспроизвести/проверить:** выполнить этот файл pytest в данном checkout без frontend-зависимостей; затем повторить только `-k colliding` с `NODE_PATH=/Users/deniscivkunov/Projects/WMS/frontend/node_modules`. Фактические результаты приведены ниже. Для обычного автономного прогона файла нужна штатная установка frontend-зависимостей.

## Что проверено и в порядке по требованиям

Все ссылки ниже относятся к текущему HEAD. Требования — `docs/requirements/WMS-456.md:99–146`.

### R1 — эффективный флаг зависит от активной карточки

`_effective_publish_ozon` возвращает false без карточки и сохраняет наследование NULL → WB при наличии карточки (`backend/app/services/fbs_stock_rule_service.py:323–340`). `rule_from_product` использует именно этот результат (`343–371`). Признак карточки берётся существующим пакетным запросом с ограничением tenant, product_id, marketplace="ozon", is_active=true (`backend/app/services/catalog_service.py:794–809`), что совпадает с критерием значка каталога (`backend/app/api/products.py:993–1005`). Нового поля или второго сохранённого признака нет.

Одиночный GET и массовое чтение используют соответствующие сервисы и выводят `view.rule.publish_ozon` (`backend/app/api/products.py:1599–1642,1645–1676`). Все три вызова `rule_from_product` передают обязательный `has_ozon_link`: строки `554–556,722–724,1013–1015` сервиса; других вызовов поиск `rg` по backend не нашёл. Тест C1 проходит (`backend/tests/test_wms456_ozon_card_gate.py:201–221`); наследование у связанного товара проверяет также `backend/tests/test_wms351_marketplace_publication_switches.py:55–58`. Дополнительная проверка PROBE-1 прошла все 12 сочетаний активной/неактивной карточки, WB false/true и сохранённого Ozon NULL/false/true.

### R2 — товары без карточки не портят результат Ozon, настоящая ошибка остаётся ошибкой

`publish_amounts_for_binding` исключает товар без активной карточки из словаря результата, а не выдаёт ему ноль (`backend/app/services/fbs_stock_rule_service.py:980–992`). Штатный `sync_ozon_stocks` сначала проверяет присутствие товара в словаре и только затем валидирует идентификаторы карточки (`backend/app/services/ozon_fbs_sync_service.py:379–397`). Поэтому отсутствие карточки и карточка без пригодного идентификатора имеют разные результаты. Статусы nothing_to_publish и confirmed остаются в существующей логике (`413–425,448–459`).

C2–C4 вызывают настоящий `sync_ozon_stocks` и `OzonMarketplaceProvider` с `FakeMarketplaceTransport`; проверяют отправленный offer_id/stock/warehouse_id, счётчики ошибок и сохранённый статус привязки (`backend/tests/test_wms456_ozon_card_gate.py:224–317`). Все три теста прошли: только B отправлен с 50; только A не вызывает транспорт; карточка C без идентификаторов оставляет product_mapping_missing.

### R3 — сохранение и потолок WB-товара

Признак карточки применяется и к старому, и к новому эффективному правилу (`backend/app/services/fbs_stock_rule_service.py:715–757`); в базе записывается эффективное значение (`885–886`). Поэтому запрос publish_ozon=true без карточки сохраняет false. Потолок считает только направления с включённым эффективным флагом (`835–848`). Выбор обнуления и планирования использует сравнение правил по конкретной площадке (`584–603,761–769,849–857,915–918`). Для такого товара старое и новое состояние Ozon — false, поэтому обнуление и публикация Ozon не вызываются.

C5 подтверждает принятие 100% WB в обоих режимах процентов и отказ для двухплощадочного товара с total=200 (`backend/tests/test_wms456_ozon_card_gate.py:320–349`). C6 проверяет сохранённый false и отсутствие вызовов Ozon, затем изменение доли WB и планирование только WB (`352–393`). C7 проверяет повторное сохранение без повторной отправки (`396–430`). PROBE-2 дополнительно проверила смешанную пачку: один запрос сохраняет false для A без карточки и true для B с карточкой; повтор сохраняет те же представления правил.

### R4 — суммы и общий физический остаток

`split_amounts` для выключенной площадки записывает ноль и продолжает цикл до расходования `remaining` (`backend/app/services/fbs_stock_rule_service.py:404–442`). Чтение published_now и публикация получают одинаково построенное правило (`551–578,1013–1018`). C8 проверяет A: published_now=50, WB={A:50}, Ozon={}; B: WB=50, Ozon=50, published_now=100 (`backend/tests/test_wms456_ozon_card_gate.py:433–460`). Тест прошёл.

Общий потолок для товара с карточкой не ослаблен: существующие тесты 60+60 → отказ, 60+40 → 100 и фактические суммы публикации 60/40 проходят (`backend/tests/test_fbs_stock_rule_service.py:1071–1165`). Режим штук, общий остаток, резерв и однократное списание проверены соответствующими наборами из команды ниже. Нового учёта остатков в diff нет.

### R5 — независимость площадок, одноразовый ноль, соседние пути

Старые ожидания тестов не ослаблены. Добавлены активные карточки Ozon в заготовки, которые уже моделировали двухплощадочный товар. В тесте совпадающих номеров карточка возникает после первого сохранения: поэтому заготовка явно включает Ozon после её появления (`backend/tests/test_fbs_stock_rule_service.py:1207–1217`); это согласуется с решением 3 требований. Реальный путь последующего включения оператором отдельно проверяет C10 (`backend/tests/test_wms456_ozon_card_gate.py:497–539`).

WMS-351 проверяет комбинации флагов и served, однократный вызов обнуления, отсутствие повторного вызова и планирование только WB при его включении (`backend/tests/test_wms351_marketplace_publication_switches.py:15–95`). Ошибка подтверждения Ozon оставляет прежнее правило, последующий успешный повтор выключает публикацию (`214–273`); здесь подменяется внешний provider, а штатные сохранение и очистка выполняются. C9 подтверждает сохранность другого товара и Ozon-привязки при изменении WB-товара (`backend/tests/test_wms456_ozon_card_gate.py:463–494`).

Отдельно выполнен сценарий B10 через настоящие `set_rule_for_products`, `_clear_previous_ozon_stock` и `sync_ozon_stocks`, с подменой только транспорта/фабрики внешнего provider и отключением автоматической диспетчеризации: положительная публикация B → выключение Ozon → повторное сохранение OFF → три цикла Ozon. Полный список отправленных количеств остался `[50, 0]`, оба обращения относятся только к offer-b (PROBE-3). Бесконечный ноль в этом сценарии не воспроизведён.

WB-only продавцы и публикация WB проверены существующими `test_fbs_stock_rule_service.py`, `test_fbs_stock_sync.py`, `test_fbs_warehouse_binding.py`. Для второго маршрута прочитан штатный `saveRule` (`frontend/src/screens/ff/products-fbs/FfProductsFbsPage.tsx:206–237`); тесты WMS-417 извлекают именно эту функцию, строят тело запроса и отправляют его в настоящий ASGI API. Два сценария совпадающих идентификаторов WB/Ozon после устранения отсутствующей зависимости прошли. Сам экран не открывался и визуальное поведение не оценивалось.

### R6 — объём изменения и простота решения

`git diff 4474ac96..HEAD -- backend frontend` содержит один производственный файл (`fbs_stock_rule_service.py`) и семь файлов тестов. По frontend diff пуст; моделей, миграций и новых колонок нет. Массовой перезаписи данных не добавлено; false записывается только выбранным товарам при сохранении (`backend/app/services/fbs_stock_rule_service.py:883–918`). Признак карточки вычисляется существующим запросом, новая сущность не создана. Формула эффективного чтения общая для представления правила и публикации; при сохранении явный входной флаг отдельно ограничен тем же признаком карточки (`750–757`).

Семантика served не менялась. Существующее включение stock_sync_enabled при адресном изменении публикуемого правила осталось прежним (`875–881`), новой логики изменения привязок нет. C7/C9 и WMS-351 подтверждают сохранность соседних настроек в проверенных сценариях. Новых пользовательских запретов, окон, подсказок или изменений дизайна этот diff не содержит. Требования интерфейса WMS-454/457 этим выводом не принимаются.

## Команды и результаты

Команды запускались из `backend` данного checkout. Локальная PostgreSQL, браузер localhost и реальные кабинеты маркетплейсов не использовались.

1. `/Users/deniscivkunov/Projects/WMS/backend/.venv/bin/ruff check .` → `All checks passed!`.
2. `/Users/deniscivkunov/Projects/WMS/backend/.venv/bin/mypy --cache-dir=/private/tmp/wms456-astra-mypy .` → `Success: no issues found in 458 source files`. Изменён только путь технического кэша проверки.
3. Основной целевой прогон:

```sh
/Users/deniscivkunov/Projects/WMS/backend/.venv/bin/python -m pytest -q -p no:cacheprovider \
  tests/test_wms456_ozon_card_gate.py \
  tests/test_fbs_stock_rule_service.py \
  tests/test_wms351_marketplace_publication_switches.py \
  tests/test_wms351_publication_concurrency.py \
  tests/test_fbs_ozon_lane.py \
  tests/test_ozon_stock_binding_cleanup.py \
  tests/test_fbs_stock_sync.py \
  tests/test_fbs_warehouse_binding.py \
  tests/test_fbs_pr140_shipment_write_off.py \
  tests/test_fbs_stock_models.py \
  tests/test_wms417_stock_http_contract.py
```

Результат: `2 failed, 239 passed, 4 skipped, 5 warnings in 34.32s`. Две ошибки — отсутствие TypeScript (F2); два skip — PostgreSQL (F1), ещё два — проверка наличия frontend TypeScript в первых сценариях WMS-417. Предупреждения — DeprecationWarning типов Swig.

4. Повтор упавших сценариев с доступной установленной зависимостью:

```sh
NODE_PATH=/Users/deniscivkunov/Projects/WMS/frontend/node_modules \
  /Users/deniscivkunov/Projects/WMS/backend/.venv/bin/python -m pytest -q -p no:cacheprovider \
  tests/test_wms417_stock_http_contract.py -k colliding tests/test_product_fbs_rule_bulk_read_api.py
```

Результат: `2 passed, 7 deselected, 5 warnings in 1.64s`. Фильтр `-k colliding` исключил bulk-read тесты; они отдельно выполнены следующей командой.

5. `/Users/deniscivkunov/Projects/WMS/backend/.venv/bin/python -m pytest -q -p no:cacheprovider tests/test_product_fbs_rule_bulk_read_api.py` → `4 passed, 5 warnings in 2.66s`. Проверяются массовое чтение, границы tenant/продавца и лимит размера пачки.

6. Дополнительный одноразовый Python-прогон через stdin, без добавления файлов тестов. Использованы `tests.conftest._reset_database`, `SessionLocal`, настоящая заготовка `tests.test_wms456_ozon_card_gate._seed_case` и штатные сервисы. Вывод:

```text
PROBE-1 PASS: 12 active/inactive x WB x raw-Ozon flag combinations, real rule/read/publication services
PROBE-2 PASS: mixed bulk A without card / B with card, effective flags False/True, totals 50/100, repeat preserves views
PROBE-3 PASS: real Ozon publication and cleanup, stocks [50, 0], repeated OFF and 3 sync cycles add no zeros
```

Для повторения PROBE-1: для A создать карточку с is_active=false/true, перебрать WB=false/true и Ozon=NULL/false/true, сравнить GET-сервис и словарь публикации с `active and (WB if Ozon is None else Ozon)`. Для PROBE-2: сохранить одной пачке A/B явное publish_ozon=true и доли 50/50, перечитать правила и повторить сохранение. Для PROBE-3: после этой пачки вызвать sync Ozon, выключить только Ozon B через его прочитанное правило, повторить OFF и трижды вызвать sync; в `FakeMarketplaceTransport.published_stocks` должны остаться только stock=50 и stock=0 для B.

7. Проверка способности новых тестов обнаруживать исходный дефект: в отдельном Python-процессе загружен текст сервиса из `4474ac96` и выполнен в пространстве имён импортированного модуля; файлы checkout не менялись. Затем запущен только `test_wms456_ozon_card_gate.py`:

```python
import subprocess
import pytest
from tests import conftest
from app.services import fbs_stock_rule_service as rules
source = subprocess.check_output(
    ['git', 'show', '4474ac96:backend/app/services/fbs_stock_rule_service.py'], text=True,
)
exec(compile(source, 'BASELINE_4474ac96_fbs_stock_rule_service.py', 'exec'), rules.__dict__)
raise SystemExit(pytest.main([
    '-q', '-p', 'no:cacheprovider', '--tb=no', 'tests/test_wms456_ozon_card_gate.py',
]))
```

Результат: `9 failed, 1 passed, 2 warnings in 0.84s`; падают C1–C6 и C8–C10, проходит C7 (повторное сохранение). В основном прогоне на HEAD все десять прошли. Это проверка чувствительности новых тестов к замене изменённого сервиса базовой версией, а не полный запуск базового checkout. Предупреждения этого вспомогательного запуска — повторный импорт pytest-плагинов для assertion rewriting.

## Границы заключения

Подтверждённого дефекта, требующего возврата реализации Sonnet на исправление, не найдено. Результаты не заменяют браузерную приёмку аналитика и не доказывают работу production. Конкуренция PostgreSQL отмечена отдельно в F1. Фронтовые команды tsc/build/unit не запускались: фронт исключён из данного круга, его diff пуст. Пустые вердикты приёмки в документах требований не заполнялись ревьюером (`docs/requirements/WMS-456.md:219–222`): это отдельный этап аналитика. Ветка, требования и код оставлены без изменений.
