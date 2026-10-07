# WMS-652: серверная проверка перед прямым prod-update

База: `cee68a42dd43aee1a7f6cf86277e6fb697133171`, worktree
`.worktrees/wms652-server-deploy-gate`, ветка `codex/wms652-server-deploy-gate`.
Прочитан свежий origin/etalon:AGENTS.md; проверен origin
`https://github.com/chivkunovd-bitdenis/WMS.git`. Runtime repository зафиксирован
в checker как `chivkunovd-bitdenis/WMS`; env не выбирает чужой зелёный репозиторий.

Тестовый контракт зафиксирован коммитом `f56717604` до кода. RED:8 ошибок
отсутствующего модуля и2 содержательных FAIL shell-пути: Docker начинал build
без gate. Guard-only первоначально уже PASS, поскольку ничего не строит.
Frozen ожидания и прежние тесты не менялись.

## Проверяемое поведение

Новый `verify_server_process_ci.py` использует stdlib urllib GET публичного
GitHub API, без gh, токенов и чтения/изменения секретов. Существующий verify_ci
проверяет точный etalon push SHA, workflow path/app/latest run и baseline jobs.
Сервер дополнительно требует current-attempt success print-regressions,
printer-windows, process-proof; единственный nonexpired artifact
`process-proof-<SHA>-<run>-<attempt>` с GitHub run/head identity и допустимым
размером. Latest run/attempt перечитывается после artifact. API/TLS/rate-limit,
неполные metadata и все неуспешные состояния останавливают выпуск.

`prod-update.sh` вызывает checker после безвредного WMS_DEPLOY_GUARD_ONLY exit
и до COMPOSE/network-probe, build, stop, backup или migration. Переменные
WMS_PROCESS_VERIFIED/WMS_DEPLOY_CI_VERIFIED не дают разрешения. Никаких новых
verified-флагов нет. Repository CLI/env override не введён.

**Это metadata gate, не повтор raw parser.** Смысл артефакта обеспечивается
immutable process-proof pipeline, который проверяет реальные raw-case отчёты;
DeployProduction отдельно проверяет полное execution evidence. Для действующей
защиты процесса новые checker/tests/prod-update должны войти в доверенную
baseline policy. Переход gate через CI не делает произвольный изменённый pipeline
доверенным и не является заменой независимого main anchor.

## Команды и результаты

```sh
python3 -m unittest scripts.ci.tests.test_server_process_gate scripts.ci.tests.test_verify_ci
/Users/deniscivkunov/Projects/WMS/backend/.venv/bin/python -m ruff check scripts/ci/verify_server_process_ci.py scripts/ci/tests/test_server_process_gate.py
/Users/deniscivkunov/Projects/WMS/backend/.venv/bin/python -m mypy --follow-imports=skip scripts/ci/verify_server_process_ci.py
bash -n scripts/deploy/prod-update.sh
```

**28 PASS**: new11 + existing17. Ruff/mypy/bash syntax PASS. Новые негативные
контроли проверяют missing/red/skipped/neutral/pending print jobs, latest red
run, wrong SHA/event/branch, stale attempt, expired/missing/duplicate/foreign
artifact и изменение attempt во время чтения. Public reader передаёт только GET
и не добавляет Authorization;403 даёт GateError.

Shell использует synthetic git/python3/docker из временной тестовой папки:
не запускаются настоящий git checkout, config или Docker. При gate exit2 —
ноль Docker calls, даже с verified=1. При guard-only —ноль gate/Docker calls.
При gate success первый следующий вызов —build migrations synthetic Docker,
который сразу останавливается. Удаление одной строки вызова gate временно даёт
2 FAIL из3 shell cases (`deploy-gate-mutation.log`). Скрипт восстановлен побайтно
в finally; после восстановления вновь28 PASS.

## Публичный доступ и границы

`public-api-read.json` сохраняет очищенное read-only доказательство: обычный
curl -q без Authorization получил HTTP200 workflow/run/artifact metadata.
Это проверка доступности API, не приёмка CI указанного запуска. Local stdlib
Python urllib не прошёл TLS issuer verification в этом macOS окружении;
сертификаты не обходились/не менялись. Новый gate в таком runtime останавливает
выпуск. Серверный Python/runtime на production не запускался и не проверен.

На production скрипт не запускался. Не затронуты main, rulesets, hotfix bot,
клиенты, deployment, физическая печать и секреты. Полный CI, интеграция policy и
независимое ревью остаются у ведущего. Продуктовая логика не менялась.
