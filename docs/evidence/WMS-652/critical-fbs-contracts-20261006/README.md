# WMS-652: отдельный контракт критических FBS-путей

База `cb0da8fd79e7fa92b1c882c3bebc9b15a55ebd3e` включает постановку R41–50/C53–63.
Авторство: отдельный тестировщик. Продукт/CI/checker не меняются; прежние защищённые
ожидания меняются только в явно разрешённом R50 фазовом контракте старой гонки.

## Checkpoint1: миграция PG create race по R50

Случай **сохранил прежний pytest ID**:
`backend/tests/test_fbs_supply_from_orders.py::test_parallel_from_orders_one_order_one_supply`.
Он теперь детерминированно удерживает mock ADD после committed pending_confirmation.
Проверяется persisted canonical operation/supply/WB ID и отсутствие order binding
до ответа; второй ASGI-запрос обязан дать503/operation_in_progress/retryable=true
с точным canonical context. После освобождения ADD winner201; тот же loser
послеconfirmed обязан дать409/order_incompatible. В итоге одна поставка,
одна confirmed-операция, order bound/in_supply, ровно один mock create и ADD.
Реальные external calls не используются: существующий e2e WB mock остаётся.

- `race-before.txt` сохраняет исходный недетерминированный тест.
- `race-old-red.log`: при управляемой фазе старое ожидание409 падает на
  **503 с operation_in_progress/pending_confirmation**. Setup succeeded;
  это содержательное рассогласование старого ожидания с фазой, не product regression.
- `race-green.log`/`race-green.xml`: мигрированный тест **1 PASS,0 SKIP**;
  обе обязательные HTTP-фазы и все DB/count invariants исполняются одним case.
- `race-negative-control.py`/`race-mutants-red.log`: in-memory порча настоящего
  `_create_operation_in_progress` на generic503 code, чужой canonical ID и
  retryable=false даёт **3 содержательных FAIL**. Product bytes неизменны.
  Охрану от изменения самого assertion/helper/manifest выполняет отдельная
  инфраструктурная часть R45/R46; здесь она не реализуется и не объявляется PASS.
- Ruff `tests/test_fbs_supply_from_orders.py` — PASS.

Команда из backend:

```sh
WMS_TEST_DATABASE_URL=postgresql+asyncpg://wms_test_runner@127.0.0.1:56635/wms_test_652_fbs_contract /Users/deniscivkunov/Projects/WMS/backend/.venv/bin/python -m pytest tests/test_fbs_supply_from_orders.py::test_parallel_from_orders_one_order_one_supply -q -n0 --tb=short -o asyncio_default_fixture_loop_scope=session -o asyncio_default_test_loop_scope=session --junitxml=../docs/evidence/WMS-652/critical-fbs-contracts-20261006/race-green.xml
```

PostgreSQL17 — отдельный synthetic test cluster на loopback56635/database
wms_test_652_fbs_contract. CI подставляет свою существующую isolated wms_test DB;
обязателен PG backend безskip, `-n0` и обе session loop настройки.

Для negative controls скопировать сохранённый `race-negative-control.py` в
`/tmp/test_wms652_race_negative.py`, запускать из root с `PYTHONPATH="$PWD/backend:$PWD/backend/tests"`
и той же WMS_TEST_DATABASE_URL:

```sh
/Users/deniscivkunov/Projects/WMS/backend/.venv/bin/python -m pytest -c backend/pyproject.toml -p tests.conftest /tmp/test_wms652_race_negative.py -q -n0 --tb=short -o asyncio_default_fixture_loop_scope=session -o asyncio_default_test_loop_scope=session
```

**Dependency closure для freeze:** основной test file (включая четыре `_create/_setup`
helper), `backend/tests/conftest.py`, `backend/tests/fbs_seed_helpers.py`,
`backend/tests/inventory_actor_helpers.py`; общий runner/pytest config уже
принадлежат инфраструктурной защите ведущего. Evidence-only negative-control
не является новым постоянно collected testcase и не должен увеличивать PG count.

Checkpoint1 не завершает C54/регрессионную карту. Настоящий QR-input path и
selection→create/add остаются отдельными следующими тестовыми шагами.
Независимое ревью/аналитическая приёмка/fullCI/production здесь не заявлены.

## Checkpoint2: настоящие экраны Chromium

`frontend/tests-e2e/wms652-critical/browser.mjs` запускает настоящий Chrome, монтирует
FfFbsOrdersScreen, FfFbsWorkspace/FfFbsAssemblyScreen и FbsPackingScanBar без подмены
React-компонентов или контроллера. Скан отправляется в настоящий input событиями
клавиатуры CDP. Подменены только HTTP API и локальный транспорт WMS Print; live
marketplace/printer не вызываются, физическая бумага не проверена.

Шесть постоянных IDs:

- `WMS652.realQr[supply_id=A]`
- `WMS652.realQr[supply_ids=A]`
- `WMS652.realQr[supply_ids=A,B]`
- `WMS652.selection[single-create]`
- `WMS652.selection[seller-warehouse-group-retry]`
- `WMS652.selection[add-existing-refusal-retry]`

Первые три сканируют именно WB QR `*DUIkWJJF`: товарный поиск обязан промахнуться,
lookup находит нужный заказ, полный GS1 КИЗ сохраняется без обрезки, настоящий PNG
QR и две точные копии ЧЗ уходят под стабильными keys, затем pack правильной строки
и следующий QR. Lookup удержан, следующие три ввода отправлены заранее; проверены
FIFO, объект, supply/task/line, шесть print jobs и два pack requests.

Selection проверяет настоящую floating bar, selected popup, create dialog,
группировку seller/warehouse, retry только отказавшей группы и actual add-existing
кнопку. Последняя показывает только совместимую WB-поставку, держит запрос до
ответа, блокирует повторный click, сохраняет checkbox selection при отказе и
делает один явный retry с теми же выбранными IDs. Это HTTP-контракт экрана;
DB/external exactly-once отдельно проверяется backend-защитой.

`browser-green/result.json`: 6 PASS, 0 SKIP. `browser-mutants/mutations.json`:
семь purposeful mutations RED (disconnect input, skip QR, duplicate QR, wrong
next order — каждый во всех трёх entry forms; wrong selected create IDs,
repeat successful group, wrong selected add IDs). `mutations.py` восстанавливает
точные исходные bytes в finally, permanent productdiff отсутствует.

Команды из root worktree (Node24+, Chrome, существующие frontend dependencies):

```sh
cd frontend && npx vite --config tests-e2e/wms652-critical/vite.config.ts
```

В отдельном терминале из root:

```sh
WMS652_EVIDENCE=docs/evidence/WMS-652/critical-fbs-contracts-20261006/browser-green node frontend/tests-e2e/wms652-critical/browser.mjs
WMS652_EVIDENCE=docs/evidence/WMS-652/critical-fbs-contracts-20261006/browser-mutants python3 frontend/tests-e2e/wms652-critical/mutations.py
```

`WMS652_CHROME` задаёт путь Chrome в CI. Loopback16686/16687 обязаны быть свободны.
Отчёт перечисляет каждый fullName ID, статус и source HEAD; отсутствие Chrome/Vite
или неверный ответ synthetic endpoint приводит к FAIL, не skip/green.
Dependency closure: все шесть файлов `frontend/tests-e2e/wms652-critical/`
(main.tsx,index.html,vite.config.ts,fixtures.mjs,browser.mjs,mutations.py),
frontend/package.json/package-lock.json и настоящий product import graph entry
FfFbsOrdersScreen. Evidence-only mutation script не collected baseline case.

Расширение шести комбинаций флагов и uncertain native receipt/remount — следующий
checkpoint. Полная C54 карта этим ограниченным набором ещё не закрыта.

## Checkpoint3: шесть флагов, native receipt и полная копия ЧЗ

Замороженный test-source SHA: `2994b446effcc3296bfebfa173f801c2054a134c`;
отдельная техническая дельта `a41637173c48ec6e2732572aa5ebc8615e8f1272`
добавила только Chrome `--mute-audio`, не меняя33 ожидания.
`cases.json` перечисляет **33 точных fullName IDs**, main runner сравнивает с ним
фактически исполненный порядок и отдельно требует PASS каждого случая. Первые
шесть IDs выше сохранены; ещё27 имеют форму
`WMS652.realQrFlags[<variant>;<entry>]`. Каждая пара выполняется самостоятельно:

- entry: `supply_id=A`, `supply_ids=A`, `supply_ids=A,B`;
- variant: `alloff`, `qr`, `reprint`, `qr+reprint`, `pool`, `qr+pool`,
  `held-receipt`, `lost-accepted-ack`, `remount-after-lost-ack`.

Шесть флагов — существующие WB-настройки, сохранённые в операторском localStorage:
все выключены; толькоQR; только точная перепечать ЧЗ; QR+перепечать;
пулЧЗ; QR+пулЧЗ. Стикер заказа не берёт ЧЗ из пула даже при двух последних
настройках. Проверяются no pool allocation в explicit select payload, полный
сканированный CIS в commit, QR/copy print keys/counts и pack в нужную строку.
`alloff`/`pool` используют существующий локальный selection и local pack key;
остальные — серверный scan UUID. Входной QR отличается от product barcode.

`held-receipt`: native HTTP принимает задание, но его ответ удержан. Уже отправлены
следующиеQR/КИЗ; до receipt нет pack первого и lookup следующего. После release
FIFO завершает оба заказа. `lost-accepted-ack`: native boundary приняла задание,
ответ оборван, pack не случился; явный повтор первого QR использует **тот же**
print key, synthetic accepted ledger даёт старую canonical receipt, затем pack
и следующий QR. Это проверка транспортного reconcile, не физической бумаги.
`remount-after-lost-ack`: тот же отказ, сохранён unfinished intent; page remount
с сохранённым localStorage, API сообщает available bound CIS, настоящий экран
возобновляет старый scan/print key и правильный заказ без второго CIS commit.

Копии ЧЗ больше не подтверждаются только равенством PNG: независимый ZXing
DataMatrixReader декодирует непосредственно pixels каждой native print PNG и
сравнивает **полный canonical CIS нужного заказа**, включая GS-separators и
подписанный хвост. Crop верхних44% отделяет матрицу от текста существующей
60×80mm этикетки. Renderer/claim/mock controller не используются для expected.
ZXing уже declared в frontend/package.json; новые packages не устанавливались.

Дополнительный negative-control runner:

```sh
WMS652_EVIDENCE=docs/evidence/WMS-652/critical-fbs-contracts-20261006/browser-flags-mutants python3 frontend/tests-e2e/wms652-critical/flags-mutations.py
```

Он отдельно нарушает canonical CIS renderer input, actual grouping run на втором
submit (при неизменном правильном label «Повторить(1)»), pack quantity, устойчивый
print intent и запрет выдачи pool CIS для explicit sticker. После каждого опыта
исходные bytes восстанавливаются в finally. Для группировки сохраняется реальный
HTTP trace с **6 POST вместо4**, successful A/C повторяются именно после retry;
предыдущий mutant checkpoint2 ловил неправильный count label до retry и не был
доказательством повторного POST. История обоих опытов сохранена.

Dependency closure дополнена `cases.json`, `flags-mutations.py`; всего8 файлов
под `frontend/tests-e2e/wms652-critical/`. Все declared внешние libraries берутся
из existing frontend package lock: bwip-js, pngjs, @zxing/library и browser/Vite.
Результаты относятся к программным заданиям и synthetic HTTP boundaries.
Приёмку C54 целиком, независимое ревью/антиослабление/fullCI/deploy ведёт root.

По прямой просьбе владельца слышимый test Chrome остановлен в18:40:23UTC
(21:40:23Moscow). Только наш test browser далее запускается с --mute-audio;
системная громкость, пользовательские браузеры и product sounds не менялись.
Прерванный mutation run не объявляется доказательством полного набора.
Итоговый повтор всех пяти mutants сохранён в `browser-flags-mutants-muted`.

## Checkpoint4: настоящие нажатия доступных кнопок

Ведущий нашёл ограничение первого helper: DOM `.click()` обходил visibility и
overlay. Теперь все selection/create/add/popup кнопки получают CDP mouseMoved /
mousePressed / mouseReleased по видимому центру после проверки размеров,
computedStyle и elementFromPoint. Checkbox нажимается через **видимый MUI root**:
встроенный native input у MUI намеренно прозрачный, но занимает тот же control;
его onChange и checked-состояние проверяются прежними бизнес-ожиданиями.
Обычная кнопка обязана быть enabled; только специальный negative busy-add click
допускает видимую disabled кнопку и требует по-прежнему один POST.
Скрытый/перекрытый элемент не получает программный click.

`button-mutations.py`: display:none на настоящей submit-кнопке → содержательный
visibilityRED до createPOST, а повтор successful groups только на actualsecond
mouse-submit → 6POST вместо4. Продукт/дизайн не изменён. Dependency closure теперь
**9 файлов** в том же `frontend/tests-e2e/wms652-critical/` (добавлен
button-mutations.py); точные33IDs и бизнес-ожидания сохранены.

```sh
WMS652_EVIDENCE=docs/evidence/WMS-652/critical-fbs-contracts-20261006/browser-button-mutants python3 frontend/tests-e2e/wms652-critical/button-mutations.py
```

Финальный source с mouse-helper: `ef991e636fd924db670f21370ff7280a62bf0279`.
`browser-button-mutants/mutations.json` на нём подтверждает hide-create visibility
RED (createPOST=0) и actual second-submit duplicate RED (createPOST=6 вместо4).
Пять расширенных print/pack mutants ранее подтверждены на `a41637173`; новая
дельта ef991 меняет только mouse helper selection-действий, не QR/flags assertions.
Финальный `browser-final-green/result.json` повторяет все33 cases на exactef991
после byte restoration, с mute-audio и actual mouse input. `browser-click-green`
сохраняет выявленное при разработке helper ограничение прозрачного MUI nativeinput;
это не productRED, исправленный helper нажимает видимый checkbox root.

## Checkpoint5: ключ explicit selection после remount

По узкому независимому review B `ef56da85cde417e796010cd3963baa6ddc853866`
добавлены assertions к тем же трём `remount-after-lost-ack` IDs. Первый и
восстановленный explicit selection POST должны иметь одинаковый непустой
idempotency_key и сохранять actual supply/order/sticker identity. Товарный
lookup miss не включён в сравнение. Базовый product trace уже был правильным;
это укрепление контракта, product fix не выполнялся, cases.json/33IDs сохранены.

Test-source SHA: `8e501fcb969ad0ceb482e479f69fd37f726862ca`.
Новый `remount-selection-mutation.py` временно меняет только request key в
saved-explicit ветке `deps.select` на randomUUID, не меняя native print dispatch.
`remount-selection-key-red/mutation-proof.json`: **ровно три remount RED** на
сообщении «restored explicit selection must reuse initial idempotency key»;
остальные30 cases PASS. Во всех трёх trace native print keys остались
scan-wb-a-order, scan-wb-a-order, scan-wb-next-order, а accepted ledger содержит
те же два уникальных intents; обе правильные pack операции завершились.
Таким образом RED не объясняется новым print key/неверным объектом/ошибкой setup.
Product bytes восстановлены в finally, productdiff после опыта пуст.

`remount-selection-key-green/result.json`: после восстановления все33 cases
PASS на том же exactsource SHA8e501, включая три усиленных remount cases.
Весь запуск использует Chrome --mute-audio. Dependency closure теперь10 файлов
под `frontend/tests-e2e/wms652-critical/`, включая новый mutation helper;
registry/CI остаются ответственностью root.

Из root при существующем isolated Vite server:

```sh
WMS652_EVIDENCE=docs/evidence/WMS-652/critical-fbs-contracts-20261006/remount-selection-key-red python3 frontend/tests-e2e/wms652-critical/remount-selection-mutation.py
WMS652_EVIDENCE=docs/evidence/WMS-652/critical-fbs-contracts-20261006/remount-selection-key-green node frontend/tests-e2e/wms652-critical/browser.mjs
```

## Checkpoint C59/R48: 43 браузерных сценария и геометрия

Последний контракт добавляет десять проверок геометрии к прежним 33 сценариям,
сохраняя их идентификаторы и ожидания. Точная матрица семи допустимых входов
упаковки, границы измерений, три намеренные поломки и результат полного
восстановленного прогона описаны в [geometry-contract.md](geometry-contract.md).
Защита всего продуктового дерева отдельно зафиксирована тестовым коммитом
`9bb8b93254a7f79da7d8fd73eedfa75a1cf69b41`; реализация проверяющего модуля
и обязательное включение этих контрактов в CI принадлежат ведущему.
