# WMS-663: отдельный контракт остаточных случаев C2/C3/C5/C7/C11/C12/C13/C14

TESTWRITER663 выполняет ограниченное поручение владельца без skills и дополнительных агентов. Прочитаны AGENTS.md, полный WMS-663 и текущий отчёт аналитика `923961749907ee212d450f25b19950c43b270ce0` — `docs/reviews/wms663-current-analyst-acceptance-20261006.md`. Выполнены fetch origin/etalon и чтение его правил. Работа продолжает существующий кандидат без rebase. Исходный HEAD этого прохода `01dec4491cfb221e0d1b061e4908d45c01b05989`; во время работы другой тестировщик сохранил свои C16/C18 коммиты до `d940e4722304366d6d8ccac313dec0500848758b`.

Владение — только два новых файла тестов и этот handoff. Продукт `1fd2d92dc30eb376c1d8a8e27238e52d963a196e` сохранён: diff backend/app и frontend product TSX (исключая test.tsx) пуст. Исходные положительные fixtures `17ce363a8360620bc6b843e003278cd4ea106678` побайтно сохранены: diff исходного `test_wms663_customs_documents_contract.py` пуст. Требования, исходные frozen-тесты, guard manifest, workflow и файлы другого тестировщика не редактировались. Никаких новых требований или архитектуры.

## Исполненный остаточный контракт

Все ссылки ниже относятся к новым файлам:

- backend: `backend/tests/test_wms663_residual_behavior_contract.py`;
- UI: `frontend/src/screens/v2/OzonExemplarDocuments.wms663.residual.dom.test.tsx`.

| C | Точное покрытие | Результат |
|---|---|---|
| C2 | UI `C2: %s exact number → absent → unchecked empty; PUT and refresh`, отдельно ГТД и РНПТ. Точный `000/ABC-09`, фактические PUT/expected_version, номер→галка→снятие; пустой номер без галки отправляет null/false. GET refresh и полное размонтирование/повторное открытие читают fake server. | 2 PASS |
| C3 | `test_c3_three_exemplars_and_other_orders_sellers_wb_are_isolated`: два SKU, три экземпляра A/81/82/83; изменён только 81, payload соседей равен исходному. Второй заказ того же seller, другой seller того же tenant и WB остаются неизменными; вызовы адресованы только исходному posting. Чужой tenant GET и save для каждого соседнего заказа — 404/ноль вызовов, действие WB в своём tenant отклонено/ноль вызовов. Доступ к разрешённому другому seller того же tenant не переизобретён как запрещённый. | PASS |
| C5 | `test_c5_gtd_then_kiz_then_rnpt_preserves_each_complete_set`: точная последовательность ГТД→КИЗ того же экземпляра→новый РНПТ; три SET, сохранность ГТД, маркировки, weight, multi_box_qty, обоих соседей. Fake cabinet после каждой записи получает полный предыдущий payload. | PASS |
| C7 | `test_c7_foreign_exemplar_id_cannot_accept_and_status_can_resolve`: после SET полный STATUS подменяет целевой 81 на чужой 99981. Ложного accepted нет, исходный ввод сохранён. Затем полный здоровый STATUS с настоящим 81 должен разрешить проверку без второго SET. | **RED на восстановлении**, подробности ниже |
| C11 | UI `C11: rejected absent → uncheck → current number, refresh and reopen preserve correction`: отказ absent/gtd_invalid→снятие галки→новый явный PUT с текущей version→refresh→reopen. `C11: delayed A status after switching %s does not mutate current component`, отдельно B и переход через другую вкладку: A GET остаётся pending, B загружается/получает dirty input, поздний A не меняет DOM/ввод/ошибки B. Используется тот же order-specific React key, что в workspace; исходный workspace test не трогается. | 3 PASS |
| C12 | Backend `test_c12_optional_missing_nullable_preserves_input_and_rejection[missing/null]`: optional weight/marks/check_status/rnpt_error_codes, сохранён конкретный gtd_invalid и выбор. `test_c12_real_json_decode_failure_is_bounded_unknown_with_saved_choice`: настоящий JSON decoder транспорта с httpx.MockTransport, испорченный JSON 200→unknown/причина/выбор; ровно один STATUS, повторного SET нет. UI malformed refresh сохраняет dirty ввод и прежний gtd_invalid; optional missing/null номеров/флагов/errors безопасны и не создают implicit absent/accepted. | 3 backend + 3 UI PASS |
| C13 | `test_c13_background_restart_selects_gtd_only_without_marking`: save checking→закрыть сессию→новая SessionLocal→реальный `sync_marketplace_order_statuses_for_target` выбирает заказ по JSON и выполняет реальный resume→accepted/тот же choices. Ни одной FbsOrderMarking до/после; только STATUS после restart, SET один. Credentials заменены тестовыми; обычная синхронизация статусов подменена отдельным no-op, не document selection/resume. Это новая сессия фонового пути, не проверка ОС-перезапуска worker-процесса. | PASS |
| C14 | `test_c14_existing_qr_after_accepted_preserves_documents_and_local_accounting`: accepted→реальный `retry_fbs_packing_box_qr`→реальная сборка заказа по двум существующим коробам→fake `/ship` с точными packages. Документные SET/сохранённый snapshot/choices не потеряны. До QR неизменны pick/pack status, picked quantities, reserve; нет ship/labels/print assets/stock writes. После QR reserve и количество InventoryBalance/InventoryMovement сохранены. Label request заменён fake batch; физическая печать и реальные labels не проверялись. В существующем API документы живут в exemplar SET, `/ship` передаёт packages: новые поля в ship не придуманы. | PASS |

## Новый воспроизведённый дефект C7 — передать разработчику

После первого STATUS `exemplar_id=99981` добавляется в retained snapshot рядом с реальными 81/82. Следующий здоровый полный STATUS содержит 81/82 и соседний SKU/91, точный исходный выбор совпадает. Внутренний `document_data.state` становится `accepted`, но `document_view.state` остаётся `unknown`, поскольку retained чужой 99981 теперь включён в ожидаемый состав и отсутствует в свежем корректном ответе.

Финальный диагностический вывод frozen нового теста:

```text
view_state: unknown
stored_state: accepted
snapshot_ids: [81, 82, 99981]
current_ids: [81, 82]
assert resolved["state"] == "accepted"  # FAIL
```

Это новый RED до исправления продукта; первоначальный чужой ответ правильно не принимается. Нарушена именно разрешимость проверки после последующего корректного полного STATUS (C7/R7). Ожидание не ослаблено до «unknown навсегда». Для разработчика минимальный предмет — безопасное восстановление после подмены ID с сохранением исходного выбора и без повторного SET. Не расширять исправление на новую архитектуру или другие требования. Данный тестировщик продукт не исправляет и повторного ревью неизменённого кода не запускает.

## Точные прогоны

Из backend:

```sh
env -u WMS_TEST_DATABASE_URL -u WMS_TEST_DATA_DIR PYTHONDONTWRITEBYTECODE=1 \
  /Users/deniscivkunov/Projects/WMS/backend/.venv/bin/python -m pytest \
  tests/test_wms663_residual_behavior_contract.py -n 1 -q --tb=short
```

Финальный результат: **7 PASS / 1 FAIL / 4.67 s, exit 1**, без skips. В начале были ошибки собственной новой оснастки (обязательный mapping_status, dict choices вместо list, position.picked_quantity и согласованность tuple); исправлены только в новом файле. Эти ошибки не выданы за продуктовый RED. C7 воспроизводится после их исправления. Отдельный финальный адресный C14 до последнего общего запуска: 1 PASS/4.74 s. Последний общий запуск повторил только восемь новых случаев после завершения исправлений оснастки.

Из frontend:

```sh
./node_modules/.bin/vitest run \
  src/screens/v2/OzonExemplarDocuments.wms663.residual.dom.test.tsx \
  --maxWorkers 1 --minWorkers 1
```

**8 PASS / 2.74 s, exit 0**. После этого файл UI не менялся. Ruff только нового backend-файла: **PASS**. Существующие наборы не запускались; build/npm ci/full tsc/mypy/full CI не выполнялись. Проектный mypy исключает tests. Никакого PostgreSQL-кластера, live DB, secret access, Mac browser, live API/ship/printing, внешних записей, TG, merge или deploy. HTTP decoder тест работает исключительно через MockTransport. В каждом backend-тесте autouse проверяет SQLite; сняты WMS_TEST overrides. Каждый запуск использует один worker; тестовые данные из существующего conftest изолированы по процессу/worker.

## Что остаётся ведущему

Новые GREEN закрывают перечисленные локальные пробелы C2/C3/C5/C11/C12/C13/C14 в указанной границе. **C7 требует исправления и адресного повторения сохранённого теста; полной приёмки нет.** Исходный DOM selector/C16, remote C10 PostgreSQL/mixed race/double click и C18 остаются у `urgent663_remaining_contract_tester`; его текущие результаты не переоценены этим проходом. Свежий официальный контракт C17 и разрешённый внешний Ozon-цикл C19 здесь не проверялись. Полный вывод по C1–C19 делает исходный аналитик один раз после объединения всех отчётов и исправления нового RED; этот handoff не подменяет его заключение.

Git-публикация включает ровно этот handoff и два новых тестовых файла. Проверенный commit SHA сообщается отдельно после commit/push, чтобы отчёт не содержал невозможную ссылку на собственный SHA. Сохранённый RED предназначен для последующего developer fix, а не для объявления продукта готовым.
