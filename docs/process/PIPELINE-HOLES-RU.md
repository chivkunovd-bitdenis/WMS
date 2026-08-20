# Pipeline v2: дырки перед активацией

Дата: 2026-08-20.

Статус: `IMPLEMENTATION_IN_PROGRESS`.

Этот файл фиксирует разрыв между целевой спецификацией
[`docs/process/PIPELINE-RU.md`](PIPELINE-RU.md) и тем, что сейчас реально
включено в репозитории. Это не список "мелких TODO"; каждый пункт ниже мешает
честно поставить `PIPELINE_ACTIVATION_APPROVED`.

## P0. Deploy exact-SHA guard включён, но build-once promotion ещё не готов

Факт из текущих файлов:

- `.github/workflows/deploy.yml` больше не деплоит push в `main`; production
  deploy запускается вручную с обязательным `release_sha`;
- workflow чекаутит detached exact SHA, передаёт `WMS_RELEASE_SHA` в
  `scripts/deploy/prod-update.sh` и smoke-проверяет `/api/version`;
- `scripts/deploy/prod-update.sh` больше не делает `checkout main`/`pull main`
  и падает, если `HEAD != WMS_RELEASE_SHA` или worktree dirty;
- контейнеры всё ещё собираются на сервере через `docker compose build`.

Почему это всё ещё дырка: exact Git SHA уже защищён, но Pipeline v2 требует
build-once immutable artifacts и promotion готовых digests. Серверная сборка
ровно того же SHA лучше прежнего `main`, но ещё не доказывает неизменность
artifact digest между acceptance и production.

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
подписывает receipts секретным ключом, не реализует полноценный fencing token,
crash replay и resource scheduler.

Почему это дырка: без controller рабочий агент всё ещё может "сказать", что
стадия пройдена, а не получить проверяемый controller-issued receipt.

## P0. Метатесты частично автоматизированы

В `pipeline/pipeline.yml` заведены `MT01`...`MT40`, чтобы CI не потерял ни один
сценарий части XII. `scripts/ci/check_pipeline_metatests.py` сейчас доказывает
первый executable slice: Product-before-workspace order, запрет `DONE` до
`ACTIVE`, entrypoint inventory, trait machine dimensions и exact-SHA deploy
guard.

Почему это дырка: наличие списка защищает от забывания требований, но не
доказывает, что Dev без Product approval реально не получает workspace, что
истёкший lock отклоняется, или что crash между external side effect и state
update идемпотентно восстанавливается. Большая часть MT02...MT40 ещё pending.

## P0. Fail-closed test egress не включён для всего тестового контура

Из прошлой диагностики и текущих требований известно, что тестовый контур должен
быть закрыт наружу по умолчанию. В этой правке не добавлен сетевой sandbox для
всех backend, frontend, worker и emulator прогонов.

Почему это дырка: тесты, которые случайно обращаются в живой WB/Ozon, остаются
классом риска, пока это не запрещено технически на уровне runner/environment.

## P1. Старые процессные документы ещё живые

Входные документы теперь получили указатель на
`docs/process/PIPELINE-RU.md` и `pipeline/pipeline.yml`, но старые Product gate
и `.dev/PROCESS.md` осознанно оставлены действующими до активации.

Почему это дырка: это безопасно для переходного состояния, но после activation
надо архивировать или превратить в короткие adapters все старые маршруты из
списка E0, иначе агенты снова увидят два канона.

## P1. Схемы есть, но не подключены к runtime receipts

Созданы `pipeline/task-state.schema.json`, `receipt.schema.json`,
`evidence.schema.json`, `case.schema.json` и `incident.schema.json`. Пока нет
producer/consumer, который обязательно пишет и проверяет эти структуры для
каждой стадии.

Почему это дырка: schema без обязательного writer/validator остаётся контрактом,
а не доказательством прохождения стадии.

## Что уже закрыто этой настройкой

- Появился `pipeline/pipeline.yml` как единая машинная таблица стадий, traits,
  lifecycle statuses, blockers, protected paths, entrypoints и required
  metatests.
- Появился CI guard `scripts/ci/check_pipeline_contract.py`.
- Появился executable local controller `pipeline/controller.py` и вход
  `scripts/pipeline/run.py`.
- Появились `hold`/`resume` и `next`/`packet`, чтобы очередь можно было
  подготовить без запуска фиксов и передавать stage между ролями.
- Появился `scripts/pipeline/dispatch.py`, который пишет одинаковые handoff
  prompts для Codex, Claude и Cursor.
- Появился `scripts/ci/check_pipeline_metatests.py`.
- Production deploy больше не стартует автоматически от push в `main` и требует
  exact `release_sha`.
- Backend отдаёт `/version`, а deploy smoke сверяет runtime SHA.
- `.github/workflows/ci.yml` запускает этот guard.
- Основные process entrypoints прямо указывают на новый канон и текущий
  неактивированный статус.
- Ветка больше не может незаметно поменять `PIPELINE-RU.md` без обновления
  `canonical_source_sha256`.

## Следующий технический slice

Самый полезный следующий slice: build-once artifact manifest и promotion exact
digests. Нужно убрать серверный `docker compose build`, собирать backend,
worker, migrations и frontend один раз в CI, сохранять manifest и продвигать
именно эти digests на production.
