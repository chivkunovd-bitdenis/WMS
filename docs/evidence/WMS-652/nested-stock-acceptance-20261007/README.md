# WMS-652: ограниченная приёмка R52, format/ledger и reference

**Software PASS; WMS-652 в целом и release ещё не приняты.** Та же отдельная
замещающая сессия Sol6.1/high `01a11390-1014-76a0-9302-fbe0fd46ed1f` вернулась
к своей постановке476d206; исходный аналитик недоступен. Автор этих документов
не писал frozen-тесты или продукт. Приёмка использует сохранённые результаты,
Git-объекты и независимое заключение, без тестов/build/browser/CI/deploy.

Текущий общий источник — `17f44649b05e6b9f5b3bc7af6657aa6418569ac4`.
Независимый review `4e4819af8f5cd4fa6685c7cf76a0f16085e15f84` на
`dce1b012e0929e227b182863bb14a378d04d3412` дал
[PASS](../nested-stock-source-review-20261007/review.md).
[Источник и привязка сохранённых XML](source-probe.json) фиксируют неизменность
всех защищённых Git-объектов между проверенным и текущим источником. Числа и
сохранность старых наборов взяты из независимого proof, его аудит не повторялся.

[Отдельный контракт](../nested-stock-test-contract-20261007/contract.json)
`f1e355525edbf41177d379c70cc5ee721986c967` опубликован до кода, все9 файлов frozen.
Четыре проверки используют настоящую SQLAlchemy Session и её SAVEPOINT/outer
commit/rollback; наблюдается только существующий `_dispatch`, worker/provider
не вызываются. Реальные имена приведены в таблице приёмки требований и source-probe.

| Требование → проверка | Сохранённый результат до → после | Вердикт |
|---|---|---|
| R52 → C66 | Ранний nested dispatch assertion RED → PASS, pending сохранён до outer commit | Подтверждено |
| R52 → C67, saved nested intent | Dispatch на nested вместо outer assertion RED → PASS, один исходный intent на outer commit | Подтверждено |
| R52 → C67, ordinary commit | PASS → PASS, дубликаты coalesced один раз; copy-only dispatcher-off mutant assertion RED | Подтверждено |
| R52 → C68 | Dispatch до outer rollback assertion RED → PASS,0 dispatch и pending очищен | Подтверждено |

[Разработчик](../nested-stock-developer-20261007/README.md) повторил3 RED/1 PASS
до guard; после получил native4 PASS/0skip/error и existing6 PASS/1knownPGskip,
всего10 PASS/1 SKIP/0FAIL/error. Известная advisory-lock проверка требует настоящего
PostgreSQL и локально **не исполнена**. Сохранены full Ruff PASS/mypy PASS563.
Продукт `1cf85fc500bc6ee7a5f4ef283b250c4bf59c5333` меняет только две строки
существующего `_after_commit`: ранний return при `in_nested_transaction()`.
Rollback hook, coalescing, аргументы и условия неизменны. Nested rollback вне R52.

**Аналитически одобряю точную product-reference миграцию
25ebc6fe13384a55cf1f2b7e5e4054bb862d002d →
1cf85fc500bc6ee7a5f4ef283b250c4bf59c5333.** Подготовленный workflow/helper
меняет только фиксированные literals; saved helper1 RED/2 PASS →3 PASS.
Product_scope.py/frozen51 и все прежние execution commands сохранены.
Текущие app bytes совпадают с1cf; old-ref отклоняет только stock-module,
proposed-ref даёт[]. Это одобрение предъявленной миграции, не main SOURCE activation.

Конечная format/ledger правка принята по независимому
[6475d8f96d47ae33a01699c6f3843092a3d2c7f7 PASS](../backup-format-ledger-review-20261007/review.md):
originale702→portableed14→AST-identicald40, точная существующая ledgerad22,
23 assertions/7 variants/5 controls, один fixed063 digest и boundary092a;
checker semantics не менялись. Текущая policy233 files/22 suites/1184 IDs сохраняет
старые230/1180; new4 точных XML IDs добавлены в backend-fbs619, прежний
backend-all.xml/exact:false. Новые module/test/uv.lock замыкают сохранённые зависимости.

[Последний полный CI37556521625](../common-ci-37556521625/summary.json) на
cbd126200788b87d1a006c5853d8e9560148cd36/tested merge
8b8f20715528122a7260d650f018a9a8b4bd29e5 **FAILED733s/12m13**:
4631 exact union,4432 PASS/198 regular XML SKIP/1 SQLite FAIL. MandatoryPG
не исполнились, aggregator FAILED/process proof SKIPPED/anchor FAILED.
Успешная цель10–15 минут не доказана; прежние615 FBS/43browser/print11+6/
Node12/CDP7/Mac110/frontend1566 PASS не являются CI нового источника.
Выбранная диагностика375581 PASS12.47s доказала ранний nested launch, но
исторический SQLite-lock owner UNKNOWN.82.156ms — SQL interval, не measuredlockwait;
четыре duplicate collector labels вне положительного27-event span квалифицированы
независимым3c9881d7d7653f3c44f3d8c62a8a2e976774ae78.

Main configddb28a5530456f2be6f7772001f72095e53be1e6/SOURCE321f остаётся исторической
установленной базой. Следуют отдельное окончательное SOURCE233 approval/pin,
main configuration, один fullCI кандидата, обычный etalon merge/push CI и deploy
с проверенным SHA. Stagingcc8e/prod8f11 этой приёмкой не изменены. Softwaredeploy
первым; бумага/оператор/provider — прежние отдельные послевыпускные условия.
