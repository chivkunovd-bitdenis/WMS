# WMS-665 / WMS-517: полный проданный набор AVpack — operational read-only аудит, 06.10.2026

## Итог и точный незакрытый блокер

**Полный свежий набор реально проданных WB КИЗ AVpack не подтверждён.** Этот проход даёт реальные production SELECT и точный блокер получения источника продаж. Не выдавать 4 пробных кода, frozen80, нынешние86 cached-sold или248 локальных кандидатов за финальный состав. Telegram не отправлялся; подпись, withdrawal create/submit, установка сертификатов, управление секретами, изменение прав и production/deploy не выполнялись.

Свежим чтением 06:53 UTC подтверждён exact seller `0b8da5d8-f43a-42f5-a2ec-43173ea844bd` в tenant `d6e1ad21-8afa-4acf-8d0b-907b9f2adcfe`: **ИП Горячкина Татьяна Ивановна, ИНН 132608771877**. Один billing profile существует, создан/обновлён 05.10.2026 14:38:21 UTC. КПП, банк и БИК пустые; расчётный и корреспондентский счета не заполнены. Значения счетов не выгружались. ИНН для существующего participant_inn доступен; пригодность сертификата/полномочия представителя из этих данных не следуют.

В exact локальном наборе до применения продажного источника248 разных marking/order/rid/CIS. Из них 86 done/sold, 91 sorted/ready_for_pickup, 71 sorted/sorted. Все 248 имеют передачу WB и локальные допустимые привязки; ни одна не старше90 дней и ни одна не удерживается withdrawal claim. В пределах seller-role SELECT таблицы withdrawal_operations и withdrawal_items пустые на время чтения. Это отсутствие локальных WMS записей, а не проверка статуса кодов в Честном знаке. Подмена факта продажи состоянием WMS запрещена; sold86 — лишь текущий cached count.

Рабочий существующий SQL-клиент — `support_agent.prod_sql.run_query` из установленного `.wms-support-agent/app`, SSH forced gateway, роль `wms_agent_s_0b8da5d8f43a42f5a2ec43173ea844bd`. Ограничения клиента и шлюза не менялись, ensure не вызывался. Живой `current_user` и exact seller/tenant возвращены самой БД. Свежий has_table_privilege показывает false для seller_wildberries_credentials, users и seller_shop_delegations. Через эту роль нельзя ни получить WB credential, ни подтвердить права конкретной пользовательской сессии. Ни encrypted token, ни plaintext token, ни поля подписи не запрашивались. Конфигурация использовалась только штатным loader внутри клиента; содержимое конфигурационных/секретных файлов не выводилось агенту или в артефакты.

На доступной browser surface 06.10.2026 нет ни одной вкладки Chrome. CUA inventory дополнительно вернул: Mac locked, automatic unlock failed. Никакая попытка разблокировки, входа или переключения seller не выполнялась. Таким образом, в этом проходе нет штатной авторизованной seller-сессии для GET реестра. Ограниченный gateway предоставляет SQL/directory, а не произвольное выполнение серверного HTTP-клиента. Другого проверенного bound WB report-client в доступных инструментах не найдено. Искать общий ключ, обходить scoped gateway, извлекать/расшифровывать токен или создавать доступ этот read-only audit не разрешает.

**На стороне WB выполнено 0 запросов supplier/sales.** Поэтому page count, S/R count, cursor, terminal[] и fresh received_at отсутствуют; незавершённая выгрузка не маскируется локальным CSV. Это блокер подключения к источнику, а не измеренный блокер длительного paging. Наличие Statistics scope у сохранённого WB подключения и ответы401/403/429 не проверены. Нет оснований писать, что токен отсутствует или невалиден. Чтобы закрыть блокер, нужен существующий авторизованный серверный/локальный report-client данного seller или доступная штатная seller-сессия на машине оператора после проверенного выпуска WMS-517. Переиздавать ключ или устанавливать сертификат для этого вывода не требуется по доказательствам данного прохода.

## Что именно требуется прочитать для доказанного полного набора

Существующий product candidate `3a65b1c61803f4a88e9c84680854a386fcec2945` прочитан как Git-код и developer handoff, **не как deployed версия**. Краткое3a65 неоднозначно в Git (есть также blob); здесь указан полный commit. `wb_sales_report.read_sales_report` использует нормальный tenant/seller-checked get_decrypted_marketplace_token на сервере приложения, shared Redis rate limiter, GET Statistics supplier/sales и exact source cursor до[]. Операционный аналитик этот service на production не запускал: это потребовало бы другого подключения, доступного приложению, и service сохраняет cache/выполняет session.commit. Никакой product запуск не выдаётся за чистый SELECT.

По [официальному описанию WB supplier/sales](https://dev.wildberries.ru/en/openapi/reports) это предварительный оперативный источник продаж и возвратов. Данные обновляются примерно каждые 30 минут; история гарантирована до 90 дней. Неподтверждённые оплаты могут отсутствовать, а finishedPrice временно равняться 0. При flag=0 одна выдача ограничена примерно 80000 строками: следующие запросы используют полное lastChangeDate последней строки, завершение —[]. Limit — один запрос в минуту на seller. Полная выгрузка этого источника сама по себе не доказывает отсутствие продаж, не отражённых WB в отчёте.

[Ответ сотрудника WB о возвратах](https://dev.wildberries.ru/forum/1317) подтверждает R в saleID и отрицательные суммы. S показан в официальном примере sales; candidate отдельно отбирает S, дедуплицирует обновления saleID, учитывает R/неизвестные типы/конфликт и точный непустой FbsOrder.wb_rid == srid. Прямое открытие WB страниц в этом проходе вернуло 498; эти сведения перечитаны из доступной индексированной официальной страницы/ответа через web search. Ограничения реального подключения дополнительно определяет фактический ответ WB.

Свежая общая сводка всех WB orders 06:51:51 UTC: 521 order/rid, самый ранний created_at_wb 31.08.2026 16:59:23 UTC, самый поздний 06.10.2026 06:31:40 UTC. Состав cached status: 190 cancelled, 4 defect, 122 done/sold, 20 new/waiting, 185 sorted. У 248 допустимых маркированных строк earliest order 17.09.2026 18:52:52 UTC. Для широкого чтения, покрывающего все существующие WB orders этого seller, исходный dateFrom можно взять 31.08.2026 19:59:23+03:00; для полного доступного 90-дневного источника читать от границы90 дней. Это предложенные параметры, а не выполненный WB запрос. После каждого ответа сохранять точный cursor, время получения, количество и S/R по exact srid; непустая первая страница или совпавшие 86 локальных строк не завершают чтение. При ошибке, 429 или остановке курсора полнота остаётся незакрытой. После полного ответа сопоставить все 248 локальных идентификаторов, отдельно сохранить причины исключения/возврата/невалидной стоимости. Стоимость для документа — именно finishedPrice точной продажи, не старый supplier/orders snapshot.

## Существующий путь на Mac и его текущая применимость

Проверен соседний постоянный checkout `.worktrees/wms665-avpack-withdrawal-helper`, HEAD `70c505acf6f7ce8202b94fcb16cc05545324eb3f`, документы `docs/requirements/WMS-665.md`, `docs/reviews/WMS-665-AVPACK-RUNBOOK.md`, исходники `scripts/ops/avpack-macos-launcher.js`, `avpack-sold-kiz-filter.js` и tracked executable `avpack-sold-kiz.command`. Скрипт не запускался. Последний product handoff прочитан в sales-report-contract: `docs/reviews/2026-10-06-wms517-sales-developer-handoff.txt`, последняя версия файла в 3a65b1c61803f4a88e9c84680854a386fcec2945. Актуальная постановка WMS-517 R18–R25 прочитана; WMS-665 в sales checkout отсутствовал и был прочитан в helper checkout.

Самодостаточный `.command` существует и запускает уже установленный Chrome через системную JXA (JavaScript for Automation, управление приложениями macOS). Он ожидает одну вкладку `https://sellerfocus.pro/seller/honest-sign/withdrawals`, не скачивает зависимости и заканчивается подготовкой штатного диалога сертификата; оператор выбирает свой сертификат/ЭЦП и подтверждает подпись. В runbook описаны необходимые разрешения Chrome Apple Events и macOS Automation. Наличие этих разрешений, CryptoPro, USB-токена и нужного сертификата на Mac Виталия здесь не проверено. Их настройки не менялись, сертификаты не перечислялись и не устанавливались.

**Этот готовый файл нельзя выдавать за помощник всех сегодняшних продаж.** Filter содержит frozen TARGET_ROW_IDS[80] и TARGET_COUNT=80, источник его снимка — wb_status=sold. Launcher признаёт успех только при targetCount===80 и открытом unsigned/unsent dialog. Он читает страницы текущего WMS реестра, но не читает supplier/sales и не добавляет новые строки вне frozen80. Его локальный fetch-filter оставляет именно эти 80. Поэтому проблема полноты не решается тем, что оператор подключит ЭЦП. Самую раннюю четырёхстрочную версию тоже нельзя использовать как итог массового запроса.

Нормальный продуктовый путь уже реализован в SellerKizWithdrawalScreen: «Выбрать все» читает все страницы по 250, далее штатный диалог CryptoPro и локальные attached challenge / detached document подписи. Новой подписывающей программы для снятия данного блокера источника по коду не требуется. По backend API пользователь должен иметь роль fulfillment_seller, effective seller нужного scope, permission honest_sign и разрешённый rollout. SQL-role не заменяет этот user-role. Готовность этого пути в браузере оператора, enabled production submit/worker/beat и фактически served SHA не подтверждены данным аудитом. Кандидат3a65 остаётся кандидатом по поручению владельца; /health возвращает лишь status=ok и не доказывает commit.

## Границы и сохранность проверки

Работа выполнена одним агентом, без skills/subagents. origin/etalon обновлён и AGENTS.md прочитан; основание отдельной ветки — `0f1460b023700a99f17b504d6af3934a02bc68cc`, ветка `codex/wms665-full-sold-operational-check-20261006`, постоянный checkout внутри WMS/.worktrees. Чужие незакоммиченные результаты в sales-report-contract не захватываются. Изменения ownership — только этот новый отчёт и безопасный CSV. Продукт, тесты, требования и бэклог не редактируются. Shared PostgreSQL56517 и любые другие тестовые БД не использовались.

Операционная часть остаётся **не подтверждена полностью**: источник WB не прочитан и подпись оператором не проверена. Сохранение отчёта/CSV в отдельной опубликованной ветке подтверждает воспроизводимость read-only доказательств и блокера, а не продуктовую приёмку, полный CI, production deploy или реальный вывод КИЗ.

## Свежие доказательства production SELECT

Запросы выполнены через неизменённый `support_agent.prod_sql.run_query`, существующий конфигурационный loader и SSH gateway. Значения настроек подключения, ключей, токенов и подписей не выводились. Роли и binding не создавались и не менялись. Вывод ограничен 120 строками на запрос; сводные counts охватывают весь exact scope, а не первые 120 строк.

### identity / 2026-10-06T06:52:58.524432+00:00

```sql
SELECT current_user,current_timestamp,id,tenant_id,name FROM sellers WHERE id='0b8da5d8-f43a-42f5-a2ec-43173ea844bd' AND tenant_id='d6e1ad21-8afa-4acf-8d0b-907b9f2adcfe'
```

```csv
current_user,current_timestamp,id,tenant_id,name
wms_agent_s_0b8da5d8f43a42f5a2ec43173ea844bd,2026-10-06 06:53:00.188284+00,0b8da5d8-f43a-42f5-a2ec-43173ea844bd,d6e1ad21-8afa-4acf-8d0b-907b9f2adcfe,ИП Горячкина Т.И.

```

### legal_profile / 2026-10-06T06:53:00.256245+00:00

```sql
SELECT id,tenant_id,seller_id,legal_name,inn,kpp,bank_name,bik,settlement_account IS NOT NULL AND settlement_account<>'' AS settlement_present,correspondent_account IS NOT NULL AND correspondent_account<>'' AS correspondent_present,created_at,updated_at FROM billing_profiles WHERE seller_id='0b8da5d8-f43a-42f5-a2ec-43173ea844bd' AND tenant_id='d6e1ad21-8afa-4acf-8d0b-907b9f2adcfe'
```

```csv
id,tenant_id,seller_id,legal_name,inn,kpp,bank_name,bik,settlement_present,correspondent_present,created_at,updated_at
2d37e695-d900-4652-aa54-646f16623017,d6e1ad21-8afa-4acf-8d0b-907b9f2adcfe,0b8da5d8-f43a-42f5-a2ec-43173ea844bd,ИП Горячкина Татьяна Ивановна,132608771877,,,,f,f,2026-10-05 14:38:21.506626+00,2026-10-05 14:38:21.506626+00

```

### local_candidate_summary / 2026-10-06T06:53:01.945441+00:00

```sql
SELECT o.status,o.wb_status,count(m.id) AS marking_rows,count(DISTINCT m.value) AS distinct_cis,count(DISTINCT o.id) AS orders,min(o.created_at_wb) AS oldest_order,min(sp.delivered_at) AS oldest_handover,max(sp.delivered_at) AS newest_handover FROM fbs_order_markings m JOIN fbs_orders o ON o.id=m.order_id JOIN fbs_supplies sp ON sp.id=o.supply_id WHERE m.tenant_id='d6e1ad21-8afa-4acf-8d0b-907b9f2adcfe' AND o.tenant_id=m.tenant_id AND o.seller_id='0b8da5d8-f43a-42f5-a2ec-43173ea844bd' AND sp.tenant_id=m.tenant_id AND sp.seller_id=o.seller_id AND m.kind='sgtin' AND m.meta_status<>'rejected' AND o.marketplace='wb' AND sp.marketplace='wb' AND o.wb_rid IS NOT NULL AND o.wb_rid<>'' AND o.status NOT IN ('cancelled','defect') AND o.pick_status<>'returned' AND sp.delivered_at IS NOT NULL AND sp.status IN ('in_delivery','done') AND (m.marking_code_id IS NULL OR EXISTS (SELECT 1 FROM marking_codes mc WHERE mc.id=m.marking_code_id AND mc.tenant_id=m.tenant_id AND mc.seller_id=o.seller_id)) AND NOT EXISTS (SELECT 1 FROM fbs_shipment_reversal_ledger r WHERE r.fbs_order_id=o.id AND r.tenant_id=o.tenant_id AND r.reversed_at IS NOT NULL) GROUP BY o.status,o.wb_status ORDER BY o.status,o.wb_status
```

```csv
status,wb_status,marking_rows,distinct_cis,orders,oldest_order,oldest_handover,newest_handover
done,sold,86,86,86,2026-09-17 20:32:35+00,2026-09-18 10:51:50.849041+00,2026-10-02 07:16:45.644147+00
sorted,ready_for_pickup,91,91,91,2026-09-17 18:52:52+00,2026-09-18 10:51:50.849041+00,2026-10-04 13:49:04.554605+00
sorted,sorted,71,71,71,2026-09-25 08:51:46+00,2026-09-25 17:14:26.231754+00,2026-10-05 09:03:39.676716+00

```

### local_identity_integrity / 2026-10-06T06:53:03.538239+00:00

```sql
SELECT count(*) AS rows,count(DISTINCT m.value) AS distinct_cis,count(DISTINCT o.wb_rid) AS distinct_rid,count(DISTINCT o.id) AS distinct_orders,count(*) FILTER (WHERE o.created_at_wb<current_timestamp-interval '90 days') AS older_than_90d,count(*) FILTER (WHERE EXISTS (SELECT 1 FROM withdrawal_items i WHERE i.marking_id=m.id AND i.tenant_id=m.tenant_id AND i.seller_id=o.seller_id AND i.holds_claim)) AS claimed_rows FROM fbs_order_markings m JOIN fbs_orders o ON o.id=m.order_id JOIN fbs_supplies sp ON sp.id=o.supply_id WHERE m.tenant_id='d6e1ad21-8afa-4acf-8d0b-907b9f2adcfe' AND o.tenant_id=m.tenant_id AND o.seller_id='0b8da5d8-f43a-42f5-a2ec-43173ea844bd' AND sp.tenant_id=m.tenant_id AND sp.seller_id=o.seller_id AND m.kind='sgtin' AND m.meta_status<>'rejected' AND o.marketplace='wb' AND sp.marketplace='wb' AND o.wb_rid IS NOT NULL AND o.wb_rid<>'' AND o.status NOT IN ('cancelled','defect') AND o.pick_status<>'returned' AND sp.delivered_at IS NOT NULL AND sp.status IN ('in_delivery','done') AND (m.marking_code_id IS NULL OR EXISTS (SELECT 1 FROM marking_codes mc WHERE mc.id=m.marking_code_id AND mc.tenant_id=m.tenant_id AND mc.seller_id=o.seller_id)) AND NOT EXISTS (SELECT 1 FROM fbs_shipment_reversal_ledger r WHERE r.fbs_order_id=o.id AND r.tenant_id=o.tenant_id AND r.reversed_at IS NOT NULL)
```

```csv
rows,distinct_cis,distinct_rid,distinct_orders,older_than_90d,claimed_rows
248,248,248,248,0,0

```

### operations / 2026-10-06T06:53:05.174450+00:00

```sql
SELECT id,state,environment,participant_inn,attempt,created_at,updated_at,workflow_error FROM withdrawal_operations WHERE seller_id='0b8da5d8-f43a-42f5-a2ec-43173ea844bd' AND tenant_id='d6e1ad21-8afa-4acf-8d0b-907b9f2adcfe' ORDER BY created_at DESC LIMIT 20
```

```csv
id,state,environment,participant_inn,attempt,created_at,updated_at,workflow_error

```

### items_summary / 2026-10-06T06:53:06.600045+00:00

```sql
SELECT state,holds_claim,count(*) AS items,count(*) FILTER (WHERE preflight_evidence::jsonb ? 'wb_sales') AS wb_sales_key_present FROM withdrawal_items WHERE seller_id='0b8da5d8-f43a-42f5-a2ec-43173ea844bd' AND tenant_id='d6e1ad21-8afa-4acf-8d0b-907b9f2adcfe' GROUP BY state,holds_claim
```

```csv
state,holds_claim,items,wb_sales_key_present

```

### normal_role_access / 2026-10-06T06:53:08.223060+00:00

```sql
SELECT current_user,has_table_privilege(current_user,'seller_wildberries_credentials','SELECT') AS credentials_select,has_table_privilege(current_user,'users','SELECT') AS users_select,has_table_privilege(current_user,'seller_shop_delegations','SELECT') AS delegations_select
```

```csv
current_user,credentials_select,users_select,delegations_select
wms_agent_s_0b8da5d8f43a42f5a2ec43173ea844bd,f,f,f

```

## Безопасный локальный артефакт для будущего exact srid сопоставления

`wms665-local-candidates-20261006.csv`: 248 локальных потенциальных строк; **это не финальный набор продаж**. Полные CIS и криптохвосты не экспортированы; `cis_md5` — только отпечаток для проверки повторов, не основание продажи и не подпись. SHA-256 файла: `c7cf4e95b0490f05c94c6034919b67e7182efb39bc23aa631f17a9f55f5c76d7`. Начало чтения 2026-10-06T06:54:18.651840+00:00; завершение 2026-10-06T06:54:25.094370+00:00. Прочитано 3 страницы 120/120/8 по UUID marking_id, после чтения общий count/rid снова 248/248. Раздельные SELECT не дают транзакционный снимок, поэтому одинаковые counts не исключают изменения данных между страницами.

```json
[
  {
    "page": 1,
    "rows": 120,
    "received_at": "2026-10-06T06:54:20.391871+00:00",
    "sql": "SELECT m.id AS marking_id,o.id AS order_id,o.wb_order_id,o.wb_rid,o.status,o.wb_status,sp.id AS supply_id,sp.wb_supply_id,sp.delivered_at,o.created_at_wb,md5(m.value) AS cis_md5 FROM fbs_order_markings m JOIN fbs_orders o ON o.id=m.order_id JOIN fbs_supplies sp ON sp.id=o.supply_id WHERE m.tenant_id='d6e1ad21-8afa-4acf-8d0b-907b9f2adcfe' AND o.tenant_id=m.tenant_id AND o.seller_id='0b8da5d8-f43a-42f5-a2ec-43173ea844bd' AND sp.tenant_id=m.tenant_id AND sp.seller_id=o.seller_id AND m.kind='sgtin' AND m.meta_status<>'rejected' AND o.marketplace='wb' AND sp.marketplace='wb' AND o.wb_rid IS NOT NULL AND o.wb_rid<>'' AND o.status NOT IN ('cancelled','defect') AND o.pick_status<>'returned' AND sp.delivered_at IS NOT NULL AND sp.status IN ('in_delivery','done') AND (m.marking_code_id IS NULL OR EXISTS (SELECT 1 FROM marking_codes mc WHERE mc.id=m.marking_code_id AND mc.tenant_id=m.tenant_id AND mc.seller_id=o.seller_id)) AND NOT EXISTS (SELECT 1 FROM fbs_shipment_reversal_ledger r WHERE r.fbs_order_id=o.id AND r.tenant_id=o.tenant_id AND r.reversed_at IS NOT NULL) ORDER BY m.id LIMIT 120"
  },
  {
    "page": 2,
    "rows": 120,
    "received_at": "2026-10-06T06:54:22.069938+00:00",
    "sql": "SELECT m.id AS marking_id,o.id AS order_id,o.wb_order_id,o.wb_rid,o.status,o.wb_status,sp.id AS supply_id,sp.wb_supply_id,sp.delivered_at,o.created_at_wb,md5(m.value) AS cis_md5 FROM fbs_order_markings m JOIN fbs_orders o ON o.id=m.order_id JOIN fbs_supplies sp ON sp.id=o.supply_id WHERE m.tenant_id='d6e1ad21-8afa-4acf-8d0b-907b9f2adcfe' AND o.tenant_id=m.tenant_id AND o.seller_id='0b8da5d8-f43a-42f5-a2ec-43173ea844bd' AND sp.tenant_id=m.tenant_id AND sp.seller_id=o.seller_id AND m.kind='sgtin' AND m.meta_status<>'rejected' AND o.marketplace='wb' AND sp.marketplace='wb' AND o.wb_rid IS NOT NULL AND o.wb_rid<>'' AND o.status NOT IN ('cancelled','defect') AND o.pick_status<>'returned' AND sp.delivered_at IS NOT NULL AND sp.status IN ('in_delivery','done') AND (m.marking_code_id IS NULL OR EXISTS (SELECT 1 FROM marking_codes mc WHERE mc.id=m.marking_code_id AND mc.tenant_id=m.tenant_id AND mc.seller_id=o.seller_id)) AND NOT EXISTS (SELECT 1 FROM fbs_shipment_reversal_ledger r WHERE r.fbs_order_id=o.id AND r.tenant_id=o.tenant_id AND r.reversed_at IS NOT NULL) AND m.id>'895b16d1-0b18-4e88-9a40-7ef5f3c2bf3c' ORDER BY m.id LIMIT 120"
  },
  {
    "page": 3,
    "rows": 8,
    "received_at": "2026-10-06T06:54:23.640153+00:00",
    "sql": "SELECT m.id AS marking_id,o.id AS order_id,o.wb_order_id,o.wb_rid,o.status,o.wb_status,sp.id AS supply_id,sp.wb_supply_id,sp.delivered_at,o.created_at_wb,md5(m.value) AS cis_md5 FROM fbs_order_markings m JOIN fbs_orders o ON o.id=m.order_id JOIN fbs_supplies sp ON sp.id=o.supply_id WHERE m.tenant_id='d6e1ad21-8afa-4acf-8d0b-907b9f2adcfe' AND o.tenant_id=m.tenant_id AND o.seller_id='0b8da5d8-f43a-42f5-a2ec-43173ea844bd' AND sp.tenant_id=m.tenant_id AND sp.seller_id=o.seller_id AND m.kind='sgtin' AND m.meta_status<>'rejected' AND o.marketplace='wb' AND sp.marketplace='wb' AND o.wb_rid IS NOT NULL AND o.wb_rid<>'' AND o.status NOT IN ('cancelled','defect') AND o.pick_status<>'returned' AND sp.delivered_at IS NOT NULL AND sp.status IN ('in_delivery','done') AND (m.marking_code_id IS NULL OR EXISTS (SELECT 1 FROM marking_codes mc WHERE mc.id=m.marking_code_id AND mc.tenant_id=m.tenant_id AND mc.seller_id=o.seller_id)) AND NOT EXISTS (SELECT 1 FROM fbs_shipment_reversal_ledger r WHERE r.fbs_order_id=o.id AND r.tenant_id=o.tenant_id AND r.reversed_at IS NOT NULL) AND m.id>'f8c488e6-d6b8-464b-86c6-9d25d6b1e87b' ORDER BY m.id LIMIT 120"
  }
]
```

## Дополнительная свежая сводка всех WB заказов

Чтение 06:51:51 UTC тем же scoped gateway, без ограничения состава сводки.

```sql
SELECT marketplace,status,wb_status,count(*) AS orders,count(wb_rid) AS rid_present,min(created_at_wb) AS earliest,max(created_at_wb) AS latest FROM fbs_orders WHERE seller_id='0b8da5d8-f43a-42f5-a2ec-43173ea844bd' AND tenant_id='d6e1ad21-8afa-4acf-8d0b-907b9f2adcfe' GROUP BY marketplace,status,wb_status ORDER BY marketplace,status,wb_status
```

WB строки полного результата (Ozon не входит в предмет проверки):

```csv
marketplace,status,wb_status,orders,rid_present,earliest,latest
wb,cancelled,canceled_by_client,185,185,2026-08-31 20:30:28+00,2026-10-02 05:38:56+00
wb,cancelled,declined_by_client,5,5,2026-09-20 15:53:31+00,2026-10-02 19:51:09+00
wb,defect,defect,4,4,2026-09-20 19:46:29+00,2026-10-01 07:55:21+00
wb,done,sold,122,122,2026-08-31 16:59:23+00,2026-10-02 04:01:31+00
wb,new,waiting,20,20,2026-10-05 09:03:48+00,2026-10-06 06:31:40+00
wb,sorted,ready_for_pickup,114,114,2026-09-17 18:52:52+00,2026-10-04 10:36:27+00
wb,sorted,sorted,71,71,2026-09-25 08:51:46+00,2026-10-05 08:38:19+00
```
