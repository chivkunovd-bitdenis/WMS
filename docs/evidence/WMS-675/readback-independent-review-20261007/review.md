# WMS-675: независимое ревью фактического readback

**PASS: сохранённые адресные чтения подтверждают26 проведённых единиц и missing0.**
Проверенная доказательная версия — `277e8f0f7c9172a8c76664a6657942ecf71284a1`,
`docs/evidence/WMS-675/native-execution-20261007/`. Product SOURCE —
`4c532f0cccfb8f99b34d68d9630a3763038fbc5f`. Ревьюер — отдельная сессия
Sol6.1 high `01a11370-eea3-7533-a616-2943d59a7bca`; readback/адаптер не авторствовал.
Прочитаны текущие правила и прежнее ограниченное ревью `371cd84c1ef9f2cba1ffd4b630831b4d18d4e5af`.

Все93 файла учтены:92 payload members совпадают по size/SHA256 с file-manifest,
сам manifest сохранён отдельно. В каждом из двух gateway-чтений все11 запросов
успешны; SQL/CSV хеши и числа строк совпадают с manifest. Identity подтверждает
exact tenant/seller/supply/warehouse, READ ONLY/RLS on.31 raw Ozon cards и scope
snapshot совпадают со своими хешами и exact31 position/product/SKU/offer/quantity.
Фактические статусы:15 delivered/posting_received,6 delivering/posting_in_pickup_point,
5 delivering/posting_on_way_to_city и5 cancelled/posting_canceled. Эти положительные
статусы/подстатусы входят в принятый native4c proof; отмены расходом не стали.

В чтениях07:53:12–07:53:32 и08:03:19–08:03:36 UTC все26 positive recipes имеют
уникальные реальные движения `fbs_shipment` по−1, с точными tenant/seller/product/
warehouse/sorting IDs и без reversal/negative/shortage.31 ledger IDs сохранены;
12 прежних expense links/header IDs остаются,14 новых movement IDs соответствуют
ровно исторической missing14. Распределение новых14 по SKU:1697770458→5,
1589998415→3,1586484429→2,1586466682→3,1695128938→1. Все52 billing IDs с прежними
physical/billing quantities и amount и26 fact IDs/quantities сохранены, дубликатов
нет. Суммы остаются null: денежная успешность не заявляется.

Все три прочитанных канала резерва равны0. По шести товарам сохранённые balances
совпадают с полной историей движений; exact sorting rows/состав шести товаров
проверены отдельно. В обоих чтениях нет несвязанных расходов и отрицательных
движений без атрибуции в пределах опубликованных scoped queries. Состав движений
и balances при повторном чтении не изменился; remaining0/repeated read delta0.
Это два отдельных набора SELECTs, не общий атомарный snapshot и не повторный conduct.

Граница причинности сохранена. Уже первый readback07:53 показывает все26 расходов,
до попытки адаптера07:55:46–07:55:57. Эта попытка завершилась exit2 /
`external_status_changed`, checkpoint/stock=`NOT_STARTED`; исходник371cd подтверждает
остановку на fresh status check до записи checkpoint/stock. Ей нельзя приписать
проведение14. В raw movements все14 новых `created_at` равны
`2026-10-07 06:27:22.537767+00`, ledger written_off — в06:27; эти поля не являются
отдельной квитанцией точного времени commit. Инициирующий actor/точный вызов
сервиса чтениями не установлен. Историческая missing14 сохранена; current missing0.
Повторная мутация для этой доказанной разницы не требуется. Provider stock-publish
не проверен и успешным не объявляется.

Один независимый офлайн-запуск:

```sh
python3 -B docs/evidence/WMS-675/native-execution-20261007/verify_readback.py
```

Exit0; [raw stdout](offline-verifier.log) и [проверка целостности/границ](verification.json)
сохранены. Generated readback-verification.json после запуска побайтно равен исходному.
Исходник verifier прочитан: он выполняет только файловую сверку, не импортирует app
и не обращается кSQL/provider. Его общий текст attribution про native completion
здесь трактуется только как согласованный штатный ledger/checkpoint, без доказательства
конкретного инициатора или call trace. Недостающие в нём проверки полного file-manifest,
raw substatuses, exact position composition/шести balance rows, duplicate IDs и времён
отдельно сверены по сохранённым данным. Подтверждённых дефектов адресного readback нет.

Production reads/writes, network/provider calls, adapter/native rerun, CI, deploy,
печать и сообщения этим ревьюером не выполнялись. Product/адаптер/tests/requirements
и исходные93 файла не изменены; сохранён только этот каталог независимого ревью.
PASS относится к доказанному состоянию учёта, не к авторству восстановления,
внешней публикации или общей продуктовой/аналитической приёмке.
