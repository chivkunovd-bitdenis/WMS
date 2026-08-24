# Agentflow — детальный reverse engineering

**Версия и проверка.** Репозиторий [saintdle/agentflow @ `7fc79ea583ef25234ee87d24ac4b78535e9c0c06`](https://github.com/saintdle/agentflow/tree/7fc79ea583ef25234ee87d24ac4b78535e9c0c06), HEAD зафиксирован 2026-08-24. Уровень: **E1** — исполняемый Python-код и тесты. Граница: это controller/adapter вокруг внешних task backend и coding CLIs. Он не является продуктовым планировщиком, CI merge queue или браузерным acceptance runner.

## Карта компонентов

| Компонент | Ответственность | Durable артефакт |
|---|---|---|
| `RootController` | единственный владелец root, schedule/resume/halt/advance | controller JSON + checkpoint |
| `Lease`/fence | исключает второго controller и старый процесс после takeover | epoch, token, hashed resume secret, continuity id |
| checkpoint module | записывает указатель текущей задачи до side effect | `*.checkpoint.json` |
| worktree module | разрешает base ref и сверяет resolved SHA | isolated worktree / pinned base |
| adapters/router | provider manifest, argv, gate reports | provider invocation/result |
| resource agents | provider-specific instructions/reviewer profiles | TOML prompt/config |
| external task backend | выбирает/переходит task и подтверждает completion | вне controller, например Beads/Herdr |

Controller сохраняет `schema=agentflow.controller, version=1` atomically под flock ([инициализация и write](https://github.com/saintdle/agentflow/blob/7fc79ea583ef25234ee87d24ac4b78535e9c0c06/src/agentflow/controller.py#L230-L281)). Это отдельное от task-backend state: controller не имеет права сам объявлять исходную задачу выполненной.

## Точная модель состояния

Terminal set ровно `completed`, `failed`, `blocked`, `halted`, `terminal` ([L28](https://github.com/saintdle/agentflow/blob/7fc79ea583ef25234ee87d24ac4b78535e9c0c06/src/agentflow/controller.py#L28)). Остальные фактически используемые checkpoint states: `idle`, `claimed_no_session`, `claimed`, `launched`, `running`, `identity_pending` ([resume guard](https://github.com/saintdle/agentflow/blob/7fc79ea583ef25234ee87d24ac4b78535e9c0c06/src/agentflow/controller.py#L647-L654)). Checkpoint schema включает `task`, `phase`, `next_action`, `root`, `controller`, `actor`, `claim_id`, `epoch`, `lease_token`, `session_id`, `state/status`, `terminal`, а terminal path добавляет `terminal_reason` ([build/save/result](https://github.com/saintdle/agentflow/blob/7fc79ea583ef25234ee87d24ac4b78535e9c0c06/src/agentflow/controller.py#L585-L631), [halt](https://github.com/saintdle/agentflow/blob/7fc79ea583ef25234ee87d24ac4b78535e9c0c06/src/agentflow/controller.py#L716-L743)).

Lease schema: `root, controller, epoch, token, acquired_at, heartbeat_at, owner_id, resume_secret_hash, continuity_id`; plaintext resume secret специально исключён из storage ([L120-L151](https://github.com/saintdle/agentflow/blob/7fc79ea583ef25234ee87d24ac4b78535e9c0c06/src/agentflow/controller.py#L120-L151)).

## Таблица переходов

| From | Условие/исполнитель | To | Машинная защита |
|---|---|---|---|
| нет lease | `acquire()` | leased, new epoch | random resume secret, atomic state |
| live foreign lease | age ≤ `stale_after` | error | `DuplicateController` |
| stale lease | только `takeover=True` | new epoch | старый token fenced |
| live same lease | valid private resume proof | reattached new epoch | token/secret rotate, continuity retained |
| `idle` | deterministic sorted task selection | `claimed_no_session` | checkpoint **до** dispatch |
| `claimed_no_session` | provider dispatch returns session | `running` или supplied state | controller re-fences after long dispatch |
| `claimed_no_session` | crash/no session | remains claimed | no implicit rerun |
| claimed/running/launched/identity_pending | `resume()` | same result | returns, does not redispatch |
| terminal | `resume()` | same terminal result | `halted=True` |
| externally confirmed task complete | `advance()` | nonterminal clear pointer | external backend must have transitioned task |
| any | `halt(valid-terminal, reason)` | terminal | reason and `no further scheduling` persisted |

Полный key path — [`resume`, L633–712](https://github.com/saintdle/agentflow/blob/7fc79ea583ef25234ee87d24ac4b78535e9c0c06/src/agentflow/controller.py#L633-L712): он записывает `claimed_no_session` до provider call; исключение намеренно оставляет этот audit marker. Поэтому падение runner не превращается в второй запуск модели с тем же task. `advance()` допускается только после независимо подтверждённого external result ([L745–754](https://github.com/saintdle/agentflow/blob/7fc79ea583ef25234ee87d24ac4b78535e9c0c06/src/agentflow/controller.py#L745-L754)).

## Retry, resume и reconcile

Это не retry engine. `resume()` выбирает новую задачу только из idle; in-flight states возвращаются вызывающему. Для crash recovery оператор/верхний controller должен исследовать provider session/task backend и либо завершить, либо сделать explicit reconcile/advance/halt. Lease takeover тоже не автоматический: heartbeat просрочен и нужен явный `takeover=True`. Аутентифицированный reattach поворачивает epoch/token/secret, чтобы displaced process не мог продолжить запись ([acquire logic L290–379](https://github.com/saintdle/agentflow/blob/7fc79ea583ef25234ee87d24ac4b78535e9c0c06/src/agentflow/controller.py#L290-L379)). Checkpoint write повторно проверяет lease под тем же lock, закрывая TOCTOU window ([L603–619](https://github.com/saintdle/agentflow/blob/7fc79ea583ef25234ee87d24ac4b78535e9c0c06/src/agentflow/controller.py#L603-L619)).

## Prompts, artifacts, Git/isolation и scope

Модель не принимает controller transitions. Ей доступны provider-specific profiles, например [Codex reviewer TOML](https://github.com/saintdle/agentflow/blob/7fc79ea583ef25234ee87d24ac4b78535e9c0c06/src/agentflow/resources/agents/codex/agentflow-reviewer.toml); exact prompt/CLI contract зависит от adapter. Worktree admission проверяет, что base ref resolves to required commit ([worktree L63–77](https://github.com/saintdle/agentflow/blob/7fc79ea583ef25234ee87d24ac4b78535e9c0c06/src/agentflow/worktree.py#L63-L77)), то есть старт воспроизводим и изолирован.

Но repository evidence не подтверждает global file allowlist, UX/product contract, automatic commit/PR merge или browser gate. Scope поэтому ограничен главным образом approved root/task/backend и pinned base, не смысловой проверкой diff. Controller также не ведёт универсальный счётчик токенов/денег или ограничение числа provider attempts; его loop brake — state idempotency и terminal halt, а budget должен дать внешний dispatcher/provider.

## Tests и практический вердикт

[test_controller.py](https://github.com/saintdle/agentflow/blob/7fc79ea583ef25234ee87d24ac4b78535e9c0c06/tests/test_controller.py) проверяет duplicate owner, stale takeover, reattach, checkpoint ownership, terminal idempotency и claim-before-dispatch; [workflow resilience tests](https://github.com/saintdle/agentflow/blob/7fc79ea583ef25234ee87d24ac4b78535e9c0c06/tests/test_workflow_resilience.py) — boundary/recovery scenarios; [provider argv tests](https://github.com/saintdle/agentflow/blob/7fc79ea583ef25234ee87d24ac4b78535e9c0c06/tests/test_provider_argv.py) — adapter invocation contract.

**Для WMS — адаптировать:** pre-side-effect durable claim, lease fencing, explicit reconcile и pinned base SHA. **Не брать как готовый ночной pipeline:** нужны отдельно product/UX contract before Dev, file-scope gate, failure taxonomy with bounded infra retry, CI/test evidence, live-browser judge, commit/push/merge/deploy proof и cost limits. Неизвестно из просмотренных модулей: точная semantics каждого external backend transition, provider-specific actual prompts at runtime, and whether any deployment integration is used in a production run.
