# WMS-666: точная принятая дельта загрузки истории для CI

06.10.2026. Тестировщик Sol 6.1 `/root/frontend_qr_finish`.
Использован прежний собственный постоянный checkout
`.worktrees/wms653-scope-attribution-20261006`, новая именованная ветка
`codex/wms666-ci-history-scope-20261006` от общего
`20448622da89b3ef4de10443af0c8c75da9cbf0c`. Новая рабочая копия не создавалась.

## Actual общий RED и граница исправления

Прочитан полный фактический scope666 log интегратора на общем `20448622d`:
4 PASS / 1 FAIL; **весь** список attribution violations содержит только
`.github/workflows/ci.yml`. Исходный frozen scope-файл и ledger прочитаны.
Проверен exact integration commit
`720307d280439e815057ee4fdd78b72134149a39`: он добавил ровно четыре строки
`with: fetch-depth: 0` к backend/frontend checkout, чтобы тест имел исходную
историю Git. Другие команды, среды и состав проверок в этой дельте не менялись.
Before workflow blob `621ee62065c67ae66d756b25057d56e780bb411d`, after
`bbec58a4b781913e7792a6718158a9fc4b806c90`.

До изменения collector добавлен realGit отрицательный контроль новых
workflow-правок. На той же actual истории тест фактически дал **5 PASS /
1 FAIL**: новый негатив прошёл, прежний полный actual-scope отказал только
на CI path. Временный диагностический log сначала сам попадал в untracked
scope, был перенесён в допустимый evidence namespace; указанный результат
получен повторным чистым прогоном после устранения этого артефакта harness.

## Опубликованный test-only commit

**9e72ac09f537fc48a02e1681bcc4ace917b7759e**, единственный изменённый файл —
`frontend/src/screens/v2/wms666ChangeScope.test.ts`; конечный blob
`69f07c26fa4966875e8aa85a24ac16f7dc8d5ac4`.
Collector исключает только совпадающий **commit + CI path + before/after
blob** указанной исторической дельты. Глобальный scope-filter workflow
не разрешает: его прямой вызов с CI path по-прежнему возвращает нарушение.
Все другие пути и коммиты оцениваются прежним способом; pending index,
worktree и untracked проверки исключением не пользуются.

Исходные пять случаев и их ожидания сохранены. Добавлены отрицательный
realGit контроль commit/untracked/unstaged/staged/index-only workflow,
положительный контроль точной исторической дельты и отказ при отсутствии
её исходного Git-объекта. Ожидаемый stderr `git fatal: invalid object name`
в последнем случае является доказательством закрытого отказа, а не ошибкой
положительного прогона.

Команда из frontend:

```sh
npm exec --yes --package=node@20 -- node node_modules/vitest/vitest.mjs run src/screens/v2/wms666ChangeScope.test.ts --no-file-parallelism
```

После исправления **8/8 PASS**, Node 20.20.2, 5.81с. Полный actual-scope
оценивает все пути общей истории за один проход и возвращает ноль нарушений.
Runtime, бизнес-тесты QR/скана/печати и workflow-файл не менялись.
Независимое узкое ревью запрошено у Sol 6.1 high `priority_663`; новое
заключение в ledger до его получения не записано. После сведения интегратор
выполнит scope653 и scope666 на новом общем конечном HEAD.

Предыдущий actual common `20448622d` уже дал scope653 **34 PASS**, 19.07с.
Этот факт подтверждён интегратором, его scope653 log/provenance находятся
рядом с scope666 log в `.agent-runs/priority-five-20261006/scopes-final/20448622da89b3ef4de10443af0c8c75da9cbf0c/`.
Это ещё не окончательный release SHA после данной scope666-коррекции.

## Полученное узкое независимое заключение

Отдельная сессия Sol 6.1 high `priority_663` дала **PASS** точного 9e72.
Её собственные три новых контроля — **3 PASS**, затем отдельно выполнен
actual shared-history case — **1 PASS**. Прежние пять случаев и raw scope
validator подтверждены байтово неизменными; полный старый набор и продукт
повторно не проверялись. [Отчёт](ci-history-scope-independent-review-20261006.md)
опубликован как `d814f65891b6f7f5d9ca81197689fa3085232611` и включён
точной копией в эту ветку.

После фактического PASS оба накопительных scope-ref двух исходных
контрактов в ledger обновлены на 9e72. Запись QR остаётся прежней;
перекрывающихся дополнительных записей одного исходного контракта не создано.
Историческая коррекция `30aea1fbf9cdc8fc3863acfb7541c57d64f98952` и её
Astra high review `2c24d7bbad63605a2cb33dc8723c7f83516eef85` сохранены как
previous provenance и не выдаются за новое Sol-ревью.
