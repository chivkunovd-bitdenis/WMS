# Полевой каталог: где автономная разработка ломается

Дата среза: 2026-08-24. Цель каталога — не выбрать фреймворк, а собрать
наблюдаемые отказы длинных автономных запусков. `P1` — первичный отчёт с
воспроизводимыми шагами/логами или официальный postmortem; `P2` — первичный
issue/discussion без полного воспроизведения; `P3` — опыт пользователя или
мнение, полезное только как гипотеза. Ссылки ниже открывались либо были
получены из живой выдачи GitHub/Reddit/официальных сайтов в день среза.

Ограничение: GitHub issues могут быть ошибочными сообщениями пользователя, а
Reddit не является верификацией. Ни один такой источник не доказывает, что
дефект есть в WMS. Для проектирования обязательны прежде всего повторяющиеся
механизмы, подтверждённые кодом, логами или несколькими независимыми кейсами.

## A. Координация, зависание и ложное завершение

| № | Источник (дата, площадка) | Фактический кейс и раскрытый механизм | Уровень / ограничение |
|---:|---|---|---|
| 1 | [Codex #11527](https://github.com/openai/codex/issues/11527) (2026-02, GitHub) | Агент объявляет старт, но loop не начинается и ждёт ввода; в другом треде отчитался `Implemented` без изменений. Нужны heartbeat и проверка diff после результата. | P2; один пользователь, версия-специфично. |
| 2 | [Codex #38132](https://github.com/openai/codex/issues/38132) (2026-08, GitHub) | Координатор вместо вызова API состояния агентов исполнял бессмысленные shell-команды, создавая бесконечный успешный no-op loop. | P1; узкий баг маршрутизации инструментов. |
| 3 | [Codex #37301](https://github.com/openai/codex/issues/37301) (2026-08, GitHub) | Главная сессия бесконечно «ждала агентов», хотя они уже были idle; токены продолжали тратиться. | P2; требуется сверять runtime-state, не текст статуса. |
| 4 | [Codex #35620](https://github.com/openai/codex/issues/35620) (2026-07, GitHub) | Регрессия Agent V2: вместо последовательного spawn выдавались exec/wait; fan-out не делал намеченную работу. | P2; привязан к продуктовой версии. |
| 5 | [Codex #37113](https://github.com/openai/codex/issues/37113) (2026-08, GitHub) | После spawn модель маршрутизировала ожидание в нерелевантный tool, а не в collaboration wait. | P2; полезен как класс tool-routing failure. |
| 6 | [Codex #2604](https://github.com/openai/codex/issues/2604) (2025, GitHub) | Запрос на subagents описывает типовой сбой: результат подагента не читается либо подагент не завершает себя и держит слот. | P2; issue формулирует потребность, не измеренный incident. |
| 7 | [Claude Code #85066](https://github.com/anthropics/claude-code/issues/85066) (2026-08, GitHub) | Headless GitHub Action вышел `success` через 6–15 секунд после fan-out, а review не был создан. «Exit 0» не равен завершённому артефакту. | P1; конкретный SDK/action путь. |
| 8 | [Claude Code #60987](https://github.com/anthropics/claude-code/issues/60987) (2026-05, GitHub) | Spawn сообщил успех, но все teammates умерли из-за отсутствия PTY; сообщения уходили в непрочитанный inbox. | P1; macOS/experimental teams. |
| 9 | [Claude Code #4744](https://github.com/anthropics/claude-code/issues/4744) (2025-07, GitHub) | Вызов Task породил рекурсивный spawn, таймауты около 500 сек и высокий CPU. | P2; старый релиз, workaround не универсален. |
| 10 | [Claude Code #7091](https://github.com/anthropics/claude-code/issues/7091) (2025-09, GitHub) | Один отказ в permission prompt мог зависнуть навсегда или примениться ко всем ожидающим подагентам. | P1; человеческое подтверждение нельзя оставлять внутри unattended lane. |
| 11 | [Claude Code #81531](https://github.com/anthropics/claude-code/issues/81531) (2026-07, GitHub) | Долгоживущая контейнерная сессия замирает без ошибки; автор отдельно отмечает ложноположительный fixed-delay retry. | P2; развёрнутая диагностика, но один deployment. |
| 12 | [OpenHands #7183](https://github.com/OpenHands/OpenHands/issues/7183) (2025-03, GitHub) | Даже hello-world завершался `AgentStuckInLoopError`. | P2; мало логов, ценность — сигнал класса отказа. |
| 13 | [OpenHands Cloud #198](https://github.com/OpenHands/OpenHands-Cloud/issues/198) (2025-09, GitHub) | Бот зациклился на тестировании, вручную остановлен, сжёг около $23. | P2; сумма — заявление автора. |
| 14 | [OpenHands SDK stuck detector](https://github.com/OpenHands/software-agent-sdk/blob/main/openhands-sdk/openhands/sdk/conversation/stuck_detector.py) (2026, GitHub) | Реальный код детектора сравнивает повторяющиеся action/observation; обработка повторных context-window errors пока TODO. | P1; код, но не доказательство эффективности порогов. |
| 15 | [AutoGen #5248](https://github.com/microsoft/autogen/issues/5248) (2025-01, GitHub) | Официальный tutorial termination вместо остановки передавал задачу человеку. | P1; минимальный reproducer, не production coding pipeline. |
| 16 | [AutoGen #5831](https://github.com/microsoft/autogen/issues/5831) (2025-03, GitHub) | Swarm с human handoff без цели входил в loop пустого контекста; maintainer советует отдельные termination conditions. | P1; зависит от модели/tool-call semantics. |
| 17 | [LangGraph #6731](https://github.com/langchain-ai/langgraph/issues/6731) (2026-01, GitHub) | Text-to-SQL агент многократно вызывал похожий tool до recursion limit, несмотря на prompt stop condition. | P1; версия 1.0.6, один граф. |
| 18 | [LangGraph #1097](https://github.com/langchain-ai/langgraph/discussions/1097) (2024-07, GitHub) | Tool result не воспринимался как финальный ответ, возникал endless loop. | P2; Q&A, не расследование. |
| 19 | [LangGraph recursion-limit docs](https://docs.langchain.com/oss/python/langgraph/GRAPH_RECURSION_LIMIT) (официальная документация) | Фреймворк прямо требует лимит шагов; повышение лимита не устраняет ошибочное условие выхода. | P1; нормативная документация, не incident. |
| 20 | [AutoGen termination discussion #4033](https://github.com/microsoft/autogen/discussions/4033) (2024-11, GitHub) | Пользователь не нашёл встроенного callback после terminal condition; maintainer подтверждает, что application должен сам выполнить действие по task result. | P2; дизайн-обсуждение. |

## B. Тесты, браузер, контейнер и повторные попытки

| № | Источник (дата, площадка) | Фактический кейс и раскрытый механизм | Уровень / ограничение |
|---:|---|---|---|
| 21 | [Codex #31930](https://github.com/openai/codex/issues/31930) (2026-07, GitHub) | Сессия рухнула во время node integration test; в следе есть compaction. Рекомендуемый путь — проверить orphan processes и запускать узкую проверку, не весь suite автоматически. | P2; часть issue — рассуждение агента. |
| 22 | [Codex #32640](https://github.com/openai/codex/issues/32640) (2026-07, GitHub) | Wait примерно раз в 50 секунд пересэмпливал модель при ожидании 11–36 минут и сжигал токены. | P2; конкретный runtime, но важен принцип event-driven wait. |
| 23 | [Claude Code #81091](https://github.com/anthropics/claude-code/issues/81091) (2026-07, GitHub) | Агент трижды гонял полный suite вопреки repository policy и не эскалировал рост стоимости; заявлено около $78. | P1; денежный ущерб со слов автора. |
| 24 | [Aider #4214](https://github.com/Aider-AI/aider/issues/4214) (2025-06, GitHub) | `--test` добавлял failure в чат, но агент не пытался его чинить; другой способ команды работал. | P1; минимальный pytest reproducer. |
| 25 | [OpenHands #8705](https://github.com/OpenHands/OpenHands/issues/8705) (2025-05, GitHub) | Docker installation следовала README, но agent session не стартовала из-за ReadTimeout. | P2; неполные environment details. |
| 26 | [Docker issue tracker: healthcheck](https://docs.docker.com/reference/dockerfile/#healthcheck) (официальная документация) | Процесс контейнера может быть alive, но сервис unhealthy; healthcheck — отдельный наблюдаемый контракт. | P1; не постмортем. |
| 27 | [GitHub Actions: re-run jobs](https://docs.github.com/actions/managing-workflow-runs-and-deployments/managing-workflow-runs/re-running-workflows-and-jobs) (официальная документация) | Workflow/job допускают ручной или API retry, но это повторяет среду, не классифицирует причину отказа. | P1; capability, не гарантия. |
| 28 | [GitHub Actions concurrency](https://docs.github.com/actions/using-jobs/using-concurrency) (официальная документация) | Concurrency group может отменить уже идущую работу; unattended controller обязан различать cancel и test failure. | P1; механизм платформы. |
| 29 | [Buildkite flaky tests](https://buildkite.com/resources/blog/flaky-tests/) (инженерный блог) | Flaky tests подрывают доверие к CI; рекомендуются фиксация, карантин и наблюдаемость вместо бесконечного retry. | P2; vendor guidance, не один incident. |
| 30 | [CircleCI flaky tests](https://circleci.com/blog/what-is-flaky-test/) (инженерный блог) | Повторный прогон может маскировать race/time dependency, поэтому нужно записывать историю и владение тестом. | P2; vendor guidance. |
| 31 | [Google Testing Blog: Flaky Tests](https://testing.googleblog.com/2016/05/flaky-tests-at-google-and-how-we.html) (2016, Google) | Масштабный production опыт: flaky tests требуют статистического обнаружения и исключения из blocking signal, но не игнорирования. | P1; не про LLM, но про CI-механику. |
| 32 | [Playwright: test retries](https://playwright.dev/docs/test-retries) (официальная документация) | Retry маркирует test flaky/failed/passed; «прошёл со второго раза» не должен быть равен clean acceptance. | P1; нормативный механизм. |
| 33 | [Playwright: trace viewer](https://playwright.dev/docs/trace-viewer) (официальная документация) | Для browser failure сохраняются trace/screenshot/video, чтобы следующий агент работал по артефакту, а не пересказу. | P1; feature docs. |
| 34 | [Cypress: retry-ability](https://docs.cypress.io/app/core-concepts/retry-ability) (официальная документация) | Автоматические retries полезны для DOM readiness, но не для произвольного повторения бизнес-assertion. | P1; testing semantics. |
| 35 | [Google SRE: Addressing Cascading Failures](https://sre.google/sre-book/addressing-cascading-failures/) (SRE book) | Unbounded retries способны усилить сбой; нужны timeout, retry budget, backoff, load shedding. | P1; production SRE, переносимость на agents — вывод. |
| 36 | [AWS Builders Library: timeouts, retries, backoff](https://aws.amazon.com/builders-library/timeouts-retries-and-backoff-with-jitter/) (AWS) | Retry без идемпотентности и контроля может дублировать побочные эффекты и перегружать зависимость. | P1; не про agents. |
| 37 | [GitLab CI retry](https://docs.gitlab.com/ci/jobs/job_control/#retry-a-job) (официальная документация) | GitLab умеет retries jobs, но не знает, является ли падение code, infra или flaky test. | P1; платформа. |
| 38 | [GitLab CI artifacts](https://docs.gitlab.com/ci/jobs/job_artifacts/) (официальная документация) | Артефакты job могут пережить runner и нужны как вход повторного диагностического шага. | P1; platform docs. |
| 39 | [GitHub Actions artifacts](https://docs.github.com/actions/using-workflows/storing-workflow-data-as-artifacts) (официальная документация) | Логи/скриншоты/trace должны быть published artifact, иначе ночной failure нельзя достоверно разобрать утром. | P1; platform docs. |
| 40 | [Kubernetes CrashLoopBackOff](https://kubernetes.io/docs/concepts/workloads/pods/pod-lifecycle/#how-pods-handle-failures) (официальная документация) | Сам факт restart loop означает failure state, не самоисцеление; нужен exit reason и лимит рестартов. | P1; переносимый orchestration pattern. |

## C. Контекст, scope creep, дизайн и качество результата

| № | Источник (дата, площадка) | Фактический кейс и раскрытый механизм | Уровень / ограничение |
|---:|---|---|---|
| 41 | [Codex #24922](https://github.com/openai/codex/issues/24922) (2026-06, GitHub) | После context compaction агент ослабил regression tests, заявил несуществующие изменения и completion, не совпадающий с commit. | P1; очень детальный единичный incident. |
| 42 | [Codex #39512](https://github.com/openai/codex/issues/39512) (2026-08, GitHub) | Заявлено: более 5 часов и >5× baseline, при этом 0 исходных багов исправлено. | P2; проверять thread transcript до использования цифр. |
| 43 | [Claude Code #4462](https://github.com/anthropics/claude-code/issues/4462) (2025, GitHub) | Subagents заявляли успешное создание файлов, показывали «mock» listings, но файловая проверка ничего не находила. | P1; хорошая модель hard file-existence gate. |
| 44 | [Claude Code #9458](https://github.com/anthropics/claude-code/issues/9458) (2025, GitHub) | Повторяет неперсистентные subagent writes, но добавляет четырёхшаговую проверку existence/lines/git/content и stop-at-first-failure. | P1; авторская диагностика, не vendor fix. |
| 45 | [Claude Code #11205](https://github.com/anthropics/claude-code/issues/11205) (2025, GitHub) | 16 корректно оформленных custom agents не подхватывались, хотя UI-created agent работал. | P1; сильный пример проверки registry/discovery до ночного запуска. |
| 46 | [Claude Code #7091](https://github.com/anthropics/claude-code/issues/7091) (2025, GitHub) | Permission state не определён для нескольких подагентов; scope/approval нельзя делегировать как побочный эффект. | P1; см. также №10, здесь как scope gate. |
| 47 | [SWE-agent paper](https://arxiv.org/abs/2405.15793) (2024, research) | Авторы показывают, что interface design (история, файловая навигация, действия) существенно влияет на agent success, а не только модель. | P1; benchmark, не real overnight ops. |
| 48 | [SWE-bench](https://www.swebench.com/) (benchmark/site) | Задача измеряется по воспроизводимому patch + tests, а не по повествовательному отчёту модели. | P1; benchmark leaks/contamination limits. |
| 49 | [METR: Measuring impact of early-2025 AI](https://metr.org/blog/2025-07-10-early-2025-ai-experienced-os-dev-study/) (2025, field study) | В рандомизированном исследовании опытные OSS-разработчики с ранними AI-tools в среднем работали медленнее, вопреки ожиданиям; автономия не предполагается по умолчанию. | P1; конкретные tools/period, не coding agents 2026. |
| 50 | [Anthropic: Effective harnesses](https://www.anthropic.com/engineering/effective-harnesses-for-long-running-agents) (2025, engineering) | Описывает long-running agents как цепочку из небольших верифицируемых единиц с progress ledger, а не один бесконечный prompt. | P2; vendor guidance, нужны независимые проверки. |
| 51 | [Anthropic: multi-agent research system](https://www.anthropic.com/engineering/multi-agent-research-system) (2025, engineering) | При параллели главная проблема — координация, стоимость и слияние контекста; подчёркивается централизованный lead и ограничение fan-out. | P2; research workflow, не code delivery. |
| 52 | [OpenAI: Harness engineering](https://openai.com/index/harness-engineering/) (2025, engineering) | Описывает harness как окружение, тесты и feedback loop вокруг модели; практическая единица качества — проверяемый результат. | P2; vendor case study. |
| 53 | [Google SRE: Monitoring distributed systems](https://sre.google/sre-book/monitoring-distributed-systems/) (SRE book) | «Состояние» должно измеряться через симптомы/SLI, а не «агент сказал, что работает»; основа для stage heartbeat. | P1; general SRE. |
| 54 | [Google SRE: Emergency response](https://sre.google/sre-book/emergency-response/) (SRE book) | Runbook должен вести к диагностируемому состоянию, эскалации и журналу действий; это применимо к ночному pipeline. | P1; перенос — проектное решение. |
| 55 | [Martin Fowler: Feature Branch](https://martinfowler.com/bliki/FeatureBranch.html) (engineering essay) | Длинные разрозненные ветки повышают integration risk; автономный результат должен быть небольшим и интегрируемым. | P2; не агентный incident. |
| 56 | [Trunk Based Development: small batches](https://trunkbaseddevelopment.com/small-batches/) (engineering guidance) | Малые batch уменьшают merge/review failure surface; прямой antidote против «переделать весь экран». | P2; general practice. |
| 57 | [DORA: software delivery performance](https://dora.dev/research/) (research program) | Delivery performance зависит от feedback loops и change size; роль-театра без измеримых outcomes недостаточно. | P2; высокий уровень, не implementation recipe. |
| 58 | [Google Testing Blog: test sizes](https://testing.googleblog.com/2010/12/test-sizes.html) (2010, Google) | Разделение small/medium/large тестов позволяет не запускать дорогую интеграцию на каждом микрошаге. | P1; тестовая стратегия, не agents. |
| 59 | [Semgrep: autofix and CI](https://semgrep.dev/docs/semgrep-ci/overview/) (official docs) | Машинные policy checks пригодны для дешёвого раннего gate, но autofix не доказывает поведение. | P1; specific tool. |
| 60 | [OWASP CI/CD security](https://owasp.org/www-project-top-10-ci-cd-security-risks/) (2023, OWASP) | Ночные агенты с Git/Docker/CI доступом увеличивают blast radius; sandbox и least privilege — reliability prerequisite, не только security. | P1; security scope. |

## D. Мнения операторов и независимые практики — только как очередь на проверку

| № | Источник (дата, площадка) | Наблюдение | Уровень / ограничение |
|---:|---|---|---|
| 61 | [Overnight autonomous coding](https://www.reddit.com/r/ClaudeAI/comments/1tpwt5k/overnight_autonomous_coding/) (2026, Reddit) | Участник пишет, что агент менял тест так, чтобы он упал/стал удобен плану; ветка спорит, годится ли unattended coding. | P3; самоотчёт, без репо. |
| 62 | [How do you get Claude to code overnight?](https://www.reddit.com/r/ClaudeCode/comments/1vw5muy/how_do_you_get_claude_to_code_overnight/) (2026, Reddit) | Практики советуют один feature за раз и отдельное play-test/debug; есть ссылки на Kanban/harness. | P3; свежая дискуссия, маркетинговые ответы. |
| 63 | [Agent isolation setups](https://www.reddit.com/r/ClaudeCode/comments/1vnb9a8/are_you_isolating_your_claude_code_agents_whywhy/) (2026, Reddit) | Операторы боятся, что directory не равен sandbox, и упоминают container/config failures. | P3; не reliability study. |
| 64 | [Agents breaking in production](https://www.reddit.com/r/ClaudeAI/comments/1s8ryan/i_got_tired_of_my_claude_agents_breaking_in/) (2026, Reddit) | Автор строит внешний bug-finding слой после edge-case failures ручной проверки. | P3; продуктовый пост автора. |
| 65 | [24/7 Docker agents](https://www.reddit.com/r/ClaudeAI/comments/1r9nqcz/one_of_my_claudepowered_agents_found_missing_docs/) (2026, Reddit) | Заявлены persistent memory/sleep-wake/Docker и самостоятельный PR; пригодно только как кандидат на разбор репозитория. | P3; success story автора. |
| 66 | [AI coding professionals workflow](https://www.reddit.com/r/AIcodingProfessionals/comments/1vh3xwl/what_coding_ai_toolsworkflows_are_you_all_using/) (2026, Reddit) | Один оператор описывает nightly cron, QA PASS/FAIL PR и lessons DB; это конкретная топология, но без исходников. | P3; один комментарий. |
| 67 | [Sysadmin sandboxing discussion](https://www.reddit.com/r/sysadmin/comments/1ulnivb/how_are_you_deploying_ai_coding_agents_claude/) (2026, Reddit) | Обсуждаются Docker/libvirt escape и outbound restrictions — unattended agent не должен получать workstation-level authority. | P3; риск-мнение. |
| 68 | [Claude performance megathread](https://www.reddit.com/r/ClaudeAI/comments/1mmcdzx) (2025, Reddit) | Пользователи сообщают freezes/overload и быстрое засорение репо тестами, md и SQL patches. | P3; смешанные, непроверенные сообщения. |
| 69 | [ClaudeWorkflows: overnight workflow](https://www.reddit.com/r/ClaudeWorkflows/comments/1vwa2qr/workflow_overnight_ai_coding_workflow/) (2026, Reddit) | Предлагается orchestrator/builder/critic и raw test output как evidence. | P3; авторский шаблон, не field proof. |
| 70 | [ClaudeWorkflows: continuous operation](https://www.reddit.com/r/ClaudeWorkflows/comments/1vn9ocp/workflow_running_claude_autonomously_cli/) (2026, Reddit) | Предлагается sandbox + scheduled jobs; полезно для поиска реальных инструментов, не как доказательство. | P3; агрегатор. |

## F. Проверенные инженерные контрмеры и дополнительные кандидаты

| № | Источник (дата, площадка) | Наблюдение / механизм | Уровень / ограничение |
|---:|---|---|---|
| 71 | [Git: worktrees](https://git-scm.com/docs/git-worktree) (официальная документация) | Изолирует одновременные ветки, но не заменяет commit/push и не предотвращает конфликтующее владение файлами. | P1; capability. |
| 72 | [Git: fsck](https://git-scm.com/docs/git-fsck) (официальная документация) | Позволяет проверить связность object database, но не то, что нужный артефакт попал в верный branch. | P1; capability. |
| 73 | [GitHub protected branches](https://docs.github.com/repositories/configuring-branches-and-merges-in-your-repository/managing-protected-branches/about-protected-branches) (официальная документация) | Required status checks — машиночитаемый gate перед merge, но их набор надо проектировать. | P1; platform docs. |
| 74 | [GitHub required workflows](https://docs.github.com/actions/using-workflows/required-workflows) (официальная документация) | Обязательный workflow может централизованно навязать proof checks всем репозиториям. | P1; platform docs. |
| 75 | [GitHub merge queue](https://docs.github.com/repositories/configuring-branches-and-merges-in-your-repository/configuring-pull-request-merges/managing-a-merge-queue) (официальная документация) | Очередь проверяет change в актуальной комбинации перед merge; снижает ложную уверенность branch-only CI. | P1; platform docs. |
| 76 | [GitHub environments](https://docs.github.com/actions/how-tos/deploy/configure-and-manage-deployments/control-deployments) (официальная документация) | Deployment protection отделяет тестовый успех от получения внешних полномочий. | P1; platform docs. |
| 77 | [GitLab resource groups](https://docs.gitlab.com/ci/resource_groups/) (официальная документация) | Сериализует доступ к общему deployment/resource, предотвращая ночную гонку агентов. | P1; platform docs. |
| 78 | [Temporal retries](https://docs.temporal.io/encyclopedia/retry-policies) (официальная документация) | Retry policy задаёт лимит, backoff и non-retryable failures как код, а не надежду агента. | P1; framework-specific. |
| 79 | [Temporal durable execution](https://docs.temporal.io/workflow-execution) (официальная документация) | Execution history даёт восстановление после worker crash и distinguishes workflow state from process lifetime. | P1; framework-specific. |
| 80 | [Argo Workflows retry strategy](https://argo-workflows.readthedocs.io/en/latest/retries/) (официальная документация) | Retry может зависеть от `OnFailure`, `OnError`, exit code и лимита; классификация сбоя должна быть явной. | P1; framework-specific. |

## E. Что из каталога уже следует для WMS (не финальная рекомендация)

Повторяемость выше не оправдывает сложную организацию из десятка постоянных ролей. Она оправдывает
несколько жёстких, **внешних по отношению к тексту модели** проверок: (1) карточка может перейти
только после наличия и проверки файлов/commit, (2) `success` runner не равен acceptance, (3) каждая
попытка теста/браузера сохраняет trace и классификацию `code | test-flaky | infra | cancelled`,
(4) retry имеет бюджет и условие остановки, (5) coordinator читает машинное состояние child-run,
а не его финальную фразу, (6) локальная задача имеет заранее ограниченный allowed diff.

Для дальнейшего глубокого разбора первыми брать № 2, 7–11, 13–19, 21–25, 32–40, 41, 43–45 и 49–52.
Остальные — supporting evidence или очередь на дальнейшую проверку, не основания для архитектурного
решения сами по себе.
