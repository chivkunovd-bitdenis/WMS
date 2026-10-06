# WMS-675 · операционный runbook после verified deploy

## Статус и назначение

Это инструкция для операционного исполнителя, а не команда на проведение.
На момент её подготовки фактическое восстановление **не выполнено**: production
read в коммите `937adf40d41fed843b3d7fe16c6f3825c9bfcf08` доказал текущую
дельту 26, но production API был на `8f11d912…`, то есть это не доказательство
развёртывания общего кандидата. Локальный SHA, этот документ и зелёная локальная
проверка не заменяют verified deploy.

Цель операции после подтверждённого общего выпуска — восстановить только
фактически недостающий расход в адресной WMS-поставке Бамбука обычным принятым
механизмом WMS-662. Нового продукта, отдельного runner-а, SQL-проведения,
нового meta-test или копии WMS-662 для этого не создаётся.

Адрес неизменен: tenant `b80a893b-ab87-42b6-8fd7-6d41502c900f`, seller
`cf6d31c5-944b-4382-af34-636ca9aa8cc3`, WMS-source supply
`b82d1e9a-30d2-4d7b-b52d-9775c3d266e3`, warehouse
`2d968c65-4a8d-414e-9076-0f201c2dba63`, marketplace `ozon`. Это ровно 31
order/position по одной единице; никакая похожая October-поставка не является
заменой этого scope.

## Единственный принимаемый вход WMS-662

Операция запускается обычным пользовательским входом уже принятого приложения:
`POST /operations/fbs-orders/sync-statuses` с телом
`{"seller_id":"cf6d31c5-944b-4382-af34-636ca9aa8cc3","marketplace":"ozon"}`
в штатном авторизованном операторском контексте. Не помещать в журнал токены,
cookies или иные credential-данные. Этот endpoint вызывает принятый
`sync_ozon_order_statuses`; именно он сохраняет observation, берёт обычные
блокировки и вызывает `conduct_supply`. Прямо вызывать `save_observations`,
`conduct_supply`, `write_off_order`, private helper либо писать SQL нельзя.
Также нельзя вызывать `deliver_supply`, создавать/подтверждать сдачу Ozon,
менять live-флаг, credentials, лимиты или bindings.

Вызов допускается только если в verified deployed candidate присутствует
принятый WMS-662 change `b4043c0df9fee0419bdfe85167bbd645f820de9c` и его
существующие guards. Его постоянная защита включает
`backend/tests/test_wms662_live_delivery_substatuses.py` из тестового коммита
`c466c65b850dd87481be5da88b99bcfaa4087414`; новый WMS-675 test-contract её не
заменяет и в операции не нужен.

`sync_ozon_order_statuses` опрашивает ограниченную очередь (до 200) данного
seller, а не принимает список из 31 IDs. Для нашего документа это безопасно
только при отдельном свежем доказательстве, что его выбранная очередь содержит
только 26 положительных записей адресной поставки: 13 `in_delivery` и 13
`done` с непроведённым ledger. Пять `cancelled` в эту очередь не входят; они
остаются частью проверки 31-позиционной поставки, но не получают target для
расхода. Если выборка содержит хоть один чужой order/supply или не может быть
доказана, endpoint **не запускать**. Не обходить это прямым вызовом service:
это конкретный технический блокер scope, который root решает отдельно.

## Ворота до mutation: prepare

Все пункты ниже фиксируются в новом неизменяемом каталоге evidence с UTC
временем, SQL/manifest и очищенными Ozon-ответами. Существующие historical
bundle и snapshot `937adf` не перезаписываются.

1. Root фиксирует verified deploy: exact SHA общего кандидата, подтверждение,
   что именно этот SHA работает в production API, и наличие принятого WMS-662.
   SHA `8f11d912…` из live read и любой локальный SHA для этого непригодны.
   В штатной среде live transport уже должен быть доступен; если он выключен,
   зафиксировать блокер, но не включать его и не менять конфигурацию.
2. Тем же обычным application transport сделать bounded read exact 31 Ozon
   posting cards, без submit/approve/ship и без изменения конфигурации. Для
   каждой карты проверить posting, SKU, offer, quantity=1 и отсутствующие
   related/weight children. Неполный ответ, HTTP-ошибка, новый child/split или
   смена состава останавливают операцию.
3. По текущему принятому классификатору WMS-662 заново посчитать proved
   quantity: положительны только допустимые `delivering`/`driver_pickup`/
   `delivered` вместе с допустимым substatus. `cancelled`, в том числе
   `cancelled_after_ship`, не становятся положительными. Snapshot `937adf`
   ожидает 26 положительных и 5 отменённых, но это ожидание, а не target.
4. Перед запуском через существующий tenant read-only collector снова прочитать
   exact identity, 31 orders/positions, ledger/movement/reversal, reserves,
   balance/location, operation facts, billing charges и относящиеся supply
   operations. Зафиксировать отсутствие truncation/error и сравнить множества
   ID с baseline. Рассчитать по позициям и суммарно
   `missing = max(0, proved_unique − already_conducted)`; уже проведённая часть
   обязана быть подмножеством свежего доказательства. Старые числа 26, 13/26 и
   11/22 не подставляются вместо этого результата.
5. До endpoint сверить его реальную poll-selection: она должна состоять только
   из 26 положительных order IDs адресной supply. Другой seller, warehouse,
   marketplace, supply или чужой ID — stop, без ручного narrowing и без SQL.

Если fresh `missing=0`, mutation не выполняется: сохранить evidence и перейти
к независимому readback. Если величина отличается от 26, действовать можно
только с заново доказанной фактической дельтой и тем же scope; это не даёт
права списать исторические 26 или все 31.

## Штатное проведение и встроенные защиты

Только после всех prepare-ворот и разрешения root исполнить endpoint один раз.
Его принятый путь сначала читает карточки, сохраняет durable observation
`observed:<supply-id>` отдельно от складской транзакции, затем берёт штатные
locks в порядке `lock_order_batch_packaging_rows` →
`lock_handoff_batch_products` → supply/orders/ledger `FOR UPDATE`. После locks
строки перечитываются с `populate_existing`; HTTP под складскими locks не
выполняется.

`save_observations` закрепляет один operation journal на supply по ключу
`observed:<supply-id>`. При timeout/потере ответа не делать второй endpoint
вслепую и тем более не сдавать Ozon повторно: сначала прочитать этот journal,
ledger, movements, facts и charges. `conduct_supply` повторно сверяет
tenant/seller/warehouse/marketplace/scope, не оживляет reversal, отбрасывает
несовпавший scope и проводит только ещё неполный ledger recipe. Обычная
публикация остатков после законного проведения не подавляется; лимит оператора
и bindings не меняются.

В текущем snapshot фактическая дельта равна 26, ledger-проведение равно 0,
есть 13 facts/26 active charges, из которых historical наборы 11/22 — строгие
подмножества. Если это подтверждено заново без дрейфа, ожидаемая добавка —
13 facts и 26 charges, а итог — 26 facts/52 active charges; 13 имеющихся facts
и 26 charges должны сохраниться теми же IDs и полями, в частности historical
11/22. Это проверяемый ожидаемый результат именно при неизменном preflight,
а не разрешение компенсировать расхождение ручной вставкой.

## Независимый readback и критерии фактической приёмки

Readback выполняет отдельный read-only исполнитель/сессия после commit, не
mutation-session и не запись endpoint. Он заново читает external exact scope и
WMS collector, сохраняет отдельный manifest и доказывает всё одновременно:

- exact 31 composition сохранился; отмены не оживлены и новая внешняя сдача не
  создана;
- все только доказанные положительные quantity имеют обычный shipment movement
  и completed ledger recipe, без reversal; нет расхода на отменённые либо
  неизвестные позиции;
- запас и reservation соответствуют проведённому recipe. При неизменном
  snapshot это означает снятие 13 оставшихся резервов и reserve=0, но при
  изменившемся fresh scope принимается только фактически пересчитанное значение;
- 13 baseline facts/26 baseline charges сохранены по ID и полям, включая
  historical 11 facts/22 charges; нет их дублей. Billing/facts для новой части
  соответствуют реально проведённому количеству;
- повторный расчёт proved minus conducted даёт `missing_delta=0`. Повторный
  обычный sync не создаёт второго movement/fact/charge;
- результат обычной stock publication фиксируется отдельно, если её выполнение
  наблюдается. Её отсутствие/ошибка не маскируется как успешная публикация.

Только эти readback-доказательства составляют приёмку **actual repair** (R6).
Проверенный deploy, preflight, runbook и commit с evidence — это лишь
**prepare**; они не закрывают WMS-675 и не являются проведением.

## Что передать интегратору

Только свежий адресный пакет из
[INTEGRATOR_IMPORT_MANIFEST_20261007.md](INTEGRATOR_IMPORT_MANIFEST_20261007.md)
можно положить поверх уже принятого `docs/requirements/WMS-675.md` интегратора.
Он не переносит product code, WMS-662 tests или прежний
`backend/tests/test_wms675_recovery_evidence_contract.py`: у последнего
зафиксированы три meta-дефекта, и он не является защитой реального учёта.
Его история не удаляется и остаётся видима в этой ветке (`85d3d84d3`,
`e0df56829`); решение о её отдельной судьбе принадлежит root.

Ни один шаг этого runbook не выполнялся при его создании. Никаких production
writes, Ozon writes, секретных кабинетов или изменений credentials не было.
