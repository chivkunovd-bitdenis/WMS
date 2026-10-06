# WMS-652: две параллельные части полного backend CI

Рабочая ветка `codex/wms652-ci-two-shards`, постоянная worktree
`.worktrees/wms652-ci-two-shards`, база ведущего `1cf3b6c11`. Прочитаны свежие
правила origin/etalon и developer skill. Работа относится только к CI,
новому shard runner/merger, их новым тестам и доказательствам. Product,
backend/tests/conftest.py, старые tests и registry не изменены.

Ведущий передал измерение успешного run37493512332: backend1085s, из них
полный Pytest965s; frontend287s. Это исходное измерение ведущего, не новый
прогон данной ветки. Цель владельца — обычный полный CI10–15 минут при
сохранении всех тестов. В этой работе полный CI **не запускался**; итоговый
один run координирует ведущий. Таймаут не сокращён до15 минут и не используется
как доказательство ускорения. Проверить цель можно только по новому run.

## Контракты до кода

`f8333d12f2e60cd4e920922e0efac60e5fb4a580`:13 новых unit/integration методов,
реальный collection snapshot и RED2 FAIL+11 errors (`contract-red.log`).
Сбор `pytest --collect-only -n0` с теми же двумя прежними ignore-файлами дал
**4625 уникальных node IDs**, без исполнения тел тестов. Полный список —
`backend-collection.json`. Сортировка и alternating split дают2313/2312,
полное объединение и ноль пересечений. Snapshot служит проверяемым исходным
примером; каждый actual CI shard собирает актуальный полный набор заново.

`cb2f5ca09cd2f81d8b10a678fe460c3774c0ae22`:дополнительный pre-fix контракт
ошибки collection/setup вне testcase. RED1 FAIL, прочие два positive controls
проверяют настоящий shell гейта для25 комбинаций producer statuses и ранний
отказ при worker collection drift (`failclosed-contract-red.log`).
После фиксации в новых тестах только explicit check=False и удаление unused
import для lint; ожидания и состав не смягчены.

## Исполнение и отказ

`backend-checks` сохраняет все прежние services/PG/migration/lint/native print
команды. Структурное сравнение YAML подтверждает их равенство без прежнего full
Pytest шага, изменений artifact upload и единственного добавления JUnit output
к прежней PG517 команде; новых PG services/schema/runs нет.
Два изолированных WMS-662 файла по-прежнему запускаются здесь против их
отдельных PostgreSQL, поэтому их прежние ignore в SQLite наборе сохранены.

`backend-shards` — matrix ровно[0,1], fail-fast:false. Каждый job устанавливает
те же backend и frontend HTTP-helper зависимости, собирает полный реальный
SQLite collection и запускает выбранную половину с `-n auto`. Collection
ошибки запрещают запуск частичного набора. В каждом xdist worker полный
collection digest сверяется до deselection; фикстуры продолжают строить
схему один раз на worker, их реализация не меняется. Новый plugin добавляет
исходный pytest node ID в JUnit property, не меняя тела/исходы тестов.

Shard artifact содержит original junit.xml и receipt.json: version,index,
count2, full collection, exact selection, pytest exit, tested SHA/run/attempt.
В Actions tested SHA также должен совпадать с checked-out git HEAD. Artifact
имена включают index/SHA/run/attempt; старый output directory не переиспользуется.

Обязательное имя `backend` сохранено как агрегатор. Он always-start после
backend-checks и matrix и shell-командой требует оба success. Missing, failed,
skipped, cancelled producer не разрешает последующее успешное объединение.
Оба shard artifact и checks artifact загружаются только по exact current
attempt именам. Merger проверяет одинаковый full collection, deterministic
selection, отсутствие дублей/пропусков/лишних JUnit cases и exact union;
каждый случай исполняется один раз. Receipt чужого SHA/run/attempt отвергается.

Original suites/cases/failure/error/skipped/message/details копируются в
backend-all.xml; исходы не превращаются в pass. Nonzero pytest exit или любой
failure/error даёт non-success merger. Ошибки вне testcase учитываются также.
Required named cases, выбранные из policy suites с report backend-all.xml,
обязаны реально пройти: missing/skip/failure отказ. Другие штатные skip
сохраняются в оригинальном виде. Existing raw process-proof parser по-прежнему
проверяет итоговый backend-all.xml. Его path и backend artifact name сохранены.

Frontend-build больше не ждёт print-regressions: оба исполняются параллельно,
process-proof сохраняет исходные needs и требует оба. Guards устанавливает
pytest/pytest-xdist **до** unittest discovery; это также зависимости новых
synthetic xdist контрактов. Все51 product-scope pytest cases выполняются
отдельной командой с product-scope.xml и SHA/run/attempt receipt, загружаются
в guard-executed-contracts artifact; process-proof скачивает его. Root module опубликован a5979fc31. Для локальной проверки его точные bytes
временно прочитаны git show в рабочий путь: все51 frozen pytest cases PASS,
actual whole-candidate CLI fixed d618 exit0, затем файл удалён из этой worktree.
Он не включён повторно в наш commit и не изменён: root интегрирует свой commit.
Сохранены product-scope.xml, product-scope-tests.log и product-scope-actual.json.

## Выполненные проверки

Из корня worktree:

```sh
/Users/deniscivkunov/Projects/WMS/backend/.venv/bin/python -m unittest scripts.ci.tests.test_backend_shards scripts.ci.tests.test_backend_shard_failclosed
/Users/deniscivkunov/Projects/WMS/backend/.venv/bin/python -m unittest scripts.ci.tests.test_process_contracts scripts.ci.tests.test_verify_ci scripts.ci.tests.test_process_deploy_gate scripts.ci.tests.test_server_process_gate
/Users/deniscivkunov/Projects/WMS/backend/.venv/bin/python -m ruff check scripts/ci/backend_shards.py scripts/ci/tests/test_backend_shards.py scripts/ci/tests/test_backend_shard_failclosed.py
/Users/deniscivkunov/Projects/WMS/backend/.venv/bin/python -m mypy --follow-imports=skip scripts/ci/backend_shards.py
python3 -m compileall -q scripts/ci/backend_shards.py scripts/ci/tests/test_backend_shards.py scripts/ci/tests/test_backend_shard_failclosed.py
git diff --check
```

**20 новых PASS,48 существующих PASS,51 product-scope PASS**;
ruff/mypy/compileall/diff PASS. Новый guard pytest command также сохраняет
raw20 ci-shards.xml в guard artifact; exact cases для регистрации сохранены
в ci-shards.xml.cases.json и product-scope.xml.cases.json.
Integration contract исполняет настоящий pytest/xdist по четырём изолированным
synthetic параметризованным тестам: обе halves и merge дают ровно4 случая.
Это исполнимость механизма, не полный backend run и не измерение CI wall time.
Пойман и исправлен import-path дефект xdist: он замораживает sys.path при первом
import plugin, поэтому repository path задаётся до import pytest/collection.

Шесть temporary mutations (`mutation-controls.log`): обе части выбирают одну
половину→1 FAIL+5 errors; снятие attempt binding→3 FAIL; разрешение executed
duplicate→1 FAIL; required skip→1 FAIL; worker drift→1 error; снятие shell
producer guards→24 FAIL. Script/YAML восстановлены побайтно в finally,
после восстановления снова16 PASS. `workflow-validation.json` фиксирует
4625→2313+2312, ноль пересечений, неизменённые services/PG/migrations/lint/print
и исходные process-proof needs.

При интеграции ведущий добавляет новый runner/tests и CI delta в защищённую
policy и подтверждает полный run точного SHA. Нужны независимое review и
новое фактическое время, прежде чем объявлять цель10–15 минут выполненной.
В этой работе main/runtime/prod/settings, product, секреты и physical printing
не изменены; Actions run не запускался.

## Последние прямые уточнения ведущего до implementation commit

Дополнительный precode9ab90f001 фиксирует actual fixed-reference scope command,
PG517 JUnit output и три helper test files/TAP: RED2FAIL+1error. Precodecfc69527e
фиксирует Redis executable installer на shard runner: RED1error; synthetic
shell тест проверяет оба состояния binary present/absent без настоящего apt.
Теперь shard dependencies также содержат прежний asyncpg0.31.0; redis-server
проверяется и при отсутствии устанавливается, чтобы required интеграция не
стала skip. Product scope CLI проверяет настоящий кандидат относительно
fixed d618, независимо от unit classifier51. Reference не берётся из candidate
документов: будущий product upgrade требует независимо утверждённой миграции.

В существующей PG517 команде добавлен только report
release-postgres/517-withdrawal.xml. Frontend после npmci выполняет node--test
TAP ровно трёх scripts/ops/tests/wms517-*.test.cjs files; wms517-mac.tap входит
в прежний frontend artifact и поэтому скачивается process-proof. Frozen109
helper tests/implementation принадлежат другим ролям и здесь не исполнялись.
Ведущий сообщил о duplicate TAP titles, которые исправляет исходный testwriter
до полного CI: новые unit tests нашего workflow не объявляют109 acceptance.
Физическая Mac подпись не является гейтом этого release, по уточнению владельца;
реальные действия Виталия остаются отдельной проверкой после deployment.

Последний targeted pytest новых20 дал20PASS/45subtestsPASS в2.53s; raw51
product scope дал51PASS в35.49s. Валидация final YAML обновлена: прежние backend
services и все checks steps сохраняются, кроме добавления PG517 report. Полный
CI и фактические10–15 минут ещё не измерены. Root регистрирует exact suites,
новый runner/tests, scope helper и CI commands после интеграции/review.
