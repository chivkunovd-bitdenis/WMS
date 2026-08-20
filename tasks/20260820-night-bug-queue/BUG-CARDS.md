# BUG-CARDS — WMS night queue на 2026-08-21

Общее правило: команды ниже только открывают карточки в local Pipeline v2
controller. Они не деплоят, не ходят в live WB/Ozon и не меняют секреты.

## BUG-WMS-PV2-001 — exact-SHA deploy: build-once promotion

- owner role: `pipeline-dispatcher`
- stage: `S01/S02` intake/classification, затем `S13/S14`, `S23`, `S26/S27`
- traits: `bug,pipeline_change,release_change`
- risk: `critical`
- источник: `PIPELINE-HOLES-RU.md` P0 exact-SHA guard, incidents `И15`–`И17`

Проблема: exact Git SHA уже защищён, но production всё ещё собирает контейнеры
на сервере. Это не доказывает, что artifact digest, принятый перед release, тот
же самый, который реально запущен.

Acceptance:

- Given owner-approved `release_sha`; When release candidate собран; Then есть
  immutable manifest с digest для backend, worker, migrations и frontend bundle.
- Given manifest; When deploy path выполняется в dry-run/staging; Then сервер
  продвигает только готовые digests и не запускает `docker compose build`.
- Given runtime smoke; Then `/api/version` и frontend bundle соответствуют
  manifest/release SHA; mismatch блокирует deploy.
- Live production deploy в этой карточке запрещён.

Tests:

- metatest/fixture на `MT15` и `MT32`: SHA match + digest mismatch блокирует
  promotion.
- dry-run тест deploy script: отсутствие manifest, dirty tree или чужой SHA дают
  typed `RELEASE_BLOCKED`.
- smoke fixture проверяет `/api/version` без обращения к production.

Command:

```bash
python3 scripts/pipeline/run.py open --task-id BUG-WMS-PV2-001 --source "2026-08-21 night queue: exact-SHA deploy residue from PIPELINE-HOLES P0 and incidents I15-I17; no live deploy" --traits bug,pipeline_change,release_change --risk-level critical
```

## BUG-WMS-PV2-002 — fail-closed WB/Ozon test egress

- owner role: `pipeline-dev`
- stage: `S01/S02`, `B01/B02/B03`, `S03/S04`, `S13/S14`, `S15/S22/S23`
- traits: `bug,external_contract,background_worker,pipeline_change`
- risk: `critical`
- источник: `PIPELINE-HOLES-RU.md` P0 fail-closed egress, metatest `MT13`

Проблема: тестовый контур может случайно обратиться в живой WB/Ozon. Это
ломает главное правило Pipeline v2: тесты по умолчанию закрыты наружу, а внешние
контракты проверяются через emulator или явно разрешённый sandbox.

Acceptance:

- Given backend/frontend/worker/e2e test run; When код пытается открыть live
  host WB или Ozon; Then запрос падает fail-closed с понятной причиной
  `test_egress_blocked`.
- Given разрешённый emulator/sandbox base URL; Then тесты проходят только через
  этот endpoint и логируют выбранный contract target.
- Existing FBS/WB sync tests не используют реальные marketplace endpoints.
- Ozon закрыт тем же guard-ом, даже если Ozon-модуль ещё не активен.

Tests:

- backend test на запрет `*.wildberries.ru`/`*.ozon.ru` в pytest и worker path.
- frontend/e2e smoke: webServer env с mock/emulator, без наружной сети.
- CI/metatest `MT13`: live external host из test mode всегда красит проверку.

Command:

```bash
python3 scripts/pipeline/run.py open --task-id BUG-WMS-PV2-002 --source "2026-08-21 night queue: fail-closed WB/Ozon test egress; no live marketplace calls" --traits bug,external_contract,background_worker,pipeline_change --risk-level critical
```

## BUG-WMS-TESTSTACK-001 — честный test-stack: migrations вместо create_all

- owner role: `pipeline-reviewer`
- stage: `S01/S02`, `B01/B02/B03`, `S13/S14`, `S15`, `S22/S23`
- traits: `bug,database_change,pipeline_change`
- risk: `high`
- источник: observed `WMS_AUTO_CREATE_SCHEMA=1` + `create_all`, shared sqlite

Проблема: часть тестов поднимает схему через `create_all`, а не через реальные
migrations. Такой прогон может быть зелёным при сломанной миграционной цепочке
и маскировать production-риск.

Acceptance:

- Given honest backend test run; When БД создаётся с нуля; Then схема строится
  миграциями, а не неявным `create_all`.
- Given `WMS_AUTO_CREATE_SCHEMA=1`; Then его область явно ограничена локальными
  seed/fixture сценариями и не проходит как release/integration proof.
- Given параллельные тесты; Then каждый процесс получает уникальный
  `WMS_TEST_DATABASE_URL` или suite сериализуется, чтобы shared sqlite не ронял
  `no such table`.
- Missing migration fails before functional tests, а не прячется фикстурой.

Tests:

- migration smoke: empty DB -> alembic head -> ключевые WMS tables существуют.
- regression test: отключённый auto-create ловит отсутствие migration.
- fixture/concurrency test: две параллельные сессии не делят
  `backend/tests/wms_pytest.sqlite`.

Command:

```bash
python3 scripts/pipeline/run.py open --task-id BUG-WMS-TESTSTACK-001 --source "2026-08-21 night queue: honest WMS test stack, WMS_AUTO_CREATE_SCHEMA/create_all must not replace migrations" --traits bug,database_change,pipeline_change --risk-level high
```

## BUG-WMS-FBS-CZ-001 — FBS/Честный знак: dispatch eligibility

- owner role: `pipeline-ba`
- stage: `S01/S02`, `B01/B02/B03`, `S03/S04`, `S15`, `S25`
- traits: `bug,external_contract,tenant_sensitive`
- risk: `critical`
- источник: FBS/ЧЗ incident, `sgtinApplied` vs `sgtinIntroduced/sgtinSoldB2B`

Проблема: WMS должен различать “код отправлен/сохранён” и “код допустим для
dispatch”. Нельзя закрывать заказ или отдавать поставку, если обязательная
маркировка есть только формально, но WB/ЧЗ статус не даёт права на передачу.

Acceptance:

- Given заказ с обязательной маркировкой; When статус кода не eligible; Then
  dispatch/deliver заблокирован с причиной для оператора и без изменения заказа
  на “завершён”.
- Given `sgtinApplied`; Then карточка фиксирует oracle: это либо запрещающий
  статус, либо требует явного owner/WB-contract решения. Не угадывать правило.
- Given eligible status (`sgtinIntroduced`/`sgtinSoldB2B` или подтверждённый
  эквивалент); Then dispatch проходит и сохраняет audit trail.
- GS separator и исходное значение КИЗ сохраняются, но секреты/токены не
  попадают в evidence.

Tests:

- backend cases на statuses: applied, introduced, soldB2B, error/unknown.
- emulator/sandbox contract case на WB meta response и readable block reason.
- Product Browser check: оператор видит блокировку и успешный путь на eligible
  code без ручной правки данных.

Command:

```bash
python3 scripts/pipeline/run.py open --task-id BUG-WMS-FBS-CZ-001 --source "2026-08-21 night queue: FBS Chestny Znak marking dispatch eligibility, preserve WB/CZ oracle, no live WB calls" --traits bug,external_contract,tenant_sensitive --risk-level critical
```

## BUG-WMS-FBS-PRINT-001 — FBS label print quantity и supply scope

- owner role: `pipeline-browser-product`
- stage: `S01/S02`, `B01/B02/B03`, `S09/S10`, `S15`, `S22`, `S25`
- traits: `bug,ui_change,print`
- risk: `high`
- источник: observed `wbDefaultQty` -> `fallbackLabelCopies`, supply-scope issue

Проблема: печать labels не должна умножать количество копий по количеству
товара/заказов и не должна печатать коды вне текущей поставки.

Acceptance:

- Given поставка на N заказов; When оператор открывает печать; Then default —
  ровно 1 label на выбранный order/code, а не `N * N`.
- Given текущая поставка; Then print payload содержит только labels/codes этой
  поставки, не все коды селлера и не соседние supply.
- Given повторная печать; Then оператор явно видит количество copies и может
  изменить его осознанно.
- Printed preview/count проверяется в browser/device-compatible flow; live printer
  не обязателен без отдельного owner approval.

Tests:

- unit/service test: `wbDefaultQty` не попадает в copies fallback.
- Playwright/Product Browser: поставка 155 заказов показывает 155 labels, не
  24025; соседняя поставка не попадает в payload.
- regression case: repeat print сохраняет явный copies value и не меняет scope.

Command:

```bash
python3 scripts/pipeline/run.py open --task-id BUG-WMS-FBS-PRINT-001 --source "2026-08-21 night queue: FBS label print quantity and supply scope, no live deploy" --traits bug,ui_change,print --risk-level high
```
