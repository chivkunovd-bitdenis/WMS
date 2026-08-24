# Каталог первичных и технических источников: автономный SDLC

Дата среза: 2026-08-24. Это **каталог кандидатов для глубокого разбора**, а не синтез и не список рекомендаций. Все URL ниже были запрошены из этой среды 2026-08-24 (для GitHub проверяется доступность репозитория/файла; содержательные выводы требуют чтения pinned revision).

## Как читать каталог

**E1** — первичный код, официальная документация или paper авторов системы; **E2** — технический engineering blog/пост команды, реализовавшей систему; **E3** — независимый evaluation paper/benchmark с воспроизводимым артефактом. «Глубоко» означает: читать исходный код/конфигурацию, а не только README; фиксировать exact revision, input/output state, prompt, tool permissions, gаты, retry и человеческий выход.

Формат: **URL — название — автор / дата — тип / evidence — что сможет раскрыть — читать глубоко**.

## A. Раннеры coding-agent и их изолированные среды

1. [OpenAI Codex harness](https://openai.com/index/unlocking-the-codex-harness/) — *Unlocking the Codex harness* — OpenAI, 2026-02-05 — E1 engineering article — app-server, protocol событий, agent loop и separation UI/runtime — article plus linked protocol/docs.
2. [Codex CLI](https://github.com/openai/codex) — *openai/codex* — OpenAI, continuously updated — E1 code — sandbox, approvals, config, exec loop, tool policy and resumability — `codex-rs/`, `docs/`, commits/tags.
3. [Codex Action](https://github.com/openai/codex-action) — *Codex GitHub Action* — OpenAI, continuously updated — E1 code — PR-triggered execution, least privilege, proxy, CI boundary — action.yml and examples.
4. [OpenAI Agents SDK Python](https://openai.github.io/openai-agents-python/) — *Agents SDK docs* — OpenAI, continuously updated — E1 docs — handoffs, guardrails, tracing, sessions, tool errors — handoffs, guardrails, sessions, tracing pages.
5. [Agents SDK source](https://github.com/openai/openai-agents-python) — *openai-agents-python* — OpenAI, continuously updated — E1 code — runner state, exceptions, max turns, agent-as-tool — `src/agents/run.py`, tests.
6. [Agents SDK JS](https://github.com/openai/openai-agents-js) — *OpenAI Agents SDK for JavaScript* — OpenAI, continuously updated — E1 code — typed handoffs/tool schemas and browser/node integrations — packages and examples.
7. [OpenAI agent evals guide](https://platform.openai.com/docs/guides/evals) — *Evals* — OpenAI, continuously updated — E1 docs — test datasets, graders, regression gates — evaluation lifecycle and API examples.
8. [OpenAI practical agent guide](https://cdn.openai.com/business-guides-and-resources/a-practical-guide-to-building-agents.pdf) — *A practical guide to building agents* — OpenAI, 2025 — E1 guide — orchestration vs single agent, tool-risk levels, escalation — workflow and guardrail sections.
9. [AI-native engineering team guide](https://cdn.openai.com/business-guides-and-resources/building-an-ai-native-engineering-team.pdf) — *Building an AI-native engineering team* — OpenAI, 2026 — E1 guide — task delegation, repository instructions, review ownership — operating model/examples.
10. [Claude Code docs](https://docs.anthropic.com/en/docs/claude-code/overview) — *Claude Code overview* — Anthropic, continuously updated — E1 docs — terminal agent capabilities and permission model — settings, hooks, subagents, CI pages.
11. [Claude Code hooks](https://docs.anthropic.com/en/docs/claude-code/hooks) — *Hooks reference* — Anthropic, continuously updated — E1 docs — deterministic pre/post tool gates and audit events — hook schema and failure semantics.
12. [Claude Code subagents](https://docs.anthropic.com/en/docs/claude-code/sub-agents) — *Subagents* — Anthropic, continuously updated — E1 docs — scoped prompts/tools/model delegation and context isolation — configuration/examples.
13. [Claude Code GitHub Actions](https://docs.anthropic.com/en/docs/claude-code/github-actions) — *Claude Code Action* — Anthropic, continuously updated — E1 docs — issue/PR triggers, permissions, CI execution — workflow examples and security caveats.
14. [Claude Code settings](https://docs.anthropic.com/en/docs/claude-code/settings) — *Settings* — Anthropic, continuously updated — E1 docs — allow/deny rules, sandboxing, shared policy — hierarchy and managed settings.
15. [Claude Code source/action](https://github.com/anthropics/claude-code-action) — *claude-code-action* — Anthropic, continuously updated — E1 code — action inputs, checkout and PR interactions — action.yml, scripts, workflow tests.
16. [Gemini CLI](https://github.com/google-gemini/gemini-cli) — *Gemini CLI* — Google, continuously updated — E1 code — tool loop, policy, extension context and checkpointing candidates — `packages/core`, docs, tests.
17. [Gemini CLI GitHub Action](https://github.com/google-github-actions/run-gemini-cli) — *run-gemini-cli* — Google, continuously updated — E1 code — CI permissions, event triggers, outputs — action.yml and examples.
18. [Aider](https://github.com/Aider-AI/aider) — *Aider* — Aider project, continuously updated — E1 code — git-aware edits, repo map, lint/test feedback loop — `aider/coders`, test commands, docs.
19. [Aider conventions](https://aider.chat/docs/usage/conventions.html) — *Conventions* — Aider project, continuously updated — E1 docs — promptable repository rules and auto-test/lint gates — conventions, `--test-cmd`, `--lint-cmd`.
20. [SWE-agent](https://github.com/SWE-agent/SWE-agent) — *SWE-agent* — Princeton NLP, continuously updated — E1 code — agent/computer interface, trajectory, environment and repair loop — `config/`, agent prompts, SWE-bench runner.
21. [SWE-agent paper](https://arxiv.org/abs/2405.15793) — *SWE-agent: Agent-Computer Interfaces Enable Automated Software Engineering* — Yang et al., 2024 — E3 paper — interface design, action space, trajectory analysis — paper plus linked code/config.
22. [OpenHands](https://github.com/All-Hands-AI/OpenHands) — *OpenHands* — All Hands AI, continuously updated — E1 code — sandboxed runtime, events, agents, microagents, evaluation — `openhands/`, docs and evals.
23. [OpenHands agent SDK docs](https://docs.all-hands.dev/sdk) — *OpenHands SDK* — All Hands AI, continuously updated — E1 docs — event stream, state, runtime/client boundaries — SDK and runtime architecture.
24. [OpenHands source](https://github.com/All-Hands-AI/OpenHands) — *OpenHands repository* — All Hands AI, continuously updated — E1 code — reusable repo instructions and trigger/context rules — locate microagent schema, matching and precedence tests at pinned revision.
25. [Cline](https://github.com/cline/cline) — *Cline* — Cline Bot, continuously updated — E1 code — plan/act state, human tool approval, checkpoints — `src/core`, prompts, checkpoint implementation.
26. [Roo Code](https://github.com/RooCodeInc/Roo-Code) — *Roo Code* — Roo Code, continuously updated — E1 code — modes, custom instructions, checkpoints, browser/terminal permissions — `.roo`, prompts, CI.
27. [Continue](https://github.com/continuedev/continue) — *Continue* — Continue Dev, continuously updated — E1 code — agent modes, rules, MCP and CI integrations — core agent loop and config schema.
28. [OpenCode](https://github.com/anomalyco/opencode) — *OpenCode* — Anomaly, continuously updated — E1 code — session persistence, permissions, plugin/tool architecture — packages/opencode source and docs.
29. [Cursor background agents](https://docs.cursor.com/background-agents) — *Background Agents* — Cursor, continuously updated — E1 docs — remote isolated agents, GitHub branch/PR lifecycle, retries/limits — lifecycle, security, and limitations.
30. [GitHub Copilot coding agent](https://docs.github.com/en/copilot/concepts/agents/coding-agent/about-coding-agent) — *About Copilot coding agent* — GitHub, continuously updated — E1 docs — issue-to-PR autonomous run, sandbox and Actions gates — setup, custom instructions, firewall pages.

## B. Workflow engines: durable state, retry, pause и human escalation

31. [LangGraph overview](https://langchain-ai.github.io/langgraph/) — *LangGraph* — LangChain, continuously updated — E1 docs — explicit graph state, nodes/edges, persistence — core concepts and runtime.
32. [LangGraph durable execution](https://langchain-ai.github.io/langgraph/concepts/durable_execution/) — *Durable execution* — LangChain, continuously updated — E1 docs — checkpoint, replay, idempotency and failure recovery — determinism/retry guidance.
33. [LangGraph interrupts](https://langchain-ai.github.io/langgraph/how-tos/human_in_the_loop/wait-user-input/) — *Interrupts* — LangChain, continuously updated — E1 docs — persisted pause/resume and approval payloads — API and restart semantics.
34. [LangGraph retry policy](https://langchain-ai.github.io/langgraph/) — *LangGraph documentation* — LangChain, continuously updated — E1 docs — bounded automatic retry at node level — retry-policy and exception-classification sections.
35. [LangGraph source](https://github.com/langchain-ai/langgraph) — *langgraph* — LangChain, continuously updated — E1 code — checkpointer, Pregel scheduler, state transition implementation — libs/langgraph and tests.
36. [Temporal durable execution](https://docs.temporal.io/workflows) — *Temporal Workflows* — Temporal, continuously updated — E1 docs — deterministic event history, retries, timeouts and compensations — workflow execution/replay.
37. [Temporal signals and queries](https://docs.temporal.io/develop/go/message-passing) — *Message passing* — Temporal, continuously updated — E1 docs — human/external intervention without destroying state — signals, updates, queries.
38. [Temporal retry policies](https://docs.temporal.io/encyclopedia/retry-policies) — *Retry policies* — Temporal, continuously updated — E1 docs — retry policy, heartbeat, workflow/task failure boundaries — all failure categories.
39. [Temporal samples](https://github.com/temporalio/samples-typescript) — *Temporal TypeScript samples* — Temporal, continuously updated — E1 code — concrete retry, signal, child-workflow and saga patterns — samples + tests.
40. [AWS Step Functions error handling](https://docs.aws.amazon.com/step-functions/latest/dg/concepts-error-handling.html) — *Handling errors* — AWS, continuously updated — E1 docs — Retry/Catch, backoff, redrive, terminal state — exact ASL examples.
41. [AWS Step Functions human approval](https://docs.aws.amazon.com/step-functions/latest/dg/connect-to-resource.html#connect-wait-token) — *Wait for a callback with task token* — AWS, continuously updated — E1 docs — explicit paused state with external approval — callback token safety and timeout.
42. [Prefect retries](https://docs.prefect.io/v3/how-to-guides/workflows/retries) — *Retry failed tasks* — Prefect, continuously updated — E1 docs — delayed/bounded retries and observability — configuration/API.
43. [Dagster software-defined assets](https://docs.dagster.io/guides/build/assets) — *Build assets* — Dagster, continuously updated — E1 docs — materialization contracts, tests, sensors and provenance — asset checks and automation.
44. [Argo Workflows pod restarts](https://argo-workflows.readthedocs.io/en/latest/pod-restarts/) — *Automatic Pod Restarts* — Argo Project, continuously updated — E1 docs — separately classifies safe pre-start infrastructure restart from application retry, with counters and cap — controller configuration and node status.
45. [Windmill flow control](https://www.windmill.dev/docs) — *Windmill documentation* — Windmill Labs, continuously updated — E1 docs — resumable flow state, retries and approval steps — flow-state and suspend behavior.
46. [Inngest durable execution](https://www.inngest.com/docs) — *Inngest documentation* — Inngest, continuously updated — E1 docs — step memoization, retries, sleeps and concurrency keys — durable execution and step API sections.
47. [Hatchet durable tasks](https://docs.hatchet.run/home/durable-tasks) — *Durable tasks* — Hatchet, continuously updated — E1 docs — stateful tasks, retries and event-driven orchestration — durable execution examples.
48. [Restate durable execution](https://docs.restate.dev/concepts/durable_execution) — *Durable Execution* — Restate, continuously updated — E1 docs — journaled side effects, wakeups and state — handlers and idempotency.

## C. Agent orchestration frameworks and implementations

49. [AutoGen](https://github.com/microsoft/autogen) — *AutoGen* — Microsoft, continuously updated — E1 code — multi-agent message protocols, termination, teams and tools — agentchat/core docs and tests.
50. [AutoGen documentation](https://microsoft.github.io/autogen/stable/) — *AutoGen documentation* — Microsoft, continuously updated — E1 docs — context isolation, serialization and recovery — state/protocol sections.
51. [Semantic Kernel process framework](https://learn.microsoft.com/en-us/semantic-kernel/frameworks/process/process-framework) — *Process framework* — Microsoft, continuously updated — E1 docs — typed events, step state, orchestration and human event injection — process samples.
52. [Semantic Kernel source](https://github.com/microsoft/semantic-kernel) — *semantic-kernel* — Microsoft, continuously updated — E1 code — process runtime and agent orchestration implementation — `dotnet/src/Experimental/Process`.
53. [Microsoft Agent Framework](https://github.com/microsoft/agent-framework) — *Agent Framework* — Microsoft, continuously updated — E1 code — workflows, executors, checkpointing, human input — docs/source/tests.
54. [CrewAI](https://github.com/crewAIInc/crewAI) — *crewAI* — CrewAI, continuously updated — E1 code — crews vs flows, guardrails, state and delegation — flow engine, examples, tests.
55. [CrewAI flows](https://docs.crewai.com/en/concepts/flows) — *Flows* — CrewAI, continuously updated — E1 docs — routers/listeners, persistence, conditional transitions — decorators and state model.
56. [PydanticAI durable agents](https://ai.pydantic.dev/durable_execution/) — *Durable execution* — Pydantic, continuously updated — E1 docs — integration with Temporal/Prefect/DBOS and resumable graphs — idempotent tool guidance.
57. [PydanticAI source](https://github.com/pydantic/pydantic-ai) — *pydantic-ai* — Pydantic, continuously updated — E1 code — typed structured outputs, retry/error validation and tools — agent graph/output validation.
58. [DSPy](https://github.com/stanfordnlp/dspy) — *DSPy* — Stanford NLP, continuously updated — E1 code — prompt modules, optimization and evaluation instead of static prompt folklore — teleprompt/evaluate modules.
59. [Haystack pipelines](https://docs.haystack.deepset.ai/docs/pipelines) — *Pipelines* — deepset, continuously updated — E1 docs — DAG components, typed connections, breakpoints and serialization — pipeline runtime/examples.
60. [LlamaIndex workflows](https://docs.llamaindex.ai/en/stable/module_guides/workflow/) — *Workflows* — LlamaIndex, continuously updated — E1 docs — event-driven steps, retries, checkpointing and human loop candidates — workflow API/examples.
61. [Mastra workflows](https://mastra.ai/docs/workflows/overview) — *Workflows* — Mastra, continuously updated — E1 docs — typed step inputs/outputs, branching, suspend/resume — state/persistence docs.
62. [Agno workflows](https://docs.agno.com/workflows/introduction) — *Workflows* — Agno, continuously updated — E1 docs — deterministic workflow with agent steps, session state and retries — workflow execution docs.
63. [Dify workflow](https://docs.dify.ai/en/guides/workflow/node) — *Workflow node reference* — Dify, continuously updated — E1 docs — visual state graph, branching, code/tool failures — node semantics and source.
64. [n8n human fallback](https://docs.n8n.io/integrations/builtin/core-nodes/n8n-nodes-base.wait/) — *Wait node* — n8n, continuously updated — E1 docs — pause/restart workflow for human input and external callbacks — execution persistence/error workflows.

## D. Реальные autonomous coding systems и benchmarks

65. [SWE-bench](https://github.com/SWE-bench/SWE-bench) — *SWE-bench* — Princeton NLP, continuously updated — E1 code/data — realistic issue→patch evaluation, dockerized test harness and contamination controls — harness, verifier, Lite/Verified data.
66. [SWE-bench paper](https://arxiv.org/abs/2310.06770) — *SWE-bench* — Jimenez et al., 2024 — E3 paper — benchmark construction, test-based acceptance and failure modes — paper + data release.
67. [SWE-bench Verified](https://openai.com/index/introducing-swe-bench-verified/) — *Introducing SWE-bench Verified* — OpenAI, 2024 — E2 — human validation of issue/test task quality and gaming risks — methodology and linked dataset.
68. [SWE-smith](https://github.com/SWE-bench/SWE-smith) — *SWE-smith* — SWE-bench authors, continuously updated — E1 code — synthetic issue generation and verifier pipeline — generation/prompts/filters.
69. [OpenAI SWE-Lancer](https://openai.com/index/swe-lancer-benchmark/) — *SWE-Lancer* — OpenAI, 2025 — E1 benchmark report — economic task framing, end-to-end agent evaluation and human review — benchmark methods/data.
70. [SWE-Gym](https://github.com/SWE-Gym/SWE-Gym) — *SWE-Gym* — SWE-Gym authors, continuously updated — E1 code/data — trajectory-driven SWE tasks, environment and reward — generation/evaluation pipeline.
71. [Terminal-Bench](https://github.com/laude-institute/terminal-bench) — *Terminal-Bench* — Laude Institute, continuously updated — E1 code — terminal agents under isolated containers and command-based verification — task specs/harness.
72. [OSWorld](https://github.com/xlang-ai/OSWorld) — *OSWorld* — XLang AI, continuously updated — E1 code — visual computer-use tasks, VM snapshots and end-state evaluators — environment/evaluation implementation.
73. [WebArena](https://github.com/web-arena-x/webarena) — *WebArena* — Zhou et al., continuously updated — E1 code — self-hosted realistic web environments and programmatic success checks — environment setup/evaluators.
74. [BrowserGym](https://github.com/ServiceNow/BrowserGym) — *BrowserGym* — ServiceNow, continuously updated — E1 code — browser agent environment, task interfaces and reproducible evaluation — benchmark wrappers/evaluators.
75. [Agentless](https://github.com/OpenAutoCoder/Agentless) — *Agentless* — Xia et al., continuously updated — E1 code — decomposition into localization/repair/validation without interactive agent loop — prompts, patch ranking, tests.
76. [Agentless paper](https://arxiv.org/abs/2407.01489) — *Agentless: Demystifying LLM-based Software Engineering Agents* — Xia et al., 2024 — E3 paper — controlled ablation of localization, repair and validation — method and reproduction.
77. [OpenHands documentation](https://docs.all-hands.dev/) — *OpenHands documentation* — All Hands AI, continuously updated — E1 docs — agent benchmark invocation, sandbox/harness and reports — benchmark configuration and linked code.
78. [MetaGPT](https://github.com/geekan/MetaGPT) — *MetaGPT* — DeepWisdom, continuously updated — E1 code — SOP artifacts, role prompts, message routing and code review claims — `metagpt/`, examples, test evidence.
79. [MetaGPT paper](https://arxiv.org/abs/2308.00352) — *MetaGPT* — Hong et al., 2023 — E3 paper — SOP as prompt/program, role outputs and communication protocol — appendices/prompts plus code.
80. [ChatDev](https://github.com/OpenBMB/ChatDev) — *ChatDev* — OpenBMB, continuously updated — E1 code — chat-chain phases, role prompts, waterfall-style artifacts and review loop — `CompanyConfig`, prompts, examples.
81. [ChatDev paper](https://arxiv.org/abs/2307.07924) — *ChatDev* — Qian et al., 2023 — E3 paper — communicative agents, phase artifacts and failure analysis — paper plus repo configs.
82. [Devon](https://github.com/entropy-research/Devon) — *Devon* — Entropy Research, continuously updated — E1 code — planning/execution shell agent, checkpoints and web UI events — agent prompts/runtime/tests.

## E. CI/CD, policy-as-code, isolation, merge and supply-chain gates

83. [GitHub Agentic Workflows](https://docs.github.com/en/actions/tutorials/develop-agentic-workflows-in-github-actions) — *Develop agentic workflows in GitHub Actions* — GitHub, 2026 — E1 docs — Markdown workflow compiled to locked YAML, agent selection and review/commit boundary — `gh-aw` usage and generated files.
84. [GitHub Actions concurrency](https://docs.github.com/en/actions/how-tos/write-workflows/choose-when-workflows-run/control-workflow-concurrency) — *Control workflow concurrency* — GitHub, continuously updated — E1 docs — cancellation/serialization keys that prevent competing agent writes — concurrency semantics.
85. [GitHub Actions environments](https://docs.github.com/en/actions/how-tos/deploy/configure-and-manage-deployments/manage-environments) — *Manage environments* — GitHub, continuously updated — E1 docs — required reviewers, wait timers and deployment protection gates — environment protection configuration.
86. [GitHub required status checks](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-protected-branches/about-protected-branches) — *Protected branches* — GitHub, continuously updated — E1 docs — merge gate, reviews, signed commits, linear history — branch rules.
87. [GitHub merge queue](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/configuring-pull-request-merges/managing-a-merge-queue) — *Merge queue* — GitHub, continuously updated — E1 docs — serial integration validation against latest base — queue behavior/failure exit.
88. [GitLab CI resource groups](https://docs.gitlab.com/ci/resource_groups/) — *Resource groups* — GitLab, continuously updated — E1 docs — mutual exclusion for deployments/agent writes — process modes/queue ordering.
89. [GitLab CI retry](https://docs.gitlab.com/ci/yaml/#retry) — *retry keyword* — GitLab, continuously updated — E1 docs — bounded retries by failure class — YAML and exit-code conditions.
90. [GitLab CI rules](https://docs.gitlab.com/ci/jobs/job_rules/) — *CI/CD job rules* — GitLab, continuously updated — E1 docs — deterministic routing/conditions for job stages — rule evaluation and examples.
91. [Dagger CI](https://docs.dagger.io/) — *Dagger documentation* — Dagger, continuously updated — E1 docs — portable pipeline as code, containers/caching and typed steps — CI SDK/examples.
92. [Buildkite dynamic pipelines](https://buildkite.com/docs/pipelines/configure/dynamic-pipelines) — *Dynamic pipelines* — Buildkite, continuously updated — E1 docs — generated pipeline stages with controlled upload/ordering — examples and security implications.
93. [Tekton Tasks](https://tekton.dev/docs/pipelines/tasks/) — *Tekton Tasks* — CD Foundation, continuously updated — E1 docs — containerized task contracts, workspaces, results and retry — TaskRun semantics.
94. [OPA policy language](https://www.openpolicyagent.org/docs/latest/policy-language/) — *Rego policy language* — OPA authors, continuously updated — E1 docs — machine-enforced admission/CI decisions detached from LLM judgment — policy/tests and bundles.
95. [Conftest](https://www.conftest.dev/) — *Conftest* — Open Policy Agent community, continuously updated — E1 code/docs — policy-as-code checks over CI config/manifests — policy test integration.
96. [Google SLSA](https://slsa.dev/spec/v1.0/) — *SLSA specification* — OpenSSF, 2023 — E1 specification — provenance, isolated build and trustworthy artifact boundary — build levels/provenance fields.
97. [Sigstore Cosign](https://docs.sigstore.dev/cosign/) — *Cosign documentation* — Sigstore, continuously updated — E1 docs — signed artifacts/attestations and verification gate — keyless/signing policy.
98. [Google Cloud Build documentation](https://cloud.google.com/build/docs) — *Cloud Build documentation* — Google Cloud, continuously updated — E1 docs — explicit human approval state before deployment — approval lifecycle and IAM.
99. [Argo CD sync waves](https://argo-cd.readthedocs.io/en/stable/user-guide/sync-waves/) — *Sync phases and waves* — Argo CD, continuously updated — E1 docs — ordered deploy hooks and failure stop conditions — phases/waves/hooks.
100. [Backstage software templates](https://backstage.io/docs/features/software-templates/) — *Software Templates* — Spotify/Backstage, continuously updated — E1 docs — scaffolded repo contracts, actions, reviewable inputs/outputs — template spec/action implementation.

## Приоритет первого чтения

Сначала брать в детальный пул: 2, 3, 5, 10–15, 20–24, 29–35, 36–41, 49–57, 65–77, 83–90 и 94–99. Это источники, где наиболее вероятно найти не ролевую болтовню, а исполнимые состояния, границы полномочий и коды переходов. Пункты 78–82 использовать как исторические/сравнительные примеры: их заявления о «командах ролей» нельзя переносить без проверки evaluator и реального кода.

## Ограничения каталога

Название, автор и дата отражают страницу/репозиторий на момент среза; у continuously updated материалов дата помечена именно так, потому что URL без pinned commit не является неизменяемым доказательством. На стадии подробного разбора каждый GitHub-источник должен получить commit SHA/permalink, а каждый документ — дату версии или архивную копию.
