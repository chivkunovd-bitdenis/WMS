# Отчёт активного Pipeline v2

Дата: 2026-08-20. Дополнение: 2026-08-21.

## Итог

Pipeline v2 находится в статусе `ACTIVE` по прямому решению владельца от 21.08.2026.
Это единственный действующий процесс для новых задач WMS; старый Product gate и
старые process docs переведены в короткие pointers.

В controller создана owner-approved волна из 49 backlog-карточек. Они находятся
на S01 и сами по себе не означают, что исправления или агенты уже запущены:
каждая карточка должна получить stage dispatch, receipts и обязательные Product,
Research, Architecture, Test, Review и Browser QA verdicts по своему профилю.

## Что уже готово для Codex, Claude и Cursor

- Есть единый источник правил: `docs/process/PIPELINE-RU.md` и машинная таблица
  стадий, рисков, обязательных доказательств и блокеров в `pipeline/pipeline.yml`.
- Есть локальный controller с командами `open`, `classify`, `advance`, `validate`,
  `status`, `report`, `hold`, `resume`, `next`, `packet`, `close`, resource
  locks/fencing, failure routing, case-result checks, release-proof recording и
  idempotent external-effect ledger. Он создаёт локальный state, packet для
  следующей роли и receipt для пройденной стадии.
- `hold` машинно запрещает случайный старт: пока карточка в `WAITING`,
  `advance` завершится ошибкой и потребует явный `resume`.
- `validate` проверяет state schema, receipt schema, receipt hash, hash-chain,
  stage/role/verdict и local signature hash.
- CI режет raw secrets в pipeline evidence/task artifacts.
- `report` строит утренний статус только из machine state:
  `python3 scripts/pipeline/run.py report`.
- Есть генератор dispatch-prompt для Codex, Claude и Cursor:
  `python3 scripts/pipeline/dispatch.py --task-id <id> --executor codex|claude|cursor`.
- Есть минимальный запуск owner-approved wave из backlog:
  `python3 scripts/pipeline/run.py start-wave --backlog-ids BLG-I04,BLG-I12 --owner-approved-by <owner>`.
  Он создаёт controller tasks из `docs/product/backlog-queue.json`, привязывает
  `BLG-*`, `wave_id`, budget enforcement и открытые `BLK-*`.
- Есть executable dry-run wave-driver:
  `python3 scripts/pipeline/wave_driver.py --format json`. Он читает только
  `WAITING` snapshots и показывает isolated worktree/ports/DB/Redis/Celery/
  emulator/resources plan, не создавая worktree, не запуская агентов и не
  записывая state.
- Есть машинная политика выбора модели: `pipeline/model-policy.yml`. Dispatch prompt теперь
  прямо пишет tier и конкретную модель: простая разработка уходит на дешёвую модель, dispatcher/BA
  на среднюю, а архитектура, продукт, ресёрч, ревью и живой браузер — на дорогую.
- Есть machine-readable budget policy: `pipeline/budget-policy.yml` и schema задают лимиты
  на wave/task/card/stage tier, warning threshold, fail-closed hard stop, usage receipt,
  recovery packet и owner override marker. CI проверяет policy отдельным check и pipeline metatest.
- Для задач, созданных через `start-wave`, `advance` требует usage receipt
  (`input_tokens`, `output_tokens`, `estimated_usd`, executor/model/tier) и
  переводит задачу в `WAITING/BUDGET_HARD_STOP`, если receipt отсутствует или
  превышен stage/task/wave budget.
- Все `MT01`...`MT40` из части XII сейчас `automated_green`. Метатесты проверяют
  сам процесс: например, что разработка не получает workspace раньше продуктового
  одобрения, старый fencing token отклоняется, красный GOLD case блокирует
  интеграцию, а повтор external side effect с тем же idempotency key не выполняется.
- В production deploy уже требуется указанный Git SHA, а runtime smoke сверяет
  запущенную версию. Автоматического deploy от push в `main` нет.
- Production deploy больше не собирает образы на сервере: CI строит offline
  release artifact для exact SHA, manifest связывает SHA, архивы и Docker image
  ID, а сервер только проверяет manifest и делает `docker load`.
- Backend pytest и frontend Playwright в GitHub CI запускаются через
  fail-closed test egress runner для WB/Ozon.
- UI-kit стал обязательным для новой экранной работы: `scripts/ui/ui_kit_usage_guard.py`
  держит базовую линию старых экранов и краснит новый экран или новую видимую
  UI-зону без импорта `frontend/src/ui-kit`, а также новый raw MUI/inline-style
  в экранном diff.
- В `frontend/src/ui-kit/` добавлены недостающие базовые элементы для будущих
  задач: формы, селект, чекбокс, вкладки, меню, модалка и каркас экрана. Контракт
  задачи теперь обязан называть компоненты из набора, а нехватку элемента фиксировать
  как `DESIGN_SYSTEM_GAP`.
- `docs/product/ui-inventory.json` теперь содержит машиночитаемый раздел
  `components`: компонент, зона, назначение, обязательные props и текущие места
  использования.
- Реестр блокировок вынесен в `docs/process/BLOCKERS-REGISTRY-RU.md`: там отдельно
  описаны pipeline-блокеры и backlog-блокеры с владельцем закрытия и минимальным
  артефактом.
- Машинная база блокировок лежит в `docs/product/blocks.json`; CI сверяет её
  один-к-одному с Markdown-реестром через `scripts/ci/check_blockers_registry.py`.
- Controller привязывает открытые `BLK-*` к backlog task и останавливает stage,
  на котором блокер должен быть снят; закрытие задачи с открытым blocker ID
  запрещено до `resolve-blocker` с evidence-файлом.
- Единая machine-readable backlog queue лежит в `docs/product/backlog-queue.json`.
  В неё входят свежие K1/K2: тормоза системы и пробная задача аналитической
  отчётности для селлера/фулфилмента.
- Для всех трёх агентов можно одинаково: снять `WAITING` с одной одобренной
  карточки, выдать dispatch, пройти нужные стадии, получить controller receipt и
  остановиться на Product/owner gate, если он требуется.

## Ограничения управляемого ACTIVE-режима

- Dry-run wave-driver уже выдаёт проверяемый isolated resource plan, но не имеет
  распределённого host, который мог бы безопасно применить план, и controller
  state пока не хранится во внешнем durable store.
- Receipt не подписываются независимым ключом, а общая проверка состояния ещё не
  применяется одинаково controller, CI и deploy.
- Registry promotion не настроен: вместо OCI registry пока используется
  fail-closed offline artifact. Это уже убирает server-side build, но не заменяет
  полноценный registry-based promotion.
- Тестовый контур закрыт для основных CI backend/e2e команд, но ad-hoc локальные
  команды и browser-level sandbox ещё не унифицированы.
- Старые процессные документы больше не действуют как отдельный канон: они
  сокращены до adapters на Pipeline v2 и проверяются activation contract guard.
- BLK-COST-001 сужен сильнее: controller runtime enforcement для `start-wave`
  задач есть, но расход пока self-reported агентом, а не подтверждён provider
  billing API.
- BLK-BACKLOG-001 сужен: backlog сведён в единую versioned очередь со stable IDs,
  зависимостями и readiness. Остаётся owner-approved wave: владелец должен выбрать
  конкретные `BLG-*`, лимиты и порядок запуска.
- BLK-PROCESS-001 сужен сильнее: runtime binding в controller есть для задач,
  созданных из backlog wave. Остаётся расширить это на старые вручную заведённые
  tasks и на глобальные process blockers.
- Старый UI-долг не погашен автоматически: экраны не переписаны на `ui-kit`.
  Новое правило защищает будущие правки, а переезд существующих экранов должен идти
  по задачам, когда эти экраны всё равно попадают в работу.

## Команды проверки

Проверить машинный контракт pipeline без изменения state:

```bash
python3 scripts/ci/check_pipeline_contract.py
python3 scripts/ci/check_pipeline_model_policy.py
python3 scripts/ci/check_pipeline_budget_policy.py
python3 scripts/ci/check_backlog_queue.py
python3 scripts/ci/check_blockers_registry.py
python3 scripts/ui/ui_guard.py
python3 scripts/ui/ui_kit_usage_guard.py
```

Проверить реализованную часть метатестов отдельно:

```bash
python3 scripts/ci/check_pipeline_metatests.py
python3 scripts/ci/check_pipeline_policy_metatests.py
python3 scripts/ci/check_pipeline_wave_driver_smoke.py
python3 scripts/ci/check_pipeline_replay_metatests.py
```

## Как начать выбранную карточку

Owner-approved wave уже создана. Для выбранной карточки dispatcher сначала читает
её текущее состояние и выдаёт следующий stage; если карточка была отдельно поставлена
на `WAITING`, её сначала снимают с удержания:

```bash
python3 scripts/pipeline/run.py status --task-id <TASK_ID>
python3 scripts/pipeline/run.py next --task-id <TASK_ID>
python3 scripts/pipeline/dispatch.py --task-id <TASK_ID> --executor codex
```

Переход к разработке (`S18 DEVELOPMENT`) возможен лишь после всех требуемых
ранних стадий и receipt `PRODUCT_APPROVED_FOR_DEV`. Активация процесса не является
разрешением на production, секреты или live-вызовы маркетплейсов.

## Блокеры конкретных карточек

1. Нет product receipt `PRODUCT_APPROVED_FOR_DEV` для каждой карточки.
2. Не пройдены обязательные для bug stages: воспроизведение, договорённость об
   ожидаемом поведении, анализ причины и регрессионный кейс либо доказанное B04
   закрытие без изменения кода.
3. Для FBS/Честного знака остаётся отдельная предметная развилка: owner или
   подтверждённый контракт WB должен определить, допустим ли `sgtinApplied` для
   dispatch. Агент не может выбирать это правило сам.

Независимые карточки продолжают ранние стадии, пока другие ждут своих typed blockers.
Production deploy, реальные вызовы WB/Ozon и работа с секретами не разрешаются
самим статусом `ACTIVE`.
