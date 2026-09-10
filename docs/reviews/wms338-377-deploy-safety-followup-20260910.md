# WMS-338 / WMS-377 — порядок миграций и закрытие старого порта

Общий deploy скрипт теперь останавливает api/worker/beat после сборки, до
миграции, делает частный pg_dump -Fc (каталог0700, файл0600), проверяет
pg_restore --list и только затем запускает миграции. Ошибка backup не
запускает миграцию; writers остаются остановленными. Это защита перед удалением
устаревшего stock ledger0261, не повод применять этот DDL в срочном mobile релизе.

После запуска web проверяется существующий seller маршрут через приватный
bridge172.18.0.1:8088, затем останавливается только старый web_seller того же
Compose project, установленного по метке контейнера БД. Чужие сервисы не
затрагиваются. CI smoke проверяет публичный HTTPS. SSH bootstrap берёт скрипт
из текущего origin/etalon, сохраняя его проверку SHA принадлежности etalon.

Три целевых теста проверяют фактический запуск shell со stub Git/Docker/Curl:
порядок stop → backup → verify → migration → route → legacy stop, права
backup, ошибку dump и испорченный архив. 3 PASS; bash -n, Ruff и Mypy PASS
в общем локальном scoped проходе. Production не изменён; живой backup, миграция,
закрытие порта и независимое review этого delta ещё не выполнены.


После independent review27228 исправленыstdin и потеряexitstatus: workflow
получаетскрипт checkedassignment ивыполняет bash-c </dev/null; pg_dumpтакже
безstdin; dockerpsдляlegacycheckedassignment, пустойсписокуспешен.
7целевыхtestsPASS: dump/archivefail, listingfail,emptylist, actualworkflow
bootstrap gitshowfail и scriptcommandчитающаяstdin. Ruff/bash-nPASS.
Повторноеindependentreviewэтогопоследнегоdeltaещёнепройдено.
