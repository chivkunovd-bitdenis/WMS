# WMS-406: финальный план применения фактов, 09.09.2026

Исследован integration SHA 0d101a3e37316aa558f34c583416495ea7ec9e84. Сам apply **не выполнялся**. Команды ниже предназначены root после его подтверждения production deployment этого приложения. WMS-408 остаётся только проектом на отдельной ветке.

Свежий production dry-run: 2026-09-09T08:20:53.432079+00:00 — 2026-09-09T08:21:02.948567+00:00, 10.321 секунды, 11 tenants. В отдельный subprocess загружены точные финальные helper и existing backfill только в память; runtime-файлы не менялись. Все SessionLocal в dry-run выполняли SET TRANSACTION READ ONLY, SHOW проверял on; statement_timeout 30 секунд. Аргумента --apply не было.

| Tenant | Создать факты | Исправить даты | Защищено начислением/счётом |
| --- | ---: | ---: | ---: |
| FFAdam (561e0810-b95e-4b1c-a478-ad6f24d99523) | 2 | 423 | 0 |
| Руспро (5baaf211-7cb7-495d-9c2b-b42121606bf9) | 0 | 0 | 0 |
| ИП Львова В.В. (5fbf633c-3ea9-4c29-b5f5-f549b122bcae) | 0 | 0 | 0 |
| WMS Test (63979f0b-2405-4eeb-a000-541baa00b1da) | 0 | 0 | 0 |
| ИП Тестовый (6dc7a501-d500-4a96-a691-b31ff53ff7b9) | 0 | 0 | 0 |
| Империя ФФ (7b98a8aa-c03c-4649-9677-a645be45c622) | 154 | 2105 | 0 |
| ПакХаб (a69067c1-e6b3-458c-93d1-e5121aaa4966) | 0 | 4 | 0 |
| Бамбук (b80a893b-ab87-42b6-8fd7-6d41502c900f) | 0 | 0 | 0 |
| AVpack (d6e1ad21-8afa-4acf-8d0b-907b9f2adcfe) | 5 | 12 | 0 |
| Фулфёдор (db45d56c-ecec-4575-b247-dacbdaca052f) | 0 | 0 | 0 |
| Diag Org (e7ef1f3a-709b-4074-92b5-9b8653045316) | 0 | 0 | 0 |
| **Всего** | **161** | **2544** | **0** |

WB candidates 18665, доказанная передача 2726; Ozon candidates 0. У 21 доказанного заказа дата уже соответствует: 2726−161−2544. Без доказательства передачи пропущено 15939. У 8794 существующих фактов не найдено proof передачи; скрипт их не удаляет. Отвязанных доказанных заказов 159; отвязанных без proof 15144 — это не число доказанно потерянных передач, там есть и неотгруженные заказы.

С прошлого dry-run 07:09Z кандидатов WB стало больше на 30, доказанных на 14. У Империи фактов стало больше на 21, redated уменьшилось с 2112 до 2105; остальные планы записи прежние. Одни агрегаты не доказывают, какой оператор или фоновый процесс изменил каждую запись. Во время нового dry-run баланс по tenant совпал по count и sum(quantity) до/после; это агрегатная проверка, не fingerprint каждой ячейки. Отсутствие записи нашим процессом отдельно гарантировано READ ONLY.

## Что именно изменит existing script

Только OperationFact.occurred_at у разрешённых старых фактов и новые OperationFact/OperationFactLine для доказанных заказов. write_operation_fact проверяет tenant у селлера, склада и товаров, защищает source/idempotency. Никаких SQL UPDATE inventory, reserve, order.supply_id и никаких новых цен/начислений в этой цепочке нет.

Перед изменением даты existing script проверяет любой BillingLedgerEntry того tenant/source order и прямую ссылку BillingInvoiceV2Source.operation_fact_id. Наличие любого такого денежного основания сохраняет старую дату, включая отменённые счета. Legacy-счёт, ссылающийся на Ledger, защищён наличием самого Ledger. Автоматическая передатировка таких оснований запрещена; пропуски нужно сохранить в выводе. На данном снимке skipped_accounted=0, это не отключение guard.

--from НЕ задаём, --skip-dates НЕ задаём: согласованы все tenants/селлеры и вся доказанная история. Batch=200 проверяется и после redated, и после INSERT. План этого снимка — 2705 фактов к изменению/созданию, ожидаемо 17 непустых транзакций по четырём tenant. Точное время записи не измерялось. Обновлённый скрипт по-прежнему делает индивидуальные проверки protected date; каждое SQL ограничено timeout, commits каждые 200 ограничивают длинные транзакции.

## Точная команда: сначала сухой прогон после deployment

Backup должен оставаться по пути /opt/wms/.deploy-backups/before-wms406-407-20260909/database.dump (root сообщил ранее проверенный backup; команда дополнительно проверяет существование и ненулевой размер). Проверка SHA256 двух модулей останавливает запуск старой версии. Не заменять несовпадающие runtime-файлы вручную: дождаться правильного deployment.

```sh
ssh -o BatchMode=yes root@sellerfocus.pro \
  'test -s /opt/wms/.deploy-backups/before-wms406-407-20260909/database.dump && docker exec -e PYTHONDONTWRITEBYTECODE=1 -i wms_prod-api-1 python - dry-run' <<'PY'
import asyncio
import hashlib
import sys
from pathlib import Path
from sqlalchemy import event, select, text
from sqlalchemy.orm import Session
from app.db.session import SessionLocal
from app.models.tenant import Tenant
import app.services.fbs_order_billing_service as helper
import scripts.backfill_fbs_order_facts as script

mode = sys.argv[1]
assert mode in {"dry-run", "apply"}
expected = [
    (helper, "579b482ed6e10e32a74d2572ba15bebaaf1614ed51341a67a5a9b28e8066843c"),
    (script, "01de7238b6219f8cbe1a768f5cbbea334215d4933df0cbc942deeb559a53b9a7"),
]
for module, digest in expected:
    assert hashlib.sha256(Path(module.__file__).read_bytes()).hexdigest() == digest, module.__name__

@event.listens_for(Session, "after_begin")
def transaction_limits(session, transaction, connection):
    if mode == "dry-run":
        connection.exec_driver_sql("SET TRANSACTION READ ONLY")
    connection.exec_driver_sql("SET LOCAL statement_timeout = '30000ms'")
    connection.exec_driver_sql("SET LOCAL lock_timeout = '3000ms'")

async def stock_snapshot():
    async with SessionLocal() as session:
        rows = await session.execute(text(
            "SELECT tenant_id::text, count(*) AS balance_rows, sum(quantity) AS quantity "
            "FROM inventory_balances GROUP BY tenant_id ORDER BY tenant_id"
        ))
        return [dict(row) for row in rows.mappings().all()]

async def main():
    print("mode:", mode, flush=True)
    print("stock_before:", await stock_snapshot(), flush=True)
    async with SessionLocal() as session:
        tenants = list(await session.scalars(select(Tenant.id).order_by(Tenant.id)))
    for tenant_id in tenants:
        print("tenant_id:", tenant_id, flush=True)
        sys.argv = ["backfill_fbs_order_facts", "--tenant", str(tenant_id)]
        if mode == "apply":
            sys.argv.append("--apply")
        await script.main()
    print("stock_after:", await stock_snapshot(), flush=True)

asyncio.run(main())
PY
```

Для **применения только после команды root** выполнить ровно этот блок, изменив единственное позиционное слово в ssh-команде: `python - dry-run` → `python - apply`. Внутри вызывается тот же существующий `scripts.backfill_fbs_order_facts.main` с `--tenant <UUID> --apply`; чужого алгоритма записи нет. Таймауты назначаются при каждой транзакции, в том числе после batch commit, а не только в начале процесса. Никакой credential/environment output не требуется.

## Проверка после применения

Сразу повторить **исходный блок с dry-run**: оба write counters должны быть 0 для уже обработанного набора. Сохранить полный вывод apply и повторного dry-run по tenant, включая failed и skipped_accounted. Если остались новые изменения, сверить их с новыми подтверждениями работы между запусками; не приписывать активность операторов backfill и не повторять apply вслепую.

Проверить, что apply не сообщил «не удалось записать». Сохранить stock_before/stock_after. При изменении агрегата сравнить реальные складские движения за тот же интервал: production продолжает работать, поэтому отличие само по себе не доказывает воздействие backfill. Слепое возвращение склада к baseline запрещено.

Суммы ставок, Ledger и invoice не создаются этим запуском. Не выполнять описанный в историческом docstring денежный backfill как автоматический следующий шаг: эта задача касается только фактов, а цены берутся исключительно из существующего согласованного механизма. Общая проверка отчёта/счёта после deployment остаётся отдельной работой root.

Для дальнейшей точной проверки защищённых дат можно сравнить только множество OperationFact ID, защищённое Ledger/Invoice **до** применения, и его occurred_at после. Новые счета во время запуска не являются нарушением. Глобальную неизменность всех финансовых/складских таблиц в работающей системе этот отчёт не утверждает.
