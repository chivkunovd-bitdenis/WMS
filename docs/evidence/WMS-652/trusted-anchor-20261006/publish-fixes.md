# WMS-652: исправления двух P1 независимого Astra A review

**Уточнение после следующего review:** описание mutex ниже сохраняет историю
первой проверки. Оно не моделировало замену единственного pending run в GitHub
и не доказывает сохранение очереди при третьем событии. Остаточный дефект,
его новый контракт до правки и ограниченная очередь разобраны в
[queue-fix.md](queue-fix.md). Текущий prepared YAML использует `queue: max`.

Исходный checkpoint `ac6628aacda5631e0be886364ed01d2a324847c4` имеет22 PASS,
но Astra A воспроизвела два дефекта публикации. Исходные review/probes сохранены
в reviewer commit `ce293da9a0f5e33e8c9f0f4ab52dcddbccca6a42`, ветка
`codex/release-20261006-astra-a`, файлы
`docs/evidence/WMS-652/release-process-protection-20261006/trusted-anchor-ac662-*`.
Эти доказательства перечитаны до исправления; ни один из frozen22 expectations
не изменён.

## Контракт до исправления

Новый `test_trusted_process_publish.py` зафиксирован отдельным коммитом
`9646bef50` до правки checker/YAML. Пять методов: оба event-пути API outage;
missing/invalid/foreign event identity; event head не подменяет свежий head;
единая очередь event kinds/run IDs/PR numbers; реальный CLI с задержанным success
POST и последующим новым failed CI. RED:4 failures (`publish-contract-red.log`),
включая прежний порядок failure→success и отсутствие failure при initial outage.

Thread probe использует настоящий CLI/strict artifact verifier и синтетические
API/download/publish callbacks. Очереди получают ключ непосредственно из
подготовленного YAML; старое выражение PRnumber/runID даёт разные mutex,
новая постоянная группа —один. Это проверка заявленной модели GitHub queue;
не внешний эксперимент публикации и не доказательство установленного workflow.

## Исправления

При initial API outage head теперь может быть получен из доверенного GitHub
workflow event **только для failure**. Проверяются repository, событие, PRnumber,
целевой etalon и полный lowercase SHA. Для PRT проверяется same-repository
head/base scope; для workflow_run дополнительно active CI path, completed
pull_request event, repository/head_repository и matching PRhead/runhead.
Missing/invalid/foreign identity не используется. Компактные искусственные
payload без scope из первоначального audit probe остаются исторической
репродукцией; новые тесты сохраняют реальные идентифицирующие поля GitHub event.

Fresh API head всегда имеет приоритет. Событие не может авторизовать success,
изменить head успешной проверки или подменить доказательства artifact. Прежние
unknown/missing artifact, wrong SHA/base/attempt и frozen pipeline проверки
сохраняются. Если сам POST недоступен, код не может гарантировать отзыв check:
это честная внешняя граница, current CI/policy enforcement остаётся обязательным.

Все publishers теперь используют постоянную `process-integrity-publishers`
concurrency group с `cancel-in-progress:false`. PRT и workflow_run, старые/новые
run ID и другие PR больше не расходятся по разным очередям. Старый outgoing
success POST обязан завершиться до начала следующего publisher; последующий
failed run публикует отказ после него. Дополнительное последнее чтение само по
себе не выдаётся за исправление race. Проверка/CIизменение/POST остаются разными
внешними операциями; global queue закрывает конкретный out-of-order publisher
случай, не является атомарной транзакцией всех систем.

## Проверки

```sh
python3 -m unittest scripts.ci.tests.test_trusted_process_check scripts.ci.tests.test_trusted_process_artifact scripts.ci.tests.test_trusted_process_cli scripts.ci.tests.test_trusted_process_publish
/Users/deniscivkunov/Projects/WMS/backend/.venv/bin/python -m ruff check scripts/ci/trusted_process_check.py scripts/ci/tests/test_trusted_process_publish.py
/Users/deniscivkunov/Projects/WMS/backend/.venv/bin/python -m mypy --follow-imports=skip scripts/ci/trusted_process_check.py
```

Итог **27 PASS**, ruff/mypy PASS. YAML BaseLoader parse/scope PASS: одна группа,
false cancel, main checkout, persist-credentials:false, файл всё ещё только в
`docs/evidence`, active `.github/workflows/process-integrity.yml` отсутствует.
Temporary mutation без failure fallback даёт2 FAIL; прежние разные queues —2 FAIL
(`publish-mutation-controls.log`). Код и YAML восстановлены побайтно в finally,
после восстановления вновь27 PASS.

Новых API-write/production/deploy/secret операций не было. Main/default/rulesets
и bootstrap policy не менялись. Установка в main требует отдельного прямого
разрешения владельца. Точный новый delta возвращается Astra A и ведущему;
собственная проверка не заменяет независимое ревью.
