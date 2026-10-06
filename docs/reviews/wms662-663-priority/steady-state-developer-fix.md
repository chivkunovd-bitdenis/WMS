# WMS-662 — минимальное исправление steady-state batch deadlock

06.10.2026. Разработчик Sol 6.1; продолжение существующего checkout
`codex/wms662-prod-handoff` после независимого RED-контракта
`3abc3987694c4a27710d598039bb2e26d84eaf9c`. До правки прочитаны локальные
AGENTS.md, актуальный origin/etalon:AGENTS.md
(`954862b718f9f2f1faefb2f00ad2fef72a6e1929`), требования WMS-662,
owner stock boundary `ddd4fb68417c6922b662849c028d7b4b21dec242`,
steady-state-handoff-tester.md и его SQL evidence, предыдущая причинная
коррекция astra-batch-causality-7f62e184.md.

**Результат разработчика: исправление проверено целевыми тестами; независимое
Astra high ревью, приёмка аналитика и полный CI остаются следующими этапами.**
Это не production readiness и не новый вердикт требований.

## Подтверждённая причина и изменение

Новый нормализованный A/B fixture устранил второй ранний UPDATE заказа B.
В исходном RED обычная C получила P2, затем ждала Seller, уже удерживаемый
batch после начисления A. Batch продолжил B под тем же внешним transaction
и встретно ждал при INSERT fbs_shipment_reversal_ledger. PostgreSQL подтвердил
40P01 и pg_cycle=True; первоначальный C=0 при ожидаемых 1800 не скрыт
последующим recovery. Конкретный внутренний FK tuple lock отдельно не измерен.

В трёх business service files добавлено 50 строк. Новый локальный helper
lock_handoff_batch_products вызывается после существующих parent/order locks
и до статусов/начислений во всех трёх observed batch entrypoints:
WB status sync, Ozon status sync и Ozon import reconciliation. Он выбирает
только существующие source=wms поставки порции с точными tenant/seller,
блокирует весь их order scope по UUID, затем все его Product по UUID
FOR UPDATE до первого seller invoice fence.

Весь order scope необходим: conduct_supply возобновляет также ранее сохранённое
доказательство неопрошенных заказов внутри выбранных поставок. Product scope
включает основную связь, товарные позиции и прежние товары существующих
резервов, поскольку отмена/снятие резервов может затрагивать старое сопоставление.
Блокировки взяты в той же внешней транзакции и не выпускаются между stock,
ledger, reserve, facts и charges. Для разных поставок одной порции больше
нет последовательности P1 → Seller → новый P2. C ожидает уже взятый stock/FK
lock, затем продолжает после commit batch.

Существующие ledger locks, seller FOR NO KEY UPDATE invoice fence, savepoints,
деньги, invoice snapshots и атомарность all-active cancellation сохранены.
Ordinary handoff/cancellation, inventory/write-off, stock publication и transport
files не менялись. Внешние карточки, split reads и WB membership по-прежнему
получаются до write locks; новый helper HTTP не выполняет. Новых таблиц,
журналов, глобального tenant/seller mutex, retry или рефакторинга нет.

Граница владельца сохранена: ordinary status refresh не вводит нового расхода.
Проводится только ещё отсутствующее количество существующей WMS-поставки,
доказанное для её точного состава, один раз. Отмена не приходует физический товар.

## Фактические проверки

- Новый frozen steady-state PostgreSQL test: **1 passed**, 2.87 s.
  pg_cycle=False, SQL errors=[], A/B/C по 1800 в ПЕРВОМ проходе,
  stock P1 13→12, P2 12→10, reserves={}, business issues=[].
  Recovery/retry assertions также выполнены; первоначальных ошибок не было.
- Старый frozen 7f62 public batch test: **1 passed**, 1.95 s.
  pg_cycle=False, SQL errors=[], A/B/C по 1800; все бизнес-ожидания и retry
  выполнены, файл побайтово неизменён.
- Frozen F6: **4 passed**, 3.54 s, настоящий PostgreSQL, serial/no xdist.
  Normal/observed handoff против отмены другого заказа сохранили stock,
  начисление 1800, полное сторно и повтор без второй внешней сдачи.
- Adjacent SQLite suite: **145 passed**, 44.92 s, два workers.
  Выполнены test_wms662_observed_handoff.py (92 исходных stock-boundary cases),
  test_wms662_astra_regressions.py, test_wms662_approve_scope_race.py,
  test_wms662_continued_billing.py, test_wms662_invoiced_continuation.py,
  test_wms662_continued_billing_cancellation.py, test_fbs_handover_billing.py,
  test_fbs_cancellations.py, test_billing_ledger_service.py,
  test_operation_facts.py, test_operation_fact_recovery.py,
  test_ozon_delivery_confirmation.py. Включены frozen financial 11 и issued
  invoice/document packing/cancellation continuation, без новых ожиданий.
- ruff check .: PASS. mypy . --no-incremental --cache-dir=/dev/null:
  PASS, 552 source files. git diff --check: PASS.
  check_task_documents.py 3abc3987: PASS, AGENTS.md/CLAUDE.md совпадают.

Первый adjacent command имел два неверных имени файлов
(test_fbs_cancellation_service.py и test_operation_fact_service.py), завершился
exit 5 без выполненных тестов. Это ошибка выбора команды, не business RED/PASS.
После исправления только списка существующих файлов выполнен приведённый
145-case прогон; product и tests между командами не менялись.

Полные stdout целевых PG прогонов и итог adjacent сохранены в
[steady-state-developer-fix-evidence.txt](steady-state-developer-fix-evidence.txt).
Deprecation warnings не являются ошибками SQL и не скрывают failures.

## Изоляция PostgreSQL и сохранность контракта

Использован только собственный ранее остановленный PostgreSQL 16.14 cluster
/tmp/wms662-steady-pg-55468-68206. Перед стартом проверены отсутствие его
postmaster и свободный 55468; перед и после каждой PG стадии SQL подтвердил
0 других client connections. Shared 55466 и 56517 не подключались и не менялись.

Steady test исполнялся через TCP 127.0.0.1:55468/wms_test_662_steady.
Для неизменённого старого теста создана база wms_test_662_batch в ЭТОМ ЖЕ
собственном кластере. Его URL сохранил ожидаемый port=55466, но query
host=/tmp/wms662-own-batch-socket-55468 направил драйвер через частный Unix
socket alias .s.PGSQL.55466 → /tmp/.s.PGSQL.55468. Это конфигурация соединения,
не изменение fixture/SQL/business assertions; TCP/shared 55466 не использован.
Независимый psql через тот же alias подтвердил actual server port=55468,
current_database=wms_test_662_batch, current_user=wms_test и 0 других клиентов.

После завершения обоих batch tests собственный cluster был штатно остановлен
и запущен на проверенном свободном 55467, который прямо допускает frozen F6
fixture. Создана собственная wms_test_662_f6; fixture проверила actual
database/user/server/port. После проверок кластер снова остановлен.
Никакой другой кластер или база не изменялись; новых больших ramdisk нет.

Tests, expectations, requirements и guards не правились. Сохранённые Git blobs:
old batch eb2255ca93ac453af1117339aa6cc9aba07ee2a0;
steady 6f60ecd6c0cd8550857d671a2368f4119b28db4c;
F6 596edfbd0a4b47c61556ffedf38e8c2488fc43f0.
Diff от 3abc3987 по backend/tests, guards, docs/requirements пуст.
Чужие untracked result files сохранены и в commit не включаются.

## Передача ведущему

Следующий шаг — независимое Astra high ревью опубликованного SHA именно этого
business delta с frozen RED/новым GREEN и сохранением invoice/stock boundaries;
затем исходный аналитик, затем полный CI финального SHA. Разработчик не
подменяет эти этапы. Пользователь запретил запуск skills/agents в этой сессии:
здесь они не запускались. Браузер, live, кабинеты секретов, main/etalon merge,
production и deploy не использовались. Владелец требует один общий выпуск:
этот commit/push не является отдельным выпуском WMS-662.
