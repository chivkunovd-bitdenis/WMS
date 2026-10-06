# WMS-663 — передача точной регистрации Close selector

06.10.2026. Process maintenance, только регистрация уже независимо проверенной
коррекции. Исходный HEAD проверки RED: `aa57886772d746d0a08341867d8828bf3ed84d5a`.

Добавлена одна пара `wms663-close-accessible-selector` в существующий
`FIXTURE_BLOB_PAIRS` и третья запись существующего реестра WMS-663.
Коррекция: `d9e022697e098a2f9c0feee6a5bf03f99cac5945`;
source frontier DOM-файла: `76f2162e22f1aa9e33a336b01109882d8a8969c6`;
before blob: `8548a75eb6963edcd5e3b3755e0a618d918f9f94`;
after blob: `7b41916c43bf144d9fdeb7772d415bdf5535ff05`.

Запись привязана к опубликованному независимому Astra high PASS именно этой
однострочной коррекции: `docs/reviews/wms663-astra-d9e022697.md`,
evidence commit `146fe6e3ad92844601c525521d20343c31340456`,
evidence blob `725f1510d8e7406bfc1077aebb0a0d17356773b7`.
Blob отчёта проверен через Git. PASS продукта и полная приёмка C16/WMS-663
этой записью не утверждаются.

## Проверки

До изменения вызов `reviewed_contract_correction` для исходного контракта
`ae2ebd3d17f4e7364b1b52de4126b8f70937652b` воспроизвёл ровно:
`WMS-663: fixture-only: последующая мутация HEAD: frontend/src/screens/v2/FfFbsSupplyWorkspace.wms663.dom.test.tsx`.
Исходные 13 fixture/edge тестов: PASS (38.257 s).

После регистрации `exact_fixture_corrections` с рабочим реестром: errors=[];
backend baseline остался `17ce363a8360620bc6b843e003278cd4ea106678`,
DOM baseline стал `d9e022697e098a2f9c0feee6a5bf03f99cac5945`.
Сравнение подтвердило сохранность всех пяти старых tuples, первых двух записей
реестра и побайтную неизменность checker вне добавленного tuple.
Дополнительные вызовы с подменой source, after blob и evidence blob новой
записи отвергнуты существующим алгоритмом.

Существующие относящиеся к checker тесты запускались без изменения файлов:

```sh
PYTHONPATH=scripts/ci python3 -m unittest -v test_fixture_contract_corrections test_fixture_contract_correction_edges test_wms663_positive_fixture_chain test_wms663_fixture_chain_history test_check_task_documents
```

Результат: 79 tests, 78 PASS, 1 FAIL, 99.393 s, exit=1. Единственное падение:
`test_fifth_pair_and_sequential_file_baselines`, строка 68:
`self.assertEqual(len(checker.FIXTURE_BLOB_PAIRS), 5)` → `AssertionError: 6 != 5`.
Предшествующие проверки реальной цепочки и baselines в этом тесте прошли.
Все отрицательные проверки, включая assertions/skips/control flow, source gap,
Git mode, review identity и лишние файлы, прошли. Полностью зелёный набор
не заявляется. Жёсткий счётчик пяти пар оставлен без правки, поскольку поручение
запрещает изменять тесты и assertions; его судьбу решает ведущий отдельно.

`git diff --check`: PASS. После commit требуется повтор scoped вызова
`reviewed_contract_correction` на сохранённом HEAD, поскольку штатный путь
читает реестр только из Git, а не из незакоммиченного файла.

## Граница ответственности и следующий шаг

Собственные пути: checker, существующий WMS-663 correction ledger и этот handoff.
Продукт, тесты, требования, guards и алгоритм допуска не менялись.
Работа параллельных исполнителей не включается в этот commit.
Полный CI, Mac browser, новый PostgreSQL, live и deploy не выполнялись.

Ведущий должен отдельно передать маленький registration diff независимому
ревьюеру. Опубликованный Astra PASS относится к d9e fixture correction;
он не является ревью этой регистрации. Эта сессия новых ревьюеров не запускает
и свою проверку за независимое ревью не выдаёт.
