# Общие паттерны и антипаттерны автономной разработки

## 1. Основание синтеза

Широкий поиск дал 279 каталожных записей:

- 99 репозиториев с кодом и workflow;
- 100 первичных технических документов, papers и официальных систем;
- 80 полевых инцидентов, issue, postmortem и reliability-материалов.

Внутри каждого каталога кандидаты дедуплицированы, но между тремя полосами намеренно есть пересечения:
например, один проект может присутствовать как код, paper и полевой incident. Это не 279 независимых
систем. Первый подробный слой содержит 34 отдельные карточки: 8 coding orchestrators, 10 первичных
agent/workflow источников, 10 reliability/failure материалов и 6 product/design источников. Выводы
ниже не опираются на количество ссылок само по себе. Каждый паттерн выводится из нескольких разных
классов evidence и затем проверяется против текущего WMS runner.

## 2. Центральный вывод

Надёжность не растёт пропорционально числу ролей. В исследованных системах устойчивость появляется,
когда **код владеет переходами, состоянием, лимитами и доказательствами**, а модель получает только
содержательное решение внутри узкой стадии.

Практически это означает три разных слоя:

```text
control plane: state, transition, retry, timeout, isolation, Git, evidence
model work: понять задачу, выбрать решение, написать/проверить изменение
acceptance: независимо доказать поведение на финальном SHA
```

Смешение этих слоёв создаёт ролевой театр: агенты пишут убедительные отчёты, но controller не знает,
что реально произошло.

## 3. Рабочий паттерн: внешнее durable state

### Механика

Состояние run должно жить вне процесса модели и вне её финального ответа. Temporal сохраняет event
history и восстанавливает worker через replay; LangGraph сохраняет checkpoints/thread state; Baton
держит persisted queue/claims/retries; Agentless передаёт конечные JSONL-артефакты между стадиями.

Минимальные поля состояния:

- `run_id`, `task_id`, `attempt_id`;
- текущая стадия и версия workflow;
- base SHA, worktree, branch, current HEAD;
- hash входного артефакта;
- started/finished timestamps;
- executor/model;
- terminal status;
- failure class/signature;
- paths к stdout/stderr/trace/screenshot/test report;
- счётчики retry/rework и расход бюджета.

### Почему это работает

После падения controller не спрашивает модель «что ты успела». Он сверяет database/event ledger,
Git и ожидаемые артефакты. Повтор начинается с последней доказанной границы.

### Граница применимости

Durable execution не делает решение правильным. Она только исключает потерю управляющего состояния.
Для WMS не требуется сразу Temporal: один orchestrator на одном хосте может надёжно начать с SQLite
и append-only attempt ledger.

Источники: `field/temporal-durable-execution.md`, `primary/05-langgraph-durable-execution.md`,
`code/03-baton.md`, `primary/08-agentless-source.md`.

## 4. Рабочий паттерн: typed transition, а не Markdown-разбор

### Механика

Результат стадии разделяется на:

1. человекочитаемый отчёт;
2. маленький машинный объект по JSON Schema.

Например:

```json
{
  "status": "pass",
  "input_sha": "...",
  "output_sha": "...",
  "findings": [],
  "evidence": ["..."],
  "next": "verify_ui"
}
```

Controller валидирует enum, обязательные поля, hashes и допустимость перехода. Модель не пишет `next`
произвольно: допустимое следующее состояние определяется таблицей workflow.

### Подтверждение

OpenAI Agents SDK и Pydantic-подобные runtimes демонстрируют typed tool/output validation; Step
Functions задаёт `Retry/Catch/Fail` структурой state machine; Claude hooks оборачивают tool call
детерминированным pre/post decision. Текущая строка WMS `ВЕРДИКТ: ...` — правильное движение в эту
сторону, но не полный контракт.

Источники: `primary/01-openai-agents-sdk-python.md`, `primary/02-claude-code-hooks.md`,
`primary/06-aws-step-functions-error-handling.md`.

## 5. Рабочий паттерн: hard artifact gate

### Механика

После работы агента controller самостоятельно проверяет:

- файл существует в назначенном worktree;
- соответствует schema/формату;
- относится к ожидаемому input SHA;
- реальный `git diff` совпадает с manifest;
- артефакт/изменение попало в отдельный commit;
- рабочее дерево не содержит посторонних изменений.

Полевые issues Claude #4462/#9458 показывают, что подробное сообщение подагента о созданном файле не
гарантирует существование файла. Codex #24922 показывает более опасную форму: финальный READY может
заявить изменение, которого нет в commit, и скрыть ослабление тестов.

### Вывод для WMS

Текущий file existence и checkpoint gate нужно сохранить, но расширить schema validation и связью с
input/output SHA. Само наличие `CONTRACT.md` или `JUDGE.md` не доказывает правильность их содержания.

Источники: `field/claude-code-4462-nonpersistent-writes.md`,
`field/claude-code-9458-hard-file-gate.md`, `field/codex-24922-false-completion.md`.

## 6. Рабочий паттерн: narrow action surface

SWE-agent показывает, что интерфейс между моделью и компьютером влияет на результат: ограниченные,
понятные действия и хорошо оформленные observations полезнее безграничного shell transcript.
Agentless идёт дальше и заменяет свободную trajectory конечными стадиями localization → repair →
validation.

Для WMS это означает:

- Shaper не имеет write-доступа к product code;
- Builder не меняет workflow, baseline, deploy или соседние карточки;
- Verifier не исправляет код;
- browser executor не выносит продуктовый вердикт;
- controller один владеет retry, Git checkpoint и переходом.

Права роли должны задаваться инструментами и filesystem policy, а не только фразой в prompt.

Источники: `primary/03-swe-agent-source.md`, `primary/04-swe-agent-paper.md`,
`primary/08-agentless-source.md`, `primary/09-agentless-paper.md`.

## 7. Рабочий паттерн: сначала цель пользователя, потом элементы

GOV.UK Service Manual требует отличать user need от заранее выбранного решения и рассматривать
неподтверждённые предложения как assumptions. Shape Up сначала ограничивает problem/appetite/no-gos,
а затем определяет элементы на низкой детализации.

Для нового WMS-модуля достаточный pre-design contract обязан отвечать:

- кто пользователь;
- что запускает его работу;
- какое решение/действие он должен выполнить;
- какой результат считается успешным;
- какие факты необходимы;
- чем это подтверждено;
- какие assumptions сделаны;
- что не входит;
- какой простой сценарий докажет понимание.

Для локальной правки полный discovery вреден. Нужны только baseline, точная delta, affected zone,
allowed files и `do_not_change`.

Источники: `product-design/govuk-user-needs.md`, `product-design/govuk-discovery.md`,
`product-design/govuk-simple-service.md`, `product-design/shapeup-set-boundaries.md`.

## 8. Рабочий паттерн: lowest sufficient fidelity

Макет нужен, чтобы ответить на вопрос, а не чтобы запустить обязательную UX-роль. Для нового flow
неизвестная навигация может требовать интерактивного прототипа. Для локальной кнопки достаточно
annotated screenshot или вообще текстовой delta.

Обязательный standalone HTML для каждого видимого бага имеет два отрицательных эффекта:

- повышает стоимость маленькой правки;
- даёт проектировщику чистый холст и поощряет переработать весь экран.

Правильная последовательность: purpose → information/flow sketch → только затем UI-kit fidelity,
если предыдущий вопрос пройден.

Источники: `product-design/govuk-prototypes.md`,
`product-design/shapeup-elements-risks-nogos.md`.

## 9. Рабочий паттерн: bounded coherent repair

Открытая Ralph-подобная петля удобна, но опасна без внешнего budget и нового evidence. Agentless
использует конечное число candidates; Step Functions и Temporal задают max attempts/non-retryable
classes; текущий WMS уже ограничивает rework.

Один отрицательный review должен породить один замороженный finding set и один связный ремонт по
сценарию/слою, а не отдельного разработчика на каждую строку. Повтор без изменения input, environment
или repair plan запрещён.

Stop condition:

- два содержательных repair rounds;
- либо повтор того же failure signature;
- либо исчерпанный task budget;
- после этого terminal `BLOCKED_REWORK`, не бесконечный цикл.

Источники: `primary/06-aws-step-functions-error-handling.md`,
`field/temporal-retry-policies.md`, `primary/09-agentless-paper.md`, WMS forensic.

## 10. Рабочий паттерн: failure taxonomy до retry

### Нужное различие

| Класс | Пример | Автоматическое действие |
|---|---|---|
| `ENV_PRESTART` | контейнер не дошёл до main process | пересоздать среду, максимум 2 |
| `INFRA_TRANSIENT` | сеть/model service temporary unavailable | backoff+jitter, максимум 2 |
| `PROCESS_CRASH` | controller/agent умер после checkpoint | reconcile и resume |
| `TEST_FLAKY_SUSPECTED` | fail, затем pass на чистом worker | сохранить оба, не считать clean |
| `TEST_DETERMINISTIC` | один failure повторён на том же SHA | route в repair |
| `CONTRACT_INVALID` | output не прошёл schema | исправить ту же стадию один раз |
| `SCOPE_VIOLATION` | diff вне allowlist | остановить попытку, не ревьюить |
| `REVIEW_FINDING` | независимая проверка нашла дефект | один coherent repair |
| `OWNER_DECISION` | необратимая бизнес-развилка | pause только этой карточки |
| `BUDGET_EXHAUSTED` | предел времени/стоимости | terminal blocker |
| `UNKNOWN` | неизвестная сигнатура | evidence + остановка, не retry storm |

### Основание

Argo отдельно рестартует pod, если main container доказанно не начинался. Playwright различает
passed/flaky/failed. Google testing practice использует rerun для диагностики, а не превращения
красного в зелёное. AWS и Google SRE предупреждают о retry amplification и требуют единого владельца
retry policy.

Источники: `primary/07-argo-pod-restarts.md`, `field/playwright-test-retries.md`,
`field/google-flaky-tests.md`, `field/aws-timeouts-retries-backoff-jitter.md`,
`field/google-sre-cascading-failures.md`.

## 11. Рабочий паттерн: evidence на попытку

Каждая test/browser attempt обязана сохранять:

- SHA и environment identity;
- command/scenario;
- exit code и duration;
- stdout/stderr;
- reporter JSON/JUnit;
- screenshot/video/trace для browser;
- failure class и signature;
- номер попытки.

Playwright trace полезен как диагностический артефакт, но не является продуктовой приёмкой. Важен
не красивый screenshot, а связь evidence с конкретным сценарием и SHA.

Источники: `field/playwright-trace-viewer.md`, `field/playwright-test-retries.md`.

## 12. Рабочий паттерн: terminal success сильнее PR или commit

AWS sample, Baton и многие GitHub-driven orchestrators заканчивают PR. Это хороший delivery boundary,
но недостаточный для WMS. Успех должен быть вычислен controller из доказательств:

```text
contract accepted
AND scope clean
AND code tests pass
AND independent review pass
AND browser task pass on candidate SHA
AND commit exists
AND branch pushed
AND integration checks pass on integrated SHA
AND [если был deploy] deployed SHA == accepted SHA
```

Любой более ранний статус должен иметь другое имя: `IMPLEMENTED`, `COMMITTED`, `PUSHED`, `CI_PASS`,
`STAGE_DEPLOYED`, `BROWSER_ACCEPTED`.

Источники: `code/01-aws-sample-autonomous-cloud-coding-agents.md`, `code/03-baton.md`,
`primary/10-github-agentic-workflows.md`, WMS Git contract.

## 13. Антипаттерн: роль как замена переходу

Добавление `requirement-critic`, `ui-critic`, `judge` или `acceptor` не гарантирует качество, если:

- вход не имеет machine schema;
- finding не содержит ID/class/evidence;
- controller не знает допустимый переход;
- отрицательный вердикт требует ручного запуска;
- роль проверяет документ, созданный той же неподтверждённой гипотезой.

Роль оправдана только при уникальном решении и независимом evidence. Механическая проверка должна
стать кодом.

## 14. Антипаттерн: self-consistent closed loop

Shaper придумывает product model, UX превращает её в contract, Developer реализует, reviewer и judge
проверяют соответствие тому же contract. Все могут быть качественными, но исходная гипотеза остаётся
непроверенной.

Кейс WMS 07-reporting это показывает: pipeline доказал соответствие своему контракту, но не
проверил, что пользователь без подсказки понимает отчёт и решает с его помощью задачу.

Разрыв петли — goal-based acceptance на реальном пользователе/независимом проверяющем либо прямое
owner approval purpose/low-fi structure до дорогой разработки.

## 15. Антипаттерн: retry как лечение

Retry оправдан только для transient failure или диагностического подтверждения flaky. Он не меняет:

- неверный продуктовый контракт;
- детерминированный тестовый defect;
- scope violation;
- неверный prompt;
- исчерпанную авторизацию.

Nested retries разных ролей и CI создают multiplicative cost. Политикой владеет один controller.

## 16. Антипаттерн: атомизация без вертикальной ценности

Разделение backend и frontend на десятки последовательных вызовов делает каждый atom формально
маленьким, но увеличивает handoff cost и откладывает проверяемое поведение. Нужен smallest coherent
vertical slice: data/API/UI/test, который можно наблюдать целиком, с внутренними checkpoint при
необходимости.

Один исполнитель может безопаснее реализовать связный slice в allowlist, чем шесть исполнителей — по
одному файлу. Независимость нужна на verifier boundary, а не между каждой строкой diff.

## 17. Антипаттерн: одинаковый путь для задач разного риска

Одна колонка, изменение действия существующего экрана и новый marketplace domain не требуют одной
цепочки. Полный Product/UX/Architecture path для локального изменения:

- повышает стоимость;
- создаёт дополнительные точки scope invention;
- замедляет feedback;
- заставляет делать mockup там, где baseline уже является макетом.

Маршрут должен быть функцией наблюдаемого риска и типа изменения, а не желания «не пропустить роль».

## 18. Что не следует копировать

- тяжёлый cloud control plane AWS ради одного локального runner;
- Temporal/Kubernetes только ради модного durable execution;
- PR-exists как terminal done;
- background-agent autonomous mode, обходящий review;
- 35–45 постоянных specialist roles;
- model-decided retries и свободный текст transition;
- high-fidelity prototype до purpose/scope gate;
- полный discovery для локальной правки;
- browser trace как замена пониманию продукта.

## 19. Минимальная комбинация, подтверждённая исследованием

Из всех рассмотренных подходов для WMS достаточно сочетать:

1. лёгкую typed state machine в SQLite;
2. отдельный Git worktree и pinned base SHA;
3. короткий purpose/scope contract, различный для patch/change/module;
4. одного Shaper только там, где действительно есть продуктовая неопределённость;
5. одного Builder на coherent vertical slice;
6. одного независимого Verifier;
7. детерминированные tests/policy/browser execution;
8. централизованную failure taxonomy и bounded recovery;
9. явный integration/release state;
10. evidence manifest, из которого controller вычисляет итог.

Это не окончательный дизайн API runner. Конкретная state machine, prompts и artifacts описываются в
`TARGET-PIPELINE-DESIGN.md`.
