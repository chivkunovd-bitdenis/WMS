# Независимое подтверждение конкретного SOURCE pin

**APPROVE** только точную пару bootstrap:

```json
{"base_sha":"4b298efc95be7b4b6b7fe5665be9f3671f1fe747","source_sha":"0151a555ac429957d0eee591317cc4326e909dfd"}
```

SHA256 policy `guards/PROCESS_CONTRACTS.json` в этом SOURCE:
`24832907fc361fcc85f7a3940394445bfead9846c4c979a657f89d45b34fae53`.
Это независимое подтверждение конкретного источника для установки trusted
checker, а не самосогласование документа кандидата. Main/pin/GitHub settings
этой сессией не изменялись.

Область повторной проверки — только интеграция после ранее принятого
`93b0757103fbd29fb00d4f198f6baab8def85172`. Прочитан integration-handoff.
`source-pin-probe.py` независимо читает immutable Git blobs, raw XML/TAP/JSON,
не исполняет тесты, браузер или код кандидата. Вывод — source-pin-probe.json.

Подтверждены **222 regular Git source/fixture/helper/test/workflow blobs**, все
actual SHA256 совпадают. **210 прежних путей и 955 прежних suite IDs сохранены**;
прежние report/format/exact не изменены. Всего **1146 IDs в18 suites**; повторы
одного теста между Linux/Windows suites являются прежним явным platform
контрактом. Внутри каждого suite policy исключает дубли.

Пять прежних обновлённых hash относятся ровно к рассмотренным CI/browser/cases
и двум Mac test files. CI, shard runner и scope source побайтно совпадают с
предыдущим независимо проверенным93b. Geometry source/assertions/cases совпадают
с принятым1c045; полный browser source closure12 включён. Четыре Mac helper,
launcher, generator и .command плюс три test files точно совпадают с7a2fa31,
который независимо принят reviewer1bd1d8508 (в общей ветке2ceddf740).
Прочитано его заключение: actualReact0/700ms PASS и110 TAP PASS; этот этап не
подменяется нашей повторной проверкой и заново не запускается.

Недостающая зависимость test_backend_shards.py — сохранённый4625 collection
`docs/evidence/WMS-652/ci-two-shards-20261006/backend-collection.json` — теперь
также защищена actual hash. Поэтому первоначальный37e5 SOURCE **не утверждён**;
0151 исправляет эту одну closure omission без изменения1146 ID.

Точные20 shards и51 scope names сверены с настоящими первоначальными XML и
общим integrated71 XML; статусы только PASS, состав точный. Mac110 сверены
с integrated TAP: полноценный plan, последовательные номера, нет duplicate,
skip/todo/cancel/fail. Browser43 policy cases совпадают с source cases.json и
сохранённым finalGREEN JSON; его source1c045 соответствует принятым bytes.
Новое локальное исполнение интегратора не выдано за полный GitHub CI.

Реальный frozen CI YAML содержит fixed d618 scope CLI, реальные pytest команды
20/51 и node--test всех трёх Mac files, сохраняет ci-shards.xml/product-scope.xml/
wms517-mac.tap и передаёт их через конкретные attempt artifacts в process-proof.
Existing builder/parser/checker защищены; их CI команда сохраняется.
Product diff d618→SOURCE пуст. Git дерево конкретного BASE4b298 действительно
не содержит policy: это допустимый bootstrap случай установленного independent
main checker045272b51. Его baseline_policy выбирает только явно заданную пару;
existing BASE policy имеет приоритет. verify_pr требует идентичные protected
hashes/blobs/modes в SOURCE/candidate/merge и сохранность suite contracts.
Последующие только document/evidence commits могут сохранить этот SOURCE;
любое изменение frozen source требует отдельного нового решения.

Новых блокеров конкретного SOURCE pin не осталось. Разрешение относится только
к приведённой паре. Действительно установленный pin, required check с доверенным
app identity, negative canary, приёмка, полный CI итогового SHA и deploy
проверяются соответствующими следующими этапами. Время10–15 минут не измерено.
