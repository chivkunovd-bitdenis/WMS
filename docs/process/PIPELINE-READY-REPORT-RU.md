# Отчёт готовности Pipeline v2 перед очередью багов

Дата: 2026-08-20.

## Итог

Pipeline v2 находится в статусе `IMPLEMENTATION_IN_PROGRESS`, а не `ACTIVE`.
Ночная очередь из пяти карточек заведена в controller и сразу поставлена в
`WAITING` с блокером `OWNER_INPUT/QUEUED_NOT_STARTED`: у карточек есть Git
snapshot состояния и packet для S01, но нет receipts, verdicts, назначенного
исполнителя или начатого исправления.

Это означает, что систему уже можно использовать для одинаковой подготовки задач
в Codex, Claude и Cursor, но нельзя честно назвать её автономным ночным конвейером
исправления багов.

## Что уже готово для Codex, Claude и Cursor

- Есть единый источник правил: `docs/process/PIPELINE-RU.md` и машинная таблица
  стадий, рисков, обязательных доказательств и блокеров в `pipeline/pipeline.yml`.
- Есть локальный controller с командами `open`, `classify`, `advance`, `validate`,
  `status`, `report`, `hold`, `resume`, `next`, `packet` и `close`. Он создаёт
  локальный state, packet для следующей роли и receipt для пройденной стадии.
- `hold` машинно запрещает случайный старт: пока карточка в `WAITING`,
  `advance` завершится ошибкой и потребует явный `resume`.
- `validate` проверяет state schema, receipt schema, receipt hash, hash-chain,
  stage/role/verdict и local signature hash.
- CI режет raw secrets в pipeline evidence/task artifacts.
- `report` строит утренний статус только из machine state:
  `python3 scripts/pipeline/run.py report`.
- Есть генератор dispatch-prompt для Codex, Claude и Cursor:
  `python3 scripts/pipeline/dispatch.py --task-id <id> --executor codex|claude|cursor`.
- Есть автоматические проверки контракта pipeline и уже реализованной части
  метатестов. Метатесты проверяют сам процесс: например, что разработка не должна
  получить workspace раньше продуктового одобрения.
- В production deploy уже требуется указанный Git SHA, а runtime smoke сверяет
  запущенную версию. Автоматического deploy от push в `main` нет.
- Production deploy больше не собирает образы на сервере: CI строит offline
  release artifact для exact SHA, manifest связывает SHA, архивы и Docker image
  ID, а сервер только проверяет manifest и делает `docker load`.
- Backend pytest и frontend Playwright в GitHub CI запускаются через
  fail-closed test egress runner для WB/Ozon.
- Для всех трёх агентов можно одинаково: снять `WAITING` с одной одобренной
  карточки, выдать dispatch, пройти intake/классификацию, собрать факты о баге
  и остановиться до следующего решения владельца.

## Что не готово для автономной ночной работы

- Controller пока локальный: он не выделяет изолированные worktree, порты, БД,
  Redis, очередь worker и emulator как защищённые ресурсы и не умеет полноценно
  восстановиться после сбоя.
- Receipt не подписываются независимым ключом, а общая проверка состояния ещё не
  применяется одинаково controller, CI и deploy.
- Registry promotion не настроен: вместо OCI registry пока используется
  fail-closed offline artifact. Это уже убирает server-side build, но не заменяет
  полноценный registry-based promotion.
- Тестовый контур закрыт для основных CI backend/e2e команд, но ad-hoc локальные
  команды и browser-level sandbox ещё не унифицированы.
- 22 из 40 обязательных метатестов ещё pending. Старые процессные документы
  также остаются действующими до явной активации Pipeline v2.

## Команды проверки

Проверить машинный контракт pipeline без изменения state:

```bash
python3 scripts/ci/check_pipeline_contract.py
```

Проверить реализованную часть метатестов отдельно:

```bash
python3 scripts/ci/check_pipeline_metatests.py
```

## Как начать только после разрешения

Сейчас все пять карточек уже стоят в `WAITING`. Чтобы начать одну конкретную
карточку, нужно письменное owner approval именно на неё, затем:

```bash
python3 scripts/pipeline/run.py resume --task-id BUG-WMS-PV2-001 --by owner
python3 scripts/pipeline/run.py next --task-id BUG-WMS-PV2-001
python3 scripts/pipeline/dispatch.py --task-id BUG-WMS-PV2-001 --executor codex
```

После `resume` допустима только подготовительная работа по S01/S02 и B01–B03.
Переход к разработке (`S18 DEVELOPMENT`) возможен лишь после product receipt
`PRODUCT_APPROVED_FOR_DEV` и отдельного owner approval на начало исправления.

## Блокеры до запуска фиксов багов

1. Нет письменного owner approval на запуск конкретной карточки; текущая очередь
   остаётся `WAITING`.
2. Pipeline v2 не `ACTIVE`, поэтому прежний Product gate продолжает действовать.
3. Нет product receipt `PRODUCT_APPROVED_FOR_DEV` для каждой карточки.
4. Не пройдены обязательные для bug stages: воспроизведение, договорённость об
   ожидаемом поведении, анализ причины и регрессионный кейс либо доказанное B04
   закрытие без изменения кода.
5. Не устранены оставшиеся P0-дыры: полная изоляция controller, независимая
   подпись receipt, полный сетевой sandbox для всех test entrypoint'ов и все
   обязательные метатесты.
6. Для FBS/Честного знака остаётся отдельная предметная развилка: owner или
   подтверждённый контракт WB должен определить, допустим ли `sgtinApplied` для
   dispatch. Агент не может выбирать это правило сам.

До снятия этих блокеров допускаются только чтение материалов, проверка contract и
подготовка карточек; production deploy, реальные вызовы WB/Ozon, работа с секретами
и изменения product/controller кода не запускаются.
