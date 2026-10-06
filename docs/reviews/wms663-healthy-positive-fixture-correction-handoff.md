# WMS-663: независимая коррекция трёх положительных STATUS fixtures

06.10.2026. Отдельный тестировщик по прямому поручению владельца. Ownership:
только `backend/tests/test_wms663_customs_documents_contract.py` и этот документ.
Это передача коррекции тестовых данных на последующее независимое Astra-ревью,
а не собственный вердикт ревью, продуктовая приёмка или подтверждение CI.

Прочитаны AGENTS.md целиком, старый тестовый файл целиком, требования R7,
F4/F4-R handoff и Astra-обоснование F4-R. Skills, агенты, браузер/Chrome,
живые базы/API и кабинеты секретов не использовались. Чужие файлы не менялись.
Fetch origin/etalon сначала не состоялся из-за отсутствия места, затем выполнен.
Правила совпадают с etalon `0f1460b023700a99f17b504d6af3934a02bc68cc`:
Git blob AGENTS.md `212dcfa56f904811892704b9bbff823c46a4c870`.
Работа продолжает имеющуюся ветку `codex/wms662-663-priority`.

## Независимое определение смысла

R7 прямо запрещает показывать успех при пустом/неполном products. Новый контракт
F4-R `8dfad7fa6e2d6e62f9aa264b7690032021550b9e` отдельно сохраняет отрицательные
случаи отсутствующего A/81, всего A, A/82 и всего B, а также полный здоровый
положительный контроль. Старые три сценария описывают успешное восстановление
выбора после restart, разрешение потерянного SET без повторной записи и здоровую
accepted-ветвь статусной матрицы. Их смысл не требует принятия неполного ответа.

Однако каждый из этих положительных ответов содержал только A/81, тогда как
реальный сохранённый snapshot содержит A/81, A/82, B/91. До F4-R продукт ошибочно
принимал весь показанный набор по этой части. Это дефект здоровых fixture-данных,
а не основание менять ожидания accepted или отменять защиту неполных ответов.
Отрицательный контракт новых неполных ответов остаётся неизменным.

Продуктовая четырёхстрочная правка уже была независимо сохранена разработчиком:
`1fd2d92dc30eb376c1d8a8e27238e52d963a196e`, непосредственный родитель этой коррекции.
Она меняет только агрегированное представление: accepted требует присутствия
всех ожидаемых показанных экземпляров в свежем STATUS. Тестировщик продукт не правил.

## Точный diff и исходные ожидания

Добавлено 72 строки, удалений нет: в каждом из трёх STATUS добавлены A/82 и B/91
с точными полями соответствующих экземпляров `_remote_snapshot()`: gtd,
is_gtd_absent, rnpt, is_rnpt_absent, weight, marks; у B сохранён is_rnpt_needed.
Отсутствующие document check_status/error поля этих здоровых соседей не вводят
отказов. Ответы, содержащие A/81, и явно выбранные значения A/81 оставлены побайтно
прежними; в lost SET/матрице флаг is_rnpt_absent=False соответствует явному save,
в restart он True соответствует явному save этого сценария.

1. `test_wms663_explicit_choice_is_saved_exactly_and_resumes_after_restart`:
   дополнен только второй queued STATUS ship_available. Первый checking-ответ,
   expire_all/restart, проверки точного выбора, accepted и единственного SET прежние.
2. `test_wms663_lost_set_response_reads_status_before_any_repeat`:
   дополнен только matching products для STATUS после потерянного SET. Исключение
   транспорта, число SET=1, требование чтения STATUS и accepted прежние.
3. `test_wms663_status_accepts_only_matching_and_keeps_other_results_nonaccepted`
   `[status_payload1-accepted]`: дополнены только products здорового элемента.
   Все девять случаев, их порядок, expected_state и остальные ответы прежние.

Нет изменений assert, имён, сигнатур, decorators, skip, параметризации либо
helpers. Доказательство Python AST: после удаления ровно шести добавленных узлов
(A/82 и B/91 в трёх ответах) полное дерево после исправления равно исходному
`ast.dump(before) == ast.dump(after)`. Каждый добавленный узел до удаления отдельно
сравнен с узлом `_remote_snapshot()` и совпал. Первый запуск этой разовой проверки
имел неверный относительный путь из backend; повтор из корня checkout прошёл.
Новый F4-R тест и требования побайтно неизменны относительно 8dfad7.

## Сохранённые полные версии

Исходный файл одинаков в 9935c91, 8dfad7 и product SHA 1fd2d92.
Git blob до: `4e1aff5a80445fa61b5697d60a26985427dfd28e`.
Git blob после: `c92c075ba9f375c578538b776207cdc6b8b56ab3`.
SHA-256 до: `f05ebf4ca228aaddc6addb50abf07d8cb18da8e93fc1dc2f9b254b4b92851665`.
SHA-256 после: `bf1654d769157c12c48577213a2a28358e96441d12d07a32d0b8abe2225460f8`.
Оба полных файла хранятся объектами Git: `git cat-file blob <blob SHA>`.
До доступен из родительского product commit, после — из отдельного correction commit;
временный каталог не является единственным источником этих данных.

## Целевые проверки

До коррекции выполнены только три точных старых node ID на product 1fd2d92:
**3 failed, 12 warnings, 6.16s**, exit 1. Исходные строки падений 371, 579, 727:
получено unknown вместо accepted; остальные бизнес-ожидания не изменялись.
Историческое прохождение этих трёх на 9935c91 и RED нового контракта известны
из исходного поручения/предыдущих handoff; здесь старый продукт повторно не запускался.

После коррекции команда из backend:

```sh
env -u WMS_TEST_DATABASE_URL -u WMS_TEST_DATA_DIR PYTHONDONTWRITEBYTECODE=1 \
  /Users/deniscivkunov/Projects/WMS/backend/.venv/bin/python -m pytest \
  tests/test_wms663_customs_documents_contract.py::test_wms663_explicit_choice_is_saved_exactly_and_resumes_after_restart \
  tests/test_wms663_customs_documents_contract.py::test_wms663_lost_set_response_reads_status_before_any_repeat \
  'tests/test_wms663_customs_documents_contract.py::test_wms663_status_accepts_only_matching_and_keeps_other_results_nonaccepted[status_payload1-accepted]' \
  tests/test_wms663_partial_accepted_status.py \
  -n 1 -q --tb=short -p no:cacheprovider \
  --basetemp=/private/tmp/wms663-healthy-fixture-tester-20261006
```

Фактически: **19 passed, 12 warnings in 40.82s**, exit 0. Это ровно три
исправленных старых сценария и все 16 новых F4-R; skip нет. Три Node/jsdom
проверки реального компонента выполнены, включая полный здоровый контроль.
Неполные свежие ответы по-прежнему дают unknown, полные здоровые — accepted.
Локальное выполнение тестов не является собственным независимым ревью.

Прочитан conftest: сняты оба WMS_TEST переопределения, DATABASE_URL задаётся
свежим SQLite-файлом с уникальным ID запуска/gw0 до импорта приложения.
Один pytest-worker; каждый jsdom/Vitest-запуск также ограничен одним worker.
Это Node/jsdom, без браузера. Первые два запуска после коррекции завершились
INTERNALERROR exit 3 до выполнения тестов: не создавался временный каталог из-за
No space left on device. После появления свободного места повторён только тот же
целевой набор. Это инфраструктурные ошибки, а не тестовый RED или GREEN.

Ruff изменённого теста с --no-cache: All checks passed; первый cached-запуск
не создал cache temporary file по той же причине нехватки места. git diff --check PASS.
101 соседний тест, полный набор, mypy, frontend build и CI не повторялись.
Отчёт разработчика об их прохождении не считается собственным доказательством.

## Передача

Отдельный correction commit содержит только старый тестовый файл и этот handoff.
Ведущему требуется независимое Astra-ревью точного correction SHA и отдельного
product SHA, затем аналитик/CI по общему процессу. Этот документ не меняет
требований, вердиктов приёмки или постоянной охраны. Merge/deploy не выполнялись.
