# Целевой автономный pipeline WMS

Версия проекта: 1.0 research proposal, 2026-08-24.

## 1. Требуемое обещание системы

Вечером владелец передаёт обычный текст с одной или несколькими задачами. Pipeline должен:

1. сохранить текст дословно;
2. отделить независимые задачи и определить маршрут каждой;
3. до дорогой работы доказать пользовательскую цель и границу изменения в объёме, соразмерном
   задаче;
4. реализовать связный работающий результат в изолированной ветке;
5. самостоятельно пройти code/test/UI/browser gates;
6. ограниченно восстановиться после ожидаемых сбоев;
7. интегрировать совместимые задачи и проверить интегрированный SHA;
8. оставить утром либо принятый Git-результат, либо точный terminal blocker с evidence и сохранённым
   checkpoint.

«Автономный» не означает «имеет право придумать необратимый складской процесс». Неопределённость
является состоянием pipeline, а не приглашением добавить экран, обязанность оператора или финансовое
правило.

## 2. Что сознательно не строим

- отдельную распределённую платформу уровня Temporal/Kubernetes;
- постоянную организацию из 15–20 агентных ролей;
- универсальный визуальный workflow builder;
- новую систему задач вместо существующего Git/repo;
- автоматический merge в `main` или production deploy без разрешённой политики;
- высокодетализированный mockup для каждой правки;
- бесконечный self-improvement/Ralph loop;
- память, где ролевой отчёт считается доказанным состоянием.

Минимальный control plane: один Python controller, SQLite, Git worktrees, JSON Schema, существующие
CI/UI scripts и browser runner.

## 3. Три модельных ответственности вместо постоянных ролей

### 3.1. Shaper

Нужен только для `CHANGE` и `MODULE`. Отвечает за user outcome, scope, data/actions/states и low-fi
structure. Не пишет product code, не меняет pipeline, не принимает свою реализацию.

Модель:

- `MODULE` или новый домен/интеграция — Sol;
- существующий экран/поток с новым поведением — Terra;
- `PATCH` — Shaper не вызывается.

### 3.2. Builder

Один исполнитель реализует coherent vertical slice: необходимую связку backend/frontend/tests в
одном контексте, но только в machine allowlist. Он не меняет contract, scope или baseline.

Модель:

- простой `PATCH` — Luna;
- обычный `CHANGE` — Terra;
- `MODULE` slice либо сложный repair — Sol только если Terra не справился один раз или complexity
  policy назначила Sol заранее.

### 3.3. Verifier

Независимо читает frozen request, contract, final diff и raw evidence. Не редактирует product code.
Выдаёт структурированные findings; browser interaction выполняет инструмент/runner, а Verifier
оценивает результат. Для нового продуктового UI он обязан сам видеть живой экран или полный trace с
goal-based task; режим выбирается явно, а не подменяется молча.

Модель:

- обычное code/UI review — Terra;
- новый домен, финансы, остатки, маркировка либо спорный UX — Sol.

### 3.4. Что перестаёт быть агентом

| Старая роль | Новое исполнение |
|---|---|
| intake | детерминированный parser + одна проверка Lead/Shaper при неоднозначности |
| requirement-critic | JSON Schema + traceability gate + Verifier |
| solution-architect | режим Shaper только для `MODULE` |
| ux-architect | часть Shaper; отдельный проход только при реально новом UI flow |
| tester | test cases формируются Shaper/Builder, валидируются Verifier и runner |
| breaker | risk-based cases внутри Verifier, не постоянная стадия |
| splitter | controller строит 1–3 coherent slices из manifest; модель помогает только при сложном DAG |
| guard | скрипты policy-as-code |
| clicker | browser executor/Playwright, не принимающая роль |
| ui-critic | часть независимого Verifier после implementation |
| ux-judge | режим Verifier с live browser для risk UI |
| product-acceptor | вычисляемый controller report + owner review только спорных assumptions |

## 4. Маршруты, пропорциональные задаче

### 4.1. `PATCH`

Условия одновременно:

- существующий экран/endpoint/поведение;
- нет новых данных, действий, ролей, маршрутов, миграций или интеграций;
- одна зона экрана либо один локальный backend defect;
- ожидаемый результат задан явно или воспроизводится;
- allowlist обычно не больше 1–4 product files.

Путь:

```text
RECEIVED -> BASELINED -> SCOPED -> BUILD -> VERIFY -> ACCEPT -> PUBLISH
```

Нет Product, Architecture, UX и standalone mockup. Baseline является текущий экран/поведение.

### 4.2. `CHANGE`

Меняется состав данных или набор действий существующего flow, но не появляется новый домен.

```text
RECEIVED -> BASELINED -> SHAPE -> BUILD -> VERIFY -> ACCEPT -> PUBLISH
```

Один Shaper, один Builder, один Verifier. Prototype только если меняется понимание или основной path.

### 4.3. `MODULE`

Новый пользовательский flow, тип документа, marketplace, внешняя интеграция, финансовая/складская
семантика или несколько новых экранов.

```text
RECEIVED -> DISCOVER -> OWNER_GATE? -> SHAPE -> SLICE_1 -> VERIFY_1
         -> REMAINING_SLICES -> INTEGRATE -> ACCEPT -> PUBLISH
```

До расширения module обязателен первый живой vertical slice. Если он не принят, pipeline не запускает
остальные slices и не расходует ночь на масштабирование неверной модели.

### 4.4. `INCIDENT`

Включается только если владелец явно сообщает, что production горит. Scope — минимальное безопасное
восстановление, затем отдельный обычный `PATCH/CHANGE` для системной причины. Research не расширяет
полномочия deploy/secret management.

## 5. Входной handshake перед ночью

Наиболее дешёвый способ не фантазировать восемь часов — один короткий preflight сразу после диктовки.
Controller за 1–3 минуты создаёт сводку:

```text
Задач: 4
PATCH: 2 — можно запускать
CHANGE: 1 — допущения обратимы, можно запускать
MODULE: 1 — нужно решение по модели тарификации
```

Владелец может ответить один раз. Если ушёл:

- `PATCH` исполняются;
- `CHANGE` исполняется только с обратимыми assumptions и явным списоком;
- `MODULE` строит discovery/shape и первый reversible slice, но не вводит необратимую бизнес-
  семантику;
- карточка с `OWNER_DECISION` паркуется, независимые продолжают работу.

Owner gate обязателен только для:

- нового денежного/тарифного правила;
- необратимой миграции/удаления данных;
- новой обязанности оператора или физического процесса;
- внешнего юридического/marketplace contract;
- доступа/секрета/deploy authority;
- двух вариантов с существенно разными пользовательскими последствиями.

Название колонки, выбор существующего UI-kit, формат внутренней функции или индекс БД не являются
owner decision.

## 6. Источник истины: SQLite и append-only evidence

### 6.1. Таблицы

`runs`:

```sql
run_id TEXT PRIMARY KEY,
workflow_version TEXT NOT NULL,
request_path TEXT NOT NULL,
base_sha TEXT NOT NULL,
status TEXT NOT NULL,
started_at TEXT NOT NULL,
finished_at TEXT,
budget_limit INTEGER,
budget_used INTEGER NOT NULL DEFAULT 0
```

`tasks`:

```sql
task_id TEXT PRIMARY KEY,
run_id TEXT NOT NULL,
route TEXT NOT NULL,              -- PATCH | CHANGE | MODULE | INCIDENT
state TEXT NOT NULL,
state_version INTEGER NOT NULL,
branch TEXT,
worktree TEXT,
base_sha TEXT,
head_sha TEXT,
contract_hash TEXT,
scope_hash TEXT,
retry_count INTEGER NOT NULL DEFAULT 0,
rework_count INTEGER NOT NULL DEFAULT 0,
blocked_reason TEXT
```

`attempts`:

```sql
attempt_id TEXT PRIMARY KEY,
task_id TEXT NOT NULL,
stage TEXT NOT NULL,
input_hash TEXT NOT NULL,
executor TEXT NOT NULL,
model TEXT,
started_at TEXT NOT NULL,
finished_at TEXT,
exit_code INTEGER,
status TEXT NOT NULL,
failure_class TEXT,
failure_signature TEXT,
stdout_path TEXT,
stderr_path TEXT,
evidence_manifest_path TEXT,
output_hash TEXT
```

### 6.2. Транзакционная граница

Перед побочным эффектом controller создаёт attempt со статусом `STARTED`. После команды он сначала
сохраняет raw output/evidence, затем сверяет Git/files, и только одной SQLite transaction переводит
attempt в terminal state и task — в следующую стадию.

При restart записи `STARTED` reconciled:

1. проверить процесс;
2. проверить worktree/HEAD;
3. проверить ожидаемый artifact/hash;
4. если side effect уже завершён — зафиксировать success без повторения;
5. если не начинался — безопасно retry;
6. если результат частичный — сохранить evidence и route в repair/blocked.

Это защищает от повторного commit/push/test после падения controller.

## 7. Файлы run

```text
night/runs/<run-id>/
  request.raw.md
  run.json
  tasks/<task-id>/
    request.json
    baseline.json
    purpose.json          # CHANGE/MODULE
    contract.json
    scope.json
    test-plan.json
    findings.json
    result.json
    attempts/<attempt-id>/
      stdout.log
      stderr.log
      junit.xml
      playwright-report/
      trace.zip
      screenshots/
      evidence.json
```

Human-readable Markdown генерируется из JSON для утреннего отчёта. Markdown не управляет состоянием.

## 8. Схемы основных артефактов

### 8.1. `request.json`

```json
{
  "task_id": "07-reporting",
  "verbatim_ranges": [{"file": "request.raw.md", "start": 112, "end": 124}],
  "summary": "Раздел отчётности для селлера и ФФ",
  "route": "MODULE",
  "route_reasons": ["new_screen", "new_reporting_api", "two_user_roles"],
  "candidate_screens": ["S-33"],
  "risk_flags": ["inventory_semantics", "multi_role_ui"],
  "unknowns": []
}
```

### 8.2. `purpose.json`

```json
{
  "primary_user": "оператор ФФ, контролирующий складской поток",
  "trigger": "нужно понять состояние и движение товара за период",
  "primary_decision": "обнаружить, где остаток или поток требует разбирательства",
  "secondary_questions": [
    "какой остаток сейчас",
    "сколько пришло и ушло",
    "какие товары дали изменение"
  ],
  "evidence": [
    {"type": "owner_quote", "ref": "request.raw.md#L112"},
    {"type": "existing_process", "ref": "frontend/src/App.tsx"}
  ],
  "assumptions": [
    {"id": "A-1", "text": "ФФ и селлер имеют один главный вопрос", "reversible": false}
  ],
  "success_observation": "пользователь без подсказки находит ответ на заданный складской вопрос",
  "non_goals": ["финансы", "стоимость хранения", "изменение остатков"]
}
```

Нереверсивное assumption `A-1` не может автоматически перейти дальше без evidence либо owner gate.

### 8.3. `contract.json`

```json
{
  "input_hash": "sha256:...",
  "route": "CHANGE",
  "screens": [{
    "id": "S-16",
    "affected_zones": ["table.columns"],
    "must_keep": ["header", "filters", "row_actions", "print_flow"],
    "elements": [{
      "id": "E-1",
      "kind": "column",
      "label": "Короб",
      "required_by": "request:R-2",
      "user_decision": "понять, в какой таре лежит товар"
    }]
  }],
  "api": {"changed": false},
  "data": {"changed": false},
  "states": ["normal", "empty", "loading", "error"],
  "acceptance_cases": ["TC-S16-BOX-01"],
  "non_goals": ["редизайн каталога", "новая навигация"]
}
```

Каждый видимый элемент имеет `required_by` и `user_decision`. Controller отклоняет элемент без связи.

### 8.4. `scope.json`

```json
{
  "base_sha": "...",
  "allowed_existing_files": [
    "frontend/src/screens/v2/FfProductsCatalogScreen.tsx",
    "frontend/tests-e2e/catalog-boxes.spec.ts"
  ],
  "allowed_new_globs": [],
  "forbidden_zones": ["frontend/src/App.tsx", "frontend/src/ui-kit/**"],
  "max_product_files": 2,
  "max_added_lines": 180,
  "max_deleted_lines": 80
}
```

Line limits — tripwire, а не автоматический quality verdict. Превышение требует нового scope decision,
а не скрытого продолжения.

### 8.5. `findings.json`

```json
{
  "input_sha": "...",
  "verdict": "fail",
  "findings": [{
    "id": "F-1",
    "class": "behavior",
    "severity": "stop",
    "requirement_ref": "contract:E-1",
    "evidence_ref": "attempts/a17/trace.zip#action-23",
    "affected_files": ["frontend/src/..."],
    "expected": "...",
    "observed": "..."
  }]
}
```

Repair получает frozen finding IDs. Новый scope нельзя добавлять под видом исправления.

## 9. Состояния и переходы

| State | Кто/что работает | Условие перехода | Следующее состояние |
|---|---|---|---|
| `RECEIVED` | controller | raw request сохранён, checksum есть | `CLASSIFY` |
| `CLASSIFY` | rules + Terra при неоднозначности | route schema valid | `BASELINE` |
| `BASELINE` | code/browser tools | base SHA, files/screens/current behavior captured | `SCOPE` или `DISCOVER` |
| `DISCOVER` | Shaper | purpose evidence valid | `OWNER_GATE` или `SCOPE` |
| `OWNER_GATE` | owner | decision recorded | `SCOPE`; без ответа — card paused |
| `SCOPE` | Shaper/controller | contract traceability + allowlist valid | `BUILD` |
| `BUILD` | Builder | diff within scope, target tests, checkpoint commit | `VERIFY_CODE` |
| `VERIFY_CODE` | scripts + Verifier | review/tests pass | `VERIFY_UI` или `INTEGRATE` |
| `VERIFY_UI` | browser runner + Verifier | required goal-based cases and invariants pass | `INTEGRATE` |
| `REPAIR` | Builder | frozen findings closed, new commit | вернуться к затронутому verify state |
| `INTEGRATE` | controller | branch rebased/merged in integration worktree, conflicts resolved by policy | `REGRESSION` |
| `REGRESSION` | CI scripts | full applicable suite pass on integrated SHA | `PUBLISH` |
| `PUBLISH` | Git controller | branch pushed/upstream verified | `DEPLOY` или `ACCEPTED` |
| `DEPLOY` | deploy workflow | deployed SHA equals candidate SHA and health pass | `LIVE_ACCEPT` |
| `LIVE_ACCEPT` | browser runner/Verifier | same cases pass on deployed SHA | `ACCEPTED` |
| `ACCEPTED` | controller | result.json complete | terminal success |
| `BLOCKED_*` | controller | terminal reason + evidence + checkpoint | terminal blocked |

Любой transition проверяет `input_hash`: старый verdict не может принять новый diff.

## 10. Machine gates по стадиям

### 10.1. До Build

- request quotes полностью покрывают исходник;
- route enum и причины валидны;
- baseline SHA существует;
- affected screen IDs есть в registry;
- `purpose.json` обязателен для `CHANGE/MODULE`;
- каждый contract element имеет requirement/outcome trace;
- non-goals и `must_keep` не пусты для существующего экрана;
- scope paths существуют либо разрешены как new glob;
- новый route имеет behavior test plan;
- destructive migration/secret/deploy flag создаёт explicit authorization gate.

### 10.2. После Build

- diff не выходит из `scope.json`;
- contract/process files не переписаны Builder;
- существующие regression tests не ослаблены без отдельного verifier finding;
- target tests реально выполнены controller, а не только записаны в `DEV.md`;
- commit существует, worktree implementation-clean;
- output SHA записан в attempt.

### 10.3. Перед Accepted

- независимый Verifier читал final SHA;
- все `stop`/`behavior` findings закрыты новым evidence;
- browser evidence относится к final/integrated SHA;
- `flaky` не приравнен к clean pass;
- branch pushed и upstream SHA совпадает;
- если deploy входил в scope, deployed SHA совпадает;
- full required checks green on the same SHA.

## 11. Failure taxonomy и точная recovery policy

| Failure class | Как определяется | Retry | После исчерпания |
|---|---|---:|---|
| `MODEL_RATE_LIMIT` | известный provider code | 2, 30s/120s+jitter | `BLOCKED_PROVIDER` |
| `MODEL_PROCESS_CRASH` | nonzero/timeout, no committed side effect | 1 после reconcile | `BLOCKED_EXECUTOR` |
| `ENV_PRESTART` | main test/agent process не стартовал | 2 recreate | `BLOCKED_ENV` |
| `ENV_RUNTIME_CRASH` | процесс стартовал, environment умер | 1 clean recreate с evidence | `BLOCKED_ENV` |
| `ARTIFACT_SCHEMA` | JSON Schema invalid | 1 same-stage correction | `BLOCKED_PROTOCOL` |
| `SCOPE_VIOLATION` | path/diff exceeds manifest | 0 automatic same attempt; discard owned uncommitted diff, rerun Builder once with feedback | second → `BLOCKED_SCOPE` |
| `TEST_ASSERTION` | deterministic assertion repeats | 0 infra retry; `REPAIR` | 2 repairs → `BLOCKED_REWORK` |
| `TEST_FLAKY` | fail then pass on clean identical SHA | no green promotion | `BLOCKED_FLAKY` or quarantine by explicit policy |
| `REVIEW_FINDING` | structured verifier finding | 1 coherent repair + 1 escalated repair | `BLOCKED_REWORK` |
| `BROWSER_TOOL_LIMIT` | automation cannot operate control, app otherwise alive | one alternate deterministic runner | `BLOCKED_EVIDENCE` |
| `OWNER_DECISION` | irreversible product field unresolved | no retry | `WAITING_OWNER` |
| `BUDGET` | hard cap reached | no retry | `BLOCKED_BUDGET` |
| `UNKNOWN` | signature unclassified | no blind retry | `BLOCKED_UNKNOWN` |

Retry принадлежит controller. Ни Builder, ни Verifier не увеличивают лимит самостоятельно.

## 12. Git lifecycle

1. Run фиксирует `base_sha` и проверяет его существование.
2. Каждая task создаёт `codex/run-<id>/<task-id>` в отдельном worktree.
3. Shaping artifacts коммитятся отдельно до product code.
4. Builder делает один commit на coherent slice; внутренние checkpoint допустимы, но утром история
   может быть squashable только отдельной политикой.
5. Repair commit содержит finding IDs.
6. Controller создаёт integration worktree от целевой base branch и последовательно применяет
   принятые commits по dependency order.
7. Regression и browser acceptance идут на integration SHA.
8. Branch push проверяется `rev-parse @{upstream}`.
9. Merge в main не выполняется без отдельной политики/разрешения. Статус остаётся `PUBLISHED`, а не
   `DONE_MAIN`, если merge не входил в authority.

Никакой `git add -A`. Только manifest paths. Pipeline-owned worktree может восстановить незакоммиченный
diff после scope failure из last checkpoint, но сначала сохраняет patch и evidence в attempt directory.

## 13. Test strategy

### На Builder

Только target tests и дешёвые guards. Команды выбирает controller из change map; Builder может
предложить дополнительные, но не объявляет их результат источником истины.

### На task verification

- target unit/API tests;
- contract test на изменённый response format;
- соседние regression cases из impact map;
- frontend type/build для затронутого workspace;
- UI guard/invariants.

### На integration SHA

- полный применимый backend suite;
- frontend build;
- risk-selected E2E;
- migration checks;
- cross-task tests.

### Flaky policy

Первый failure сохраняется. Один rerun на чистом worker с тем же SHA — только диагностика:

- fail/fail одинаково → deterministic;
- fail/pass → flaky;
- разные failures → unstable/unknown.

`flaky` не выпускается как clean. Временный quarantine возможен только для заранее известного test ID
с владельцем и сроком, не по решению ночного агента.

## 14. Product/design gate

### Для нового модуля

Shaper обязан сначала создать low-fidelity `purpose + elements` модель, не HTML-полотно:

```text
USER: кто
TRIGGER: когда открыл
PRIMARY DECISION: один главный вопрос
FACTS: что нужно увидеть
ACTIONS: что реально делает
SEQUENCE: в каком порядке
ERROR/EMPTY: что мешает
NO-GOS: чего нет
EVIDENCE: почему это не фантазия
```

Только после этого выбирается prototype fidelity. Если вопрос только о составе данных, достаточно
табличной структуры. Если неизвестна навигация/flow — интерактивный prototype. Production-like HTML
не является обязательным форматом.

### Для локальной правки

Baseline screenshot/DOM + annotation:

```text
ZONE: table.column.box
BEFORE: короб не виден
AFTER: колонка показывает barcode грузоместа
KEEP: все остальные колонки, фильтры, row action, print flow
FILES: два
```

Любая новая зона переводит task из `PATCH` в `CHANGE` и требует нового scope, а не молчаливого
расширения.

## 15. Browser acceptance

Есть два разных типа кейсов:

### Prescribed case

Проверяет механику: открыть экран, выбрать значение, нажать действие, получить ожидаемый state.

### Goal-based case

Проверяет понимание: Verifier получает пользовательский вопрос, но не инструкцию, какой control
нажать. Он должен найти ответ и записать interpretation. Для нового отчёта/модуля обязателен хотя бы
один goal-based case.

Пример для «Остатки и движения»:

> На каком товаре расход за выбранный месяц вырос сильнее всего и на каком складе это произошло?

Если интерфейс содержит данные, но проверяющий не может без объяснения найти и правильно истолковать
ответ, product acceptance красный, даже когда Playwright selectors зелёные.

## 16. Конкретные prompts

Prompts хранятся версионированными файлами и получают JSON inputs. Ни один prompt не объясняет
controller, какой переход сделать.

### 16.1. Shaper

```text
Ты формируешь минимальный контракт задачи WMS. Не пишешь product code и не проектируешь
экран до доказанной пользовательской цели.

Входы:
- request.json и дословные цитаты;
- baseline.json: существующие экраны, данные и поведение;
- route: PATCH | CHANGE | MODULE;
- политика необратимых решений;

Выходы: purpose.json (если требуется), contract.json, scope-candidate.json,
test-plan.json. Все обязаны пройти приложенные JSON Schema.

Правила:
1. Назови одного primary user и одно primary decision. Для второй роли либо докажи тот же
   вопрос evidence, либо раздели interface contract.
2. Каждое поле, колонка, действие и блок получает required_by и user_decision.
3. Мнение без owner quote, observed process, analytics или current code пометь assumption.
4. Нереверсивное assumption не закрывай сам: status=owner_decision.
5. Для существующего экрана сначала зафиксируй must_keep и affected_zones. Не добавляй
   соседнюю зону ради улучшения.
6. Выбирай smallest solution. Идеи вне границы идут в non_goals, не в contract.
7. Prototype определи только как ответ на конкретный design question и выбери минимальную
   достаточную fidelity.
8. Не меняй UI-kit, routes, data model или external integration, если этого не требует
   прослеживаемый contract item.

Перед сдачей проверь: может ли незнакомый пользователь выполнить goal-based acceptance
scenario без знания твоего замысла. Не утверждай, что может; только сформулируй сценарий.
```

### 16.2. Builder

```text
Ты реализуешь один coherent vertical slice WMS. Product decisions уже заморожены.

Входы:
- request.json, contract.json, scope.json, test-plan.json;
- exact worktree, base SHA и current HEAD;
- при repair: frozen findings.json.

Полномочия:
- менять только paths/globs из scope.json;
- запускать target commands;
- создавать product code/tests, требуемые contract items.

Запрещено:
- менять contract, purpose, scope, workflow, baseline и verdict;
- ослаблять существующий regression test ради зелёного результата;
- добавлять экран, route, колонку, действие, UI-kit primitive или операторский шаг без
  contract item;
- исправлять соседние дефекты;
- commit/push/deploy вручную: этим владеет controller.

Порядок:
1. Сверь каждый intended file с scope.
2. Реализуй весь slice, сохраняя must_keep.
3. Добавь/измени behavior tests. Если существующий test должен измениться, объясни связь с
   contract item в machine output.
4. Запусти target checks, но считай их предварительными: controller повторит сам.
5. Верни только build-result.json по schema и краткий human note.

Если contract физически невыполним в scope, status=scope_insufficient с точными paths и
причиной. Не расширяй scope сам.
```

### 16.3. Verifier

```text
Ты независимый проверяющий. Ты не писал contract и code. Product code редактировать нельзя.

Входы:
- дословный request;
- purpose.json, contract.json, scope.json;
- final diff base_sha..candidate_sha;
- raw test/browser evidence с attempt IDs;
- baseline для затронутых зон.

Проверь по порядку:
1. Решена ли дословная просьба, а не только внутренний contract.
2. Каждый diff path и visible element прослеживается к contract.
3. Must_keep действительно сохранён; нет скрытого redesign.
4. Tests проверяют поведение и не стали слабее. Сопоставь claims с raw result.
5. Ошибки, пустота и partial failure не выдают старые/нулевые данные за свежие.
6. Для UI просмотри живой candidate SHA и выполни назначенные cases. Для нового
   аналитического экрана обязательно выполни goal-based case без подсказки controls.
7. Каждая finding содержит ID, class, severity, requirement/evidence refs, expected,
   observed и affected files.

Не предлагай соседние улучшения. Не объединяй отсутствие evidence с code defect:
используй class=evidence или environment. Верни findings.json по schema.
```

## 17. Логика выбора модели

Модель выбирает controller по risk flags, а не роль сама повышает себе класс:

```text
Luna: локальный builder, browser executor, deterministic summarization
Terra: обычный shaping, builder, independent review, research extraction
Sol: новый домен/integration, financial/inventory invariant, final disputed UX,
     одна escalated repair после Terra failure
```

Повышение модели не сбрасывает rework counter и не разрешает новый scope.

## 18. Budget и loop policy

На task заранее задаются:

- max model calls;
- max wall time;
- max rework = 2;
- max environment restarts = 2;
- max transient retries = 2;
- max changed files/lines tripwire;
- max browser attempts = 2;
- model escalation count = 1.

Budget — control-plane policy. Shaper может предложить уменьшить scope, но не увеличить лимит.
При hard cap pipeline сохраняет checkpoint/evidence и завершает `BLOCKED_BUDGET`.

Ориентировочные вызовы:

| Route | Номинальные модельные вызовы |
|---|---:|
| PATCH | Builder + Verifier = 2 |
| CHANGE | Shaper + Builder + Verifier = 3 |
| MODULE first slice | Shaper + Builder + Verifier = 3, иногда 4 с architecture research |
| Repair | +1 Builder, тот же Verifier на frozen findings |

Это вместо 16–21 вызова на одну доменную карточку текущего pipeline.

## 19. Утренний отчёт

Controller генерирует его из state/evidence:

```text
Run: 2026-08-24-night-01
Принято: 3/4

07-reporting — BLOCKED_OWNER
  Нужное решение: общий ли главный вопрос у ФФ и селлера
  Выполнено: purpose, baseline, два low-fi варианта
  Code: не начинался

catalog-box — ACCEPTED
  Request -> contract: 4/4 items
  Candidate SHA: ...
  Pushed: origin/...
  Integrated SHA: ...
  Tests: clean
  Browser: 3 prescribed + 1 goal-based, clean
  Deploy: не входил в задачу
```

Нельзя писать одно слово «готово», если цепочка завершилась только commit или локальным браузером.

## 20. Критерий, что target pipeline действительно заработал

Не количество документов и не self-test runner. Нужен пилот из трёх реальных задач:

1. локальный `PATCH` — доказать короткий путь без mockup и redesign;
2. `CHANGE` существующего экрана — доказать purpose/delta/scope и browser evidence;
3. небольшой `MODULE` — доказать first vertical slice, recovery после искусственно убитого controller
   и интеграцию.

Пилот принят, если:

- controller автоматически возобновился после process kill;
- scope violation остановлена до review;
- flaky test не стал clean;
- negative finding автоматически ушёл в один bounded repair;
- все accepted результаты имеют pushed SHA;
- browser evidence относится к integrated SHA;
- ни одна карточка не потребовала ручного «пропихивания» обычного технического сбоя;
- owner был нужен только на заранее определённом substantive gate.
