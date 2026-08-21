# S12 TASK_CUT - BLG-I16

## Verdict

`TASK_CUT_READY`

## Atomic vertical card

### `BLG-I16-C1` - Mass complete packing as one durable supply operation

**Observable operational result.** On the existing supply surface, one press
of `Всё упаковано` submits one server-accepted bulk intent for the current
supply. The operator receives a prompt truthful result for the whole supply,
or a recoverable accepted-operation state with visible progress and a final
read-back. The browser no longer serially sends mutating requests for each
line. A repeat press, lost response, reload, worker retry, or duplicate
delivery converges to the same operation and does not duplicate warehouse
effects.

**Vertical boundary.** The card contains the complete user-to-durable-result
path: accepting a bounded target set; preserving each existing line-level
eligibility check; durable idempotency and operation state; processing and
recovery; an authoritative operation/result read path; and the existing
operator surface's accepted, running, complete, partial, empty, rejected, and
recoverable-unknown outcomes. It is independently useful only as one card:
the server operation without truthful operator read-back leaves a warehouse
worker opaque, while UI feedback without one durable operation leaves the
current serial mutation behavior in place.

**Required invariants.**

1. Acceptance captures the current supply and a deterministic target set.
   Replays cannot expand that set or start a competing operation.
2. The bulk path preserves all existing authorization, marking, quantity, box,
   stock, reservation, status, and other line-level business checks. It does
   not repair KIZ, stock, boxes, or supply composition.
3. Each line's business effect occurs at most once for the accepted intent.
   Existingly complete lines are reported as such, rather than changed again.
4. A failed or conflicting line cannot erase completed lines. A partial result
   names the unfinished lines and their reasons, and never presents the supply
   as fully packed.
5. Reload and recovery obtain the authoritative server result. A local spinner,
   a bare HTTP success, or a lost response is not completion evidence.
6. The card adds no alternate manual completion flow and makes no external
   marketplace call.

## Acceptance surface for S15

| ID | Fixture / oracle | Expected observable result |
| --- | --- | --- |
| `I16-C1-AC01` | Supply with multiple independently eligible unfinished lines | One user action creates one bulk operation; all eligible target lines complete under their existing rules; read-back reports a full result and the browser issued no per-line mutation sequence. |
| `I16-C1-AC02` | Large representative supply that cannot safely finish in normal interactive wait | The action is acknowledged as one accepted operation; progress is truthful and recoverable; final read-back provides the whole-supply result without a frozen or indefinitely silent screen. |
| `I16-C1-AC03` | Duplicate request/double press, lost response then retry, page reload, and worker retry for the same accepted intent | There is one target set and no duplicated line/business effects; every path returns the same current or final operation result. |
| `I16-C1-AC04` | Mixed target set with eligible lines plus lines blocked by existing marking, quantity, box, stock, reservation, status, role, or other eligibility checks | Safe lines retain their completed result; each unfinished line is discoverable with a concrete reason; supply-level status is not falsely complete. |
| `I16-C1-AC05` | All target lines already complete, and a supply with no actionable target for another business reason | The former returns an idempotent completed summary with no new effect; the latter returns a truthful zero-change or business-rejection outcome. |
| `I16-C1-AC06` | General rejection before work: wrong supply, absent authority, or invalid shared precondition | The server accepts no operation work and leaves no partial changes; the operator receives the existing appropriate rejection state. |
| `I16-C1-AC07` | Concurrent line change while the operation runs, followed by a system interruption after some lines completed | The newer state is not overwritten; completed lines survive recovery; remaining lines are reported as incomplete/conflicted, never silently skipped or duplicated. |
| `I16-C1-AC08` | Completed and partial operations followed by ordinary page reload | Server read-back restores the same counts, per-line outcomes, and applicable supply status; no local-only result disappears or becomes a new operation. |

S15 must turn each row into deterministic direct and breaker cases, with
isolated local fixtures, reset/recovery method, assertions for the one-mutation
boundary, and volume coverage. It must add a visible-interface case if the
implementation introduces progress or result UI; the post-diff classifier must
then add `ui_change` and route the required S09/S10/S24/S25 work before
development acceptance.

## Delivery boundaries and handoff

1. This is one atomic vertical card, not separate frontend, route, database, or
   worker cards. Splitting those layers would not leave an observable safe
   warehouse result.
2. `S13 ARCHITECT_PLAN` owns the resource graph, API contract, persistence and
   additive migration design, locking/transaction boundaries, idempotency-key
   semantics, worker/retry strategy, operation status transport, performance
   threshold, UI-kit assessment, exact files, and worktree locks. This cut
   selects none of those implementation details.
3. `S15 CASE_FACTORY` owns executable fixture design and independent breaker
   coverage. `S16` Product decides only after it receives the approved S11
   contract, this cut, S13 plan, and S15 case material.
4. Any change that removes one server operation, weakens line checks,
   idempotency, partial-result truthfulness, or read-back requires S12 rework.

## Explicit exclusions

No implementation, code-file scope, migration, schema decision, API endpoint,
queue choice, UI component choice, test execution, commit, push, deployment,
production action, secret access, or live WB/Ozon call is authorized by this
stage.

**Next stage:** `S13 ARCHITECT_PLAN`, owned by `solution-architect`, because
this task has the `database_change` and `background_worker` traits.
