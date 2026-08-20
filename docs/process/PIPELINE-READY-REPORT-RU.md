# Отчёт готовности Pipeline v2 перед очередью багов

Дата: 2026-08-20. Дополнение: 2026-08-21.

## Итог

Pipeline v2 находится в статусе `IMPLEMENTATION_IN_PROGRESS`, а не `ACTIVE`.
Ночная очередь из пяти карточек заведена в controller и сразу поставлена в
`WAITING` с блокером `OWNER_INPUT/QUEUED_NOT_STARTED`: у карточек есть Git
snapshot состояния и packet для S01, но нет receipts, verdicts, назначенного
исполнителя или начатого исправления.

Это означает, что pipeline уже можно использовать как исполнимый управляемый
контур для запуска стадий и агентов, но глобальный режим `ACTIVE` ещё не включён:
старый Product gate остаётся действующим до отдельной owner activation line.

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
- Для всех трёх агентов можно одинаково: снять `WAITING` с одной одобренной
  карточки, выдать dispatch, пройти нужные стадии, получить controller receipt и
  остановиться на Product/owner gate, если он требуется.

## Что не готово для автономной ночной работы

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
- Старые процессные документы остаются действующими до явной активации Pipeline
  v2. Это безопасно для перехода, но не даёт объявить новый процесс единственным
  каноном без отдельного activation PR/line.
- BLK-COST-001 сужен: статический budget contract, warning/hard stop policy, owner override
  marker и recovery packet закрыты. Остаётся runtime accounting: provider usage receipts,
  durable aggregation по wave/card/stage и фактическая блокировка dispatch по измеренному
  расходу; policy явно не заявляет runtime enforcement.
- Backlog пока не сведён в единую versioned очередь со stable IDs, зависимостями,
  readiness и owner-approved wave.
- Старый UI-долг не погашен автоматически: экраны не переписаны на `ui-kit`.
  Новое правило защищает будущие правки, а переезд существующих экранов должен идти
  по задачам, когда эти экраны всё равно попадают в работу.

## Команды проверки

Проверить машинный контракт pipeline без изменения state:

```bash
python3 scripts/ci/check_pipeline_contract.py
python3 scripts/ci/check_pipeline_model_policy.py
python3 scripts/ci/check_pipeline_budget_policy.py
python3 scripts/ui/ui_guard.py
python3 scripts/ui/ui_kit_usage_guard.py
```

Проверить реализованную часть метатестов отдельно:

```bash
python3 scripts/ci/check_pipeline_metatests.py
python3 scripts/ci/check_pipeline_policy_metatests.py
python3 scripts/ci/check_pipeline_replay_metatests.py
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
5. Не устранены оставшиеся activation blockers: distributed controller,
   независимая подпись receipt, полный сетевой sandbox для всех test entrypoint'ов
   и архивирование старых process entrypoint'ов после activation.
6. Для FBS/Честного знака остаётся отдельная предметная развилка: owner или
   подтверждённый контракт WB должен определить, допустим ли `sgtinApplied` для
   dispatch. Агент не может выбирать это правило сам.

До снятия этих блокеров допускаются только чтение материалов, проверка contract и
подготовка карточек; production deploy, реальные вызовы WB/Ozon, работа с секретами
и изменения product/controller кода не запускаются.
