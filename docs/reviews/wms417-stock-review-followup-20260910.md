# WMS-417 / WMS-338 / WMS-060 — stock follow-up

Рабочее дерево: `/Users/deniscivkunov/Projects/WMS/.worktrees/wms338-stock-min-formula`.
Ветка: `feat/wms338-stock-min-formula`. Исходный чистый HEAD:
`c14abc46c52202a17875eead6be0bf71fbfcc7bd`. Удаление ledger/is_fbs/consume и
миграция 0261 из этого коммита сохранены. Канон и handoff принадлежат координатору
и не редактировались. Этот отчёт — доказательства исполнителя, не приёмка.

Прочитаны инструкции и относящиеся карточки канона, полные handoff координатора
WMS_ASTRA_TAKEOVER_2026-09-10.md / WMS_CLAUDE_HANDOFF_2026-09-09.md,
astra-review-result-stock-453bb87d.md и полный stock_merge-review.md из
`docs/reviews/artifacts/wms417-opus5-six-20260910/` координатора. Findings проверены
по текущему коду; предложения ревью не принимались автоматически.

## Что изменено и доказано

- Finding 2 подтверждён и исправлен в `fbs_stock_rule_service.py`: сохранение
  процентного режима и reset старого fbs_stock_limit больше не обнуляют
  операторские quantities WB/Ozon. Возврат в штуки сравнивает ввод с сохранёнными
  потолками даже после процентного режима. Прежние/уменьшенные значения можно
  сохранить после падения free; увеличение проходит прежнюю проверку физического
  свободного остатка. Тест сохраняет WB50/Ozon30, переключает доли, снижает
  физический остаток до40, возвращает прежние потолки и получает публикацию40.
- Finding 3 подтверждён и исправлен в `marketplace_unload_service.py`: Product
  locks в replace_lines, plan_request и draft confirm_request берутся по
  отсортированным UUID. Реальный PostgreSQL replay запускает два документа с
  обратным порядком двух товаров. Пока первый держит блокировку, серверный
  pg_blocking_pids подтверждает ожидание второго на первом же товаре. После
  освобождения обе операции завершаются; проверены статусы, строки, реальные
  резервы, неизменный физический баланс и отсутствие движений.
- Finding 5 подтверждён и исправлен в `fbs_stock_rule_service.py`: single/bulk
  published_now используют распределение отдельно внутри каждого физического
  склада, как publish_amounts_for_binding. Тест сравнивает результат с настоящим
  методом расчёта публикации WB/Ozon на двух складах в обоих режимах. Общий
  named direction reserve по существующему поведению отправителя консервативно
  вычитается на каждом физическом складе; общий free на карточке вычитает его
  один раз. Алгоритм отправителя этим изменением не расширялся.
- Legacy set/summary исправлены в `fbs_warehouse_binding_service.py`: ввод числа
  делегируется общей проверке правила и явно выбирает units mode. Частичная
  правка применяется после seller/Product locks к перечитанным потолкам, не
  перезаписывая остальные значения устаревшим снимком. Summary возвращает
  физический free в совместимых полях limit/available; allocated_total остаётся
  только суммой сохранённых потолков и не вычитается из наличия. Превышение
  возвращает прежний HTTP409 с сообщением о реальном остатке. HTTP-тест проверяет
  запись5 при retired limit0/free5, отказ6 и сохранение5 при переходе в проценты.
- Finding 7 НЕ подтвердился: настоящий callee
  `fbs_stock_sync_service.publish_explicit_zero_for_binding` сам коммитит pending
  и окончательное подтверждение. Тест вызывает настоящую WB-ветку обёртки;
  подменены только HTTP transport WB и выдача синтетического token. Отдельная
  сессия читает target0/confirmed0/status confirmed после закрытия zero_session;
  повтор не отправляет второй PUT. Лишний commit не добавлен.

Исправлено старое ожидание test_share_rule_keeps_allocation_the_rule_does_not_reach:
активные потолки WB100/60 теперь должны сохраняться, как и неактивный Ozon40.
Предыдущая формулировка об успешном WMS-060 означала лишь наличие полей в коде:
она НЕ доказывала работоспособность массового HTTP-запроса. Ни эта запись, ни
предыдущий отчёт не дают основания считать UI принятым.

## Точные файлы этого изменения

- backend/app/services/fbs_stock_rule_service.py
- backend/app/services/fbs_warehouse_binding_service.py
- backend/app/services/marketplace_unload_service.py
- backend/tests/test_fbs_stock_rule_service.py
- backend/tests/test_wms417_stock_review.py
- backend/tests/test_wms417_unload_lock_order.py
- backend/tests/test_wms417_stock_http_contract.py
- docs/reviews/wms417-stock-review-followup-20260910.md

## Проверки

Из backend: `uv run ruff check .` PASS; `uv run mypy .` PASS, 436 source files.
Фронтенд не изменялся; его type/build в этом follow-up не запускались.

Целевой набор rule/stock review/actual frontend HTTP: **59 passed, 1 xfailed**.
HTTP-тест извлекает настоящий saveRule из FfProductsFbsPage через TypeScript AST,
выполняет его и отправляет сформированный JSON в настоящий ASGI API на
синтетическом tenant. Это проверка контракта, не клики в браузере.

Связанный набор (rule, stock review, stock sync, warehouse binding, unload
availability/completion, bulk read, manual binding HTTP, migration) сначала дал
129 passed / 1 skipped / 1 failed. Единственная ошибка была в новом тесте:
использован короткий URL вместо реально зарегистрированного /operations URL.
Исправленный HTTP-тест затем прошёл и в SQLite, и в отдельном PostgreSQL-прогоне.
Пропуск миграции в SQLite ожидаем; её реальный PostgreSQL replay прошёл.

PostgreSQL17.10, отдельная synthetic DB `wms417_stock_review_20260910`:
первый набор нового stock review, трёх unload replay, manual HTTP и migration0261
дал **10 passed**. Финальный набор с сохранёнными shortage/transfer/reservation
тестами WMS-338 дал **17 passed** (в том числе реальная конкуренция двух заказов
за последнюю штуку, недостача и передача без резерва в обоих режимах):

```sh
WMS_TEST_DATABASE_URL=postgresql+psycopg:///wms417_stock_review_20260910 \
uv run pytest -q tests/test_inventory_stock_cap_wms338.py \
  tests/test_wms417_unload_lock_order.py tests/test_wms417_stock_review.py \
  tests/test_wms338_legacy_quota_migration.py
```

После завершения тестов эта synthetic DB удалена. Полный pytest не запускался.

## Открыто координатору; приёмку не закрывать

1. WMS-060: single save реально проходит HTTP и сохраняет units_mode/числа.
   Bulk save в FfProductsFbsPage.tsx отправляет `{product_ids, ...body}`, тогда
   как ProductsFbsRuleBulkBody требует `{product_ids, rule: body}`. Реальный
   ответ422: missing rule / extra flat fields. Сценарий count=2 сохранён как
   **strict xfail** с явной причиной и не считается успешным. После исправления
   фронтенда удалить xfail; неожиданный успех будет сигналом XPASS/ошибкой теста.
2. FbsStockDialog.tsx:172 содержит `!rule.unitsMode || ...` в increasesCap.
   Возврат из процентов в прежние штуки после снижения free может блокироваться
   на клиенте, хотя исправленный сервер его принимает. Проверено чтением кода,
   не браузером. Нужна узкая правка выражения и ручной UI-проход.
3. backend/app/api/fbs_sellers.py GET stock-pool самостоятельно читает retired
   fbs_stock_limit и вычисляет available_for_this_binding как limit минус чужие
   потолки. Исправление service summary исправляет PUT-ответ, но этот отдельный
   GET его не вызывает. Нужен перевод чтения на физический free; не считать
   весь legacy API закрытым только по зелёному тесту service/PUT.

Эти три файла исключены последним назначением владения. Запрошено расширение
только на эти узкие правки; ответа на момент фиксации нет, файлы не изменены.
Findings1/6 Ozon и finding4 product merge — другие исполнители, здесь не оценены
как выполненные. inventory_count/warehouse_map, root checkout, frozen worktree,
Ozon sync, TSD API, chat/App.tsx не менялись. Новых таблиц/журналов/счётчиков нет.
Упаковка и навигация FBS не затронуты. Клиентские stock/financial данные,
ключи/секреты/квота не использовались и не менялись ради тестов.

Нужны независимое read-only review итогового SHA, устранение перечисленных
межслойных дефектов, CI и ручная проверка на собранном из согласованного SHA
стенде: одиночное/массовое правило, проценты→штуки после падения free, WB/Ozon
на двух физических складах, повтор выключения публикации и перечитывание.
Browser/live/marketplace acceptance этим прогоном не заявляется. Merge/deploy
исполнителем не выполняются.
