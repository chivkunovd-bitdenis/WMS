# Pipeline v2: дырки перед активацией

Дата: 2026-08-20.

Статус: `IMPLEMENTATION_IN_PROGRESS`.

Этот файл фиксирует разрыв между целевой спецификацией
[`docs/process/PIPELINE-RU.md`](PIPELINE-RU.md) и тем, что сейчас реально
включено в репозитории. Это не список "мелких TODO"; каждый пункт ниже мешает
честно поставить `PIPELINE_ACTIVATION_APPROVED`.

## P0. Offline build-once artifact promotion реализован, registry promotion не настроен

Факт из текущих файлов:

- `.github/workflows/deploy.yml` больше не деплоит push в `main`; production
  deploy запускается вручную с обязательным `release_sha`;
- workflow чекаутит detached exact SHA, передаёт `WMS_RELEASE_SHA` в
  `scripts/deploy/prod-update.sh` и smoke-проверяет `/api/version`;
- `scripts/deploy/prod-update.sh` больше не делает `checkout main`/`pull main`
  и падает, если `HEAD != WMS_RELEASE_SHA` или worktree dirty;
- CI один раз собирает backend и web для exact SHA, сохраняет их в offline
  release artifact и создаёт manifest с SHA-256 архивов и Docker image ID;
- workflow передаёт artifact на production-server вместе с exact SHA;
- `prod-update.sh` принимает только manifest из этого artifact, повторно
  сверяет SHA, SHA-256 и image ID, загружает образы и запускает compose без
  `docker compose build`.

Что ещё не готово: registry promotion (push/pull OCI image digests) не
реализован и не заявляется реализованным. Для него потребуются отдельно
выданные registry configuration и credentials. Пока production использует
fail-closed offline path: отсутствующий, подменённый или несоответствующий SHA
manifest останавливает deploy до миграций и restart.

## P0. Controller появился, полный wave-driver и единый validation engine ещё не готовы

Добавлен `pipeline/controller.py` и вход `scripts/pipeline/run.py` с командами
`open`, `classify`, `hold`, `resume`, `next`, `packet`, `advance`, `validate`,
`status`, `close`. Контроллер пишет runtime state в `.pipeline-state/`,
публикует snapshot в `tasks/<task-id>/`, создаёт packet для следующей роли и
structured receipt при `advance`.

Что закрыто после первичного slice: задачу можно машинно поставить в `WAITING`;
пока она ждёт владельца, `advance` запрещён. Это защищает подготовленную очередь
от случайного старта до явного `resume`.

Что ещё не закрыто: это минимальный local controller, а не полный `wave-driver`.
Он ещё не выдаёт настоящие isolated worktrees/ports/DB/Redis/Celery/emulator, не
подписывает receipts независимым секретным ключом, не реализует полноценный
fencing token, crash replay и resource scheduler.

Почему это дырка: без controller рабочий агент всё ещё может "сказать", что
стадия пройдена, а не получить проверяемый controller-issued receipt.

## P0. Метатесты автоматизированы, activation ещё не включён

В `pipeline/pipeline.yml` заведены `MT01`...`MT40`, чтобы CI не потерял ни один
сценарий части XII. Все 40 сейчас имеют статус `automated_green` и проверяются
тремя suite в CI: `check_pipeline_metatests.py`, `check_pipeline_policy_metatests.py`
и `check_pipeline_replay_metatests.py`.

`check_pipeline_metatests.py` доказывает executable controller slice:
Product-before-workspace order, запрет `DONE` до `ACTIVE`, entrypoint inventory,
trait machine dimensions, resource locks/fencing, queue isolation, failure routes,
dependency invalidation, machine report и защиту от подделки stage/receipt.

MT02/MT03 закрыты local scope guard: `scripts/ci/check_pipeline_scope_guard.py`
сверяет PR diff/base либо локальные staged/working/untracked изменения с
`control_plane_protected_paths`. Изменение `pipeline/**`, workflow, deploy
scripts или `tasks/*/state.json` без явного `pipeline_change`/`control-plane`
в `PIPELINE_SCOPE_ALLOW`, PR label либо PR body marker останавливает CI.
Сценарии блокировки и трёх способов разрешения выполняются из
`check_pipeline_metatests.py`.

Почему это всё ещё не `ACTIVE`: метатесты больше не pending, но activation
остаётся выключен до owner activation line, независимой receipt-подписи,
унифицированного distributed wave-driver и полного audit старых entrypoint'ов.

## P0. Fail-closed test egress не включён для всего тестового контура

Из прошлой диагностики и текущих требований известно, что тестовый контур должен
быть закрыт наружу по умолчанию. Добавлен локальный runner
`scripts/testing/test_egress_guard.py`: он запускает Python/Node тестовую
команду с deny-by-default allowlist, блокирует WB/Ozon до DNS/соединения и
требует явный `WMS_TEST_EGRESS_ALLOW_LIVE_MARKETPLACES=1` для live endpoint.
Его контракт проверяется через MT13. Основной GitHub CI backend `pytest` и
frontend `npx playwright test` запускаются через этот runner.

Почему это всё ещё дырка: ad-hoc локальные команды, отдельные shell-entrypoint'ы
и browser-level сетевой sandbox ещё не унифицированы. Тесты, которые обходят
runner, всё ещё могут обратиться в живой WB/Ozon, поэтому до полной активации
нужен audit всех штатных test entrypoint'ов или сетевой sandbox уровнем ниже
процесса.

## P0. Crash/restart lane: MT04, MT22 и MT40 проверяются автономно

Добавлены `pipeline/replay.py` и `scripts/ci/check_pipeline_replay_metatests.py`.
Они без запуска controller или LMS/WMS читают временные копии того же
`state.json`/`journal.jsonl`: MT04 восстанавливает следующий stage после
последнего receipt и терпит оборванную последнюю строку журнала, MT22
восстанавливает все task-state wave, MT40 не повторяет внешний effect по
durable `effect_key`, если crash произошёл до обновления task state.

Это автономный contract probe плюс controller-level `external-effect`: controller
пишет durable effect ledger по idempotency key и повторный вызов того же ключа
не выполняет side effect второй раз. До полной активации всё равно нужен такой
же idempotency contract для реальных provider adapters и deploy integration.

## P1. Старые процессные документы ещё живые

Входные документы теперь получили указатель на
`docs/process/PIPELINE-RU.md` и `pipeline/pipeline.yml`, но старые Product gate
и `.dev/PROCESS.md` осознанно оставлены действующими до активации.

Почему это дырка: это безопасно для переходного состояния, но после activation
надо архивировать или превратить в короткие adapters все старые маршруты из
списка E0, иначе агенты снова увидят два канона.

## P1. Схемы подключены к controller validate, но не стали независимой подписью

Созданы `pipeline/task-state.schema.json`, `receipt.schema.json`,
`evidence.schema.json`, `case.schema.json` и `incident.schema.json`.
`pipeline/controller.py validate` уже проверяет task-state schema, receipt
schema, receipt hash, hash-chain, stage/role/verdict и signature hash для
выданных controller receipt.

Почему это всё ещё дырка: signature пока является hash-подписью внутри локального
controller, а не подписью независимым ключом, недоступным worker. Эта проверка
ловит ручную подмену receipt, но ещё не является полноценной trust boundary для
distributed wave-driver.

## Что уже закрыто этой настройкой

- Появился `pipeline/pipeline.yml` как единая машинная таблица стадий, traits,
  lifecycle statuses, blockers, protected paths, entrypoints и required
  metatests.
- Появился CI guard `scripts/ci/check_pipeline_contract.py`.
- Появился executable local controller `pipeline/controller.py` и вход
  `scripts/pipeline/run.py`.
- Появились `hold`/`resume` и `next`/`packet`, чтобы очередь можно было
  подготовить без запуска фиксов и передавать stage между ролями.
- `validate` теперь проверяет state schema, receipt schema, receipt hash,
  hash-chain, stage/role/verdict и local signature hash.
- CI проверяет pipeline evidence/task artifacts на raw Authorization/Cookie/API
  key/token patterns.
- Появился `report`, который строит утренние строки только из machine state.
- Появился `scripts/pipeline/dispatch.py`, который пишет одинаковые handoff
  prompts для Codex, Claude и Cursor.
- Появился `scripts/ci/check_pipeline_metatests.py`.
- Появились `scripts/ci/check_pipeline_policy_metatests.py` и
  `scripts/ci/check_pipeline_replay_metatests.py`; все `MT01`...`MT40`
  сейчас `automated_green`.
- Появился scope guard для protected control-plane paths и controller resource
  leases/fencing tokens для конфликтующих файлов, таблиц, процессов и queues.
- Production deploy больше не стартует автоматически от push в `main` и требует
  exact `release_sha`.
- Backend отдаёт `/version`, а deploy smoke сверяет runtime SHA.
- `.github/workflows/ci.yml` запускает этот guard.
- Основные process entrypoints прямо указывают на новый канон и текущий
  неактивированный статус.
- Ветка больше не может незаметно поменять `PIPELINE-RU.md` без обновления
  `canonical_source_sha256`.

## Следующий технический slice

Самый полезный следующий slice: заменить локальную hash-signature на независимую
receipt-подпись, недоступную worker, и довести controller до distributed
wave-driver: isolated worktrees/ports/DB/Redis/Celery/emulator, общий recovery
store и единый validation engine для controller, CI и deploy.
