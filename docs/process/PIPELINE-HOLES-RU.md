# Pipeline v2: дырки перед активацией

Дата: 2026-08-20.

Статус: `TARGET_PIPELINE_NOT_ENFORCED`.

Этот файл фиксирует разрыв между целевой спецификацией
[`docs/process/PIPELINE-RU.md`](PIPELINE-RU.md) и тем, что сейчас реально
включено в репозитории. Это не список "мелких TODO"; каждый пункт ниже мешает
честно поставить `PIPELINE_ACTIVATION_APPROVED`.

## P0. Deploy всё ещё не exact-SHA promotion

Факт из текущих файлов:

- `.github/workflows/deploy.yml` по push в `main` заходит на сервер, делает
  `git fetch origin`, `git checkout main`, `git reset --hard origin/main` и
  запускает `./scripts/deploy/prod-update.sh`;
- `scripts/deploy/prod-update.sh` повторно делает `git fetch`, `git checkout
  main`, `git pull --ff-only origin main` или `git reset --hard origin/main`,
  затем заново собирает `migrations`, `api`, `celery_worker`, `celery_beat` и
  `web` через `docker compose build`.

Почему это дырка: Pipeline v2 требует build-once immutable artifacts, promotion
ровно разрешённого SHA и runtime verification по `git_sha + artifact_digest`.
Текущий deploy доказывает только, что сервер собрал текущее `origin/main`;
он не доказывает, что выкатился тот SHA, который прошёл acceptance.

## P0. Controller и единый validation engine не реализованы

Добавленный `scripts/ci/check_pipeline_contract.py` проверяет только машинный
контракт: стадии, traits, hash канонического Markdown, entrypoint pointers и
наличие 40 метатестов. Он не является `wave-driver`: не выдаёт worktree, не
подписывает receipts, не ведёт event journal, не делает compare-and-swap state и
не управляет lease/fencing token.

Почему это дырка: без controller рабочий агент всё ещё может "сказать", что
стадия пройдена, а не получить проверяемый controller-issued receipt.

## P0. Метатесты пока объявлены, но не доказывают поведение

В `pipeline/pipeline.yml` заведены `MT01`...`MT40`, чтобы CI не потерял ни один
сценарий части XII. Их статус сейчас `declared_pending_controller`, а не
`automated_green`.

Почему это дырка: наличие списка защищает от забывания требований, но не
доказывает, что Dev без Product approval реально не получает workspace, что
истёкший lock отклоняется, или что crash между external side effect и state
update идемпотентно восстанавливается.

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
- `.github/workflows/ci.yml` запускает этот guard.
- Основные process entrypoints прямо указывают на новый канон и текущий
  неактивированный статус.
- Ветка больше не может незаметно поменять `PIPELINE-RU.md` без обновления
  `canonical_source_sha256`.

## Следующий технический slice

Самый полезный следующий slice: E-1 deploy safety fuse. Нужно заменить текущий
deploy на build-once artifact manifest, promotion exact digests, `/version`
проверку backend/worker/frontend и rollback/stop plan. Это снижает самый опасный
разрыв: "приняли один SHA, выкатили другой".
