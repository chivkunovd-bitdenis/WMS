# WMS-672: bounded independent peer-drain contract/wiring review

**PASS для нового контракта и его additive CI wiring; замечаний нет.**
Проверены test-first `a0e4409300d4897234c501474de2bfe45478e488` и общий pre-code
источник `e527352058eac5cc0e1640d75ed6031459ab1f1c`. Реализация механизма drain
и actual Linux эффективность этим отзывом не принимаются.

Два новых теста исполняют фактические utility и screen function через тот же
TypeScript AST/transpile подход. Decode boundary удерживается явным Promise,
а наблюдение ошибки и event-loop flush не зависят от тайминга PNG/Chromium.
Async case заставляет peer №2 первым отклониться, удерживает остальные уже
начатые peers и после release вызывает отличный поздний отказ peer №1.
Сохранение именно первого объекта ошибки проверяется по identity, а не выбором
первого rejected элемента в порядке исходного списка. Sync case бросает ошибку
на втором вызове при уже удерживаемом первом и проверяет тот же lifecycle.

Held snapshot фиксирует подключённый iframe, незавершённую операцию, busy и
inboundLabelPrinting.current до settlement активной работы. После release
проверяются ноль pending, отсутствие новых cohorts после известного отказа,
перенос исходной причины, cleanup ровно один раз при pending=0, снятие guard/busy
и ноль source saves, передач/mark POST. Контракт не задаёт число peers, окно
decode или срок ожидания. Он не обещает завершение произвольного зависшего
native decoder и не является выполненной повторной браузерной печатью.

Сохранённый pre-code TAP имеет **2 целевых FAIL,0 PASS,0 skips/cancel** на
`failed tape source must live until held active decode peers settle`.
Диагностика async baseline: cleanup при pending15, connected=false,
finished=true, busy/guard=false; после release pending0/ready14.
Sync baseline: cleanup при pending1, после release pending0/ready1.
Это meaningful RED из реальной исполняемой операции, а не import/setup ошибка.
В независимой сессии тесты не повторялись.

CI добавляет одну команду node --test и отдельный raw
`$RUNNER_TEMP/release-print/672-peer-drain.tap`. Предыдущая команда семи native
cases и последующие старые browser/PDF команды сохранены. Ошибки не подавляются;
existing always-upload собирает raw directory, process-proof получает report
как `print/672-peer-drain.tap`. Registry требует ровно два новых TAP имени.
Новый файл побайтно совпадает с отдельным test-first commit.

Closure сравнен с ранее просмотренным `296107aafcf44d1ac5afa623d32c644fa5396233`:
единственный новый защищённый файл — `wms672-peer-drain.test.mjs`, единственный
изменённый прежний hash — reviewed one-line CI addition. Остальные 226 прежних hashes
сохранены; **все actual Git blobs 228 файлов совпадают с registry**.
Все прежние suite definitions/1168 case IDs сохранены; итог **20 suites/1170 IDs**.
Utility/screen/package/lock dependencies нового теста уже protected.
Точные старые C5/11, native7 и scope51 остаются без изменений.

Существующий Linux counterexample сохраняет значение: после раннего удаления
при injected150 corrected retry успешен, после299 возникает иной native reject.
Новый held-peer RED доказывает техническую границу controlled preparation;
он не доказывает, что раннее удаление является достаточной причиной native
Chromium отказа. Исторический 16-window source review и Linux FAIL не переписаны.
Нужны отдельное source review реализации, actual unchanged Linux C5 и приёмка.

Эта сессия меняет только evidence; product/tests/workflow/policy не редактирует,
старые7/11/scope51 и полный CI не запускает, новый SOURCE/product-ref не одобряет.
