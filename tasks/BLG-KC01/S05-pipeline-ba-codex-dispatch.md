# WMS Pipeline Dispatch

Executor: `codex`
Task: `BLG-KC01`
Stage: `S05`
Role: `pipeline-ba`
Recommended model: `gpt-5.6-terra` (`moderate`)

## Read First

- `.codex/skills/wms-pipeline-autopilot/SKILL.md`
- `AGENTS.md`
- `docs/process/PIPELINE-RU.md`
- `pipeline/pipeline.yml`
- `pipeline/model-policy.yml`
- `pipeline/budget-policy.yml`
- `tasks/BLG-KC01/state.json`

## Executor Rules

- Use .codex/skills/wms-pipeline-autopilot/SKILL.md if present; otherwise read AGENTS.md directly.
- If the user explicitly allowed multi-agents, spawn a worker only for this role and disjoint scope.
- Tell subagents not to push unless the owner explicitly asks for that.
- Do not fix bugs unless this exact stage and role authorize implementation.
- If packet status is `WAITING`, stop after the required start checks and report the blocker.
- Do not set `DONE` while `pipeline/pipeline.yml` status is not `ACTIVE`.
- Do not touch secrets, live deploy, or live WB/Ozon.

## Model Policy

Policy: `pipeline/model-policy.yml`
Tier: `moderate`
Recommended model: `gpt-5.6-terra`

Reasons:
- stage S05 / role pipeline-ba default tier is moderate

Rules:
- Do not upgrade above the recommendation unless the packet, owner, or fresh evidence shows a higher-risk class.
- Do not downgrade product, research, architecture, review or Product Browser stages.
- Simple implementation defaults to cheap; dangerous implementation escalates to moderate, not automatically to expensive.
- If the executor cannot select the exact named model, use the cheapest available equivalent at the same tier.

## Budget Policy

Policy: `pipeline/budget-policy.yml`
Stage tier budget: `1.25 USD` / `600000` tokens
Task budget: `8.0 USD` / `2500000` tokens
Wave budget: `35.0 USD` / `12000000` tokens
Hard stop: `True`; reason code `BUDGET_HARD_STOP`
Owner override marker: `PIPELINE_BUDGET_OVERRIDE: owner-approved`
Usage receipt fields: `task_id`, `stage`, `role`, `executor`, `model`, `tier`, `input_tokens`, `output_tokens`, `estimated_usd`, `agent_id`, `recorded_at`

Rules:
- Dispatcher includes the stage budget in every handoff prompt.
- A stage that reaches warning_ratio reports usage in its receipt.
- A stage that reaches hard_stop_ratio must stop and request owner override before more expensive work.
- Product, research, architecture, review and browser stages remain expensive when model-policy says so; budget pressure cannot downgrade judgment gates.

## Controller Packet

```json
{
  "task_id": "BLG-KC01",
  "stage": "S05",
  "role": "pipeline-ba",
  "status": "RUNNING",
  "traits": [
    "process_change"
  ],
  "risk_level": "medium",
  "model_policy": "pipeline/model-policy.yml",
  "required_stages": [
    "S01",
    "S02",
    "S05",
    "S06",
    "S07",
    "S11",
    "S12",
    "S15",
    "S16",
    "S17",
    "S18",
    "S19",
    "S20",
    "S21",
    "S22",
    "S23",
    "S26"
  ],
  "done_stages": [
    "S01",
    "S02"
  ],
  "worktree": "/Users/deniscivkunov/Projects/WMS/.worktrees/pipeline-unified-v2",
  "branch": "codex/wms-pipeline-unified-v2-20260820",
  "base_sha": "69c271678782d7dcfa39df97cd905cbee1678727",
  "wave_id": "wave-a1b311d18f07",
  "backlog_item_id": "BLG-KC01",
  "backlog_item": {
    "id": "BLG-KC01",
    "title": "Развернуть клиентские входящие по приёмке, навигации, остаткам, отгрузке и печати",
    "source_section": "клиентский список 1-14",
    "business_meaning": "Эта карточка объединяет четырнадцать отдельных требований клиента к повседневной работе приёмки, складов, отгрузки, навигации и печати. Их нельзя отдавать разработчику одной большой задачей, потому что у каждого пункта свой экран, бизнес-результат, риск и способ проверки. Product и бизнес-аналитик должны сначала превратить каждый client_item ниже в отдельную атомарную карточку с контрактом поведения и тест-кейсами, не потеряв ни одного исходного требования.",
    "client_items": [
      {
        "id": "KC-01",
        "title": "Красные бейджи входящих документов от селлера",
        "business_meaning": "В общих списках фулфилмент сейчас не видит сразу, какие документы приёмки и отгрузки недавно созданы селлером и какие из них требуют реакции. Рядом с такими входящими документами должны появляться красные цифры или единички, чтобы сотрудник ФФ замечал новую работу без ручного просмотра каждого раздела. Это именно счётчик новых или требующих внимания документов от селлера, а не показатель брака, расхождений или количества товаров."
      },
      {
        "id": "KC-02",
        "title": "Счётчик приёмки по коробам",
        "business_meaning": "Во время приёмки оператору важно понимать не только количество товарных строк, но и сколько физических коробов заявлено и уже принято. Без такого счётчика нельзя быстро оценить прогресс и заметить, что один из коробов ещё не обработан. Экран приёмки должен показывать понятное соотношение принятых и ожидаемых коробов и обновлять его после каждого подтверждённого действия."
      },
      {
        "id": "KC-03",
        "title": "Выбор склада на приёмке",
        "business_meaning": "При приёмке товара система должна понимать, на какой физический склад поступает остаток, иначе дальнейший учёт и отгрузка становятся недостоверными. Если у организации несколько складов, оператору нужно дать ясный выбор только из доступных рабочих складов и сохранить его в результате приёмки. Если реальный склад один, система должна выбрать его автоматически и не заставлять оператора каждый раз подтверждать очевидное значение."
      },
      {
        "id": "KC-04",
        "title": "Клик по логотипу ведёт на главную",
        "business_meaning": "Оператор часто переходит между глубокими рабочими экранами и должен быстро возвращаться к началу системы. Сейчас логотип не даёт ожидаемого перехода, поэтому приходится искать главную страницу через меню или кнопку назад. Нажатие на логотип в любом основном разделе должно стабильно открывать главную страницу, не выполняя побочных действий и не теряя данные без предупреждения."
      },
      {
        "id": "KC-05",
        "title": "Скрывать FBS-склады в общем списке",
        "business_meaning": "Служебные склады FBS сейчас могут отображаться рядом с обычными физическими складами во всех общих списках и селекторах. Пользователь рискует выбрать техническую сущность там, где требуется реальное место хранения, а списки становятся перегруженными. По умолчанию общие складские сценарии должны скрывать FBS-склады, оставляя их только в тех процессах или специальных фильтрах, где они действительно нужны."
      },
      {
        "id": "KC-06",
        "title": "Подтверждение закрытия при несохранённых изменениях",
        "business_meaning": "Оператор может заполнить форму приёмки или другой рабочий экран, а затем случайно закрыть его и потерять несохранённые изменения. Закрытие может произойти не только по кнопке, но и по Escape, клику вне диалога или переходу на другую страницу. Система должна одинаково распознавать изменённую форму во всех этих случаях и просить подтвердить выход, позволяя остаться и продолжить работу."
      },
      {
        "id": "KC-07",
        "title": "Общий пул остатков не умножается по складам",
        "business_meaning": "Сейчас общий доступный остаток товара можно независимо выставить на несколько складов, как будто на каждом из них лежит полный объём. Если физически есть всего 500 единиц, система может разрешить поставить по 500 на каждый склад и суммарно пообещать маркетплейсам больше товара, чем существует. Нужна единая модель пула и резервов, которая ограничивает сумму распределений реальным остатком и понятно показывает, сколько уже назначено каждому складу."
      },
      {
        "id": "KC-08",
        "title": "При скане отгрузки нельзя руками менять количество",
        "business_meaning": "В сценарии отгрузки каждое сканирование товара должно подтверждать конкретный физический экземпляр, который оператор действительно держит в руках. Возможность вручную увеличить количество позволяет записать отгрузку товара, который не был отсканирован и, возможно, отсутствует. После выбора сканирующего режима количество должно изменяться только успешными сканами и разрешёнными отменами последних сканов, а обычное поле ручного редактирования должно быть недоступно."
      },
      {
        "id": "KC-09",
        "title": "Убрать ячейку из коробов",
        "business_meaning": "Сейчас короб может требовать привязки к складской ячейке, хотя сама отгрузка уже физически собрана и готова к проведению. Это обязательное поле не помогает оператору выполнить действие, а останавливает фактическую отгрузку из-за недостающей технической связи. Ячейку нужно убрать из обязательных данных короба, сохранив её только как информацию о месте хранения товара там, где она реально нужна для поиска, размещения или отбора."
      },
      {
        "id": "KC-10",
        "title": "Календарь отгрузок должен показывать данные",
        "business_meaning": "Календарь отгрузок сейчас ничего не показывает, поэтому фулфилмент не видит предстоящую нагрузку и сроки передачи поставок маркетплейсам. Причина может быть в отсутствии данных, неправильной выборке API или в том, что интерфейс не отображает полученный результат, и это нужно различить диагностикой. После исправления календарь должен показывать реальные отгрузки по датам, корректно объяснять действительно пустой период и позволять открыть документ из выбранного дня."
      },
      {
        "id": "KC-11",
        "title": "Список товаров по ячейкам",
        "business_meaning": "Сотруднику склада нужен прямой ответ на вопрос, в какой ячейке сейчас лежит конкретный товар и что находится в выбранной ячейке. Сейчас эту информацию приходится восстанавливать по отдельным операциям или искать обходными способами, что замедляет поиск и инвентаризацию. Нужен список или отчёт с поиском по товару и ячейке, актуальным количеством и явным отображением обычных и служебных зон хранения."
      },
      {
        "id": "KC-12",
        "title": "Штрихкоды должны передаваться в WB",
        "business_meaning": "В процессе подготовки и передачи поставки Wildberries должен получать товарные штрихкоды в том составе и формате, который ожидает его API. Если WMS не отправляет их или отправляет не то поле, документ может создаться неполным либо потребовать ручной доработки в кабинете маркетплейса. Сначала нужно подтвердить актуальный контракт Wildberries и место передачи штрихкодов, затем реализовать отправку и проверить реальный запрос и результат без раскрытия секретных данных."
      },
      {
        "id": "KC-13",
        "title": "Excel-загрузка отгрузки в WB",
        "business_meaning": "Фулфилменту нужен способ передавать в Wildberries состав отгрузки сразу по коробам через поддерживаемый Excel-файл, а не переносить данные вручную по одному элементу. До реализации непонятно, какой шаблон, обязательные поля и ограничения принимает Wildberries и можно ли безопасно повторить подход, используемый в MP Fit. Нужно исследовать живой контракт и примеры, описать полный пользовательский сценарий формирования и загрузки файла, а затем реализовать его с проверкой ошибок и итогового принятия данных маркетплейсом."
      },
      {
        "id": "KC-14",
        "title": "Одинаковый порядок QR и листа подбора",
        "business_meaning": "QR-этикетки и позиции в листе подбора сейчас могут печататься в разной последовательности. Оператору приходится вручную искать соответствие между двумя пачками документов, что замедляет сборку и повышает риск наклеить код не на тот товар. Нужно выбрать единую ведущую сортировку и применять её к обоим печатным результатам, а тест должен сравнивать порядок на одном и том же наборе заказов."
      }
    ],
    "type": "product_intake",
    "priority": "medium",
    "status": "intake",
    "readiness": "needs_product_discovery",
    "dependencies": [
      "BLG-F01"
    ],
    "suggested_roles": [
      "Product",
      "BA",
      "solution-architect"
    ],
    "suggested_stages": [
      "S01",
      "S02",
      "S12"
    ]
  },
  "budget_enforced": true,
  "budget_usage": {
    "input_tokens": 300,
    "output_tokens": 100,
    "estimated_usd": 0.0025
  },
  "blocked_by": [],
  "blocker": null,
  "resume_condition": null,
  "rules": [
    "Read AGENTS.md, docs/process/PIPELINE-RU.md and pipeline/pipeline.yml first.",
    "Do not accept your own work.",
    "If status is WAITING, do not advance; report the blocker and wait for resume.",
    "If budget_enforced is true, advance requires usage receipt fields.",
    "If blocked_by is non-empty, do not pass the blocker resume stage without resolve-blocker evidence.",
    "Use python3 scripts/pipeline/run.py advance only for the stage you own.",
    "Do not set DONE while pipeline status is not ACTIVE."
  ]
}
```

## Required Start

```bash
python3 scripts/pipeline/run.py next --task-id BLG-KC01
python3 scripts/pipeline/run.py validate --task-id BLG-KC01
```

## Required Finish

Only after completing the owned stage:

```bash
python3 scripts/pipeline/run.py advance --task-id BLG-KC01 --stage S05 --verdict <ALLOWED_VERDICT> --role pipeline-ba --agent <agent-id> --executor codex --model gpt-5.6-terra --tier moderate --input-tokens <INPUT_TOKENS> --output-tokens <OUTPUT_TOKENS> --estimated-usd <USD>
python3 scripts/pipeline/run.py packet --task-id BLG-KC01
python3 scripts/pipeline/dispatch.py --task-id BLG-KC01 --executor codex
```
