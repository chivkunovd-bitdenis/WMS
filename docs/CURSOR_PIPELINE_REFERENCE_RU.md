# Справочник: агенты, субагенты, скиллы и правила Cursor

> **Назначение:** единый документ со всеми ролями, скиллами и правилами, которые подмешиваются в AI-агента в Cursor для этого проекта.  
> **Источники:** `~/.cursor/`, `AGENTS.md`, `.cursor/` в репозитории WMS.  
> **Версия пайплайна:** v2 (реформа 2026-06-10).  
> **Дата сборки:** 2026-06-26.

---

## Оглавление

1. [Как это устроено](#1-как-это-устроено)
2. [Иерархия приоритетов](#2-иерархия-приоритетов)
3. [Активные агенты пайплайна v2](#3-активные-агенты-пайплайна-v2)
4. [Deprecated-агенты](#4-deprecated-агенты)
5. [Субагенты Task (встроенные в Cursor IDE)](#5-субагенты-task-встроенные-в-cursor-ide)
6. [Глобальные скиллы](#6-глобальные-скиллы)
7. [Cursor-managed скиллы](#7-cursor-managed-скиллы)
8. [Скиллы репозитория WMS](#8-скиллы-репозитория-wms)
9. [Глобальные правила (~/.cursor/rules/)](#9-глобальные-правила-cursorrules)
10. [Правила репозитория WMS](#10-правила-репозитория-wms)
11. [User Rules (настройки Cursor)](#11-user-rules-настройки-cursor)
12. [Типовые цепочки по типу задачи](#12-типовые-цепочки-по-типу-задачи)
13. [Режимы Cursor](#13-режимы-cursor)
14. [Модели для субагентов](#14-модели-для-субагентов)

---

## 1. Как это устроено

В каждый чат Cursor подмешивает несколько слоёв инструкций:

| Слой | Где живёт | Что делает |
|------|-----------|------------|
| **System prompt** | Внутри Cursor | Как работать с инструментами, формат ответов, Task, режимы |
| **Global rules** | `~/.cursor/rules/*.mdc` | Пайплайн, гейты, стиль общения — на все проекты |
| **Global agents** | `~/.cursor/agents/*.md` | Роли для Task / subagent |
| **Global skills** | `~/.cursor/skills/` | Пошаговые инструкции для типов задач |
| **Workspace rules** | `AGENTS.md`, `.cursor/rules/` | Правила конкретного репозитория (WMS) |
| **User Rules** | Cursor Settings → Rules | Твои персональные правила (git, PR, деплой) |

**Единица работы в v2:** одна **фича** = один прогон цепочки агентов до Definition of Done.

**HANDOFF:** между агентами передаётся блок `---HANDOFF---` … `---END---`.

---

## 2. Иерархия приоритетов

При конфликте (сверху вниз):

1. Явный запрос пользователя в чате
2. System / tool instructions
3. `000-pipeline-v2-supersedes-v1.mdc` — v2 побеждает старый блок User Rules
4. Global rules с `alwaysApply: true`
5. Workspace rules (`AGENTS.md`, `wms-queue.mdc`, `wms-issues.mdc`)
6. Requestable rules (`external-contracts`, `ui-engineering-checklist`, `buglog-distillation`)
7. Скиллы — когда задача их требует

---

## 3. Активные агенты пайплайна v2

Файлы: `~/.cursor/agents/*.md`  
Маршрутизация: `~/.cursor/agents/orchestrator.md`, `~/.cursor/PIPELINE.md`

---

### 3.1 orchestrator

**Описание:** Orchestrator agent for Cursor dev pipeline. Determines task type, chooses the slim agent chain (spec → planner → builder → adversarial-reviewer → verifier), sends first agent with handoff.

**Роль:** маршрутизатор упрощённого пайплайна v2. Сам **не пишет код**.

**Что делает:**
- Определяет тип задачи (новый проект / фича / баг / UI / рефакторинг / релиз)
- Выбирает цепочку агентов и скиллов
- Формирует первый HANDOFF
- Перед `builder`: контрактный пакет показывается владельцу → ждёт `ок` / `Agent`
- После `verifier`: Feature Completion Report → стоп (если не continuous mode)

**Запрещено:**
- Кодить самому
- Вызывать deprecated-агентов
- Пропускать adversarial-reviewer перед verifier для нетривиальных изменений
- Считать задачу готовой без runtime proof

---

### 3.2 spec

**Описание:** Unified spec agent — discovery, requirements baseline, business process, domain model, and UX/UI contract prep. Replaces analyst, discovery, baseline-writer, business-process-analyst, domain-modeler.

**Роль:** единый агент спецификации. Из сырого ввода владельца выдаёт **контрактный пакет** для planner. **Не пишет код.**

**Выходной пакет (все применимые блоки):**
1. **Requirements Baseline** — проблема, outcome, scope, constraints, non-goals
2. **Discovery notes** — факты vs допущения; choice-вопросы при блокировках
3. **Business process** — роли, шаги, успех/ошибка, инварианты (если меняется user flow)
4. **Domain model lite** — сущности, статусы, lifecycle, инварианты
5. **UX/UI draft** — 2–3 паттерна + рекомендация; черновик UX/UI Contract; UI states matrix
6. **Technical flow L1** — trigger → call chain → async → external → DB → fallbacks
7. **MVP slice** — что в фиче / что отложить / как проверить

**Обязательные правила:**
- Choice-based вопросы только при блокирующих развилках
- Сценарии по-русски, без имён функций (`scenario-owner-readable.mdc`)
- Шаблон сценария — skill `scenario-contract` (единственный источник)
- Gap scan: противоречия и пробелы → choice-вопросы

**Следующий шаг:** planner (или ui-designer для сложного нового экрана)

---

### 3.3 planner

**Описание:** Development planner — scenario contract, flow trace, technical contract, step-by-step plan with verification per step.

**Роль:** превращает пакет spec в план реализации. **Не пишет код.**

**Вход:** контрактный пакет от spec + одобрение владельца `ок` / `Agent`

**Обязательные артефакты:**
1. **Scenario contract + Flow trace** — skill `scenario-contract`; flow trace для разработки
2. **Technical contract:**
   - Endpoints/events (method, path, auth, idempotency)
   - Request/response shapes
   - Error model (коды → что видит пользователь)
   - Async: queue, task_id, retry, stale recovery
   - DB/state writes
   - External APIs: method, codes, rate limits, fallbacks
   - Invariants
   - Regression tests to add
3. **Implementation plan** — малые шаги (≤5 файлов для рефакторинга); на каждый шаг: цель / файлы / проверка / runtime proof hint

**Следующий шаг:** builder

---

### 3.4 builder

**Описание:** Development builder — implement plan, write tests, produce runtime proof draft. Replaces separate test-engineer for standard flow.

**Роль:** реализация + тесты + черновик runtime proof.

**Обязательные правила:**
- `engineering-standards.mdc` на каждом шаге
- `external-contracts-gate.mdc` при интеграциях
- `small-steps-discipline.mdc` при рефакторинге
- Не начинать без scenario + technical contract от planner
- Не начинать UI без UX/UI Contract от spec / ui-designer

**Что делает:**
1. Реализует только по плану, минимальный diff
2. Тесты в том же изменении (skill `write-tests`)
3. Runtime proof draft — реальный вывод команд (`runtime-proof-gate.mdc`)
4. Обновляет `docs/DATA_FLOW.md` / `docs/LOGIC.md` при изменении flow
5. `TASKLOG.md` — запись (commit только по явной просьбе)

**Архитектура (FastAPI):**
- Routes: `app/api` — без бизнес-логики
- Logic: `app/services`
- Models: `app/models`
- DB: `app/db`
- Типы везде; конкретные except; logger, не print

**Запрещено:**
- Массовые requeue/reprocess без явной команды
- Параллельный путь той же логики «на всякий случай»
- Файлы >400 строк без плана разбиения
- Считать задачу готовой (это делает verifier)

**Следующий шаг:** adversarial-reviewer

---

### 3.5 ui-designer

**Описание:** UX/UI designer — patterns, UX/UI Contract, states matrix, visual baseline. Replaces ux-pattern-scout and ux-ui-designer.

**Роль:** выпускает UX/UI контракт, чтобы реализация не превращалась в «кашу». **Не пишет production-код.**

**Вход:** пакет от spec + существующие экраны проекта

**Обязательно:**
- Skill `ux-ui-contract` — финальный UX/UI Contract
- Skill `ui-states-matrix` — все состояния и допустимые действия
- `ui-engineering-checklist.mdc` — modal scroll, pointer events, race guards
- Visual baseline — на какой экран ориентируемся

**Выход:**
1. UX/UI Contract (полный)
2. UI states matrix
3. Visual baseline reference
4. Choice questions — только при UX-развилке, блокирующей реализацию

**Следующий шаг:** planner → frontend-ui-engineer

---

### 3.6 frontend-ui-engineer

**Описание:** Frontend UI engineer — React UI by UX/UI Contract, ui-engineering-checklist, responsive states.

**Роль:** реализует UI по контракту с инженерной дисциплиной.

**Вход:** UX/UI Contract + UI states matrix; `ui-engineering-checklist.mdc`

**Обязательно в коде:**
- Modal: `maxHeight: calc(100vh - Npx)`, body scroll внутри
- Drag/canvas: `pointerdown/move/up`, `user-select: none`
- Global shortcuts: игнорировать focus в input/textarea/contenteditable
- Async lists: guard от stale responses
- Polling: silent при фоновом refresh; pause при открытой модалке
- Таблицы в модалках: `tableLayout: fixed` или карточки на узких экранах
- Optimistic update после success actions

**После реализации:** responsive pass (`responsive-pass`); UI runtime proof

**Запрещено:**
- Перепроектировать UX без возврата в ui-designer
- Mouse-only handlers на canvas
- Блокировать primary UI await-ом тяжёлого sync

**Следующий шаг:** adversarial-reviewer

---

### 3.7 adversarial-reviewer

**Описание:** Adversarial code reviewer with fresh context — hunts races, dead code, duplicate paths, contract violations, UI mechanics. Replaces reviewer and self-review loop.

**Режим:** `readonly: true` — не переписывает фичу.

**Роль:** независимый ревьюер. Получает diff + требования + контракты **без истории чата автора**.

**Чек-лист (каждый пункт: OK / ISSUE / N/A):**

**A. Engineering standards**
- Один путь для одной бизнес-логики
- Фоновые задачи: enqueue после commit; уникальные task_id; идемпотентность
- Stale-recovery для running/pending
- Read endpoints не запускают тяжёлые side-effects
- Слои api → services → models/db
- Файл >400 строк — план разбиения
- Мёртвый код удалён
- Дубли validation rules сведены

**B. External contracts**
- HTTP method/endpoint/status codes сверены с документацией
- Ошибки 402, 429, timeout → видимый fallback
- Payload содержит заявленные поля

**C. Async / race (~35% багов)**
- Out-of-order responses игнорируются
- Optimistic UI vs server truth согласованы
- Celery revoke/reschedule не ломает flush

**D. UI mechanics**
- Modal: max-height + inner scroll
- Drag: user-select none; pointer events
- Global keydown не перехватывает input
- Polling: silent / pause when modal open
- tableLayout fixed / cards на узких экранах

**E. Tests**
- Регрессионный тест на суть бага, не implementation detail
- Тест проверяет контракт, не только 200 OK
- api/service изменены → tests/ изменены

**F. Scope & ops**
- Нет массовых side-effects без команды пользователя
- Env/migrations/docker согласованы

**Verdict:** APPROVE / APPROVE WITH WARNINGS / **BLOCK**

**Следующий шаг:** builder (fix) или verifier (if APPROVE)

---

### 3.8 verifier

**Описание:** Final verifier — CI gates, runtime proof validation, release checklist. Merges release-guard. readonly.

**Роль:** финальный гейт. Подтверждает готовность **только фактами** (команды + вывод).

**Проверяет:**
1. Scenario contract + runtime proof (не только текст)
2. UX/UI Contract + UI runtime proof (если UI)
3. Verdict adversarial-reviewer: BLOCK → не подтверждать
4. `git diff --name-only`, `git status`
5. Опасные зоны: migrations, alembic, /db/, auth, settings, .env, docker-compose, Caddyfile
6. **CI** (обязательно): ruff, mypy, pytest; frontend lint/build
7. **Runtime proof:** pytest -v, curl, celery log, Playwright — реальный вывод
8. Tests coverage warning: routes/services без tests/
9. **Release checklist:** миграции, env vars, secrets не в git, rollback, BUGLOG/TASKLOG

**Verdict:** **READY** / **NOT READY**

**Запрещено:**
- Подтверждать при красном CI
- Принимать текстовый proof без вывода команд
- Пропускать BLOCK от adversarial-reviewer

---

## 4. Deprecated-агенты

Файлы-заглушки в `~/.cursor/agents/`. При вызове — redirect и stop.

| Агент | Redirect | Бывшая роль |
|-------|----------|-------------|
| **analyst** | spec | Анализ требований |
| **discovery** | spec | Discovery |
| **baseline-writer** | spec | Requirements baseline |
| **business-process-analyst** | spec | Бизнес-процесс |
| **domain-modeler** | spec | Доменная модель |
| **backlog-slicer** | spec | MVP slice (теперь в spec) |
| **solution-architect** | spec / planner | Technical contract (теперь в planner) |
| **ux-pattern-scout** | ui-designer | Поиск UX-паттернов |
| **ux-ui-designer** | ui-designer | UX/UI дизайн |
| **reviewer** | adversarial-reviewer | Код-ревью |
| **test-engineer** | builder | Написание тестов |
| **refactorer** | builder + refactor-safe | Рефакторинг |
| **release-guard** | verifier | Release checklist |

---

## 5. Субагенты Task (встроенные в Cursor IDE)

Запускаются через инструмент **Task** (`subagent_type`). Это не файлы в `~/.cursor/agents/`, а встроенные типы Cursor.

### 5.1 Активные

| subagent_type | Описание |
|---------------|----------|
| **generalPurpose** | Универсальный агент для сложных многошаговых задач: research, поиск, выполнение |
| **explore** | Быстрый readonly-обход кодовой базы по паттернам и ключевым словам |
| **shell** | Специалист по терминалу: git, CI, bash-команды |
| **cursor-guide** | Документация Cursor: Desktop, IDE, CLI, Cloud Agents, Bugbot |
| **ci-investigator** | Разбор одного упавшего CI-check в PR → краткий root cause |
| **best-of-n-runner** | Изолированный git worktree для параллельных попыток / best-of-N |
| **orchestrator** | Маршрутизатор пайплайна v2 |
| **spec** | Unified spec agent |
| **planner** | Planner agent |
| **builder** | Builder agent |
| **ui-designer** | UI designer |
| **frontend-ui-engineer** | Frontend UI engineer |
| **adversarial-reviewer** | Adversarial reviewer (свежий контекст) |
| **verifier** | Verifier (readonly) |

### 5.2 Deprecated в Task UI

Те же redirect, что в §4: analyst, discovery, baseline-writer, business-process-analyst, domain-modeler, backlog-slicer, reviewer, test-engineer, refactorer, release-guard, ux-pattern-scout, ux-ui-designer, solution-architect.

### 5.3 Параметры Task

- `run_in_background` — фоновый запуск
- `readonly` — только чтение
- `model` — явная модель (см. §14)
- `resume` — продолжить предыдущего агента
- `interrupt` — прервать running-агента

---

## 6. Глобальные скиллы

Путь: `~/.cursor/skills/<name>/SKILL.md`

---

### 6.1 Активные скиллы

#### project-bootstrap
**Описание:** Собирает основу нового проекта (product brief, архитектуру, roadmap и backlog) через intake-вопросы.

**Когда:** старт нового продукта/проекта.

**Процесс:**
1. Intake — 8 вопросов одним сообщением (что делает продукт, пользователь, MVP, не-MVP, интеграции, деплой, дедлайн, что уже сделано)
2. Product brief, architecture overview, модули, roadmap, backlog, порядок фич
3. Артефакты в документах; **код не писать** до принятия плана

---

#### new-feature
**Описание:** Реализует новую функциональность безопасно и по шагам.

**Цепочка:** orchestrator → spec → planner → builder → adversarial-reviewer → verifier

**Процесс:**
1. spec: baseline, discovery, business process, domain, MVP slice, UX draft
2. planner: scenario contract + flow trace + technical contract
3. ui-designer при UI
4. Test coverage (WMS: `feature-test-coverage`)
5. План → скелет → логика → интеграция
6. Тесты, adversarial-reviewer, verifier + runtime proof

**Ограничения:** не менять архитектуру без нужды; не трогать несвязанное; не «готово» без проверки.

---

#### bugfix
**Описание:** Исправляет баги минимальными правками: локализация → причина → точечный фикс → регрессия.

**Цепочка:** spec (кратко) → planner → builder → adversarial-reviewer → verifier

**Процесс:**
1. Локализовать баг и причину
2. Scenario contract если сценарный баг
3. Минимальный фикс
4. Регрессионный тест
5. Scenario proof; BUGLOG + `buglog-distillation.mdc`

---

#### refactor-safe
**Описание:** Локальный рефакторинг без изменения поведения.

**Процесс:**
1. Что рефакторим и зачем; неизменяемый внешний контракт
2. Ограниченная зона (минимум файлов)
3. Не менять сигнатуры, ошибки, side effects
4. Объяснить, почему поведение не изменилось
5. Прогнать релевантные тесты

**Связь:** `small-steps-discipline.mdc` — ≤5 файлов/шаг.

---

#### write-tests
**Описание:** Полезные автотесты без избыточности и хрупкости.

**Процесс:**
1. Уровень: unit / integration / e2e (только если без полного сценария нельзя)
2. Positive, negative, edge cases; регрессионный смысл
3. Избегать таймингов, порядка выполнения, деталей реализации
4. Для queue/retry — проверить дубли и error path
5. Прогнать тесты перед завершением

---

#### scenario-contract
**Описание:** Единственный источник шаблонов сценария. Defines and verifies end-to-end user scenario contracts.

**Когда:** любой нетривиальный bugfix/feature с user-visible flow, API, background job, DB, queue/retry, UI.

**До кода — Сценарий (контракт):**
- Кто участвует
- Действие пользователя
- Что увидеть/получить
- Как система обрабатывает (смыслом)
- Что сохраняется/меняется
- Чего быть не должно
- Проверка «всё ок» (Дано/Когда/Тогда)
- Проверка «если сломалось»
- Для разработки (опционально): flow trace

**До «готово» — Проверка сценария (proof):**
- Где проверяли, что сделали, что увидели, что изменилось в данных
- Автотесты, остаточные риски
- **Обязательно runtime evidence** (`runtime-proof-gate.mdc`)

**Формат:** `scenario-owner-readable.mdc` — русский, без имён функций в основном тексте.

---

#### requirements-baseline
**Описание:** Extracts a stable Requirements Baseline from raw input.

**Когда:** любое нетривиальное изменение.

**Шаблон:**
- Problem / user intent
- Primary user outcome
- Success criteria (observable)
- Scope / Out of scope
- Constraints
- UX constraints (где в UI, navigation, pattern)
- Non-goals
- Open questions (choice-based)
- Assumptions

**Правила:** не просить заполнить бриф; извлекать из сырого ввода; UI placement hard-check.

---

#### deep-discovery-choice
**Описание:** Один глубокий discovery-pass; уточнения только choice-based (A/B/C/D + Agent).

**Процесс:**
1. Facts / implied intent / unknowns
2. UI placement hard-check
3. Только blocking unknowns → choice protocol
4. Discovery summary → feeds requirements-baseline

**Чеклист:** user/roles, workflow/pain, moment of success, data/entities, UI surface, failure modes, security, billing, observability, non-goals.

---

#### business-process
**Описание:** Formalizes business process: roles, steps, success/failure, invariants.

**Шаблон:** Actors, Trigger, Preconditions, Steps, Success outcome, Failure outcomes (top 3), Invariants, What must NOT happen.

---

#### domain-model-lite
**Описание:** Lightweight domain model: entities, statuses, transitions, invariants.

**Шаблон:** Entities (purpose, owner, fields), Statuses/lifecycle, Permissions, Invariants, Edge cases.

**Связь:** для WMS — align с `wms-domain-model`.

---

#### wms-domain-model
**Описание:** Доменная база WMS: глоссарий, сущности, инварианты.

**Глоссарий MVP:** Warehouse, Zone, Location, SKU/Product, Stock, Receiving, Putaway, Picking, Packing, Shipping, Inventory count.

**Инварианты:** stock moves only via transactions; Available = on_hand - reserved; location constraints в service layer.

---

#### design-new-screen
**Описание:** Проектирует новый экран через UX/UI спецификацию до кода.

**Процесс:**
1. Цель экрана и сценарий
2. UX-паттерн (modal/drawer/wizard/…) + референсы в проекте
3. Блоки и порядок
4. Primary/secondary actions; Save/Cancel/Close policy
5. empty/loading/error/success states
6. Визуальная концепция
7. Только потом — реализация

---

#### ux-ui-contract
**Описание:** Конкретный UX/UI contract — actions, close/save/cancel, states, validations.

**Шаблон:** Entry point, UX pattern, Layout blocks, Primary action, Secondary actions, Close policy, Form rules, State matrix (empty/loading/saving/success/error), Post-success, Visual baseline, Accessibility.

---

#### ui-states-matrix
**Описание:** UI states и allowed actions per state.

**Минимум:** idle, loading, editing (dirty), validating, submitting, success, error (recoverable/blocking).

---

#### ui-scenario-proof
**Описание:** UI working proof: happy + error path, actions clickable, close/save works.

**Шаблон:** Environment, Entry point, Happy path (steps/expected/observed), Error path, Actions verified (Save/Cancel/Close), Unsaved changes, States observed, Remaining UX risks.

---

#### design-system-apply
**Описание:** Единый visual baseline, ритм отступов, стиль карточек/таблиц/форм/кнопок.

**Baseline:** `Dashboard.html` или ближайший референс.

**Токены (пример):** accent `#5b4fd4`, positive `#16a34a`, negative `#dc2626`, radius-card `12px`.

---

#### visual-baseline
**Описание:** Visual baseline reference для UI work.

**Процесс:** найти референс → список элементов для consistency → проверить states (normal/hover/focus/disabled/error/loading).

---

#### responsive-pass
**Описание:** UI понятен на desktop/tablet/mobile.

**Процесс:** layout-сценарии, интерактивные элементы, overflow/переносы, главные действия не теряются.

---

#### e2e-user-scenarios
**Описание:** Стабильные Playwright e2e по TC-ID из Test coverage.

**Принципы:**
- Проверять что видит пользователь и итог процесса
- Селекторы: `data-testid`
- Без sleep; детерминизм данных
- Arrange (seed) → Act (UI) → Assert (UI + optional API/DB)

**WMS:** TC-ID в заголовке test() или комментарии; только строки Applies=Y.

---

#### ci-gates
**Описание:** Обязательные CI-гейты; нельзя «готово» без зелёного.

**Гейты:** ruff, mypy, pytest; npm run build; playwright test.

**WMS:** содержательный `### Test coverage` в PR; TC в e2e specs; bypass: `skip-test-coverage-check`.

---

#### release-prep
**Описание:** Готовность к merge/release.

**Чеклист:** feature flag, миграции, rollback, changelog, docs; опасные зоны (env, billing, auth, data flows).

---

#### autopilot-backlog
**Описание:** Автопилот по GitHub Issues: ready → vertical slice → gates → PR → next.

**Процесс:** label `ready`, skip `blocked`; AC Given/When/Then; pytest + Playwright; PR с DoD; CI green; merge → next.

---

### 6.2 Deprecated скиллы

#### self-review
**DEPRECATED** → используй **adversarial-reviewer**. Builder может сделать 30-сек sanity check — не замена ревью.

#### ux-pattern-scout
**DEPRECATED** → **ui-designer**. Scout existing UI → 2–4 patterns → recommendation + risks.

#### solution-architecture-brief
**DEPRECATED** → technical contract в **planner**. Шаблон: components, data flow, contracts, error model, idempotency, observability, alternatives, risks.

---

## 7. Cursor-managed скиллы

Путь: `~/.cursor/skills-cursor/`

| Скилл | Описание |
|-------|----------|
| **canvas** | Live React Canvas рядом с чатом для аналитики, таблиц, charts, MCP-результатов; обязателен для `.canvas.tsx` |
| **sdk** | Cursor SDK (TypeScript `@cursor/sdk`, Python `cursor-sdk`) — агенты из скриптов/CI |
| **babysit** | Держать PR merge-ready: conflicts, comments, CI loop |
| **split-to-prs** | Разбить работу на маленькие PR |
| **create-rule** | Создать Cursor rule в `.cursor/rules/` |
| **create-skill** | Создать Agent Skill (SKILL.md) |
| **create-subagent** | Создать custom subagent |
| **create-hook** | Cursor hooks (`hooks.json`) |
| **update-cursor-settings** | Настройки IDE (settings.json) |
| **update-cli-config** | CLI config |
| **statusline** | Кастомная status line в CLI |
| **shell** | Shell skill |
| **migrate-to-skills** | Миграция на skills |

---

## 8. Скиллы репозитория WMS

Путь: `.cursor/skills/` в репозитории

### feature-test-coverage
**Описание:** Таблица покрытия кейсами (TC-ID, негативы) для issue/PR по AGENTS.md.

**Источники:**
1. `docs/MVP_DECISIONS_RU.md`
2. `docs/IMPLEMENTED_PRODUCT_SCENARIOS_EN.md`
3. `docs/IMPLEMENTED_PRODUCT_SCENARIOS_TEST_CASES_EN.md`

**Артефакт:**
```markdown
### Test coverage

| TC-ID | Title (short) | Applies (Y/N) | Notes |
|-------|-----------------|---------------|-------|
```

**Quality bar:** Notes = мини-спек (действие → видимый результат; негативы); ≥2 строки TC; маркеры Given/When/Then. CI: `scripts/ci/check_pr_test_coverage.py`, `check_e2e_tc_mentions.py`.

---

## 9. Глобальные правила (~/.cursor/rules/)

### 9.1 alwaysApply: true (всегда активны)

#### automated-pipeline-v2.mdc
Автопайплайн v2: цепочка агентов, HANDOFF, DoD, стек Python/FastAPI, архитектура слоёв, миграции, скиллы, глобальные гейты. Заменяет старый User Rules block.

#### 000-pipeline-v2-supersedes-v1.mdc
Жёстко отменяет v1 (analyst, test-engineer, reviewer…). Источник правды — automated-pipeline-v2.

#### engineering-standards.mdc
**Hard rules** (нарушение = BLOCK):
- Слои: api → services → models/db; один owner domain rules
- Single path: одна операция = один code path
- Async: enqueue after commit; unique task_id; idempotent; stale-recovery; GET не запускает тяжёлую работу
- Файл >400 строк → split или план
- Рефактор ≤5 файлов/шаг
- Нет мёртвого кода; no bare except
- Тесты на поведение, не implementation
- Нет bulk requeue без команды

#### small-steps-discipline.mdc
Рефактор ≤5 файлов/шаг; зелёный check между шагами; одна логическая concern/шаг; vertical slice для фич; не 20+ file WIP без checkpoint.

#### runtime-proof-gate.mdc
«Готово» требует: команды + реальный вывод (exit code, строки). Текст без output = FAIL. UI: Playwright/screenshot. Autotests green ≠ enough для user-visible без mapping test→user step.

#### scenario-contract-gate.mdc
Нетривиальный flow → Сценарий (контракт) до кода; Проверка сценария (proof) до «готово». Шаблон — skill `scenario-contract`.

#### requirements-baseline-gate.mdc
Нетривиальная работа → Requirements Baseline до планирования/кода. Блокирующие пробелы → choice-based вопросы.

#### ux-ui-contract-gate.mdc
UI/UX изменения → UX/UI Contract до UI-кода; UI Scenario Proof до «done».

#### feature-based-workflow.mdc
Работа фичами; владелец видит L0; контракты до кода; стоп после контракта и после фичи (Feature Completion Report). Continuous mode — opt-in.

#### pipeline-artifacts.mdc
Кто что производит: spec (baseline, domain, UX), planner (scenario, technical contract, plan), builder (code, tests, proof), ui-designer, frontend-ui-engineer, adversarial-reviewer, verifier.

#### choice-based-questions.mdc
Уточнения только A/B/C/D + Agent (safe MVP default). Формат: вопрос, опции, Recommendation, Risk. Gap scan перед планированием.

#### owner-plain-language.mdc
Простой русский для владельца; термины с расшифровкой; не техно-конспект; объём по вопросу.

#### owner-readability-8-10.mdc
8–10/10: сначала по-человечески, потом настоящие имена инструментов. Два слоя в одном ответе. Первый абзац — ответ по сути.

#### scenario-owner-readable.mdc
Сценарии на русском; роли (пользовательница, куратор, система); без имён функций/таблиц в основном тексте. Шаблоны контракта и proof.

#### task-log-after-change.mdc
После behavior-changing задачи → TASKLOG.md; bugfix → BUGLOG.md; commit только по явной просьбе пользователя.

### 9.2 alwaysApply: false (по контексту)

#### external-contracts-gate.mdc
Внешние API: сверка method/endpoint/status; error fallbacks; rate limits; payload verification.

#### ui-engineering-checklist.mdc
Modal scroll, drag/pointer, global keydown, polling, tableLayout, stale response guards, optimistic UI.

#### buglog-distillation.mdc
После багфикса: root cause → тест или rule update (обязательно).

---

## 10. Правила репозитория WMS

### AGENTS.md (always applied в workspace)

**Product source of truth:**
- `docs/MVP_DECISIONS_RU.md` — tenants, billing, WB import-only, терминология
- `docs/BACKLOG_EPICS_RU.md` — epic map
- `docs/UI_DESIGN_SYSTEM_RU.md` — MUI, эталон `FfProductsCatalogScreen.tsx`

**Autopilot loop:**
1. Issue label `ready`, skip `blocked`
2. Acceptance criteria + **Test coverage traceability** (таблица TC-ID в issue)
3. Vertical slice: api → services → models → db; Celery tasks в `app/tasks`
4. Tests: pytest backend; Playwright e2e user-visible
5. Gates: `ruff && mypy && pytest`; `npm run build && npm run test:e2e`
6. PR + green CI
7. Mark done → next ready

**Test coverage (CI enforcement):**
- Блок `### Test coverage` в PR description
- ≥2 строки TC, Y, маркеры Given/When/Then/negative
- E2e specs: TC-ID mentions
- Bypass: label `skip-test-coverage-check`

**E2E rules:**
- User-centric path через UI
- `data-testid`
- `waitForResponse` параллельно с click
- Form reset: capture `currentTarget` before await

### .cursor/rules/wms-issues.mdc

Issues-режим (GitHub Issues `ready`) + инженерные хард-правила WMS. **Не queue autopilot** — см. `wms-queue.mdc`.

- One feature per PR
- Backend boundaries: api / services / models / db
- No raw SQL in routes; types; no bare except; no print
- UI change → Playwright e2e user-visible outcome
- Issues `ready`; AGENTS.md + green CI

### .cursor/rules/wms-queue.mdc

Queue autopilot (`docs/PARALLEL_AGENT_TASKS.md`, worker pool, `.cursor/state/*.done`, worktree). Старт — только **новый чат**; см. файл.

---

## 11. User Rules (настройки Cursor)

Персональные правила, подмешиваются глобально:

| Правило | Суть |
|---------|------|
| **committing-changes-with-git** | Commit только по явной просьбе; git safety; HEREDOC message; no force push main |
| **creating-pull-requests** | PR через `gh`; status + diff + log; push -u; body template |
| **Follow ALL instructions** | Скиллы, rules, MCP — полностью |
| **Real environment** | Реальный shell; не сдаваться после одной ошибки |
| **Communication** | Code citations `startLine:endLine:path`; markdown links; качественная проза |
| **Code principles** | Minimize scope; no over-engineering; match conventions; useful tests only |
| **Деплой и Git** | Всё на сервере в git; секреты в .env; CI перед продом; docker compose up |
| **Автопайплайн (дубликат)** | Цепочка v2, HANDOFF, DoD — **перекрывается** `000-pipeline-v2-supersedes-v1` |

---

## 12. Типовые цепочки по типу задачи

| Тип | Цепочка | Скиллы |
|-----|---------|--------|
| Новый проект | spec → planner → verifier (план, без кода) | project-bootstrap |
| Новая фича (backend) | spec → planner → builder → adversarial-reviewer → verifier | new-feature, scenario-contract, write-tests |
| Баг | spec → planner → builder → adversarial-reviewer → verifier | bugfix, scenario-contract, write-tests |
| Рефакторинг | spec → planner → builder → adversarial-reviewer → verifier | refactor-safe, small-steps-discipline |
| UX проектирование | spec → ui-designer → adversarial-reviewer → verifier | ux-ui-contract, ui-states-matrix, design-new-screen |
| UX реализация | spec → ui-designer → planner → frontend-ui-engineer → adversarial-reviewer → verifier | + ui-scenario-proof, responsive-pass |
| Фича + новый экран | spec → ui-designer → planner → (FE + builder) → adversarial-reviewer → verifier | composite |
| Релиз / merge | adversarial-reviewer → verifier | release-prep |

---

## 13. Режимы Cursor

| Режим | Назначение |
|-------|------------|
| **Agent** | Реализация, полный доступ к инструментам |
| **Plan** | Readonly планирование, без правок |
| **Debug** | Систематическая отладка с runtime evidence |
| **Ask** | Readonly вопросы и исследование |

---

## 14. Модели для субагентов

Если пользователь явно запрашивает модель для subagent — только из списка:

- `claude-4.6-sonnet-medium-thinking`
- `claude-opus-4-7-thinking-xhigh`
- `claude-opus-4-8-thinking-medium`
- `composer-2.5-fast`
- `gpt-5.3-codex`
- `gpt-5.4-medium`
- `gpt-5.5-medium`
- `grok-build-0.1`

Если запрошенной модели нет в списке — не подставлять другую; сообщить пользователю.

---

## Definition of Done (сводка)

- `ruff check .` — зелёный
- `mypy .` — зелёный
- `pytest` / `make check` — зелёный
- `npm run build && npm run test:e2e` (если frontend)
- Runtime proof — вывод команд
- Scenario proof для user-visible flows
- adversarial-reviewer: не BLOCK
- verifier: READY
- TASKLOG / BUGLOG обновлены
- PR: `### Test coverage` (WMS product changes)

---

## Feature Completion Report (шаблон)

```text
Feature Completion Report — [title]
1. Product (L0): what user can do now
2. Process: action → steps → visible result
3. Data & call flow (L1): what changed
4. Architecture (light): modules touched
5. Out of scope
6. How to verify (3 concrete checks)
7. Runtime proof summary (commands + outcome)
8. Risks / follow-ups
9. Suggested next feature
```

---

## HANDOFF (шаблон между агентами)

```text
---HANDOFF---
Что сделано: [кратко]
Затронутые файлы: [список]
Риски: [что может пойти не так]
Следующий агент: [spec | planner | builder | ui-designer | frontend-ui-engineer | adversarial-reviewer | verifier]
Что ему нужно: [инструкция]
---END---
```

---

*Документ сгенерирован для репозитория WMS. При изменении `~/.cursor/` обновляйте этот файл вручную или попросите агента пересобрать.*
