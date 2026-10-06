# WMS-652: независимая проверка процесса из default main

Подготовлено в постоянной worktree `.worktrees/wms652-trusted-anchor`, ветка
`codex/wms652-trusted-anchor`, от frozen-контракта `a1c09ecfc`.
Прочитан свежий `origin/etalon:AGENTS.md`. Продуктовый код и существующий frozen
`test_trusted_process_check.py` не менялись. Владелец рабочего результата —
только checker, подготовленный workflow, дополнительные тесты и эти доказательства.
Registry/основной CI/валидатор исходных отчётов принадлежат ведущему.

## Проверяемая граница

`verify_pr(get, repository, pr)` — только helper сведений GitHub. Его результат
всегда содержит `evidence_complete: false` и **не разрешает публикацию успеха**.
Это сохраняет исходный frozen unit-контракт метаданных. Обязательный entrypoint
`verify_pr_evidence(get, download, repository, pr)` добавляет точный артефакт;
CLI всегда вызывает его, в том числе в read-only `--pr` режиме. Необязательный
`download=` аргумент helper направляет вызов в тот же строгий entrypoint.

Проверяется открытый PR этого репозитория в etalon, полные head/base/merge SHA.
Trusted BASE обязан иметь `guards/PROCESS_CONTRACTS.json`; автоматического
bootstrap нет. HEAD сохраняет каждый baseline file hash и каждый suite/report/
format/exact/case. API Git trees BASE/HEAD/MERGE должны быть полными; blob SHA и
mode каждого baseline-protected файла совпадают. Self-updated hash не разрешает
изменение теста, helper, CI, deploy или checker. Merge policy равна HEAD policy.

CI определяется по настоящему workflow ID/path `.github/workflows/ci.yml`,
событию pull_request, этому PR/head/base, GitHub Actions app и последнему run/
attempt. Обязательны success восемь jobs: baseline, backlog, backend,
frontend-build, охрана, print-regressions, printer-windows, process-proof.
Skipped/neutral/missing, старый base и более новый неуспешный run дают отказ.
PR и latest attempt перечитываются до результата и повторно после артефакта.

Обязателен единственный доступный artifact текущего run/attempt с именем
`process-proof-<merge SHA>-<run id>-<attempt>`. GitHub artifact metadata сверяется
с run/head; `execution.json` внутри ZIP — с tested merge/head/base/run/attempt
и SHA256 точных policy bytes. Ограничения: archive64MiB, expanded128MiB,
512 entries, metadata64KiB; запрещены повторные пути, traversal, symlink,
зашифрованные записи и malformed JSON. Архив не извлекается. Raw-case verification
здесь намеренно не дублируется: его выполняет immutable process-proof pipeline,
сам pipeline/checker защищён сравнением baseline Git blobs.

## Контракты до кода и проверки

Добавочный artifact-контракт сохранён коммитом `7a0811308` до checker. Initial
RED: 18 ошибок отсутствующего модуля (`tests-before-code.log`). Дополнительный
CLI-контракт обнаруженного null merge сохранён коммитом `b2d014d85` до исправления:
3 PASS, 1 содержательный FAIL (`cli-contract-red.log`). Он доказывает, что
временное отсутствие merge SHA обязано публиковать failure на известный head;
старый success не оставляется без обновления только из-за null merge.
Позднейшие изменения этих двух собственных тестов — только порядок import,
литералы dict и соединение контекстов lint; ожидания не изменены.

```sh
python3 -m unittest scripts.ci.tests.test_trusted_process_check scripts.ci.tests.test_trusted_process_artifact scripts.ci.tests.test_trusted_process_cli
/Users/deniscivkunov/Projects/WMS/backend/.venv/bin/python -m ruff check scripts/ci/trusted_process_check.py scripts/ci/tests/test_trusted_process_artifact.py scripts/ci/tests/test_trusted_process_cli.py
/Users/deniscivkunov/Projects/WMS/backend/.venv/bin/python -m mypy --follow-imports=skip scripts/ci/trusted_process_check.py
python3 -m compileall -q scripts/ci/trusted_process_check.py scripts/ci/tests/test_trusted_process_artifact.py scripts/ci/tests/test_trusted_process_cli.py
```

Итог: **22 PASS**, ruff PASS, mypy PASS, compileall PASS. Модуль использует stdlib;
тестовые GitHub get/download/publish callbacks синтетические. Внешние checks
не публиковались и живой PR этим проходом не принимался.

Четыре mutation controls временно удаляли защиты в собственном checker, после
чего исходник восстановлен побайтно в finally. Удалённая blob/mode защита дала
2 FAIL, metadata защита —6 FAIL, обязательные jobs —5 FAIL, обход strict CLI
через metadata helper —2 FAIL (`mutation-controls.log`). После восстановления
вновь22 PASS. Frozen negative tests отдельно сохраняют guards для selfhash/
workflow/tests/cases, skip/missingjob, wrongbase, newattempt и headchange.

## Подготовленный минимальный main diff — НЕ установлен

Для установки требуется отдельное прямое разрешение владельца менять main.
Подготовленные файлы для этого будущего diff:

1. `scripts/ci/trusted_process_check.py` — standalone checker, без candidate imports.
2. `process-integrity.yml` из этой evidence-папки → `.github/workflows/process-integrity.yml`.

Workflow слушает pull_request_target(etalon) и workflow_run(CI completed),
checkout только `main`, persist-credentials:false, никогда candidate checkout.
Permissions: contents/actions/pull-requests read, checks write. Единственный
командный шаг выполняет checker из main с `--publish`; тела checks идут
структурированным JSON stdin в gh api, не сообщениями людям. Публикация запрещена
с `--pr` и вне workflow event. PR head берётся свежим чтением, не из выражений
непроверенного event. YAML синтаксис и эти границы проверены
(`workflow-validation.log`); активного файла в `.github/workflows/` нет.

Read-only режим после установки кода (сейчас не запускался против GitHub):

```sh
python3 scripts/ci/trusted_process_check.py --repository owner/repository --pr 123
```

До установки anchor в main и trusted policy в BASE gate не является действующей
branch protection. Main/default/rulesets не менялись; main PR не создавался.
Не выполнялись deployment, клиентские/production операции, печать и управление
секретами. Независимое Astra review и итоговая интеграция выполняются ведущим.
Официальные API/event semantics сверены с GitHub Docs:
https://docs.github.com/en/rest/actions/workflow-runs
https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows

## Продолжение после независимого Astra A review

Два P1 publication случая исходного22-PASS checkpoint разобраны в
[publish-fixes.md](publish-fixes.md). Новый контракт9646bef50 до исправления,
текущий общий результат27 PASS. Валидный trusted event head —failure-only fallback;
все publishers —одна постоянная non-cancelling очередь. Workflow по-прежнему
только подготовлен и не установлен в main.

Следующий Astra A review обнаружил вытеснение pending failure третьим событием.
[queue-fix.md](queue-fix.md) исправляет прежнюю неточную модель очереди и
фиксирует дополнительный контракт `b6cac70ed` до YAML delta. Текущий результат
**30 PASS**. Константная группа теперь имеет `queue: max` и false cancel;
это максимум 100 pending, не неограниченная очередь. При заполнении GitHub
отменяет новый запуск, поэтому безграничная гарантия отзыва старого check не
заявляется. Workflow остаётся только подготовленным.

Подготовлен также явный owner-reviewed вход для первого BASE без policy:
[bootstrap-preparation.md](bootstrap-preparation.md). Additive контракт
`f4e6d2526` до кода, текущий общий результат **39 PASS**. Default без файла
разрешения остаётся refuse; новый source применяется только к exact original
BASE после доказанной отсутствия policy в полном tree. Конкретный source pin
заполняет ведущий после review. Конфигурация/активный workflow в main этим
исполнителем не установлены.
