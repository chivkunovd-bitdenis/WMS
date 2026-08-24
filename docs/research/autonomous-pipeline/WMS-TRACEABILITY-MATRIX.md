# Матрица: проблема WMS → причина → внешнее evidence → целевое решение

## Как читать

Матрица не доказывает, что внешняя система целиком подходит WMS. Она показывает, какой конкретный
механизм подтверждает решение каждой локальной проблемы. Ссылки на карточки находятся в
`source-analyses/`; фактический локальный flow — в `CURRENT-PIPELINE-AS-EXECUTED.md`.

## 1. Нечёткое требование превращается в придуманный продукт

**Симптом.** Владелец называет модуль или отчёт без полного перечня сущностей и сценариев. Текущий
Product обязан закрыть все вопросы самостоятельно, поэтому assumption может стать новой обязанностью
оператора, сущностью или экраном.

**Корневая механика.** Нет различия между обратимым implementation default и необратимым product
decision. Вопросы собраны, но controller не имеет typed owner-gate policy.

**Внешнее evidence.** GOV.UK требует считать неподтверждённые предложения assumptions и начинать с
user/outcome, а не решения (`product-design/govuk-user-needs.md`, `govuk-discovery.md`). LangGraph и
Step Functions показывают явное persisted pause/callback state вместо скрытой остановки в тексте
(`primary/05-langgraph-durable-execution.md`, `primary/06-aws-step-functions-error-handling.md`).

**Решение.** `purpose.json` с evidence/assumptions; explicit reversible flag; `OWNER_GATE` только для
денег, необратимых данных, новой физической обязанности, внешнего контракта и полномочий. Независимые
карточки продолжаются.

**Проверка.** Pipeline test: нереверсивное assumption не допускает `BUILD`; название колонки — не
создаёт owner gate.

## 2. Дизайн начинается до ответа «для кого и зачем»

**Симптом.** Формально стройный экран не объясняет пользователю главное решение. На 07-reporting
Product сформулировал разумный контракт, но весь downstream loop проверял именно его, а не понимание
незнакомого пользователя.

**Корневая механика.** Acceptance проверяет contract conformance, geometry и prescribed clicks, но не
goal-based task. Один общий экран для двух ролей был принят как assumption без доказательства общей
главной задачи.

**Внешнее evidence.** GOV.UK связывает интерфейс с пользовательским outcome и реальным usability
test (`product-design/govuk-simple-service.md`). Прототип выбирается по конкретному исследовательскому
вопросу и минимальной достаточной детализации (`govuk-prototypes.md`).

**Решение.** До mockup: primary user, primary decision, necessary facts, evidence, non-goals и один
goal-based acceptance scenario. Две роли на одном UI требуют доказанного общего primary decision.

**Проверка.** Verifier получает вопрос, а не инструкцию по controls; записывает найденный ответ и его
интерпретацию.

## 3. Локальная правка превращается в redesign

**Симптом.** Видимый frontend-баг автоматически получает Sol Product/UX, standalone `MOCKUP.html` и
полную цепочку. Каждая роль может привнести новый элемент.

**Корневая механика.** Нет маршрута `PATCH`; mockup создаётся как самостоятельная страница; scope
allowlist появляется после contract, когда расширение уже легализовано.

**Внешнее evidence.** Shape Up задаёт appetite/boundaries/no-gos до проектирования
(`product-design/shapeup-set-boundaries.md`). Agentless последовательно сужает impact до конечного
repair set (`primary/08-agentless-source.md`). Hooks/policy gate способны остановить запрещённый tool
или path до изменения (`primary/02-claude-code-hooks.md`).

**Решение.** Отдельный `PATCH` route: baseline → annotated delta → file/zone allowlist → Builder →
Verifier. Никакого нового mockup. Добавление новой зоны автоматически останавливает task и требует
переклассификации в `CHANGE`.

**Проверка.** Fixture «поменять подпись одной кнопки» должен завершаться двумя модельными вызовами и
не создавать Product/UX/Architecture artifacts.

## 4. Слишком много ролей и вызовов

**Симптом.** Одна domain-card вызывает примерно 16–21 моделей до rework. Billing наблюдался как
многократные `20 → review → 7 → review → 4` atom loops.

**Корневая механика.** Механические проверки представлены ролями; backend/frontend одного поведения
разрезаны на последовательные контексты; независимость применяется между атомами, а не на acceptance
boundary.

**Внешнее evidence.** Agentless показывает finite staged artifacts без свободной команды ролей
(`primary/09-agentless-paper.md`). AWS/Baton показывают небольшой controller/worker path, хотя их
terminal criteria недостаточны (`code/01-*`, `code/03-baton.md`).

**Решение.** Shaper (по необходимости), Builder (один coherent vertical slice), independent Verifier.
Guards, browser execution, retry и report — код. Nominal calls: PATCH 2, CHANGE/MODULE slice 3.

**Проверка.** Controller metrics считают вызовы на accepted slice и сравнивают с baseline wave.

## 5. Pipeline нужно вручную пропихивать после падений

**Симптом.** После Docker/browser/model/controller failure состояние приходится восстанавливать по
журналам; повтор может стартовать не с той стадии.

**Корневая механика.** State — набор файлов и process observation, без transactional attempt ledger,
lease, claim-before-side-effect и reconcile.

**Внешнее evidence.** Agentflow сохраняет claim/checkpoint до provider dispatch и использует lease
fencing (`code/05-agentflow.md`). Temporal хранит event history (`field/temporal-durable-execution.md`).
Baton хранит queue/claim/retry state (`code/03-baton.md`).

**Решение.** SQLite `runs/tasks/attempts`, attempt `STARTED` до side effect, raw evidence до terminal
transition, resume reconciliation по process/worktree/HEAD/artifact.

**Проверка.** Chaos-test убивает controller: до model call, во время edit, после commit до state write,
во время test. Ни один сценарий не дублирует commit и не теряет task.

## 6. Docker/browser/test failure не классифицирован

**Симптом.** Инфраструктурный blocker мог превратиться в code finding и вызвать dev repair; текстовые
фразы позже частично исправили это, но parser остаётся хрупким.

**Корневая механика.** Нет structured failure enum, attempt evidence и централизованной retry policy.

**Внешнее evidence.** Argo различает pre-main pod restart и application retry
(`primary/07-argo-pod-restarts.md`). Playwright различает passed/flaky/failed
(`field/playwright-test-retries.md`). AWS/Google SRE ограничивают retry и предупреждают об amplification
(`field/aws-*`, `field/google-sre-*`).

**Решение.** Failure taxonomy в `TARGET-PIPELINE-DESIGN.md`; retry только для `ENV_PRESTART` и
`INFRA_TRANSIENT`, один diagnostic rerun для test; неизвестное не ретраится слепо.

**Проверка.** Table-driven controller tests на каждый failure class/attempt cap.

## 7. Зелёный со второго раза считается успехом

**Симптом.** Повторный тест может скрыть race/timing defect; morning report не отличает clean от flaky.

**Корневая механика.** Хранится финальный exit, а не история attempts и одинаковый SHA/environment.

**Внешнее evidence.** Playwright выделяет статус `flaky`; Google использует повтор для обнаружения
нестабильности, а не для стирания первого результата (`field/playwright-test-retries.md`,
`field/google-flaky-tests.md`).

**Решение.** `fail → pass` = `BLOCKED_FLAKY` или заранее разрешённый quarantine; оба artifacts
сохраняются.

**Проверка.** Искусственно flaky test никогда не выдаёт terminal clean.

## 8. Ролевой отчёт не совпадает с файловой системой/Git

**Симптом.** Агент может заявить созданный файл или готовый diff, которого нет; tests могут быть
ослаблены, а READY — не соответствовать commit.

**Корневая механика.** Controller доверяет existence/section больше, чем content/hash/commit, а
финальные claims не строятся машиной.

**Внешнее evidence.** Claude #4462/#9458 и Codex #24922 (`source-analyses/field/`).

**Решение.** Expected artifact manifest, JSON Schema, input/output hashes, Git diff verification,
semantic review test changes; итог генерирует controller.

**Проверка.** Fake agent response без файла; файл в другом worktree; report с неверным SHA; ослабленный
test — все должны fail closed.

## 9. Review приходит после дорогой неверной реализации

**Симптом.** Reviewer качественно нашёл дефекты широкого контракта, но после нескольких atoms и часов
работы.

**Корневая механика.** Scope/purpose hypothesis не имеет независимого дешёвого gate до Build.

**Внешнее evidence.** Shape Up ищет risk/rabbit holes до commitment (`product-design/shapeup-*`).
GOV.UK использует low-fidelity prototypes до production (`govuk-prototypes.md`).

**Решение.** Traceability + no-go + baseline-delta machine gate, первый vertical slice для module,
goal-based prototype acceptance для неизвестного UI.

**Проверка.** Module expansion запрещён до accepted first slice.

## 10. Rework дробится и зацикливается

**Симптом.** Каждый finding превращается в dev-atom; новый reviewer заново собирает картину; старый
repair plan продолжает жить после изменения diff.

**Корневая механика.** Findings не имеют ID/input SHA/affected files; repair не заморожен; retries
распределены между ролями.

**Внешнее evidence.** Typed Retry/Catch/max attempts Step Functions/Temporal; finite candidates
Agentless; retry budgets SRE.

**Решение.** `findings.json` с input SHA, один coherent repair по frozen set, max 2 rounds, repeated
signature terminates.

**Проверка.** После нового SHA старый verdict не принимается; один файл не делится между repairs.

## 11. Карточка «сделана», но фича не интегрирована

**Симптом.** Runner требует commit, но не push, PR/integration/full regression/deploy match. Общий
acceptor не объединяет branches.

**Корневая механика.** Terminal predicate заканчивается на card branch, а слово `СДЕЛАНО` сильнее
evidence.

**Внешнее evidence.** Большинство GitHub orchestrators также заканчивают PR, что показывает удобную,
но недостаточную границу (`code/01-*`, `code/03-baton.md`). GitHub workflows/branch checks отделяют
job/merge states (`primary/10-github-agentic-workflows.md`).

**Решение.** Явные `COMMITTED/PUSHED/INTEGRATED/CI_PASS/DEPLOYED/LIVE_ACCEPTED`; terminal `ACCEPTED`
вычисляется на одном candidate/integrated SHA.

**Проверка.** Push SHA mismatch или browser evidence другого SHA блокирует acceptance.

## 12. Общая волна блокируется одной карточкой

**Симптом.** `product-acceptor` не стартует до завершения всех карточек; один owner/browser blocker
лишает отчёта принятые независимые результаты.

**Корневая механика.** Run terminal агрегирован как all-or-nothing, а dependency graph не отделяет
независимые components.

**Внешнее evidence.** Durable task engines хранят per-task terminal state; Cezar/Baton имеют отдельные
run/queue records (`code/02-cezar.md`, `code/03-baton.md`).

**Решение.** Per-task terminal state; run report всегда формируется. Integration groups блокируются
только реальной dependency edge.

**Проверка.** Одна `WAITING_OWNER` карточка не останавливает publish другой без dependency.

## 13. Наблюдаемость путает живой процесс и реальный прогресс

**Симптом.** Process matcher говорит «идёт», хотя orchestrator умер или работает другая wave; наличие
artifact не означает accepted code.

**Корневая механика.** Нет lease/heartbeat по `run_id`, stage attempt и progress age.

**Внешнее evidence.** Agentflow lease fencing/heartbeat (`code/05-agentflow.md`), Temporal workflow ID
and history (`field/temporal-durable-execution.md`).

**Решение.** Lease owner, heartbeat, current attempt ID, last durable transition, stale threshold;
status читает SQLite, не глобальный `pgrep`.

**Проверка.** Два controller одного run не получают lease; stale takeover fencing блокирует старый.

## 14. Итоговое покрытие исходных требований владельца

| Требование | Где закрыто |
|---|---|
| обычная диктовка задач вечером | input handshake + `request.raw.md/request.json` |
| новый модуль целиком | `MODULE` + first vertical slice + expansion/integration |
| минималистичный осмысленный дизайн | purpose/element/no-go/goal-based gate |
| локальная правка не редизайнит экран | `PATCH`, baseline delta, zone/file allowlist |
| минимум ролей | Shaper/Builder/Verifier; остальное код |
| pipeline не нужно толкать | SQLite attempts, lease, reconcile, failure taxonomy |
| Docker/test/browser failures | отдельные classes и bounded recovery |
| подробные prompts/conditions/docs | `TARGET-PIPELINE-DESIGN.md` sections 8–16 |
| результаты research не теряются | отдельные source cards + Git branch |
| готовность честная | SHA-linked terminal predicate and report |
