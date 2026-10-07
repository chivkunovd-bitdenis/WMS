# Общая интеграция ночного выпуска 07.10.2026

Это подготовка в собственном постоянном worktree `.worktrees/night1007-integration`, ветка `codex/night1007-integration`, исходный проверенный etalon `4b298efc95be7b4b6b7fe5665be9f3671f1fe747`. Исходный PR387 и рабочие ветки исполнителей не изменяются. Явно принятая ведущим база f606 (product d618 + pipeline0151) импортирована отдельным merge92d5e402d с подтверждённой сохранностью222paths/1146IDs. Принятая686 импортируется точным0d054a2256322428e815ed78fc8d149b0c140aa6; новые ветки без ревью/приёмки не взяты. Полные тесты только в CI, локальные dependency installs не выполняются.

Владелец передал через ведущего: «отменяй никаких там нигде согласований не надо будет… я иду спать… с утра … готовым». Ведущий зафиксировал разрешение на необходимые исправления процесса, точный проверенный SOURCE→main bootstrap, merge etalon и deploy без следующего вопроса. Это не отменяет отдельные роли тестировщика/разработчика/ревью/аналитика, защиту старых сценариев и проверку фактически установленной версии. Интегратор main/etalon/deploy не меняет; выпуск выполняет ведущий после проверок.

## Точные текущие отказы прежней общей базы

PR387 HEAD `f6066d68bd198794602a6e8916612d0d3b32460f`, actual tested merge `2d1707cacdb9bbd2e92eee75115c9749ac969fcc`, CIrun37523087363, attempt1.

| Место | Проверенный факт | Узкая передача |
| --- | --- | --- |
| backend-shard-0 job112473176355 | 4 FAIL параметров `test_prod_deploy_backup.py::test_deploy_requires_verified_backup_before_migration` (пустой, dump, listing, retry),2210PASS/98SKIP/1XFAIL;621.10s | Fixture копирует3 старых файла (14–26) и не содержит нового verifier. Script80–83 запускает его доDocker; StopIteration127 или `backup failed` assertion113 вместо ожидаемой ветки. |
| backend-shard-1 job112473177232 | 3 FAIL параметров того же теста (archive,empty,network),2210PASS/99SKIP;672.48s | stderr: отсутствует syntheticrepo/scripts/ci/verify_server_process_ci.py. `subnet/gateway changed` assertion123 не достигается. |
| print-regressions job112473176356 | 10PASS/1FAIL,0SKIP; C5 `wms672-box-labels.test.mjs:303` | На308 не появился alert `WMS672 decode failed at299` за30s; диагностический screenshot тоже не успел за3s. Не удалять случай и не выдавать увеличение ожидания за исправление. |
| backend required aggregator | отказ после красных producers; нет backend-all artifact | Это правильное fail-closed следствие, не отдельный продуктовый дефект. process-proof SKIPPED вследствие failures. |
| process-integrity | required отказ | Работает installed main anchor; отсутствие completed successful raw-proof не принимается. Gate не ослаблять. |

Исторический отказ `test_parallel_from_orders_one_order_one_supply` наd618/run37505511512 не является текущим проваломf606: последние short summaries обоих shards содержат только7 fixture failures.

Отдельный existing diagnostic `codex/wms672-c5-linux-diagnostic`/b44ef1077, run37527056184: неизменный C5 проходит первоначальную ошибкуdecode и падает уже на retry `transfer():121`, вызов317, `waitForFunction`30s. Это иной наблюдаемый этап; root назначил отдельного tester652 PID5934. Его diagnosticbranch намеренно заменяет весь CI коротким прогоном и НЕ является источником общей pipeline или разрешением урезать проверки. Product fixes — только после meaningful RED и отдельной роли; интегратор их не делает.

## Серверный verifier не замаскирован исправлением fixture

[Свежий runtime proof](server-gate-runtime-readonly.json): read-only SSH на существующий `/opt/wms`, Python3.10.12, checkout8f11d912. Три public urllib GET без Authorization дали200 для workflow/run/artifact metadata с проверкойTLS; доступ есть, rate57/60 после чтения. Новыйservergate в установленном checkout ещё отсутствует. Exact source verifier+verify_ci изf606 выполнен только в памяти Python, без записей на сервере, Docker, DB, build/migrations или deploy. Imports PASS; installed oldSHA корректно отказан exit4 `Нет push-CI etalon для указанного SHA; выкладка ожидает CI`.

Это proof исполнимости и негативного пути на настоящем runtime. Оно не доказывает GREEN будущего общегоSHA. После merge общегоSHA в etalon нужен его exact pushCI и current proof artifact, затем повтор server verifier передdeploy. Секреты/конфигурацияключей не читались и не изменялись; TLS не обходился.

## Минимальная база и почему она шире прямой675

Прямой ремонт675 использует принятую662, отдельная новая продуктовая675 не нужна. Нужны наблюдения точного состава, `conduct_supply`, идемпотентный ledger, источники/остатки, блокировки и начисления. Конкретные runtime пути: новый `fbs_observed_handoff_service.py`; `fbs_shipment_service.py` вызывает его в1362/1606/2210/2306/2319; `ozon_fbs_sync_service.py`1014/1073 и `wb_marketplace_orders_service.py`940 сохраняют/применяют observations. `conduct_supply` вызывает существующие source service, billing и Ozon packing service. Существующие модели ledger/stock уже есть вetalon. Свежий675 analyst отдельно пересчитает фактическуюmissingdelta; исторические26 не применяются автоматически.

Но одна изолированная662 не является проверяемой базой всех обязательных1146 сценариев. Existing SOURCE0151 уже независимо принят с productreference d618 и защищает663 release-retry,517 withdrawal/sales/Mac,666/672/673 UI/печать и остальные согласованные процессы. Статический import-check защищённых backendtests прямо нашёл отсутствующие вetalon productmodules: observed_handoff для675, ozon_exemplar_documents для663, wb_sales_report для517. Нельзя сохранить эти обязательные тесты на бумаге и исключить их необходимый продукт.

Рекомендованный ранее принятый общий baseline: exact producttree `d61805978b3e7878d1056c99b4e6e0823edf49a5` плюс process/source `0151a555ac429957d0eee591317cc4326e909dfd` и последующие doc/evidence commits387. Productdiff d618→f606 пуст по прежнему independently accepted scope. Состав не импортируется молча: ниже полный явный перечень. Если выбрать более узкую product662-only базу, надо сначала доказать все1146 старых случаев на ней; имеющихся доказательств такого поднабора нет, исключениеtests не допускается.

| Прежний согласованный контур | Почему нужен при сохранении принятого общегоSOURCE |
| --- | --- |
| 662 и675 | Точный accounting/observed handoff и incident regression, прямая основа ремонтаБамбука. Берётся исходный accepted механизм/guards; новая meta-test ветка675 не берётся. |
| 663 | Ozon requirements/documents/explicitretry и общий FBSworkspace/API; обязательные backend/PG/UIcases, новый module импортируется защищённым тестом. |
| 666 | Настоящий текущий подбор/упаковка, общий workspace/scanners; protected realFBSbrowser43 и frontend cases не должны вернуться к отвергнутому layout. |
| 517 | WB sales-backed withdrawal и Mac helper; обязательные withdrawalPG5/Mac110 и backend tests требуют wb_sales_report. Это зависимость согласованной общей охраны, не бизнес-зависимость675. |
| 653/657/659/660/667/669/670/672/673 | Уже согласованный прежний общий пакет: stock/scope, размеры/короба/этикетки/каталог и print/browser/PGcontracts. Сохраняются принятойbase, не переобъявляются новой функцией ночного запроса. |
| 681/683/656 | Прежние hotfixes сохранены; etalon уже включает QR681. Нельзя перезаписать их более ранним checkout. |
| 652 | Все222 protected paths,18suites,1146IDs, Linux/Windows/PG/browser/PDF/Mac/shards, реальные raw receipts и main anchor. |
| Миграционная цепочка | В387 есть9 исторических assistant/staging merge revisions; это закрытие ancestry схемы для общего migrationCI, не поручение добавить новую assistantfeature. Перед переносом подтвердить closure и целевыеmodels; отдельные migrations без кода не применять. |

Пакет не включает новую651: accepted existing «упаковано» сохраняется по позднему решению владельца. Старые API/FBS компоненты зачастую содержат сразу662/663/666; по отдельным названиюcommit/файлу их бездумно не смешивать.

## Пересечения новых веток: только план, не импорт

Снимок изменённых путей из текущих рабочих refs; не означает PASS/готовность этихHEAD.

| Новая дорожка | Пересечение с принятой прежней базой |
| --- | --- |
| 658 | seller_catalog.py и seller_fulfillment_catalog_service.py: scoped merge сохранит каталожную669 и новыйимпорт; не checkout wholefile. |
| 654 | ci.yml: новаяPGстрока должна лечь в общий принятойpipeline и реальныйreceipt. |
| 681 | FfFbsSupplyWorkspace.tsx и assembly.dom.test.tsx: сохранить текущий666/662 экран и новую recovery кнопку, ожидания старых тестов не заменять. |
| 671/687 | FfInboundRequestView.tsx: stock action в выбранных строках плюс прежние accepted изменения документа. |
| 679/680 | FfInboundRequestView.tsx, fbsSupplyAssembly.ts, fbsUx.ts: общие print/datahelpers, сохранить прежнюю FBSлогику и поля. |
| 684/586 | Прямого недокументного пересечения с прежним producttree сейчас нет; печатные данные всё равно проверить адресно при общей сборке. |
| 686 | ci.yml и импорт actualfrontend вdocs/mockup: frozen11/Node24 job сохранится в новойpipeline, print-injection/drift проверяется build. Это отдельный demo, не новая productFBO. |

Каждая новаяветка входит только по точному tested/reviewed/acceptedSHA с её документом. При конфликте продуктовой логики — возврат отдельному developer/reviewer; интегратор не придумывает поведение и не переписывает frozen expectations. Общее independently accepted SOURCE формируется после этих передач.

## Конкретный путь SOURCE → pin без ослабления

У current actualBASE4b298 ещё нет PROCESS_CONTRACTS. Поэтому existing main loader может использовать новый exact reviewed SOURCE из trusted config; BASE/evidence остаётся4b298. Сохранить все прежние222 paths/1146IDs иreport semantics, дополнять новыми tests/source closure/receipts; изменить hashes существующихprotectedfiles только для перечисленных independently reviewed изменений. Fixed product_scope trusted-ref d618 меняется только на отдельно принятую exactproductbase, не HEAD или новыйномерзадачи.

Отдельные positive/negative перехода должны показать: старыйpin отказывает новой согласованнойdelta; новый проверенныйpin принимает её; removal/skip/ослаблениестарогоassertion/command, чужаяdelta иself-rehash остаютсяRED. Новые явные jobs/PGcases входят в required producers иraw proof; сторонний optional job не подменяет mandatoryreceipt.

Минимальный main diff после принятияSOURCE: в существующем `scripts/ci/process_bootstrap.json` одна строка source_sha0151→полный40SHAпровереннойSOURCE; base_sha остаётся4b298. Checker/workflow/ruleset/ключи не меняются. Ведущий выполняет этот уже разрешённый владельцем технический этап после exactreview; интегратор его не применяет. SHA не выдумывается доfreeze.

Если сначала влить387 и тем самым добавитьpolicy вetalonBASE, bootstrappin уже НЕ выбирается: BASEвсегдапобеждает иlocalBASEchecker тоже сохранит прежниеprotectedbytes. Для такого следующего перехода нужен отдельный tested trustedmigration механизм; простое изменениеbootstrapJSON не поможет. Поэтому порядок подготовки одного общего SOURCE критичен. ПолныйCI finalSOURCE, actualnegativecanary, обязательные9checks, ordinary merge, fullpushCI итоговогоetalon и реальноinstalledSHA — разные доказательства; ничего из будущихэтапов этим планом не объявлено выполненным.
