# Минимальный план внедрения

## Принцип

Не переписывать текущий `scripts/night.py` целиком и не запускать новую большую волну на непроверенном
controller. Каждый этап должен дать самостоятельно наблюдаемое улучшение и быть испытан на одной
реальной карточке.

## Этап 0. Заморозить эталон и измерения

До правок:

- pin текущий runner SHA;
- сохранить три replay fixtures: успешная карточка 07-reporting, scope-expansion 06-picking-list и
  browser/Docker blocker;
- собрать baseline: модельные вызовы, wall time, ручные вмешательства, rework count, accepted commits;
- определить target metrics.

Критерий завершения: существующие инциденты воспроизводимо прогоняются как controller fixtures без
реальных paid/model вызовов.

## Этап 1. Control plane без изменения ролей

Добавить рядом с runner:

- SQLite `runs/tasks/attempts`;
- lease/heartbeat по `run_id`;
- structured attempt status/failure class;
- claim-before-model-call;
- reconcile на restart;
- JSON `result` для текущих Markdown-артефактов;
- status command, читающий database, а не `pgrep`.

Старые роли и prompts пока остаются. Цель — сначала убрать потерю состояния и ручной resume, не
смешивая это с продуктовой реформой.

Обязательные tests:

1. kill до model call;
2. kill после file write;
3. kill после commit, до state update;
4. stale lease takeover;
5. второй controller не запускается;
6. restart не дублирует commit/model attempt.

Критерий завершения: один реальный старый-format `PATCH` переживает искусственное падение и
автоматически доезжает до прежней точки приёмки.

## Этап 2. Failure taxonomy и evidence

Ввести:

- enum классов из target design;
- централизованный retry policy;
- attempt manifest с SHA/command/exit/duration;
- Playwright `retain-on-failure`, screenshot/video/trace paths;
- один diagnostic rerun и отдельный `flaky` status;
- terminal blockers без удаления evidence.

Обязательные fixtures:

- Docker не стартовал;
- browser process crash до scenario;
- deterministic assertion failure;
- fail/pass flaky test;
- rate limit;
- unknown error.

Критерий завершения: ни один infra fixture не идёт в code repair; ни один deterministic test failure
не идёт в blind retry; `flaky` не становится clean.

## Этап 3. Короткий `PATCH` route

Это первый продуктовый эффект реформы.

Добавить:

- route classifier с machine features;
- `baseline.json`, `contract.json`, `scope.json` для delta;
- zone/file allowlist до Builder;
- два вызова: Builder и independent Verifier;
- controller-owned target checks, commit, push/evidence.

Пилот: одна реальная локальная правка существующего экрана. Желательно такой кейс, где текущий pipeline
создал бы mockup и полный UX-chain.

Критерии:

- не создано новых Product/UX/Architecture artifacts;
- не затронуты соседние зоны;
- не больше двух nominal model calls;
- branch pushed;
- browser evidence на том же SHA;
- owner не пропихивал стадии.

## Этап 4. `CHANGE` с purpose gate

Добавить Shaper и схемы:

- `purpose.json`;
- visible element traceability;
- `must_keep/affected_zones/non_goals`;
- prototype intent и fidelity decision;
- goal-based browser scenario;
- frozen findings + two-round repair.

Пилот: ограниченное изменение состава данных или действия одного существующего экрана, не 07-reporting
целиком.

Критерий: Verifier способен отклонить внутренне корректный экран, если goal-based task не решается,
и finding автоматически возвращается в один coherent repair.

## Этап 5. `MODULE` и first vertical slice

Только после успеха предыдущих этапов:

- owner-gate policy для необратимых решений;
- first-slice barrier;
- dependency/integration worktree;
- full regression on integration SHA;
- per-task partial completion report;
- optional deploy/live acceptance states.

Пилот должен быть небольшим новым модулем, а не новой волной из девяти связанных карточек.

Критерий: первый slice проходит целиком до дальнейшей нарезки; убийство controller восстанавливается;
интегрированный SHA опубликован; deploy, если разрешён, проверен по тому же SHA.

## Этап 6. Удалить лишние роли

Только после сравнения пилотов убрать из default paths:

- отдельные analyst/requirement-critic;
- обязательный ux-architect для любого visible change;
- tester/breaker/splitter как постоянные model stages;
- clicker как модельную роль;
- общий product-acceptor, блокирующий весь run.

Файлы старых ролей можно оставить как archive/replay reference до миграции всех fixtures. Удаление
раньше времени лишит нас сравнительной базы.

## Порядок Git-работы

Каждый этап — отдельная ветка и отдельный narяд, потому что это изменение самого процесса, а не экрана.
После каждого этапа:

1. review diff и controller tests;
2. replay fixtures;
3. один реальный canary task;
4. commit + push;
5. только затем следующий этап.

Нельзя смешивать в одном commit control-plane durability, новые product prompts и изменения UI WMS:
иначе при неудаче невозможно определить, что именно помогло или сломало run.

## Метрики пилота

| Метрика | Ожидание |
|---|---|
| model calls на PATCH | ≤ 2 nominal |
| model calls на CHANGE | ≤ 3 nominal |
| ручные технические вмешательства | 0 для известных failure fixtures |
| потерянные/несохранённые artifacts | 0 |
| scope violations, дошедшие до review | 0 |
| flaky, помеченные clean | 0 |
| accepted без pushed SHA | 0 |
| browser evidence с другим SHA | 0 |
| repeated identical repair signature | 0 после terminal policy |
| module expansion до принятого slice | 0 |

## Что делать с экраном 07-reporting

Не включать его redesign в реализацию pipeline. После появления `CHANGE` route его можно дать как
отдельную продуктовую задачу: перепроверить primary user/decision, выполнить goal-based scenarios и
только затем решить, требуется ли упрощение. Исследование pipeline само по себе не даёт разрешения
менять экран.
