# Единый исполнимый конвейер разработки WMS

Версия: **2.0, 20.08.2026**.

Статус: **целевая каноническая спецификация; ещё не активирована технически**.

Этот документ описывает один процесс для всей разработки WMS: от исправления текста или бага
до подключения нового маркетплейса целиком. После технической активации он становится единственным
нормативным источником процесса. `AGENTS.md`, карточки правил и подсказки агентов должны содержать
только краткое напоминание и ссылку на версию этого документа, а не второй параллельный процесс.

Сам Markdown ничего не принуждает. Процесс считается активным только после реализации
`pipeline/pipeline.yml`, контроллера, CI-ворот, exact-SHA deploy и метатестов из части XII.
До этого запрещено писать, что новый конвейер уже «работает железно».

---

# ЧАСТЬ I. ЦЕЛЬ И НЕИЗМЕННЫЕ ПРИНЦИПЫ

## 1. Цель

Владелец должен иметь возможность вечером написать:

> Подключи Ozon.

или:

> На упаковке пропала кнопка печати.

и не управлять исполнителями ночью. Конвейер самостоятельно:

1. сохраняет исходную просьбу без переписывания;
2. определяет, какие виды работы затронуты;
3. включает нужную глубину исследования и проектирования;
4. проектирует правильный складской процесс и интерфейс;
5. пишет прямые и разрушительные кейсы до разработки;
6. выдаёт изолированные задания разработчикам;
7. не позволяет агентам перезаписывать чужую работу;
8. проводит Code Review и массовый прогон;
9. доказывает цельный путь через UI, API, данные, worker и внешнюю систему;
10. проводит независимую финальную приёмку, а для любого operator flow — живую Product Browser-приёмку;
11. сохраняет результат в Git с точным SHA;
12. выкатывает только явно разрешённый SHA и умеет откатиться;
13. утром показывает короткий отчёт с результатом, доказательствами и только настоящими
    вопросами владельцу.

Цена моделей и число тестов вторичны. Главные ограничения — доказуемость результата,
воспроизводимость, безопасность, отсутствие бессмысленных блокеров и время владельца.

## 2. Что считается провалом

Провал конвейера — любое из событий:

- дефект первым нашёл оператор на живом складе;
- после релиза нарушился складской инвариант;
- произошла тихая порча или расхождение данных;
- один tenant, селлер или склад увидел чужие данные;
- тестовый контур обратился в живой кабинет внешней системы;
- задеплоен SHA, отличный от принятого;
- агент затёр или смешал чужой diff;
- Product Browser принял не тот экран, роль, данные или версию;
- задача названа готовой без commit, push, необходимых тестов и вердиктов;
- работа зависла без состояния, владельца заставили вручную искать и перезапускать агента;
- повторился уже закрытый дефект, а конвейер не распознал регрессию.

Зелёный тест, замечание Code Review или Product rework провалом не являются. Они означают,
что защита сработала до живого склада.

## 3. Оракулы — кто вправе сказать «должно быть так»

У каждого ожидания в требовании и кейсе называется источник правды.

1. **Закон, безопасность и изоляция данных.** Не могут быть отменены удобством или мнением.
2. **Жёсткий контракт внешней системы.** Версия API, документация, проверенный sandbox/emulator.
3. **Физика склада.** Товар не бывает в двух местах; нельзя отгрузить больше остатка;
   маркировочный код одноразовый; движение оставляет проверяемый след.
4. **Подтверждённое продуктовое решение владельца.** Что нужно сотруднику склада, какие действия
   и данные должны быть на экране.
5. **Утверждённый Product/UX-канон.** Применяет решения владельца к конкретному процессу.
6. **Текущий код.** Отвечает только на вопрос «что происходит сейчас», но не «как должно».

Если два непреложных оракула конфликтуют, задача получает `BLOCKED_ORACLE_CONFLICT`. Агент не
выбирает удобный вариант сам. Факт жалобы доказывает наличие проблемы, но не автоматически
доказывает правильное новое поведение.

## 4. Один процесс, а не несколько конвейеров

Любая работа проходит общее ядро:

```text
INTAKE
→ IMPACT_CLASSIFIED
→ BEHAVIOR_CONTRACT_READY
→ PRODUCT_CONTRACT_APPROVED
→ TASK_CUT_READY
→ CASES_READY
→ PRODUCT_APPROVED_FOR_DEV
→ DEVELOPMENT
→ CODE_REVIEW_PASSED
→ FUNCTIONAL_TESTS_PASSED
→ INTEGRATION_PASSED
→ FINAL_ACCEPTANCE_APPROVED
→ RELEASE_RESULT
```

Различается только набор дополнительных стадий. Он вычисляется признаками задачи, а не выбором
агента «сегодня сделать попроще».

Единственная ранняя terminal-ветка — расследование, доказавшее, что изменение кода не требуется:
`NO_DEFECT` или `DUPLICATE` закрывается через B04 с Product/oracle и registry receipts. Оно не
имитирует Dev, deploy или production trace.

---

# ЧАСТЬ II. МАШИННЫЙ КОНТРАКТ И СОСТОЯНИЕ

## 5. Четыре слоя принуждения

### 5.1. `pipeline/pipeline.yml`

Единственная машинная таблица допустимых стадий, условий входа, вердиктов, возвратов и
аннулирования старых решений. YAML — человекочитаемый формат данных. Сам по себе он не является
защитой; его читает контроллер и повторно проверяет CI.

### 5.2. Контроллер `wave-driver`

Только контроллер имеет право:

- вычислить обязательные стадии;
- выдать агенту роль, worktree и окружение;
- перевести задачу на следующую стадию;
- принять подписанный артефакт стадии;
- аннулировать зависимые вердикты;
- повторить, припарковать или возобновить работу;
- передать принятый SHA в интеграцию и release.

Рабочий агент не меняет состояние задачи и не принимает собственную работу.

### 5.3. CI

CI заново вычисляет профиль по исходной карточке и Git diff. Он не доверяет галочкам агента.
Merge блокируется, если отсутствует обязательная стадия, независимый verdict, тест, доказательство,
разрешение файла или точный SHA.

### 5.4. Deploy

Deploy принимает только разрешённый `release_candidate_sha`, повторно проверяет состояние волны
и отказывается работать при несовпадении SHA, красном CI, отсутствии rollback или финального
применимого S25 acceptance receipt.

## 6. Защита управляющего контура

Рабочим агентам запрещено менять в обычной задаче:

- `pipeline/**`;
- контроллер и валидаторы;
- `.github/workflows/**`;
- production deploy/rollback;
- runtime state своей задачи;
- verdict другого агента.

Изменение управляющего контура — отдельная задача типа `pipeline_change`, требующая явного
подтверждения владельца, независимого review и метатестов. Версия и hash `pipeline.yml`
фиксируются при старте задачи; подменить процесс посередине нельзя.

## 7. Runtime state задачи

Авторитетное runtime state хранится в controller-owned хранилище вне рабочих worktree. В
`tasks/<task-id>/state.json` контроллер публикует hash-linked read-only snapshot для Git, CI,
восстановления и аудита. Рабочий агент не получает write-capability к controller store; ручная
правка snapshot не меняет состояние и обнаруживается валидатором.

Контроллер пишет состояние атомарно через compare-and-swap и ведёт append-only event journal.
Каждый transition и внешний side effect получает idempotency key; после crash replay не может
повторно создать отгрузку, миграцию, комментарий или deploy. `state.json` — восстановимый snapshot
журнала, а не единственная копия истины.

Обязательные поля:

```json
{
  "task_id": "TASK-20260820-001",
  "source_hash": "sha256:...",
  "pipeline_version": "2.0",
  "pipeline_hash": "sha256:...",
  "traits": ["bug", "ui_change", "print"],
  "required_stages": [],
  "current_stage": "DEVELOPMENT",
  "status": "RUNNING",
  "base_sha": "...",
  "branch": "fix/...",
  "worktree": ".worktrees/...",
  "environment_id": "...",
  "database": "...",
  "redis_namespace": "...",
  "celery_queue": "...",
  "emulator_namespace": "...",
  "owner_agent": "...",
  "attempt": 1,
  "lease_until": "...",
  "heartbeat_at": "...",
  "last_valid_receipt": "...",
  "blocker": null,
  "resume_condition": null,
  "verdicts": {},
  "commits": []
}
```

Допустимые состояния выполнения:

- `QUEUED`;
- `RUNNING`;
- `WAITING`;
- `REWORK`;
- `PARKED`;
- `IMPLEMENTATION_DONE`;
- `READY_FOR_RELEASE`;
- `DEPLOYING`;
- `MONITORING`;
- `STABILIZED_WITH_DEBT`;
- `INVESTIGATION_DONE`;
- `CANCELLED`;
- `DONE`.

Неопределённого состояния «агент вроде что-то делал» не существует.

Причина ожидания или остановки не кодируется вторым набором lifecycle status. Она хранится в
`blocker.type` и `blocker.reason_code`, например `OWNER_INPUT`, `ENV`, `FIXTURE`, `EXTERNAL`,
`ORACLE_CONFLICT`, `BASELINE`, `ACCESS`, `SECURITY` или `RELEASE`. Stage-specific результаты
вроде `BLOCKED_FIXTURE`, `PRODUCT_BROWSER_BLOCKED` и `MONITORING_NO_TRAFFIC` остаются verdict
receipt и однозначно переводятся контроллером в `WAITING`, `PARKED` или `MONITORING`.

## 8. Единый контракт стадии

Каждая стадия в `pipeline.yml` описывается одинаково:

```yaml
stage_id:
enabled_when:
input_schema:
role:
permissions:
forbidden:
entry_requires:
artifacts:
pass_verdict:
failure_verdicts:
next_on_pass:
return_on_rework:
invalidates:
timeout:
retry_limit:
blocker_types:
```

Артефакт стадии — структурированный receipt с task id, `run_id`, controller-issued role binding,
agent identity, input/output hashes, parent receipt hash, baseline SHA, временем, выводом и verdict.
Контроллер подписывает receipt ключом, недоступным worker. CI проверяет подпись и запрещает одной
identity совмещать несовместимые роли в одной карточке. Свободный Markdown может быть приложен для
человека, но не является машинным результатом.

Условная стадия не пропускается молча. Для неё создаётся `NOT_APPLICABLE_VERIFIED` receipt с
признаками, diff evidence и независимым подтверждением impact-reviewer. Если post-diff
классификация обнаружила применимость, skip-receipt аннулируется.

---

# ЧАСТЬ III. ПРИЗНАКИ И ПРОФИЛИ ЗАДАЧ

## 9. Аддитивные признаки

На входе классификатор ставит один или несколько признаков:

| Признак | Что обязательно добавляет |
|---|---|
| `bug` | воспроизведение и oracle; root cause/escape/regression только при `DEFECT_CONFIRMED`, B04 при no-change |
| `ui_change` | UX-контракт, макет, Design Review, визуальный регресс, Product Browser |
| `process_change` | карта текущего и целевого процесса, Product Domain Approval |
| `external_contract` | research источника, контракт по полям, emulator/sandbox cases |
| `new_domain` | полный domain dossier, карта FBS/FBO, GAP, два архитектора и арбитраж |
| `new_module` | исследование новой capability, процесс, GAP и архитектурная фальсификация даже внутри известного домена |
| `database_change` | совместимость миграции, backfill, rollback, инварианты |
| `background_worker` | retry, outage, очередь, гонки, повторный запуск |
| `print` | формат, содержимое, размеры, повторная печать, printer evidence |
| `mobile_contract` | совместимость ТСД и отдельный consumer verdict |
| `tenant_sensitive` | negative authorization и isolation cases |
| `release_change` | exact-SHA, smoke, rollback, production trace |
| `emergency` | сокращение только явно разрешённых стадий и обязательный долг после стабилизации |
| `pipeline_change` | защита контура и полный набор метатестов |

Пример: «На Ozon пропадает кнопка этикетки» получает `bug + ui_change + external_contract +
print + background_worker`. Обязательные стадии объединяются.

Кроме traits карточка получает `risk_level: low | medium | high | critical`. `high/critical`
вычисляется, а не выбирается агентом по ощущениям: достаточно риска потери/порчи данных или денег,
cross-tenant доступа, необратимой внешней записи, миграции/backfill, изменения двух и более ключевых
складских процессов либо общей поверхности с большим blast radius. `new_module` ставится для любой
существенно новой WMS-capability с нуля, даже если marketplace или домен уже знаком.

В `pipeline.yml` каждый trait содержит не prose-обещание, а `required_stages`, `required_receipts`,
`case_dimensions` и `acceptance_surfaces`. Минимальные typed receipts:

| Trait | Обязательные дополнительные receipts |
|---|---|
| `bug` | всегда reproduction + oracle/triage; при `DEFECT_CONFIRMED` root-cause/escape + regression, при B04 registry closure |
| `ui_change` | UX, Design, visual implementation, Product Browser |
| `process_change` | current/target map, GAP, Product Domain |
| `external_contract` | versioned field/status contract, emulator или разрешённый sandbox proof |
| `new_domain`, `new_module` | dossier, capability coverage, process map, GAP, independent architecture review |
| `database_change` | migration compatibility, backfill, integrity proof, restore/rollback rehearsal |
| `background_worker` | retry/idempotency, queue isolation, outage and replay proof |
| `print` | content/layout/size, repeat-print and real printer or approved device evidence |
| `mobile_contract` | versioned consumer contract и независимый mobile receipt |
| `tenant_sensitive` | negative authorization и cross-tenant isolation receipt |
| `release_change` | immutable artifact manifest, exact promotion, smoke, rollback и trace |
| `emergency` | signed bypass scope, immediate smoke/rollback и автоматически заведённый debt |
| `pipeline_change` | owner authorization, independent control-plane review и все metatests |

## 10. Двойная классификация

Первая классификация выполняется до разработки по формулировке, экрану, процессу и затронутым
компонентам. Вторая — после Git diff.

Post-diff guard автоматически добавляет признаки, если обнаружены:

- новый или изменённый внешний клиент;
- новый route;
- миграция или модель данных;
- UI-файл или видимое поведение;
- worker/очередь;
- печатный шаблон;
- mobile contract;
- общий файл нескольких экранов.

Если профиль расширился, контроллер возвращает задачу к первой недостающей стадии и аннулирует
зависимые verdict. Нельзя спрятать внешний вызов, назвав задачу «маленьким багом».

## 11. Маршруты разных задач

### 11.1. Баг

Happy path только для disposition `FIXED_RELEASED`:

```text
REPORT
→ B01 REPRODUCTION
→ B02 EXPECTED_BEHAVIOR
→ B03 ROOT_CAUSE_AND_ESCAPE
→ CASES
→ PRODUCT_BEFORE_DEV
→ FIX
→ CODE_REVIEW
→ REGRESSION
→ PRODUCT_BROWSER
→ PROD_TRACE
→ INCIDENT_CLOSED
```

Результаты воспроизведения:

- `REPRODUCED` — обычный маршрут исправления;
- `NOT_REPRODUCED` — не означает «дефекта нет», требует наблюдения или дополнительных данных;
- `INTERMITTENT` — создаёт telemetry/monitoring task и повторный маршрут;
- `BLOCKED_FIXTURE` — фиксирует недостающую безопасную фикстуру;
- `BLOCKED_ENV` — фиксирует несовпадение версии или окружения;
- `EXPECTED_BEHAVIOR` — требует подтверждённый оракул и Product verdict, затем B04 либо
  переклассификацию в improvement;
- `DUPLICATE` — B04 с canonical incident и triage receipt.

### 11.2. Небольшое улучшение или UI-правка

Не проходит полный domain research, если не затрагивает внешний контракт. Но обязательно получает
атомарную карточку, Product Before Dev, макет при видимом изменении, кейсы до разработки, Code
Review, функциональный прогон и Product Browser после разработки.

### 11.3. Новый домен или маркетплейс

Получает полный профиль частей IV–VI. «Подключить Ozon» не режется сразу на dev-задачи. Сначала
должно быть доказано, что понятен весь процесс, внешние контракты, границы WMS и UX.

### 11.4. Авария

Активируется только явной фразой владельца о production emergency. Это заранее описанный профиль
в `pipeline.yml`, а не ручное отключение CI. До deploy обязательны S01, S02, применимая B01,
минимальный S08, direct regression и складские invariants S15, S16–S20, targeted S22, S23, S25,
S26–S28. Database, tenant и irreversible внешние traits никогда не теряют свои safety receipts.

Обязательны:

- подписанный `EMERGENCY_BYPASS_USER_APPROVED` с scope, причиной, сроком и exact stage exceptions;
- минимальный diff;
- root cause hypothesis;
- независимый Code Review;
- targeted Product Browser, прямой smoke и проверенный rollback/stop;
- exact immutable artifact;
- автоматически созданный долг на недостающую глубину research, cases, full regression и полную
  Product Browser acceptance matrix.

После smoke статус только `STABILIZED_WITH_DEBT`, не `DONE`. Аварийный bypass не является Product
approval для пропущенных стадий. Каждое исключение создаёт immutable debt task с owner, сроком и
resume stage; оно не исчезает при закрытии hotfix. Инцидент получает `DONE` только после полного
post-gate, S28 и закрытия всего safety debt.

---

# ЧАСТЬ IV. ПОЛНАЯ ЛЕНТА СТАДИЙ

## 12. Intake и impact

### S01. `INTAKE`

`dispatcher` сохраняет дословную просьбу, вложения и временные метаданные. Исходник неизменяем;
все интерпретации хранят ссылку на source span.

Выход: `TASK_INTAKE_READY` и `CARD.json`.

### S02. `IMPACT_CLASSIFICATION`

Классификатор ставит признаки, экран, зону, процесс, surface и предполагаемые ресурсы. Неизвестный
экран не блокирует intake: используется `UNKNOWN`, после чего screen mapper ищет соответствие.

Выход: `IMPACT_CLASSIFIED` или `IMPACT_BLOCKED`; во втором случае task получает `WAITING` и
типизированный blocker с точным условием возобновления.

### B01. `BUG_REPRODUCTION`

Обязателен для trait `bug`. Изолированный `bug-investigator` воспроизводит симптом на зафиксированном
baseline и fixture, связывает его со screen/process/operation и создаёт typed receipt:

- `REPRODUCED` → B02;
- `NOT_REPRODUCED` → B02, затем наблюдение с конкретным сигналом и сроком; это не закрытие;
- `INTERMITTENT` → `OBSERVABILITY_ACTIVE`, status `WAITING`, автоматическое возобновление B01 по сигналу;
- `BLOCKED_FIXTURE` или `BLOCKED_ENV` → controller создаёт repair subtask и возобновляет B01;
- доказанный внешний/доступовый blocker → `PARKED` только по правилам раздела 31.

### B02. `EXPECTED_BEHAVIOR_CONTRACT`

`bug-investigator` называет оракул и сравнивает отчёт с ожидаемым поведением. Выход:

- `DEFECT_CONFIRMED` → B03;
- `EXPECTED_BEHAVIOR` → B04 с `NO_DEFECT` либо переклассификация в improvement с новым contract;
- `DUPLICATE` → B04 с canonical incident и incident-triage receipt;
- `ORACLE_CONFLICT` → `WAITING` с blocker `ORACLE_CONFLICT` и точным вопросом владельцу;
- `EVIDENCE_INSUFFICIENT` → назад в B01/observability, а не к выдуманному root cause.

### B03. `ROOT_CAUSE_AND_ESCAPE_ANALYSIS`

Для подтверждённого дефекта фиксируются causal chain, слой возникновения, почему дефект прошёл
существующую защиту, нормализованный fingerprint и какая защита должна была поймать его раньше.
Выход: `ROOT_CAUSE_ESCAPE_READY | ROOT_CAUSE_REWORK | ROOT_CAUSE_BLOCKED`. Его receipt обязателен
для S08 и S15; symptom-only fix не допускается.

### B04. `INVESTIGATION_CLOSURE_NO_CHANGE`

Разрешён только для `NO_DEFECT` с Product/oracle receipt либо `DUPLICATE` с canonical incident id и
incident-triage receipt. Контроллер обновляет incident/docs registries и выдаёт terminal
`INVESTIGATION_DONE` с disposition. `NOT_REPRODUCED`, `INTERMITTENT` и отсутствие root-cause evidence
не могут использовать B04 и остаются в observation/reproduction loop.

## 13. Исследование нового домена и внешнего контракта

### S03. `DOMAIN_RESEARCH`

Для `new_domain` создаётся `DOMAIN-DOSSIER.md`, а для `new_module` — scoped `MODULE-DOSSIER.md`;
оба содержат машинную capability matrix. Для модуля берутся только применимые lanes, но обязательны
операционный процесс, релевантные competitor workflow/screens и доказательство границ WMS.
Обязательные lanes:

- официальная API-документация с версией и датой;
- инструкции продавцу и оператору;
- модели FBS/FBO и полный автомат статусов;
- каталог, заказы, остатки, резервы, маркировка, печать, отгрузка, отмены и возвраты;
- pagination, rate limits, batch behavior, partial success, retries, webhooks/polling;
- реальные боли пользователей и продавцов;
- конкуренты: последовательность процесса, экраны, сильные решения и ограничения;
- безопасность, роли, tenant, селлер и склад;
- объёмные и аварийные режимы.

Каждый claim содержит URL/источник, версию, дату, уровень `official | live_sandbox | observed |
hypothesis`. Hypothesis либо проверяется, либо становится blocking/non-blocking question.

Research закрывается `RESEARCH_READY` только при нулевом числе необработанных применимых capability
rows.

Для изменения существующего внешнего вызова выполняется узкий contract research только затронутой
области, но post-diff guard проверяет, что область не занижена.

### S04. `RESEARCH_CRITIC`

Изолированный критик не читает выводы автора до собственного поиска критических контрактов.
Он ищет пропущенные endpoints, статусы, ограничения, breaking changes и противоречия.

Выход: `RESEARCH_PASSED | RESEARCH_REWORK | RESEARCH_BLOCKED`.

## 14. Процесс и GAP

### S05. `PROCESS_MAP`

`process-architect` описывает путь целиком, отдельно по бизнес-моделям. Для каждого шага:

- физическое действие;
- роль;
- данные и документ;
- внешнее событие;
- ручная операция;
- успех, ошибка, пустота, повтор и отмена;
- наблюдаемый след.

На этой стадии не проектируются компоненты интерфейса.

### S06. `GAP_ANALYSIS`

`gap-analyst` накладывает целевой процесс на существующую WMS по экранам, процессам, API, данным,
worker, печати и mobile. Каждая capability получает `reuse | extend | new | reject` и объяснение.
Новый экран допускается только если существующая поверхность не обслуживает процесс без создания
монолита или дублирования.

### S07. `PRODUCT_DOMAIN_APPROVAL`

Product читает research, process map и GAP вместе. Он не может утверждать процесс до появления
карты. Вердикты:

- `PRODUCT_DOMAIN_APPROVED`;
- `PRODUCT_DOMAIN_REWORK`;
- `PRODUCT_DOMAIN_BLOCKED`.

## 15. Изменения, блокировки и UX

### S08. `BEHAVIOR_CONTRACT_AND_BLOCK_AUDIT`

Для каждой задачи, меняющей runtime-поведение, `business-analyst` создаёт versioned
`BEHAVIOR-CONTRACT.json`: actor, screen/process, current → target, входы/выходы, success/error/empty/
forbidden/partial/repeat, данные и побочные эффекты, инварианты, out-of-scope и оракулы. Для нового
домена contract выводится из process map и GAP; для бага — из B02/B03. Для docs-only или доказанно
непродуктового изменения независимый impact-reviewer может выдать `NO_RUNTIME_BEHAVIOR`; молчаливого
пропуска нет.

По каждому изменению фиксируются цель, заблокированная возможность, warehouse value и цена отказа.
Любая UI/server-блокировка получает:

- условие;
- слой;
- что видит оператор;
- как разблокировать;
- ущерб при снятии;
- подтверждающий негативный кейс;
- уверенность;
- ссылку на инцидент или оракул.

Нет доказанного ущерба — правило считается кандидатом на удаление, а не обязательной защитой.

Выход: `BEHAVIOR_CONTRACT_READY | NO_RUNTIME_BEHAVIOR | BEHAVIOR_CONTRACT_REWORK |
BEHAVIOR_CONTRACT_BLOCKED`.

### S09. `UX_CONTRACT_AND_MOCKUPS`

Для каждого видимого изменения создаются конкретные макеты всех состояний. Экран сначала собирается
из существующего `ui-kit`. Недостающий компонент становится отдельной задачей на расширение kit и
проходит Design Review до использования в модуле. Контроллер автоматически создаёт child card и
dependency edge в той же волне; родитель не получает S17, пока не зафиксирован принятый
`ui_kit_version/component_sha`. Это не вопрос владельцу без настоящего blocker.

Контракт UI обязан назвать компоненты из `frontend/src/ui-kit/index.ts` по зонам экрана:
таблица, действия, статусы, формы, вкладки, меню, модалка, каркас. Если компонент отсутствует,
stage возвращает typed blocker `DESIGN_SYSTEM_GAP`, а не разрешение сверстать локально.

### S10. `DESIGN_REVIEW`

`design-judge` проверяет макет по `docs/product/UX_CANON_RU.md`, warehouse noise, scanner-first,
переполнению, длинным данным, разрешениям, loading/empty/error/forbidden/partial. «Не нравится» без
правила и сломанной работы не является verdict.

Выход: `DESIGN_APPROVED | DESIGN_REWORK | DESIGN_BLOCKED`.

### S11. `PRODUCT_CONTRACT_APPROVAL`

Product подтверждает business/warehouse contract до нарезки на карточки. Для видимого изменения он
также подтверждает цельный операторский процесс и warehouse rationale каждого элемента. Для backend,
worker, data или pipeline change он подтверждает ожидаемый операционный эффект и отсутствие
незапрошенного изменения пользовательского процесса.

Выход: `PRODUCT_CONTRACT_APPROVED | PRODUCT_CONTRACT_REWORK | PRODUCT_CONTRACT_BLOCKED`.

## 16. План, критика и кейсы

### S12. `TASK_CUT`

Целевой процесс режется на вертикальные атомарные карточки, а не на несвязанные frontend/backend
кусочки. Каждая карточка оставляет наблюдаемый пользовательский или операционный результат.

### S13. `ARCHITECT_PLAN`

Первый архитектор строит resource graph: файлы, экраны, процессы, routes, services, таблицы,
миграции, queues, contracts, print и mobile. Он назначает порядок, locks и волны.
Для `new_domain` и `new_module` S13 обязателен независимо от числа карточек и текущего risk level,
потому что S14 не может фальсифицировать отсутствующий план.

### S14. `ARCHITECT_FALSIFICATION`

Для `new_domain`, `new_module`, нескольких пересекающихся задач и high/critical risk change второй изолированный архитектор
строит свой план без чтения первого. Машина сравнивает планы. Расхождения получает arbiter:

- `ACCEPT_PLAN_1`;
- `ACCEPT_PLAN_2`;
- `REPLAN`;
- `BLOCKED`.

Неразрешённый high-risk conflict блокирует разработку.

### S15. `CASE_FACTORY`

`case-writer` создаёт прямые кейсы до кода. Для каждого изменённого поведения и каждого process
journey обязательно работает минимум один независимый `case-breaker`; для high/critical risk —
несколько с разными attack lanes. Число вариантов не ограничивается; ограничивается только
отсутствие оракула, уникального риска или воспроизводимой фикстуры.

Кейсы покрывают применимые классы:

- happy;
- empty;
- invalid;
- forbidden;
- repeat/idempotency;
- partial success;
- cancel/resume;
- outage/timeout;
- concurrency;
- volume/pagination;
- role/tenant/warehouse;
- external contract;
- background retry;
- print/scanner/device;
- read-back/reload.

Coverage matrix связывает requirement → capability → process transition → incident/block → direct
case → breaker cases. Независимый `case-auditor` проверяет матрицу. `CASES_READY` разрешён только
при нуле непокрытых применимых строк и verdict `CASE_AUDIT_PASSED`.

До Dev у каждого case уже выбраны executor type, fixture/reset и planned automation binding; S19
после реализации обязан превратить каждый такой план в runnable reference, не переписывая oracle.

Выход: `CASES_READY | CASES_REWORK | CASES_BLOCKED`.

### S16. `CARD_PRODUCT_APPROVAL_BEFORE_DEV`

Product получает не идею, а точный пакет: hash исходника, утверждённый contract, атомарную карточку,
архитектурные зависимости, UI-макеты при их наличии и полный набор cases с оракулами. Он проверяет,
что реализация всей карточки действительно даст нужный цельный результат и что кейсы не закрепляют
неверное поведение.

Выход: `PRODUCT_APPROVED_FOR_DEV | PRODUCT_CARD_REWORK | PRODUCT_CARD_BLOCKED`. Verdict привязан
к hash всего пакета. Любое изменение карточки, contract, макета или cases аннулирует его. Без этого
verdict контроллер не выдаёт workspace.

## 17. Разработка и техническая проверка

### S17. `WORKSPACE_ALLOCATION`

Контроллер выдаёт отдельные branch, worktree, database, Redis namespace, Celery queue, ports,
emulator namespace и evidence directory. Пустые границы запрещают работу. Общий ресурс получает
lock. Аналитические агенты пишут в отдельные shards; один aggregator сливает их детерминированно.

### S18. `DEVELOPMENT`

Один Atomic Dev Agent реализует одну утверждённую карточку. Он меняет только разрешённые ресурсы,
не принимает собственный результат и передаёт scoped commit SHA.

Выход: `DEV_DONE | DEV_REWORK | DEV_BLOCKED` плюс чистый worktree и commit.

### S19. `TEST_AUTOMATION_BINDING`

Независимый test-automation agent связывает каждый required case с исполнимым драйвером:
`pytest`, Playwright, API/contract runner, worker harness, emulator или approved manual acceptance.
Binding фиксирует case version, `executor_type`, `executable_ref/test_id`, fixture builder/reset,
timeout, expected trace и evidence schema. Manual допускается только для человеческой UX/device
оценки, которую невозможно детерминировать; он не заменяет автоматизируемые проверки.

Выход: `CASES_EXECUTABLE | AUTOMATION_REWORK | AUTOMATION_BLOCKED`. Ни один детерминируемый GOLD,
breaker или invariant case не может попасть в функциональный прогон без runnable binding.

### S20. `CODE_REVIEW`

Независимый reviewer проверяет requirement fit, scope, contracts, migrations, pagination, state
transitions, partial failures, retries, tenant isolation, tests и качество доказательств.

Finding обязан иметь тип `CONTRACT | PLAN | IMPLEMENTATION | AUTOMATION | MIGRATION`: возврат идёт
соответственно в S08, S13, S18, S19 либо owning database stage/receipt с транзитивной инвалидацией.
Выход: `CODE_REVIEW_PASSED | CODE_REVIEW_REWORK | CODE_REVIEW_BLOCKED`.

## 18. Исполнение, интеграция и финальная приёмка

### S21. `DOCUMENTATION_AND_REGISTRY_UPDATE`

По impact обновляются docs/runbook, domain memory, contracts, screens, processes, incidents, blocks
и cases. Для нового domain/module долговечная память хранится в
`docs/product/domains/<domain>/`: versioned capability matrix, источники, competitor workflow/screen
evidence с provenance, process map, GAP и freshness/revalidation каждого claim. Последующие баги
переиспользуют свежие строки и переоткрывают только затронутые или устаревшие.

Общие registry обновляются через per-task shards и детерминированный aggregator с referential-
integrity проверкой. Неприменимость получает `DOCS_REGISTRY_NA_VERIFIED`, а не пустой diff.

Выход: `DOCS_REGISTRY_PASSED | DOCS_REGISTRY_REWORK | DOCS_REGISTRY_BLOCKED`.

### S22. `FUNCTIONAL_TESTING`

Детерминированные runner исполняют все обязательные direct, breaker, adjacent и invariant cases
на production-like stack. Упавший кейс один раз повторяется на свежем состоянии. Повторное падение
— finding; разный результат — `FLAKY`, который чинится, а не игнорируется.

Сильный triage-agent не имеет права объявить кейс устаревшим по вкусу. Изменить ожидание можно
только по новому подтверждённому оракулу. `SNAPSHOT_CHANGED` блокирует интеграцию до классификации.

Для `ui_change` обязательны `ui_guard.py`, `ui_kit_usage_guard.py`, token/ui-kit provenance check
и zone visual regression на нужных viewport со loading/empty/error/forbidden/partial/long-data
состояниями. Сам Dev не обновляет baseline. Любое baseline change требует новых Design и Product
receipts.

Каждый finding получает тип `PRODUCT_DEFECT | CASE_DEFECT | FIXTURE_DEFECT | ENV_DEFECT | FLAKY`:
первый возвращает в S18, второй в S15, третий/четвёртый в repair subtask с возвратом S22, пятый —
в flake remediation. Выход: `FUNCTIONAL_TESTS_PASSED | FUNCTIONAL_REWORK |
FUNCTIONAL_BLOCKED`.

### S23. `INTEGRATION_AND_FULL_REGRESSION`

Карточки сливаются по одной в pinned integration SHA. Для каждого SHA CI сначала один раз собирает
immutable artifact/image digests для migration, backend, worker и frontend, фиксирует lockfile/
base-image provenance и SBOM в release manifest, затем выкатывает именно эти digests на isolated
integration stand. Между слияниями на них гоняются ключевые кейсы, после волны — весь обязательный
набор домена, все эталоны и инварианты. Результат содержит `git_sha + artifact_digests` и виновника
первого красного перехода. Позднее эти артефакты только продвигаются, не пересобираются.

Canonical integration ref fast-forward перемещается на тот же проверенный SHA. Любой merge/rebase,
создавший другой SHA или tree, аннулирует regression и downstream approval и повторяет S23.

Выход: `INTEGRATION_PASSED | INTEGRATION_REWORK | INTEGRATION_BLOCKED`.

### S24. `DESIGN_IMPLEMENTATION_REVIEW`

Обязателен для `ui_change`. Независимый design-judge на живом exact `git_sha + artifact_digests`
integration stand сравнивает
реализацию с утверждённым макетом и zone baseline: breakpoints, длинные данные, все состояния,
типографика, интервалы, переполнение и происхождение компонентов из ui-kit. Если новая зона
не импортирует `frontend/src/ui-kit`, это `DESIGN_IMPLEMENTATION_BLOCKED`.

Выход: `DESIGN_IMPLEMENTATION_APPROVED | DESIGN_IMPLEMENTATION_REWORK |
DESIGN_IMPLEMENTATION_BLOCKED`. Rework возвращается в S18; новый baseline требует S10 и S11.

### S25. `FINAL_ACCEPTANCE`

Для operator-visible flow после Code Review, зелёных функциональных тестов и интеграционного
регресса отдельный сильный Product Agent открывает живой видимый браузер на точном `git_sha +
artifact_digests` integration stand и руками проходит цельные
процессы. Playwright, API, скриншот и пересказ разработчика не заменяют этот verdict.

Фиксируются URL, SHA, роль, tenant, данные, клики/сканы, видимые success/error/empty/forbidden
состояния, read-back, reload и visual-noise verdict.

Acceptance matrix связывает каждый required product journey, затронутую роль/tenant/screen и
критические success/error/empty/forbidden ветки с конкретным browser run и evidence. Массовые
технические breaker-cases исполняют runner, но Product обязан пройти все продуктовые journeys.
`PRODUCT_BROWSER_APPROVED` разрешён только при нуле непокрытых обязательных строк matrix.

Выход:

- `PRODUCT_BROWSER_APPROVED`;
- `PRODUCT_REWORK_REQUIRED`;
- `PRODUCT_BROWSER_BLOCKED`.

Для pure-internal задачи S25 использует заранее объявленный independent acceptance surface и typed
`<SURFACE>_APPROVED`. Контроллер нормализует допустимый внешний или внутренний receipt в
`FINAL_ACCEPTANCE_APPROVED`; для operator-visible flow таким receipt может быть только
`PRODUCT_BROWSER_APPROVED`.
После `FINAL_ACCEPTANCE_APPROVED` lifecycle task становится `IMPLEMENTATION_DONE`.

Любое изменение затронутой зоны после approval аннулирует Code Review, functional, integration,
Design Implementation и Product Browser receipts для нового SHA.

## 19. Release и production trace

### S26. `RELEASE_AUTHORIZATION`

Контроллер формирует `release_candidate_sha`, artifact manifest, green CI proof, rollback SHA и
draft release packet. Финальный утренний отчёт достраивается из machine state после S28 либо честно
показывает `READY_FOR_RELEASE`/`MONITORING`.
Production deploy — отдельное действие только по явной команде владельца или заранее выданному
разрешению на конкретную волну. Эта стадия выполняется всегда и завершает развилку честным
машинным результатом:

- `RELEASE_AUTHORIZED` — конкретный SHA и artifact manifest разрешено выкатывать, далее S27;
- `READY_FOR_RELEASE` — реализация принята и опубликована, но разрешения на production deploy не было;
- `RELEASE_BLOCKED` — пакет неполон или обнаружен риск, далее исправление с указанной resume stage.

`READY_FOR_RELEASE` — нормальный результат задачи без полномочий на deploy, но не синоним `DONE`.

### S27. `DEPLOY_EXACT_SHA`

Deploy не переключает ветку, не делает `pull main` и не пересобирает результат. Он продвигает только
разрешённые immutable digests из release manifest и после запуска сверяет `/version` по `git_sha +
artifact_digest` для backend, worker и frontend. Migration plan заранее доказывает backward
compatibility, backup/restore и отдельно допустимость rollback; если down-migration опасна,
автоматический rollback откатывает приложение, но не врёт об откате данных. Несовпадение или smoke
failure останавливает release и исполняет заранее проверенный stop/rollback plan.

### S28. `PRODUCTION_MONITORING`

До release подписывается `monitoring_plan`: запрос/знаменатель qualifying events, expected effects,
окно, minimum sample, error/invariant thresholds и автоматический stop/rollback trigger. Измеряется
отношение `qualifying_events → expected_effects`, failures, invariants и error signals.

- `PRODUCTION_TRACE_PASSED` → `DONE`;
- `MONITORING_NO_TRAFFIC` → остаётся `MONITORING` с reason `WAITING_SIGNAL` до события или заранее
  определённой эскалации, но не становится `DONE`;
- `PRODUCTION_TRACE_FAILED` → incident, stop/rollback по plan и rework с указанной owning stage.

Для изменения без бизнес-трафика monitoring plan может заранее определить runtime/smoke trace как
достаточный оракул; это решение нельзя добавить после выката ради зелёного статуса.

### 19.1. Сводная таблица переходов

Именно эта последовательность переносится в `pipeline.yml`. `next_enabled_stage` означает первую
обязательную стадию ниже по total order после проверки traits и risk. Так условная стадия не создаёт
обрыва маршрута. Каждая отключённая стадия требует `NOT_APPLICABLE_VERIFIED`, а не отсутствие строки.
Для каждой строки validator разрешает только перечисленный pass verdict, custom verdict из описания
стадии и два schema-generated исхода `<STAGE_ID>_REWORK` / `<STAGE_ID>_BLOCKED`. Последний валиден
только с blocker и resume condition по разделу 31; иначе receipt отклоняется.

| Стадия | Включается | Допустимый принятый verdict | Следующая |
|---|---|---|---|
| S01 Intake | всегда | `TASK_INTAKE_READY` | S02 |
| S02 Impact | всегда | `IMPACT_CLASSIFIED` | `next_enabled_stage` |
| B01 Bug Reproduction | `bug` | `REPRODUCED`, `NOT_REPRODUCED` или `INTERMITTENT` | B02 либо observation loop |
| B02 Expected Behavior | `bug` | `DEFECT_CONFIRMED`, `EXPECTED_BEHAVIOR`, `DUPLICATE` или typed waiting | B03, B04, reclassification либо waiting |
| B03 Root Cause/Escape | подтверждённый `bug` | `ROOT_CAUSE_ESCAPE_READY` | `next_enabled_stage` |
| B04 Investigation Closure | доказанный `NO_DEFECT` или `DUPLICATE` | `INVESTIGATION_DONE` | terminal без fake Dev/release |
| S03 Research | `external_contract`, `new_domain` или `new_module` | `RESEARCH_READY` | `next_enabled_stage` |
| S04 Research Critic | любой `external_contract`, `new_domain` или `new_module`; low/medium external — узкая проверка | `RESEARCH_PASSED` | `next_enabled_stage` |
| S05 Process Map | `new_domain`, `new_module` или `process_change` | `PROCESS_MAP_READY` | `next_enabled_stage` |
| S06 GAP | `new_domain`, `new_module` или `process_change` | `GAP_READY` | `next_enabled_stage` |
| S07 Product Domain | `new_domain`, `new_module` или `process_change` | `PRODUCT_DOMAIN_APPROVED` | `next_enabled_stage` |
| S08 Behavior/Block | runtime change либо explicit N/A audit | `BEHAVIOR_CONTRACT_READY` или `NO_RUNTIME_BEHAVIOR` | `next_enabled_stage` |
| S09 UX Contract | `ui_change` | `UX_CONTRACT_READY` | `next_enabled_stage` |
| S10 Design Review | `ui_change` | `DESIGN_APPROVED` | `next_enabled_stage` |
| S11 Product Contract | всегда | `PRODUCT_CONTRACT_APPROVED` | `next_enabled_stage` |
| S12 Task Cut | всегда; для атомарной задачи pass-through | `TASK_CUT_READY` | `next_enabled_stage` |
| S13 Architect Plan | `new_domain`, `new_module`, несколько карточек, database/worker или high/critical risk | `ARCH_PLAN_READY` | `next_enabled_stage` |
| S14 Falsification | `new_domain`, `new_module`, conflicts или high/critical risk | `ARCH_REVIEW_PASSED` | `next_enabled_stage` |
| S15 Case Factory | всегда | `CASES_READY` + `CASE_AUDIT_PASSED` | `next_enabled_stage` |
| S16 Card Product Gate | всегда | `PRODUCT_APPROVED_FOR_DEV` | `next_enabled_stage` |
| S17 Workspace | всегда | `WORKSPACE_READY` | `next_enabled_stage` |
| S18 Development | всегда | `DEV_DONE` | `next_enabled_stage` |
| S19 Test Automation | всегда | `CASES_EXECUTABLE` | `next_enabled_stage` |
| S20 Code Review | всегда | `CODE_REVIEW_PASSED` | `next_enabled_stage` |
| S21 Docs/Registries | всегда, включая explicit N/A | `DOCS_REGISTRY_PASSED` или `DOCS_REGISTRY_NA_VERIFIED` | `next_enabled_stage` |
| S22 Functional Testing | всегда | `FUNCTIONAL_TESTS_PASSED` | `next_enabled_stage` |
| S23 Integration | всегда | `INTEGRATION_PASSED` | `next_enabled_stage` |
| S24 Design Implementation | `ui_change` | `DESIGN_IMPLEMENTATION_APPROVED` | `next_enabled_stage` |
| S25 Product Acceptance | browser для operator flow; иной explicit acceptance surface для pure internal | `FINAL_ACCEPTANCE_APPROVED` из допустимого typed receipt | `next_enabled_stage` |
| S26 Release Authorization | всегда как явная развилка | `RELEASE_AUTHORIZED`, `READY_FOR_RELEASE` либо `RELEASE_BLOCKED` | S27, ожидание команды либо typed rework |
| S27 Immutable Deploy | только `RELEASE_AUTHORIZED` | `DEPLOYED_EXACT_ARTIFACT` | S28 |
| S28 Monitoring | после deploy | `PRODUCTION_TRACE_PASSED`, `MONITORING_NO_TRAFFIC` или `PRODUCTION_TRACE_FAILED` | `DONE`, monitoring либо rollback/rework |

Для любой warehouse/operator-visible карточки типизированным эквивалентом S25 может быть только
живой `PRODUCT_BROWSER_APPROVED`. Для чистого pipeline, CI или инфраструктурного изменения
acceptance surface называется заранее (`pipeline_meta_tests`, `worker_operation`, `data_invariant`)
и получает независимый receipt; молчаливое `N/A` запрещено.

### 19.2. Возвраты и блокеры

Успешная таблица выше не разрешает модели придумывать маршрут при ошибке. `pipeline.yml` хранит
exact mapping; контроллер выбирает его по typed finding, а не по свободному тексту.

| Где найдено | Тип результата | Обязательный возврат |
|---|---|---|
| B01–B04 | fixture/env/evidence/closure | repair, observability либо owning B-stage; B04 только с terminal proof |
| S03–S07 | research/process/GAP/product finding | самая ранняя S03/S05/S06, владеющая неверным входом |
| S08/S11 | behavior/oracle/product contract | S08; при конфликте оракулов — typed waiting |
| S09/S10 | UX/design | S09; если неверен process — S05 |
| S12 | неверная нарезка | S12 |
| S13/S14 | plan/conflict | S13 |
| S15/S16 | case, contract или card finding | S15, S08 или S12 по типу finding; затем новый S16 receipt |
| S17 | workspace/isolation | rehydrate S17, не Product/Dev rework |
| S18 | implementation | S18 |
| S19 | case/harness/implementation binding | S15, S19 или S18 соответственно |
| S20 | contract/plan/implementation/automation/migration | S08, S13, S18, S19 или owning database receipt |
| S21 | docs/registry integrity | S21 либо стадия-владелец неверного факта |
| S22 | product/case/fixture/env/flaky | S18, S15, repair S22 или flake remediation соответственно |
| S23 | merge/regression/artifact | виновная карточка S18/S19/S20, затем полный S23 |
| S24 | implementation/mockup/process | S18, S09 или S05 соответственно |
| S25 | Product finding | typed owning stage S18/S09/S08/S05; затем заново весь invalidated downstream |
| S26 | неполный release packet | стадия-владелец отсутствующего receipt |
| S27/S28 | deploy/trace failure | stop/rollback + incident + typed owning stage |

Любой `*_BLOCKED` обязан ссылаться на допустимый blocker раздела 31 и `resume_stage`; иначе это
`REWORK` или orchestration incident, а не остановка задачи.

---

# ЧАСТЬ V. ТЕСТОВАЯ ФАБРИКА И ДОКАЗАТЕЛЬСТВО ЦЕЛЬНОГО ПРОЦЕССА

## 20. Карточка кейса

Обязательная схема:

```yaml
id:
title:
screen:
zone:
process:
actor_role:
tenant:
seller:
warehouse:
device:
fixture:
fixture_version:
fixture_builder:
external_mode:
preconditions:
adjacent_state:
variant:
steps:
executor_type:
executable_ref:
test_id:
automation_status:
timeout:
expected_ui:
expected_api:
expected_authorization:
expected_transaction:
expected_db:
expected_worker:
expected_external:
expected_print:
read_back:
reload_assertion:
oracle:
oracle_version:
related_blocks:
related_incidents:
status:
```

Для мутации доказательная цепочка проходит применимые звенья:

```text
screen → action/scan → API → authorization → transaction → DB → worker
→ marketplace/print → read-back → reload screen
```

Проверка одного метода или HTTP 200 не доказывает пользовательский процесс.
Каждое ребро impact/resource graph получает evidence либо независимо подписанную причину N/A.
Для user-visible мутации `screen`, `action/scan`, `read-back` и `reload` никогда не могут быть N/A;
для фонового эффекта обязательны enqueue, worker effect, durable write и read-back через потребителя.

## 21. Статусы кейсов

- `GOLD` — ожидание подтверждено оракулом. Красный блокирует интеграцию.
- `SNAPSHOT` — зафиксировано текущее поведение без решения «так должно». Изменение требует triage
  и блокирует release до классификации, но не объявляется дефектом автоматически.
- `QUESTION` — противоречие без ответа. Становится blocking/non-blocking decision item.
- `FLAKY` — невоспроизводимый результат. Не исключается молча; получает owner и ремонт.
- `QUARANTINED` — допускается только с причиной, owner, issue и сроком; просрочка блокирует release.

## 22. Изоляция прогонов

Каждый run получает уникальные:

- database/schema;
- tenant/seller/warehouse fixtures;
- Redis namespace;
- Celery queue;
- ports;
- emulator namespace;
- object storage prefix;
- evidence directory.

Test network работает fail-closed: исходящий трафик запрещён, allowlist содержит только явно
разрешённые emulator/sandbox endpoints. Ошибка конфигурации не должна приводить к живому WB/Ozon.

Сброс БД без сброса очереди, Redis, worker и emulator не считается свежим состоянием.

Каждый мутирующий case получает fresh snapshot/transaction либо входит в явно ordered journey group.
Clock и random seed фиксируются; перед assert действует worker drain+ack barrier. После case/run
создаётся teardown/TTL receipt, в том числе после crash. По умолчанию доступен только локальный
emulator; внешний sandbox разрешается лишь для именованного test tenant отдельным receipt.

## 23. Масштаб

Количество кейсов определяется покрытием состояний и рисков, а не целевой цифрой. Тысячи кейсов
допустимы, если они детерминированы и исполняются runner. AI используется для исследования,
генерации, разрушения и triage; массовое повторяемое исполнение автоматизируется.

Полный регресс масштабируется только после доказанной изоляции. Ширина потоков увеличивается по
CPU, RAM, DB connections, queue lag и flake rate, а не по постоянному числу в документе.

---

# ЧАСТЬ VI. РЕЕСТРЫ И ДОЛГОВЕЧНАЯ ПАМЯТЬ

## 24. Реестр экранов

`frontend/screens.registry.json` хранит стабильные screen id, route, component, zones, files,
shared owners, процессы, API/data/worker/print/mobile links. Новый экран или новая зона не могут
закрыть наряд без записи в реестре.

## 25. Реестр процессов

`docs/product/processes.json` связывает физические и цифровые шаги, экраны, таблицы, внешние
события и кейсы. Он обновляется любой задачей, изменившей процесс. Без него adjacent selection
считается недоказанным.

## 26. Реестр дефектов и инцидентов

Один файл на дефект предотвращает конфликты параллельной записи:

```text
incidents/INC-YYYYMMDD-NNN/incident.yaml
```

Обязательные поля:

```yaml
id:
source:
detected_at: production | staging | test | review
reported_at:
symptom:
business_damage:
screen:
zone:
process:
surface: [ui, api, worker, database, print, external]
actor_role:
tenant_scope:
expected_behavior:
oracle:
reproduction_status:
fixture:
root_cause:
escaped_because:
fingerprint:
fingerprint_version:
fingerprint_fields: [screen, process, operation, normalized_symptom_or_error, contract]
reopened_from:
regression_cases:
fix_sha:
code_review_verdict:
functional_verdict:
product_browser_verdict:
production_trace:
disposition:
status:
```

Допустимые disposition имеют разные contracts:

- `FIXED_RELEASED` — root cause/escape, cases, fix SHA, review, tests, Product Browser и production trace;
- `FIXED_NOT_RELEASED` — те же pre-release receipts и честный `READY_FOR_RELEASE`;
- `NO_DEFECT` — подтверждённый expected-behavior oracle и Product receipt, без фиктивного fix SHA;
- `DUPLICATE` — canonical incident id и incident-triage receipt;
- `CANNOT_REPRODUCE_MONITORING` — observability policy, signal, срок и automatic reopen; не закрывается
  как исправленный дефект.

Fingerprint строится контроллером из нормализованных полей и version, а near-duplicate проходит
incident-triage. Повтор после `FIXED_RELEASED` создаёт `REGRESSION_AFTER_FIX` с `reopened_from` и
повышенным приоритетом.

## 27. Остальные постоянные реестры

- `docs/product/blocks.json` — блокировки и доказательство ущерба;
- `docs/product/contracts/<system>.json` — поле, версия, источник, дата и срок revalidation;
- `cases/` — versioned case cards;
- `fixtures/` — именованные воспроизводимые состояния;
- `frontend/src/ui-kit/` — канонические компоненты;
- `docs/etalon/<screen>/<zone>/` — принятые визуальные эталоны зон;
- `docs/ENV-RU.md` — идентификаторы окружений и ссылки на места секретов, но не значения;
- `tasks/_wave/<id>/BOARD.json` — машинная доска, генерирующая короткий Markdown-вид.

---

# ЧАСТЬ VII. РОЛИ, ИЗОЛЯЦИЯ И ПАРАЛЛЕЛИЗМ

## 28. Роли

| Роль | Обязанность | Не имеет права |
|---|---|---|
| `dispatcher` | сохранить intake и признаки | выбрасывать или переписывать просьбу |
| `impact-classifier` / `screen-mapper` | traits, risk, surfaces и stable screen id | занижать профиль ради короткого маршрута |
| `impact-reviewer` | независимо проверить профиль и N/A | подтверждать собственную классификацию |
| `bug-investigator` | reproduce, oracle, root cause и escape | чинить только symptom без causal receipt |
| `business-analyst` | versioned behavior contract | принимать реализацию |
| `researcher` | domain dossier и field contract | писать внешние факты по памяти |
| `research-critic` | искать пропуски независимо | принимать research из вежливости |
| `process-architect` | цельный складской процесс | рисовать UI до процесса |
| `gap-analyst` | reuse/extend/new/reject | плодить дубли без доказательства |
| `product-domain` | принять процесс | придумывать внешний контракт |
| `product-contract` | принять общий behavior/UX contract | утверждать ещё не созданную atomic card |
| `product-card` | принять exact card + cases перед Dev | принимать пакет с изменившимся hash |
| `block-auditor` | доказать ущерб блокировки | сохранять правило без кейса |
| `screen-designer` | макеты из kit | своя случайная вёрстка |
| `design-judge` | суд по канону | verdict «не нравится» |
| `architect-1` | resource graph и план | считать конфликты на глаз |
| `architect-2` | независимая фальсификация | читать первый план до своего |
| `arbiter` | разрешить расхождения | оставить high-risk conflict открытым |
| `case-writer` | прямые cases с oracle | подгонять expectation под код |
| `case-breaker` | разрушительные варианты | редактировать прямой кейс |
| `case-auditor` | проверить coverage matrix | дописывать покрытие и принимать его сам |
| `atomic-dev` | одна approved card | менять scope и принимать себя |
| `test-automation` | привязать cases к runners | менять oracle под реализацию |
| `reviewer` | независимый review | подменять Product Browser |
| `docs-aggregator` | shards, registry и integrity | переписывать факты без owning receipt |
| `runner` | детерминированно исполнять | решать, как должно быть |
| `triage` | классифицировать расхождение | менять oracle без источника |
| `product-browser` | живой конечный процесс | засчитывать Playwright вместо кликов |
| `release-controller` | exact-SHA и rollback | выбирать другой SHA |

Модель — capability role, задаваемая конфигурацией, а не ручной ночной выбор владельца. При
недоступности конкретной модели контроллер использует разрешённый fallback того же класса или
паркует роль; он не заменяет сильную принимающую роль дешёвой.

`pipeline.yml` содержит incompatibility matrix. Минимально несовместимы: researcher↔research-
critic, architect-1↔architect-2, case-writer↔case-breaker/case-auditor, atomic-dev↔reviewer/design-
judge/product-card/product-browser, любой artifact producer↔его approver. Одна identity не обходит
это сменой имени роли; CI сверяет controller-issued bindings.

## 29. Resource locks

Параллельно идут только карточки без пересечения по:

- файлу и shared component;
- screen zone;
- API/service;
- таблице/миграции;
- Redis/Celery namespace;
- external contract;
- print template;
- mobile consumer;
- warehouse process.

Новая обнаруженная граница сначала возвращается архитектору и пересчитывает locks. Агент не
расширяет scope молча.

Lock выдаёт только контроллер как lease с fencing token. Ресурсы захватываются в одном каноническом
порядке; upgrade сначала освобождает набор и запускает replan, поэтому взаимная блокировка не
лечится ручным снятием. Запись с устаревшим token отклоняется даже после истечения lease. Acquire,
renew, release и forced expiry остаются в append-only audit.

## 30. Возобновление

Каждый agent run имеет lease и heartbeat. После timeout контроллер проверяет receipt, journal и Git,
а затем идёт по remediation ladder: fresh environment → alternate capable executor/model →
diagnostic role → split/replan. Повторный crash агента или команды сам по себе не является blocker.
`PARKED` допускается только при доказанном blocker из раздела 31 либо исчерпанном заранее заданном
владельцем compute budget; во втором случае формируется полный recovery packet. По умолчанию
стоимостного лимита нет.

После рестарта контроллер читает state, сверяет branch/worktree/SHA/environment и продолжает с
последнего валидного receipt. Перезапуск с начала без необходимости запрещён.

---

# ЧАСТЬ VIII. БЛОКЕРЫ, ВОПРОСЫ И АННУЛИРОВАНИЕ VERDICT

## 31. Настоящие блокеры

Работа может остановиться только если:

- требуется конкретный доступ или разрешение владельца;
- внешний контракт неизвестен и безопасно непроверяем;
- действие необратимо или может повредить данные;
- есть финансовый, регуляторный, security или tenant risk;
- конфликтуют подтверждённые оракулы;
- отсутствует безопасная fixture/environment;
- baseline или release SHA не установлены;
- исчерпан явно заданный владельцем compute budget.

Каждый blocker содержит evidence, причину невозможности продолжения, точное действие разблокировки,
ответственного и resume stage.

## 32. Non-blocking решения

Обратимые UX/implementation решения Product или Architect принимают самостоятельно по канону,
существующим процессам и лучшей проверяемой практике. Они записываются в decision log, но не будят
владельца ночью.

Вопросы владельцу собираются одним пакетом. Blocking-вопросы не позволяют начать зависимую
разработку; независимые карточки продолжаются.

## 33. Инвалидация

Каждый receipt перечисляет hash-linked `depends_on`. Контроллер строит dependency DAG — граф
зависимостей — и при изменении входа транзитивно аннулирует всех потомков. Ручной список ниже —
обязательный минимум и метатест, а не единственный механизм:

- source/requirement → всё после intake;
- process map → Domain Product, behavior/UX, cards, cases и downstream;
- behavior/UX/design → Product Contract, cards, cases и downstream;
- card/case/oracle → S16, automation binding и весь downstream;
- code/test change → S19–S25 и release receipts;
- docs/registry hash, влияющий на contract/process → S21 и зависимый downstream;
- integration SHA/tree/artifact digest → S23–S28;
- release manifest/SHA/digest → release authorization, deploy и monitoring.

Verdict привязан к hash входов и не переносится на новую версию «по смыслу».

---

# ЧАСТЬ IX. ДОКАЗАТЕЛЬСТВА И БЕЗОПАСНОСТЬ

## 34. Evidence manifest

`docs/evidence/<task-id>/manifest.json` содержит:

```yaml
task_id:
wave_id:
source_hash:
pipeline_hash:
code_sha:
integration_sha:
artifact_digests:
release_manifest_digest:
migration_head:
environment_id:
role:
tenant:
case_ids:
fixture_versions:
browser:
device:
timestamps:
producer:
commands:
artifact_hashes:
redaction_status:
```

Raw HAR, Authorization, cookies, токены, пароли и чувствительные тела запросов в Git запрещены.
В Git попадают только санитизированные structured logs, маскированные screenshots и manifest.
Secret scan блокирует commit/CI.

Evidence schema работает по allowlist и классифицирует данные как public/internal/PII/secret.
До записи редактируются argv/env, URL query, headers, logs и screenshot OCR; tenant, seller, order,
barcode и marking code заменяются стабильными псевдонимами. Нужный для диагностики raw artifact
хранится только в access-controlled store с TTL и никогда не попадает в Git. Любой сохраняемый
artifact требует fail-closed `REDACTION_VERIFIED`; один regex secret scan не считается достаточным.

## 35. Baseline

До любой проверки фиксируются branch/git SHA и artifact digests приложения, frontend, API, worker,
mobile и migration, migration head, environment, external mode, tenant, fixture и evidence
directory. Неизвестная, пересобранная или смешанная версия даёт `BASELINE_BLOCKED`, а не
предположение.

## 36. Честность доказательства

- screenshot доказывает только видимое состояние;
- HTTP 200 не доказывает бизнес-эффект;
- запись в БД не доказывает read-back и UI;
- Playwright доказывает автоматизированный сценарий, но не Product approval;
- Code Review доказывает качество реализации, но не удобство процесса;
- Product Browser без точного SHA и role/tenant не засчитывается;
- зелёный стенд не доказывает production deploy.

---

# ЧАСТЬ X. CI, MERGE, DEPLOY И УТРЕННИЙ ОТЧЁТ

## 37. Обязательные CI-ворота

CI проверяет:

1. pipeline version/hash;
2. повторную impact classification по diff;
3. полный required-stage set;
4. receipt каждой обязательной стадии;
5. независимость ролей;
6. разрешённый scope полного Git diff;
7. отсутствие конфликтующих locks;
8. commit/test/case/evidence linkage;
9. green GOLD cases и invariants;
10. отсутствие untriaged SNAPSHOT_CHANGED и просроченных quarantine;
11. sanitization/secret scan;
12. отсутствие неавторизованных изменений управляющего контура; для `pipeline_change` — signed
    owner authorization, isolated control-plane review и все metatests;
13. валидный S25 receipt по declared acceptance surface; для operator flow — Product Browser;
14. exact integration SHA/tree и immutable artifact digests;
15. подпись, role binding и incompatibility каждого receipt;
16. runnable binding каждого required case;
17. typed receipts для применимых migration/worker/tenant/mobile/print traits;
18. post-dev Design Implementation verdict для `ui_change`.

Локальные hooks помогают раньше, но не являются источником правды.

## 38. Definition of Done

У задачи с изменением есть три разных уровня завершения, и в отчёте нельзя подменять один другим:

- `IMPLEMENTATION_DONE` — код принят на точном integration SHA, все pre-release проверки и
  независимая acceptance пройдены, immutable artifacts собраны, ветка опубликована;
- `READY_FOR_RELEASE` — release packet собран, но production deploy не был разрешён;
- `DONE` — разрешённый SHA действительно работает в production и подтверждён production trace.

Для доказанного B04 no-change отдельный terminal `INVESTIGATION_DONE` означает только, что
расследование закрыто с `NO_DEFECT`/`DUPLICATE` и registry receipts. Он не называется реализацией,
release или production-ready результатом.

Если задача по договорённости не должна попадать в production, её честный конечный статус —
`IMPLEMENTATION_DONE` или `READY_FOR_RELEASE`. Слово «готово» без уточнения уровня запрещено.

Карточка `DONE` только когда:

- source и traits зафиксированы;
- все обязательные стадии имеют валидные receipts;
- Product Before Dev и применимая финальная S25 acceptance прошли; для operator flow — Product Browser;
- scoped commit существует и worktree чист;
- branch pushed;
- Code Review passed;
- обязательные cases и full integration regression зелёные;
- integration SHA известен;
- release state честно разделён на not authorized/deployed/monitoring/done;
- production trace прошёл; `MONITORING_NO_TRAFFIC` оставляет задачу в `MONITORING`;
- incident/cases/process/screen registries обновлены по impact;
- blockers и remaining risks названы.

## 39. Утренний отчёт

Одна страница на волну:

- исходная фраза владельца;
- что сделано и что осознанно не входило;
- capability coverage для нового домена;
- экран/процесс до и после;
- Product verdicts;
- tests: total, passed, findings, flaky, quarantined;
- commits, pushed branches, integration и deployed SHA;
- production trace;
- parked/blocking items и точное действие владельца;
- расходы и длительность как справочная метрика.

Агентские рассказы о том, «как всё хорошо», не заменяют числа, SHA и evidence.

---

# ЧАСТЬ XI. ПЛАН ТЕХНИЧЕСКОГО ВНЕДРЕНИЯ

## 40. Текущее состояние

В репозитории уже есть отдельные элементы: экранный реестр, Product gate-документы, UI-канон,
часть hooks/CI и реестр живых инцидентов. Они не образуют описанный выше controller. Текущий
`naryad close`, клиентские hooks и Markdown-галочки нельзя считать машинной state machine.

Из известных P0 перед активацией:

- production workflow выбирает SHA, а внутренний deploy-скрипт может переключить ветку; build-once
  artifact promotion и runtime digest verification пока отсутствуют;
- тестовая конфигурация должна быть fail-closed по внешней сети;
- scope и close должны проверяться одинаковым CI-валидатором для всех клиентов;
- старые и новые процессные документы нельзя оставлять параллельными канонами.

## 41. Этапы

### E-1. Safety fuse

- build-once immutable artifacts и deploy без `checkout main`/rebuild;
- runtime verification `git_sha + artifact_digest`, rollback command и stop criteria;
- deny-by-default test egress;
- fail-closed PII/secret redaction evidence.

### E0. Канонический машинный контракт

Создать:

```text
pipeline/pipeline.yml
pipeline/pipeline.schema.json
pipeline/task-state.schema.json
pipeline/receipt.schema.json
pipeline/evidence.schema.json
pipeline/case.schema.json
pipeline/incident.schema.json
```

Тот же activation PR атомарно задаёт `canonical_base_ref`, `integration_ref` и `release_ref`,
переводит процессные разделы `AGENTS.md` и `CLAUDE.md` в короткие pointers и supersede/archive:

```text
.dev/PROCESS.md
.dev/.dev/PROCESS.md
docs/CURSOR_PIPELINE_REFERENCE_RU.md
docs/WMS_FEATURE_GATE_PROTOCOL_RU.md
docs/WMS_PRODUCT_AGENT_RU.md
docs/process/PIPELINE-ADDITIONS-RU.md
docs/process/PIPELINE-DESIGN-RU.md
docs/process/TASK-PIPELINE-ARCHITECT-RU.md
```

Repo-safety, environment, Git и secret rules из `AGENTS.md` не архивируются. Activation имеет
отдельный rollback commit и одновременно обновляет entrypoints Claude/Cursor/Codex; частичное
переключение, при котором два клиента видят разные каноны, запрещено.

Перед activation validator строит grep/allowlist inventory всех process references, включая
`.cursor/skills/**`, `.cursor/rules/**`, `.cursor/hooks.json`, `.claude/agents/**`,
`.claude/settings*.json`, `.dev/roles/**` и `.dev/templates/**`. Каждый файл либо становится
versioned adapter/pointer к этому pipeline hash, либо архивируется. Любая живая ссылка на superseded
route блокирует activation.

### E1. State controller и единый validator

Команды:

```text
pipeline open
pipeline classify
pipeline advance
pipeline validate
pipeline resume
pipeline status
pipeline close
```

`close`, CI и deploy используют один validation engine.

### E2. Реестры и feedback loop

Связать screen, process, incident, block, case и contract registries. Перенести существующие
инциденты как candidate/GOLD только при наличии oracle.

### E3. Production-like isolated environment

Версионированные fixtures, безопасный sanitized subset только когда синтетики недостаточно,
изоляция DB/Redis/Celery/storage/emulator и воспроизводимый reset.

### E4. Role receipts и тестовая фабрика

Реализовать независимые roles, schemas, case generation, breakers, runner и triage. Сначала
инциденты и затрагиваемые решения, затем полный domain coverage без искусственного лимита кейсов.

### E5. Жёсткий Design system gate

Базовый W12 уже реализован: `ui_kit_usage_guard.py` запрещает новый экран или новую видимую
UI-зону без импорта `ui-kit`, а `ui-inventory.json` содержит раздел `components`. Дальше:
zone baselines, codemods переезда старого долга и связка с `invariants.js`.

### E6. Resumable `wave-driver`

Leases, heartbeat, retry, parking, locks, shards/aggregation, resource scheduling и recovery.

### E7. Метатесты

Все сценарии части XII должны быть зелёными.

### E8. Матрица профилей

Пять обязательных end-to-end примеров:

1. маленькая UI-правка;
2. backend bug;
3. внешний contract change;
4. пересекающаяся multi-card wave;
5. вертикальный slice нового домена.

Они не заменяют trait coverage. До активации каждый объявленный trait и risk-level исполняется хотя
бы один раз; отдельно обязательны migration/backfill/restore, worker retry/outage, tenant isolation,
print/scanner, mobile consumer, new module, emergency debt closure и составная high-risk волна.

### E9. Первая автономная ночь

Полная волна без ручного управления. Утром владелец получает отчёт за десять минут чтения.

### E10. Новый домен целиком

Только после успешных профилей и recovery test запускать полный Ozon-подобный модуль.

---

# ЧАСТЬ XII. МЕТАТЕСТЫ САМОГО КОНВЕЙЕРА

## 42. Обязательные сценарии до активации

Конвейер не считается железобетонным, пока автоматизированно не доказано:

1. Dev без `PRODUCT_APPROVED_FOR_DEV` не получает workspace.
2. Агент меняет файл вне scope — local guard и CI независимо блокируют.
3. Агент пытается изменить `pipeline.yml` обычной задачей — merge блокируется.
4. Агент умирает посреди стадии — задача возобновляется с последнего receipt.
5. Два агента требуют один файл, таблицу или процесс — контроллер сериализует.
6. При расширении diff профиль пересчитывается и добавляет недостающие стадии.
7. Product отклоняет макет — development и downstream не стартуют.
8. После `PRODUCT_BROWSER_APPROVED` изменился код — старый verdict аннулирован; изменение contract,
   card или cases аннулирует `PRODUCT_APPROVED_FOR_DEV`.
9. Case expectation пытаются переписать под код без oracle — CI блокирует.
10. GOLD case красный — integration блокируется.
11. SNAPSHOT изменился — release ждёт triage.
12. Evidence содержит token/cookie — commit или CI блокируется.
13. Test service обращается к production WB/Ozon — сеть блокирует запрос.
14. Worker одной задачи пытается обработать очередь другой — isolation test падает.
15. Deploy получил SHA A, но сервер/бандл показывает SHA B — deploy падает и откатывается.
16. Баг повторился после fix — создаётся `REGRESSION_AFTER_FIX` со старой историей.
17. `NOT_REPRODUCED` не закрывает баг, а переводит на наблюдение/данные.
18. Маленькая UI-правка не запускает полный domain research.
19. Изменение внешнего вызова всегда включает contract research и emulator cases.
20. «Подключить Ozon» включает полный `new_domain` profile.
21. Настоящий blocker паркует одну карточку, независимые продолжаются.
22. После рестарта машины controller восстанавливает всю волну.
23. Ни один рабочий агент не может принять собственный результат.
24. Ни одна карточка не получает `DONE` без commit, push, tests и финальных verdicts.
25. Утренний отчёт восстанавливается только из machine state, а не из памяти чата.
26. Worker подделывает роль reviewer/Product — controller signature и CI отклоняют receipt.
27. Истёкший worker пишет по старому lock — fencing token отклоняет запись.
28. Новый крупный внутренний модуль получает `new_module` research/process/GAP/falsification.
29. Required case без runnable binding блокирует functional stage.
30. UI-код без post-dev Design Implementation receipt не достигает Product Browser/release.
31. `MONITORING_NO_TRAFFIC` не переводит задачу в `DONE`.
32. Git SHA совпал, но artifact digest отличается — promotion/deploy блокируется.
33. Activation PR не обновил хотя бы один процессный entrypoint — новый канон не активируется.
34. Emergency profile без signed scope или immutable debt блокируется; после smoke статус не `DONE`.
35. Два мутирующих case в разном порядке дают тот же результат либо объявлены ordered journey.
36. Каждый failure verdict достигает typed owning stage, repair, waiting или rollback без тупика.
37. Изменение любого receipt input транзитивно аннулирует потомков dependency DAG.
38. Каждый trait создаёт declared stages, receipts, case dimensions и acceptance surface.
39. Migration release не проходит без совместимости, restore rehearsal и честной rollback policy.
40. Crash между external side effect и state update не повторяет effect благодаря idempotency journal.

## 43. Критерий активации

Новый процесс становится действующим только когда одновременно:

- E-1–E7 реализованы и сохранены в Git;
- CI и deploy используют один validator;
- все объявленные метатесты зелёные;
- вся матрица E8 прошла без ручного управления между стадиями;
- старые процессные каноны архивированы, а `AGENTS.md` указывает на этот документ и pipeline hash;
- владелец подтвердил активацию строкой ниже.

До этого статус: `TARGET_PIPELINE_NOT_ENFORCED`.

---

# ЧАСТЬ XIII. ПОДТВЕРЖДЕНИЕ ВЛАДЕЛЬЦА

Редактирование документа и реализация технических этапов не означают автоматическую активацию.

```text
PIPELINE_IMPLEMENTATION_APPROVED: 2026-08-20
PIPELINE_ACTIVATION_APPROVED: <дата или нет>
```

`PIPELINE_IMPLEMENTATION_APPROVED` разрешает строить controller и gates.
`PIPELINE_ACTIVATION_APPROVED` ставится только после критериев части XII.
