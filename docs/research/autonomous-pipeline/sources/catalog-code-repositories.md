# Каталог исполняемых репозиториев: автономные coding-pipeline

Дата сбора: 2026-08-24. Это первичный каталог для дальнейшего разбирательства, а не перечень рекомендованных решений. Все URL проверены через GitHub Search/API или открытие репозитория. `A` означает, что в публичном коде явно видны workflow/state/runtime; `B` — видны исходники и заявленная релевантность, но перед выводами нужна проверка конкретной реализации; `C` — полезный комплементарный код (eval, review, infrastructure), не готовый end-to-end pipeline.

## 1. Наиболее близкие к задаче: orchestration, durable state, автономный delivery

| # | Репозиторий | Почему в каталоге | Читать глубоко | Уровень | Дубль / оговорка |
|---|---|---|---|---|---|
| 1 | [aws-samples/sample-autonomous-cloud-coding-agents](https://github.com/aws-samples/sample-autonomous-cloud-coding-agents) | AWS-реализация: задача в изолированном runtime превращается в PR; есть admission, durable orchestration и GitHub-интеграция. | `docs/design/ORCHESTRATOR.md`, `ARCHITECTURE.md`, `COMPUTE.md`, `src/` | A | Один из главных эталонов cloud-control-plane; AWS-специфичен. |
| 2 | [open-mercato/cezar](https://github.com/open-mercato/cezar) | Локальный fire-and-forget orchestrator: worktrees, workflows, persisted JSON/NDJSON, агентные backend'ы. | `packages/`, `.ai/cezar/` schema, workflow definitions, tests | A | Близок к ночной локальной эксплуатации, но UI/cockpit может быть лишним. |
| 3 | [mraza007/baton](https://github.com/mraza007/baton) | Issue poller → isolated worktree → CLI agent → PR; явная машина `Claimed/Running/RetryQueued/Released`. | `symphony/orchestrator.py`, `worker.py`, `state.py`, `WORKFLOW.md` | A | Узок, но очень ценен для retry/reconcile. |
| 4 | [doordash-oss/agentic-orchestrator](https://github.com/doordash-oss/agentic-orchestrator) | Feature prompt → research/plan/code/review/PR; прямо борется с потерей контекста и огромными diff. | `packages/`, `src/`, workflow prompts, tests | A | Нужна проверка зрелости и фактических гейтов. |
| 5 | [saintdle/agentflow](https://github.com/saintdle/agentflow) | Durable goals/claims/evidence/review/integration, provider-neutral handoff и fail-closed preflight. | `agentflow/`, `skills/`, `docs/`, tests | A | Важен как противовес «отчётам вместо состояния». |
| 6 | [gabrielkoerich/orchestrator-sh](https://github.com/gabrielkoerich/orchestrator-sh) | Bash-orchestrator Issue → router → worktree → tmux agent → commit/push/PR/review/merge. | `bin/`, `lib/`, `workflow/`, Bats tests | A | Малый и читаемый; GitHub Issues — жёсткая привязка. |
| 7 | [maxtechera/orchestrator](https://github.com/maxtechera/orchestrator) | Документированная ticket state machine, executor/verifier separation, fail-closed done. | `SKILL.md`, `WORKFLOW.md`, `docs/STATE_MACHINE.md`, `examples/` | A | Prompt/workflow package, не полноценный runtime. |
| 8 | [q3ok/coordinated-agent-team](https://github.com/q3ok/coordinated-agent-team) | Детерминированный state machine, contracts, runtime artifacts, repair loops и role prompts. | `.github/agents/CONTRACT.md`, `WORKFLOW.md`, `DISPATCH-REFERENCE.md`, agents | A | Очень близок к исследованию промптов/артефактов; не считать доказательством production. |
| 9 | [ZenulAbidin/stringbean](https://github.com/ZenulAbidin/stringbean) | Resumable MCP-style planning→review→implementation→review; полные prompts/output/transition log. | `stringbean/`, workflow config, `tests/`, docs | A | Сильный кандидат для durable audit trail. |
| 10 | [Untrivial-ai/agent-orchestrator](https://github.com/Untrivial-ai/agent-orchestrator) | Parallel agents в isolated workspaces; CI, review comments, merge conflicts возвращаются нужной сессии. | `apps/`, `packages/`, daemon/controller code, tests | A | GUI-heavy; отделить полезный feedback loop от оболочки. |
| 11 | [sipyourdrink-ltd/bernstein](https://github.com/sipyourdrink-ltd/bernstein) | Детерминированный non-LLM coordination loop, worktrees, replayability, signed lineage. | `src/`, workflow config, tests, docs | A | Может быть избыточен, но ценный для предсказуемости контроллера. |
| 12 | [digitaldrywood/detent](https://github.com/digitaldrywood/detent) | GitHub Project board → worktree → agent → validation gate → serialized merge train. | Go source, validation adapters, state model, docs | A | Важен для merge train и не-параллельной интеграции. |
| 13 | [eugeneorlov/noxdev](https://github.com/eugeneorlov/noxdev) | Ночной автономный coding-loop с Docker isolation, worktree safety и review. | `src/`, Docker, workflow config, tests | B | Проверить, не README-only ли review. |
| 14 | [sethdford/shipwright](https://github.com/sethdford/shipwright) | Fleet/delivery pipeline «issue to deployed PR», workers и DORA-метрики. | `cmd/`, `internal/`, workflow definitions, tests | B | Может быть чрезмерно платформенным. |
| 15 | [kelos-dev/kelos](https://github.com/kelos-dev/kelos) | Kubernetes-native orchestration автономных coding agents. | controllers, CRDs, charts, docs | B | Для сравнения reliability, не прямой кандидат в WMS. |
| 16 | [JeiKeiLim/tenet](https://github.com/JeiKeiLim/tenet) | Long-horizon spec/DAG orchestration и три критика. | workflow/DAG engine, agent profiles, tests | B | Нужен разбор полезности 3 critics против расходов. |
| 17 | [mksglu/hatice](https://github.com/mksglu/hatice) | Автономная orchestration system для coding agents. | `src/`, workflow engine, docs/tests | B | Кандидат на первичную верификацию. |
| 18 | [backmeupplz/superharness](https://github.com/backmeupplz/superharness) | Multi-agent orchestration через tmux. | shell/runtime, configs, docs | B | Инфраструктурный вариант, нужен кодовый аудит. |
| 19 | [frizynn/gralph](https://github.com/frizynn/gralph) | Ralph-loop implementation: PRD-driven multi-agent execution + worktrees. | Go source, loop prompts, tests | B | Сравнить с bounded-rework, чтобы не получить бесконечный цикл. |
| 20 | [syuya2036/ralph-loop](https://github.com/syuya2036/ralph-loop) | Агент-независимый autonomous loop. | scripts, templates, docs | B | Паттерн loop, не готовый delivery system. |
| 21 | [alfredolopez80/multi-agent-ralph-loop](https://github.com/alfredolopez80/multi-agent-ralph-loop) | Multi-agent Ralph с quality gates, hooks и tests. | hooks, stage definitions, tests | B | Особенно проверить claim о 925 tests. |
| 22 | [NTCoding/autonomous-claude-agent-team](https://github.com/NTCoding/autonomous-claude-agent-team) | Hook-driven deterministic code workflow как готовый пример. | `.claude/`, hooks, workflow docs, example project | A | Близок к текущему WMS hook-подходу. |
| 23 | [Sdraugel/albert](https://github.com/Sdraugel/albert) | Multi-agent harness + live HUD, полезен для runtime state/observability. | orchestrator scripts, agent config, HUD | B | UI не основная ценность. |
| 24 | [badvision/clawed](https://github.com/badvision/clawed) | Production-tested (заявлено) workflow execution/delegation для разработки. | controller, workflows, tests/docs | B | Проверить подтверждённость production claims. |
| 25 | [hashangit/zflow](https://github.com/hashangit/zflow) | Phase-gated SDLC для skills-capable harnesses. | workflow YAML, role skills, tests | B | Близок к role-heavy системе: искать как режет лишние роли. |
| 26 | [tinhtran24/maestro](https://github.com/tinhtran24/maestro) | Go multi-agent framework с deterministic engineering workflow. | `internal/`, workflows, agent adapters, tests | B | Не путать с одноимёнными GUI. |
| 27 | [BankNatchapol/Loop-Control-Plane](https://github.com/BankNatchapol/Loop-Control-Plane) | Local-first kanban + workflow engine для autonomous loops. | engine/state, board adapters, tests | B | Сравнить control plane с минимальной необходимостью. |
| 28 | [kazz187/taskguild](https://github.com/kazz187/taskguild) | Kanban transitions запускают agents; Q&A/permissions/worktrees/notifications. | workflow transitions, runners, tests | B | Важен для точки «ждёт человека» vs autonomous. |
| 29 | [redevops-io/sidekick](https://github.com/redevops-io/sidekick) | DAG auto-approved worktrees, multi-provider sessions. | DAG planner/executor, adapters, tests | B | Проверить, как решает dependency and integration. |
| 30 | [tumf/conflux](https://github.com/tumf/conflux) | Spec-driven parallel coding поверх OpenSpec, concurrent worktrees. | spec parser, scheduler, tests | B | Нужен для контракта спецификация→задачи. |

## 2. Worktree / issue / PR control plane

| # | Репозиторий | Почему | Читать глубоко | Уровень | Оговорка |
|---|---|---|---|---|---|
| 31 | [ClipboardHealth/groundcrew](https://github.com/ClipboardHealth/groundcrew) | Backlog dispatch к локальным interactive agents, sandbox per worktree. | scheduler, sandbox, task model, tests | A | Хорош для isolation. |
| 32 | [daintreehq/daintree](https://github.com/daintreehq/daintree) | Delegation environment: sessions/worktrees/context/workflow automation. | daemon, context injection, workflow code | B | UI/terminal management может доминировать. |
| 33 | [alamops/agetor](https://github.com/alamops/agetor) | Local-first kanban + worktrees для Codex/Claude. | task queue, agent runners, tests | B | Проверить механизм acceptance. |
| 34 | [usemozzie/mozzie](https://github.com/usemozzie/mozzie) | Desktop orchestration, dependencies, review workflow. | backend state, worktree manager, review code | B | Desktop UI необязателен. |
| 35 | [aliengiraffe/vigilante](https://github.com/aliengiraffe/vigilante) | Sandbox-first, credential scoping и audit logs. | sandbox policy, worktree isolation, audit log | A | Ценно для безопасности, не для UX pipeline. |
| 36 | [first-fluke/agent-valley](https://github.com/first-fluke/agent-valley) | Linear → provider agents в isolated worktrees. | Linear adapter, dispatcher, worktree/PR code | B | SaaS tracker integration. |
| 37 | [andrewhathaway/ag.sh](https://github.com/andrewhathaway/ag.sh) | CLI для параллельных agents/worktrees. | shell commands, worktree lifecycle, tests | B | Low-level utility. |
| 38 | [clawnify/ateam](https://github.com/clawnify/ateam) | Claude/OpenCode/Codex crew в Git worktrees, remote/local. | runner, configs, state | B | Собирательная инфраструктура. |
| 39 | [ensemblr-hq/ensemblr](https://github.com/ensemblr-hq/ensemblr) | Pi/Claude orchestration, делегирование и интеграция. | app core, worktree manager, agent protocol | B | macOS-specific surface. |
| 40 | [pablocalofatti/minion-toolkit](https://github.com/pablocalofatti/minion-toolkit) | Разбивает задачи и спаунит isolated workers. | task splitter, prompts, worktree scripts | B | Проверить, кто делает integration. |
| 41 | [joshuaswarren/agentyard-cli](https://github.com/joshuaswarren/agentyard-cli) | Workflow + isolated worktrees/tmux for Claude. | CLI, session state, workflow config | B | Узкий provider. |
| 42 | [TNJ2026/orbit](https://github.com/TNJ2026/orbit) | Role teams dispatch/execute/review tasks в worktrees. | team workflow, dispatcher, review loop | B | Проверить реальный runtime. |
| 43 | [nwiizo/ccswarm](https://github.com/nwiizo/ccswarm) | Claude multi-agent worktree isolation + specialist roles. | orchestration scripts, role prompts | B | Возможен prompt-pack. |
| 44 | [asynkron/Asynkron.Swarm](https://github.com/asynkron/Asynkron.Swarm) | Parallel coding agents in Git worktrees. | scheduler/worktree code | B | Low-level orchestration. |
| 45 | [ISO-Framework](https://github.com/snehith01001110/ISO-Framework) | Rust worktree lifecycle library/CLI/MCP. | crate, isolation tests, MCP tools | A | Компонент для надёжной изоляции, не pipeline. |
| 46 | [cristicretu/diri](https://github.com/cristicretu/diri) | Native macOS agents across worktrees/hosts. | session manager, remote control, tests | B | OS-specific. |
| 47 | [nnayz/zeus](https://github.com/nnayz/zeus) | macOS multi-agent worktree/remote orchestrator. | core source, state/worktree layer | B | Аналог Diri. |
| 48 | [rodrigooler/ork](https://github.com/rodrigooler/ork) | macOS terminal deck for coding agents in worktrees. | app state, process/worktree code | B | UI-centric. |
| 49 | [arnaultpascual/atelier](https://github.com/arnaultpascual/atelier) | Worktrees, approval inbox, model/cost selection. | security/approval layer, runner, tests | B | Полезен для sensitive-operation gates. |
| 50 | [mirage-security/flight-mac](https://github.com/mirage-security/flight-mac) | GUI orchestration local/remote workspaces. | app backend, workspace lifecycle | C | Mainly operational UI. |

## 3. Role prompts, SDLC contracts, quality/review/test gates

| # | Репозиторий | Почему | Читать глубоко | Уровень | Оговорка |
|---|---|---|---|---|---|
| 51 | [pridiuksson/cursor-agents](https://github.com/pridiuksson/cursor-agents) | Template «battle-tested» multi-agent development workflow. | `.cursor/`, agent definitions, workflow docs, examples | B | Проверить machine enforcement. |
| 52 | [ronnycoding/.claude](https://github.com/ronnycoding/.claude) | Claude config: special agents, skills, automated GitHub workflow, decomposition. | `.claude/agents`, hooks, workflows | B | Prompt/config corpus. |
| 53 | [jmagly/aiwg](https://github.com/jmagly/aiwg) | Cognitive architecture + specialized agents / structured workflows across harnesses. | agent specs, commands, workflow templates | B | Методология может быть тяжелее runtime. |
| 54 | [nicolasbrandao/sisan](https://github.com/nicolasbrandao/sisan) | Claude Code plugin с PM, architect, QA, UI/UX etc. | plugin manifest, role prompts, workflow rules | B | Полезен именно для анализа лишних ролей. |
| 55 | [angsuk/copilot-orchestra](https://github.com/angsuk/copilot-orchestra) | Multi-agent TDD workflow. | prompts, test/review stages, examples | B | Узок на Copilot/TDD. |
| 56 | [hieund-it/geminikit](https://github.com/hieund-it/geminikit) | Gemini CLI multi-agent/skills, architecture consistency/token optimization. | skills, coordinator, tests | B | Provider-specific. |
| 57 | [Deepsim-AI/DS-EO](https://github.com/Deepsim-AI/DS-EO) | Engineering-org framework: governance/workflows/quality control. | role/process definitions, enforcement code | B | Может быть больше framework, чем executable runtime. |
| 58 | [liuqin164/openclaw-agents-team-skill](https://github.com/liuqin164/openclaw-agents-team-skill) | YAML multi-agent software workflow. | YAML transitions, role instructions | B | Config-only candidate. |
| 59 | [feifeifeimoon/GitSquad](https://github.com/feifeifeimoon/GitSquad) | GitHub-centric autonomous software workflow. | GitHub integration, agent graph, tests | B | Needs implementation check. |
| 60 | [arpit-deshmukh/AI-Multi-Agent-Development-System](https://github.com/arpit-deshmukh/AI-Multi-Agent-Development-System) | Requirements → architecture/schema/code/review/debug/deploy graph. | graph definition, nodes, tests | B | Хорош для comparison only. |
| 61 | [vedantdubey19/AutoDev-Ai](https://github.com/vedantdubey19/AutoDev-Ai) | Multi-agent build/test/improve system. | agents, orchestration, test runner | B | Requires source-quality audit. |
| 62 | [BjornMelin/codeforge](https://github.com/BjornMelin/codeforge) | LangGraph-based agentic software dev, GraphRAG/shared state/model routing. | graph, state schema, tool layer, tests | B | Риск overengineering; полезно как negative comparison. |
| 63 | [Sebasbo/Autonoma](https://github.com/Sebasbo/Autonoma) | Code modification, analysis and testing collaboration. | task graph, tools, tests | B | Framework candidate. |
| 64 | [solofberlin/agent-workflow](https://github.com/solofberlin/agent-workflow) | PM→tech lead→coder→reviewer path. | templates, workflow scripts | C | Простой contrast-role example. |
| 65 | [gdamron/mahler](https://github.com/gdamron/mahler) | Human-orchestrated multi-agent workflow tool. | workflow engine, task model | B | Useful boundary of human approval. |
| 66 | [shizonic/ccaf](https://github.com/shizonic/ccaf) | Claude Code Agent Framework: roles and parallel orchestration. | framework core, role configs, tests | B | Проверить artefacts & retry. |
| 67 | [speedchen-git/AI-PM-workflow](https://github.com/speedchen-git/AI-PM-workflow) | Provider-agnostic PM workflow/slash commands. | command templates, requirements artifacts | C | Только input/product layer. |
| 68 | [Design-Jarvis](https://github.com/renfei-design/Design-Jarvis) | Design-team orchestration с lead review/persistent decisions. | agents, memory, UX/review workflow | B | Для design governance, не code delivery. |
| 69 | [jakreymyers/agentic-engineer](https://github.com/jakreymyers/agentic-engineer) | 45+ agents, workflows incl. engineering/research. | agents/workflows/templates | C | Хороший антипример role explosion. |
| 70 | [chithudas/agentos-kit](https://github.com/chithudas/agentos-kit) | 35+ agents, parallel workflows/security/DevOps. | role configs, orchestration, tests | C | Анализировать стоимость/сложность, не копировать. |

## 4. Независимые acceptance gates, browser/test/review и evaluation

| # | Репозиторий | Почему | Читать глубоко | Уровень | Оговорка |
|---|---|---|---|---|---|
| 71 | [mr-karan/hodor](https://github.com/mr-karan/hodor) | Real GitHub PR/GitLab MR multi-step code reviewer. | reviewer graph, provider tools, GitHub/GitLab adapters, tests | A | Review component, не delivery pipeline. |
| 72 | [SWE-agent/SWE-agent](https://github.com/SWE-agent/SWE-agent) | Один из базовых open coding agents: issue→repo edit→test/evaluation. | `sweagent/agent`, environment, run/eval configs | A | Не orchestration, но baseline worker. |
| 73 | [SWE-bench/SWE-bench](https://github.com/SWE-bench/SWE-bench) | Воспроизводимый benchmark/harness для repository bug fixes. | harness, evaluation scripts, task schema | A | Гейт качества, не product acceptance. |
| 74 | [SWE-bench/SWE-smith](https://github.com/SWE-bench/SWE-smith) | Генерация/валидация задач для agent evaluation. | task generation/validation pipeline | B | Useful for internal eval design. |
| 75 | [OpenHands/OpenHands](https://github.com/OpenHands/OpenHands) | Mature open agent runtime: sandbox, tools, evaluation and event state. | `openhands/agenthub`, runtime, event stream, tests | A | General agent platform; extract runtime patterns only. |
| 76 | [All-Hands-AI/OpenHands](https://github.com/All-Hands-AI/OpenHands) | Historical/canonical fork path if needed for lineage. | runtime/event/state history | C | Likely duplicate/renamed; avoid double counting. |
| 77 | [Aider-AI/aider](https://github.com/Aider-AI/aider) | Git-aware coding agent with test/lint integration and auto-commits. | `aider/`, git integration, test commands | A | Single-agent baseline. |
| 78 | [paul-gauthier/aider](https://github.com/paul-gauthier/aider) | Old canonical URL for Aider. | — | C | Duplicate of Aider-AI/aider; keep for source resolution only. |
| 79 | [microsoft/playwright](https://github.com/microsoft/playwright) | Browser acceptance infrastructure, traces/screenshots/retries. | `packages/playwright-test`, retry/reporting docs/tests | A | Foundation, not agent pipeline. |
| 80 | [microsoft/playwright-mcp](https://github.com/microsoft/playwright-mcp) | Browser tools exposed to agents, relevant to true browser judge. | server, tool definitions, tests | A | Component for browser gate. |
| 81 | [browserbase/stagehand](https://github.com/browserbase/stagehand) | Agent-friendly browser automation with deterministic escape hatches. | SDK/actions, evals/tests | B | External service orientation. |
| 82 | [langchain-ai/langgraph](https://github.com/langchain-ai/langgraph) | Durable stateful agent graph, checkpoints, interrupts, retry policies. | `libs/langgraph`, examples, tests; fault-tolerance docs | A | Framework; must not imply it is necessary. |
| 83 | [temporalio/temporal](https://github.com/temporalio/temporal) | Durable execution/retries/timeouts/sagas for controllers. | samples, workflow/retry code, tests | A | Heavy infrastructure contrast. |
| 84 | [PrefectHQ/prefect](https://github.com/PrefectHQ/prefect) | Orchestration, retries, state handlers, observability. | engine, states, retry tests | A | General workflow framework. |
| 85 | [dagster-io/dagster](https://github.com/dagster-io/dagster) | Asset/job orchestration with explicit IO/materialization. | execution/state/retry, tests | A | Useful artifact/evidence model, too broad for direct adoption. |
| 86 | [Netflix/conductor](https://github.com/Netflix/conductor) | Durable microservice workflow engine with failure handling. | core server, task states, retry configs | A | Enterprise-scale contrast. |
| 87 | [SKYLENAGE-AI/SWE-CI](https://github.com/SKYLENAGE-AI/SWE-CI) | Benchmark for agents maintaining code through CI. | benchmark harness, CI task setup, evaluator | B | Evaluation corpus, not runtime. |
| 88 | [Proximal-Labs/frontier-swe](https://github.com/Proximal-Labs/frontier-swe) | Long-horizon coding benchmark, implementation/performance/ML. | task/eval harnesses | B | Helps set realistic overnight evaluation. |
| 89 | [facebookresearch/sweet_rl](https://github.com/facebookresearch/sweet_rl) | Research code for multi-turn collaborative reasoning agent training. | environments, evals, training setup | C | Research only. |
| 90 | [amazon-science/SWE-PolyBench](https://github.com/amazon-science/SWE-PolyBench) | Multilingual repo-level agent evaluation. | datasets, evaluator, runners | B | Benchmark complement. |

## 5. Второй эшелон: проверять после A-кандидатов, не включать в основной дизайн без кода

| # | Репозиторий | Почему / точки чтения | Уровень | Возможный дубль или риск |
|---|---|---|---|---|
| 91 | [GreenSheep01201/claw-empire](https://github.com/GreenSheep01201/claw-empire) | CLI/OAuth/API-agent office; смотреть scheduler, persistence, policies. | B | «Автономная компания» может быть UI-first. |
| 92 | [monoes/monomind](https://github.com/monoes/monomind) | Persistent memory/knowledge graph/self-coordinating orgs; смотреть storage & task lifecycle. | B | Memory-heavy. |
| 93 | [internet-development/daedalus](https://github.com/internet-development/daedalus) | Planning CLI + beans-based coding orchestration; смотреть planning/execution boundary. | B | Experimental. |
| 94 | [TenchiNeko/standalone-orchestrator](https://github.com/TenchiNeko/standalone-orchestrator) | Local LLM Plan→Build→Test→Fix; смотреть loop/retry implementation. | B | Hardware/local-model specific. |
| 95 | [h4ckologic/bughunter-ai](https://github.com/h4ckologic/bughunter-ai) | State-machine orchestration + vault, но security domain; смотреть only reliability mechanics. | C | Не переносить offensive behavior. |
| 96 | [lib4u/rufler](https://github.com/lib4u/rufler) | Swarm wrapper; проверить actual executable coordination. | C | Вероятно marketing-heavy. |
| 97 | [mojomast/swarmussy](https://github.com/mojomast/swarmussy) | Experimental distributed workflow/TUI; смотреть state model. | C | В разработке. |
| 98 | [shortcut119/Multi-Agent-AI-Swarm](https://github.com/shortcut119/Multi-Agent-AI-Swarm) | Аналог experimental swarm. | C | Вероятный дубль swarmussy. |
| 99 | [stackconsult/agent-orchestra-production-build-tmp](https://github.com/stackconsult/agent-orchestra-production-build-tmp) | Routing/budget/security claims; проверять code/tests before citation. | C | Name signals temporary build. |
| 100 | [solofberlin/agent-workflow](https://github.com/solofberlin/agent-workflow) | Minimal role chain; useful control sample. | C | Already catalogued #64; duplicate listing intentionally not counted. |

## Как использовать каталог дальше

Первыми для детального разбора стоит брать #1–12, #22, #31, #35, #45, #71–85: у них наиболее явно наблюдаемы исполняемые переходы, durable state, worktree/Git integration, самостоятельные проверки или recovery. Для каждого следующего разбора необходимо отдельно подтвердить существование перечисленных файлов и отличить код от деклараций README.

Не путать показатели: этот каталог содержит **99 уникальных кандидатов** (строка #100 — намеренно помеченный дубль и в число не входит). Реальный дизайн WMS нельзя строить из числа звёзд, заявления «production-ready» или списка ролей: нужны конкретный state transition, артефакт, gate, failure classification и тест на них.
