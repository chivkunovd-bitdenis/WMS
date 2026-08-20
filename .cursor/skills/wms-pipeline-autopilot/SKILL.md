---
name: wms-pipeline-autopilot
description: >-
  Запуск полного Pipeline v2 цикла WMS через controller:
  open/classify/hold/resume/next/packet/advance/status/validate/close,
  с разделением Dispatcher, BA, Product, Dev, Reviewer и Browser Product ролей.
---

# WMS Pipeline Autopilot

## Когда использовать

Используй этот skill для любой задачи WMS, которую нужно провести через Pipeline v2: баг, UI,
backend, warehouse process, FBS/FBO/WB/Ozon, печать, worker, database, mobile, release-пакет или
pipeline change.

Skill не даёт права обходить Product gate, делать deploy, менять секреты или редактировать runtime
state руками.

## Источники перед стартом

1. Проверь путь: Git-root WMS или worktree внутри `/Users/deniscivkunov/Projects/WMS/.worktrees/`.
2. Прочитай `AGENTS.md`.
3. Прочитай `docs/process/PIPELINE-RU.md`.
4. Прочитай `pipeline/pipeline.yml`.
5. Для команд смотри `pipeline/controller.py`; запускать их нужно через wrapper
   `python3 scripts/pipeline/run.py ...`.

Пока `pipeline/pipeline.yml` не содержит `status: "ACTIVE"`, нельзя ставить `DONE` и нельзя
называть Pipeline v2 полностью активированным. Нормальная цель разработки до release — честный
controller status вроде `IMPLEMENTATION_DONE` или `READY_FOR_RELEASE`, если эти стадии реально
пройдены.

## Полный цикл

### 1. Open

Dispatcher сохраняет исходную просьбу и первичные traits:

```bash
python3 scripts/pipeline/run.py open \
  --source "<дословная просьба владельца>" \
  --traits "bug,ui_change" \
  --risk-level medium \
  --owner-agent pipeline-dispatcher
```

Затем dispatcher закрывает S01 intake receipt, только если `next` показывает S01:

```bash
python3 scripts/pipeline/run.py next --task-id <TASK-ID>
python3 scripts/pipeline/run.py advance \
  --task-id <TASK-ID> \
  --stage S01 \
  --verdict TASK_INTAKE_READY \
  --role pipeline-dispatcher \
  --agent <agent-id>
```

Traits берутся из `pipeline/pipeline.yml`: `bug`, `ui_change`, `process_change`,
`external_contract`, `new_domain`, `new_module`, `database_change`, `background_worker`, `print`,
`mobile_contract`, `tenant_sensitive`, `release_change`, `emergency`, `pipeline_change`.

### 2. Classify

Если impact уточнился, Dispatcher переклассифицирует задачу:

```bash
python3 scripts/pipeline/run.py classify \
  --task-id <TASK-ID> \
  --traits "bug,ui_change,print" \
  --risk-level high
```

После классификации dispatcher закрывает S02 impact receipt, только если `next` показывает S02:

```bash
python3 scripts/pipeline/run.py next --task-id <TASK-ID>
python3 scripts/pipeline/run.py advance \
  --task-id <TASK-ID> \
  --stage S02 \
  --verdict IMPACT_CLASSIFIED \
  --role pipeline-dispatcher \
  --agent <agent-id>
```

Не занижай traits ради короткого маршрута. `risk-level` должен отражать деньги, данные, tenant
isolation, необратимые внешние записи, миграции и размер складского процесса.

### 3. Next и packet

Перед каждым агентом:

```bash
python3 scripts/pipeline/run.py status --task-id <TASK-ID>
python3 scripts/pipeline/run.py next --task-id <TASK-ID>
python3 scripts/pipeline/run.py packet --task-id <TASK-ID>
```

`next` показывает первый missing stage и роль. Если роль не твоя, остановись и передай packet
нужному агенту. Агент не выполняет чужую стадию и не принимает собственный результат.
Если `status` или `next` показывает `WAITING`, нельзя вызывать `advance`: верни blocker и
resume condition владельцу и жди явного `resume`.

Удержание и снятие удержания:

```bash
python3 scripts/pipeline/run.py hold \
  --task-id <TASK-ID> \
  --blocker-type OWNER_INPUT \
  --reason-code <CODE> \
  --reason "<причина>" \
  --resume-condition "<условие снятия>"

python3 scripts/pipeline/run.py resume --task-id <TASK-ID> --by owner
```

### 4. BA stages

`pipeline-ba` делает S08/S12/S15 пакет:

- S08 behavior contract: actor, screen/process, current → target, states, data, side effects,
  invariants, out-of-scope, oracle.
- S12 cards: вертикальные атомарные карточки с наблюдаемым складским результатом.
- S15 cases: direct + breaker cases и coverage matrix requirement → card → case → oracle →
  planned executor.

После завершения stage:

```bash
python3 scripts/pipeline/run.py advance \
  --task-id <TASK-ID> \
  --stage S08 \
  --verdict BEHAVIOR_CONTRACT_READY \
  --role pipeline-ba \
  --agent <agent-id>
```

Для S12 используй `TASK_CUT_READY`, для S15 — `CASES_READY` с отдельной записью `CASE_AUDIT_PASSED`
в human artifact, пока controller принимает один pass verdict.

### 5. Product before dev

`pipeline-product` принимает S11 и S16 до разработки:

```bash
python3 scripts/pipeline/run.py advance \
  --task-id <TASK-ID> \
  --stage S11 \
  --verdict PRODUCT_CONTRACT_APPROVED \
  --role pipeline-product \
  --agent <agent-id>

python3 scripts/pipeline/run.py advance \
  --task-id <TASK-ID> \
  --stage S16 \
  --verdict PRODUCT_APPROVED_FOR_DEV \
  --role pipeline-product \
  --agent <agent-id>
```

Product проверяет warehouse rationale, operator flow, exact card package и cases. Он не пишет код
и не заменяет S25.

### 6. Dev

`pipeline-dev` начинает только после `PRODUCT_APPROVED_FOR_DEV` и workspace stage. Он реализует одну
approved card, добавляет релевантные тесты, делает scoped commit и только потом сдаёт S18:

```bash
python3 scripts/pipeline/run.py advance \
  --task-id <TASK-ID> \
  --stage S18 \
  --verdict DEV_DONE \
  --role pipeline-dev \
  --agent <agent-id>
```

Без commit SHA и проверенного diff `DEV_DONE` запрещён.

### 7. Reviewer

`pipeline-reviewer` делает S20. Он ищет defects типов `CONTRACT`, `PLAN`, `IMPLEMENTATION`,
`AUTOMATION`, `MIGRATION` и возвращает в owning stage. Product он не принимает.

```bash
python3 scripts/pipeline/run.py advance \
  --task-id <TASK-ID> \
  --stage S20 \
  --verdict CODE_REVIEW_PASSED \
  --role pipeline-reviewer \
  --agent <agent-id>
```

### 8. Browser Product

`pipeline-browser-product` делает S25 только в живой видимой вкладке. Playwright, API, screenshot,
curl и чтение кода не засчитываются.

Human verdict для operator flow — `PRODUCT_BROWSER_APPROVED`, но controller pass verdict для S25:

```bash
python3 scripts/pipeline/run.py advance \
  --task-id <TASK-ID> \
  --stage S25 \
  --verdict FINAL_ACCEPTANCE_APPROVED \
  --role pipeline-browser-product \
  --agent <agent-id>
```

В evidence обязательно: URL, exact SHA/artifact если доступен, роль, tenant, данные, клики/сканы,
visible success/error/empty/forbidden, read-back/reload и acceptance matrix.

### 9. Validate и close

Проверить state:

```bash
python3 scripts/pipeline/run.py validate --task-id <TASK-ID>
```

Закрывать можно только тем статусом, который разрешён текущим controller:

```bash
python3 scripts/pipeline/run.py close --task-id <TASK-ID> --status IMPLEMENTATION_DONE
python3 scripts/pipeline/run.py close --task-id <TASK-ID> --status READY_FOR_RELEASE
python3 scripts/pipeline/run.py close --task-id <TASK-ID> --status CANCELLED
```

`DONE` запрещён до `ACTIVE`, разрешённого exact-SHA deploy и production trace.

## Жёсткие запреты

- Не редактировать `.pipeline-state/**`, `tasks/*/state.json` и receipts руками.
- Не писать pass verdict до того, как `next` показывает нужный stage.
- Не совмещать несовместимые роли: Dev не reviewer, не Product и не Browser Product.
- Не менять секреты, deploy, production runtime или внешний кабинет ключей.
- Не объявлять «готово» без commit SHA, branch/status, controller receipts и честного уровня
  завершения.
