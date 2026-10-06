# WMS-662 — независимое ревью c36b8ab: FAIL F6

Дата: 06.10.2026. Проверен точный product SHA
`c36b8abee120e57b27e50d3358cfdc533cd411eb`, прежде всего delta двух служб
от тестового контракта `91c89c55370b81389ae2b9968869a674a6dbb723`.
Прямое поручение — независимое Astra high ревью без навыков и субагентов;
ownership ограничен этим новым отчётом. Полностью прочитаны AGENTS.md,
owner-cases.md, failure-cases.md и astra-review-ca4808f.md. После fetch правила
сверены с origin/etalon; различий AGENTS.md нет. Также прочитаны затронутые
вызывающие пути, контракт F4/F5, его RED-отчёт и передача разработчика.

**Итог: FAIL, новое P1 F6 — обратный порядок блокировок товара и селлера.**
F4/F5 в зафиксированных сценариях исправлены: самостоятельно воспроизведены
11 целевых PASS, 38 соседних PASS, атомарный откат неполного сторно и два
дополнительных сценария тарифов. Но новая блокировка селлера в отмене
образует достижимый цикл ожидания с передачей другого заказа того же товара.
Порядок SQL-запросов подтверждён исполнением реального кода на SQLite;
сам PostgreSQL deadlock не запускался и за воспроизведённое зависание не выдаётся.
Это ревью кода, не приёмка, CI или разрешение выпуска.

## F6 · P1 · Отмена берёт seller → product, передача — product → seller

Место изменения: `backend/app/services/fbs_cancellation_service.py:150–156`.
Новый `FOR NO KEY UPDATE` по Seller выполняется до завершения отмены и
снятия резерва, в том числе когда у отменяемого заказа вообще нет начислений.
Успешный выход из вложенной транзакции не завершает внешнюю транзакцию.

Реальный путь кнопки отмены:
`_lock_order` → `_finish_local_cancellation` → `reverse_fbs_order_billing`
берёт Seller; затем `_release_reservation` вызывает
`inventory_service.update_fbs_order_reservation`, который блокирует Product
через `lock_stock_product` (`inventory_service.py:58–70,137–140`).
Связи: `fbs_cancellation_service.py:225,244`,
`wb_marketplace_orders_service.py:506–509`.
У неприкреплённого, неподобранного заказа нет предшествующей блокировки товара:
`release_picks_of_cancelled_order` сразу возвращает 0 при supply_id=None.

Штатная передача другого Ozon-заказа сначала списывает товар и корректирует
резерв, удерживая Product, затем вызывает `charge_handed_over_orders` и
`record_fbs_order_confirmed`, который ждёт Seller (`fbs_shipment_service.py:
1268–1304`, `fbs_order_billing_service.py:213–218`). Наблюдаемая передача также
сохраняет порядок product → seller (`fbs_observed_handoff_service.py:849–869`).

Конкретное расписание: два разных заказа одного tenant/seller/product.
Заказ A входит в передаваемую поставку, заказ B без поставки отменяется.
Передача A успела заблокировать Product P; отмена B заблокировала Seller S.
Теперь A ждёт S, а B ждёт P. Общего заказа или поставки, которые заранее
сериализовали бы эти операции, нет. Обычная отмена не берёт advisory lock
`ozon-delivery`; он защищает только штатную передачу. Даже фоновые Ozon-запросы
используют другой ключ `ozon`, поскольку marketplace входит в хеш ключа.

Режимы блокировок проверены компиляцией **тех же исполняемых SQLAlchemy Select**
для диалекта PostgreSQL: `key_share=True` без `read=True` здесь даёт именно
`FOR NO KEY UPDATE`, не совместимый `FOR KEY SHARE`. При описанном расписании
оба ожидания конфликтуют. Время жизни блокировок и таблица конфликтов сверены
с [официальной документацией PostgreSQL, §13.3.2–13.3.4](https://www.postgresql.org/docs/current/explicit-locking.html#LOCKING-ROWS).

Независимая трассировка двух реальных путей, без изменения реализации:

```text
NORMAL_LOCK_ORDER {
 'cancel': ['sellers NO KEY UPDATE', 'products FOR UPDATE', 'COMMIT'],
 'handover': ['COMMIT', 'COMMIT', 'COMMIT', 'COMMIT', 'COMMIT',
              'products FOR UPDATE', 'products FOR UPDATE',
              'products FOR UPDATE', 'products FOR UPDATE',
              'sellers NO KEY UPDATE', 'COMMIT']
}
INVERSION_CONFIRMED: distinct order/supply scope, same seller/product;
actual normal handoff and local cancellation, no outer commit between conflicting locks
```

Дополнительная трассировка `_apply_status(..., 'cancelled', None)` и настоящего
observed sync дала тот же обратный порядок. Это **не параллельный PG-прогон**:
SQLite не исполняет эти построчные блокировки. FAIL основан на подтверждённом
порядке реальных запросов, достижимом расписании двух транзакций и правилах
конфликта PostgreSQL. Ни выбор транзакции-жертвы, ни длительность ожидания,
ни конкретный последующий финансовый результат экспериментально не установлены.

Нужно согласовать порядок seller/product во всех затронутых путях отмены и
передачи, сохранив полное атомарное сторно и границы tenant/order. Нельзя
исправлять это снятием защиты от конкурентного продолжения. Отдельный контракт
должен ставить две транзакции на барьеры между первыми и вторыми блокировками;
после исправления — проверить на согласованной изолированной PostgreSQL
завершение обеих операций, деньги, расход и резерв. Проверка общего сценария
«два опросчика одного заказа» этот случай двух разных заказов не заменяет.

## F4/F5 и прежние инварианты

| Область | Независимый результат |
|---|---|
| F4, V2 packing=document без legacy packing | PASS: первый счёт 1800, итог начислений 2800, preview и второй счёт ровно 1000. Оба счёта и их источники неизменны после повторов; третьей платы нет. |
| F5, Ozon после invoiced continuation | PASS: одна настоящая `reverse_fbs_order_billing` сторнирует все 4 active charges сборки/упаковки; баланс 0. Повтор сохраняет все поля всех ledger headers, исходные charges и первый счёт. |
| Ошибка внутри F5 | PASS: после третьего настоящего flush сторно внедрён RuntimeError. Все 3 сторно откатились, исходные 4 charges остались идентичны; внешний commit сохранил status=cancelled. Следующий вызов полностью обнулил баланс, ещё один повтор ничего не изменил; первый счёт прежний. |
| F1/F2, scope snapshot, cancelled split remainder | Старые контрактные проверки воспроизведены без изменения ожиданий; PASS. |
| F3 и item invoice continuation | Прежние проверки увеличения количества, двух начислений до счёта, публичных счетов и repeated sync воспроизведены; PASS. |
| WB policy | Ветка подтверждённой WB-передачи возвращается до новой блокировки и сторно. Настоящие соседние `test_fbs_cancellations.py` и `test_fbs_handover_billing.py` прошли, включая сохранение только подтверждённых начислений и повтор отмены. |
| Seller/tenant/savepoint | Seller ограничен tenant+seller; active charges ограничены tenant+source_type+order+две услуги. Сторно всего набора находится внутри одного savepoint; вложенные writer savepoints не коммитят внешнюю транзакцию. Атомарность проверена инъекцией выше. |
| Invoice/continuation | Оба creators и продолжение используют seller NO KEY UPDATE до изменения финансовых строк. Обратного order-lock у invoice в просмотренном пути нет. Это не снимает F6 с товарной блокировкой вызывающего складского пути. |

## Смешанные единицы и граница document/tariff group

Самостоятельный дополнительный сценарий использовал один Ozon-заказ с двумя
товарами. Сначала подтверждено и выставлено по 1 штуке каждого; затем заказ
увеличен до 2+2, реальный sync допроводит остаток, публичные preview/create/get
выставляют второй счёт. Повторный sync сохраняет оба снимка счетов.

Сборка — 1000/item. Историческая V2 ставка упаковки селлера — 800/document,
товарная ставка второго товара — 600/item (с обоими seller_id и product_id).
Первый счёт **3400**, второй **2600**: дополнительные две сборки и только одна
поштучная упаковка. Document-строка не оплачивается повторно. Это PASS для
смешанных строк внутри одного начисления, не только разных service_code.

Второй вариант использует одну V2 document-ставку упаковки для обоих товаров.
Текущее первоначальное начисление берёт по 800 с каждой товарной строки:
первый счёт **3600**, второй **2000**, обе дополнительные document-строки нулевые.
Первый writer делал так и до c36b8ab. Исправление ведёт `document_billed` по
product_id, **не по группе tariff_version_id всего документа**. Этот прогон
доказывает отсутствие повторной платы уже оплаченных строк, но не утверждает,
что историческая семантика «одна плата за каждый товар» эквивалентна «одна плата
за весь документ». Группировка document/tariff group не реализована ни старым
первоначальным writer, ни этой delta; новый товар той же группы будет отдельной
строкой. Не выдаю это за подтверждённый контракт единой платы на группу и не
меняю исторические ожидания в рамках исправления F4.

Применимость проверена по действующим ограничениям: БД разрешает product tariff
только с seller_id и unit=item; новый document-тариф матрица запрещает, но старые
document-версии продолжает читать. Соседний тест этой совместимости прошёл.
Две предварительные подготовки дополнительных проб были отвергнуты
`ck_billing_tariff_v2_scope` (product=document; затем product без seller);
они не являются product FAIL. Итоговый смешанный сценарий соблюдает constraint.

## Выполненные команды и точность SHA

Из backend, Python основного checkout:
`/Users/deniscivkunov/Projects/WMS/backend/.venv/bin/python`.
Каждому прогону явно заданы собственные WMS_TEST_DATABASE_URL/WMS_TEST_DATA_DIR,
PYTHONDONTWRITEBYTECODE=1; pytest запускался с `-p no:cacheprovider`.

```sh
python -m pytest -q -p no:cacheprovider \
  tests/test_wms662_continued_billing_cancellation.py \
  tests/test_wms662_invoiced_continuation.py \
  tests/test_wms662_continued_billing.py \
  tests/test_wms662_approve_scope_race.py \
  tests/test_wms662_astra_regressions.py --tb=short
# 11 passed, 6 warnings in 4.65s

python -m pytest -q -p no:cacheprovider \
  tests/test_fbs_cancellations.py tests/test_fbs_handover_billing.py \
  tests/test_billing_ledger_service.py tests/test_operation_facts.py \
  tests/test_operation_fact_recovery.py \
  tests/test_billing_tariff_matrix.py::test_matrix_refuses_new_document_rates_but_keeps_reading_old_ones \
  --tb=short
# 38 passed, 6 warnings in 38.45s
```

Базы `/private/tmp/wms662-c36b8ab-{review,adjacent,probes,tariffs,mixed-valid,lockorder,normal-lockorder}.sqlite`
и соответствующие отдельные каталоги `*-data` принадлежат только этому ревью.
Дополнительные пробы исполнялись Python через stdin с настоящими frozen helpers,
без записи/подмены файлов тестов и без ослабления assertions. Fixture
`fake_credentials_and_no_network.__wrapped__(pytest.MonkeyPatch)` замещала
учётные данные синтетическими и запрещала реальный HTTP. PostgreSQL разработчика,
живые отгрузки, Telegram и кабинеты/значения секретов не использовались.

Во время первого набора HEAD разработчика продвинулся до `0bb83b679`.
Проверено: этот commit меняет только developer report; diff backend/app,
backend/tests и guards от c36b8ab пуст. Дополнительные пробы выполнены в отдельном
постоянном worktree `.worktrees/wms662-review-c36b8ab`, созданном строго от c36b8ab,
в ветке `codex/wms662-review-c36b8ab`. Индекс и ветка разработчика не менялись.
Product c36b8ab также проверен через `git ls-remote` в
`refs/heads/codex/wms662-prod-handoff` — временный отказ push уже устранён.

`git diff --check c36b8ab^ c36b8ab` успешен. Все tests/guards неизменны между
91c89c553 и c36b8ab; прежние F1/F2/approve/observed/PG contracts и guards
неизменны от 956cd8a35, F3 — от e85b767, invoice — от 6662bb620.
Контракт F4/F5 является непосредственным родителем product-fix; собственный
RED повторно не запускался, его доказательства прочитаны в опубликованном
`wms662-f4-f5-testwriter.md`. Broad 129, PG, полный lint/mypy и CI в этом
ревью не повторялись; результаты разработчика не присваиваются.

## Воспроизведение порядка блокировок F6 без PostgreSQL

Из backend точного checkout запустить следующий Python через stdin с отдельными
WMS_TEST_DATABASE_URL=sqlite+aiosqlite:////private/tmp/...sqlite и WMS_TEST_DATA_DIR.
Он только наблюдает запросы реальных функций; PG dialect используется для
компиляции SQL, соединение остаётся SQLite. Порядок подтверждается assertions,
сама взаимная блокировка этим скриптом не имитируется.

```python
import sys, asyncio
sys.path.insert(0, "tests")
import conftest, pytest
from sqlalchemy import event
from sqlalchemy.dialects import postgresql
from test_wms662_observed_handoff import seed, fake_credentials_and_no_network
from test_wms662_approve_scope_race import ready_order, normal_handoff, ApproveRaceTransport
from app.db.session import SessionLocal, engine
from app.services import fbs_cancellation_service as cancellation

phase = None
trace = {"cancel": [], "handover": []}

def capture(conn, clause, multiparams, params, options):
    if phase and getattr(clause, "_for_update_arg", None) is not None:
        sql = str(clause.compile(dialect=postgresql.dialect()))
        for table in ("products", "sellers"):
            if "\nFROM " + table + "\n" in sql or "\nFROM " + table + " " in sql:
                trace[phase].append(table + (
                    " NO KEY UPDATE" if "FOR NO KEY UPDATE" in sql else " FOR UPDATE"))

def committed(conn):
    if phase:
        trace[phase].append("COMMIT")

async def main():
    global phase
    with pytest.MonkeyPatch.context() as patch:
        fake_credentials_and_no_network.__wrapped__(patch)
        await conftest._reset_database()
        async with SessionLocal() as session:
            case = await seed(session, "ozon", count=2)
            case.orders[1].supply_id = None
            await session.commit()
            await ready_order(session, case, case.orders[0], 1)
        event.listen(engine.sync_engine, "before_execute", capture)
        event.listen(engine.sync_engine, "commit", committed)
        phase = "cancel"
        async with SessionLocal() as writer:
            order = await cancellation._lock_order(writer, case.tenant.id, case.orders[1].id)
            await cancellation._finish_local_cancellation(
                writer, case.tenant.id, order, actor_user_id=None)
            await writer.commit()
        phase = "handover"
        async def no_change():
            pass
        await normal_handoff(case, ApproveRaceTransport(case, no_change))
        phase = None
        event.remove(engine.sync_engine, "before_execute", capture)
        event.remove(engine.sync_engine, "commit", committed)
        print("NORMAL_LOCK_ORDER", trace)
        assert trace["cancel"].index("sellers NO KEY UPDATE") < \
            trace["cancel"].index("products FOR UPDATE") < trace["cancel"].index("COMMIT")
        tx, inverted = [], False
        for item in trace["handover"]:
            if item == "COMMIT":
                inverted |= "products FOR UPDATE" in tx and "sellers NO KEY UPDATE" in tx and \
                    tx.index("products FOR UPDATE") < tx.index("sellers NO KEY UPDATE")
                tx = []
            else:
                tx.append(item)
        assert inverted, trace
    await engine.dispose()

asyncio.run(main())
```

Отчёт сохраняется и публикуется отдельным коммитом, содержащим только этот файл.
Main, etalon, product, tests и expectations этим ревью не изменены.
