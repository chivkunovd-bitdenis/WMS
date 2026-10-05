# WMS-676: developer evidence for R8 process repair

This is implementation evidence, **not independent PASS, acceptance, installation
or CI**. The complete independent Astra high FAIL report
`astra-review-5f007b6.md` remains unchanged. The candidate needs a separate Astra
high review before root separately installs it. Installed TG SHA
`1906222619556db64bba92165221dab8b3803180` was not changed.

## Scope and saved contract

Read local AGENTS.md, full WMS-676 requirements and full Astra report. Fetched
origin/etalon and read its AGENTS.md; the owner's explicit process-repair/model
instruction governs this continuation of the published candidate. No skills,
nested agents, Telegram messages, merge, deploy or live model request were used.
Ownership: installer, new race tests, and this developer evidence only.
The reviewer's report and both pre-existing untracked result files were not
staged or changed. The frozen test file is identical to `e009c3fc0`.

The first seven new tests were saved before installer edits in
`38bc5bee9032ef35ad6dafd06789100ef1868325`. On the original installer they
returned **7 FAIL in 4.08s**, including actual unsafe bootout attempts intercepted
before execution and unpublished bytes installed by the synthetic fixture.
Two additional tests were saved in `4e7a685ab` before the implementation commit:
replacement during atomic gate and installed-file mutation after bootstrap.
On the partial fix these gave **1 PASS / 1 FAIL** before adding the reporting
boundary check. A final isolated replay of **all nine** tests against Git bytes
of original `5f007b6e22bce6a36f2255e239e7d3891c2af0bd` gave
**9 FAIL in 5.24s**. Earlier transient collection/harness errors were fixed before
the meaningful RED run; they are not counted as defect evidence.

## Repairs and process observations

**F1:** identify the actual service before the gate and again after atomic gate
replacement. A changed PID aborts without TERM to the replacement or bootout.
After drain, a live launchd replacement must acknowledge this installation's
unique private marker, have its own process group, and have no other group members.
Otherwise the installer aborts. A real `python -m support_agent` respawn test
confirms the gate acknowledges its PID and starts no second worker. Separate tests
cover replacement before the gate, during atomic replacement, and an unacknowledged
replacement after drain.

**F2:** require an initially idle dedicated group (PGID equals service PID and
only that PID is present). Await all members of that group even when PPID is
already 1, plus observed descendants outside the group. Send plain SIGTERM only
to the identified parent; do not use launchd's termination deadline. A real worker
creates a child on its final tick, crashes with `os._exit`, and is reaped before
the first PPID observation. The test verifies PPID=1 while the child is still alive
and allows intercepted bootout only after its natural completion. A short timeout
leaves that work alive and restores entrypoint bytes without bootout. No model
child is killed by the test cleanup.

Read-only live metadata on 06.10.2026 showed installed service PID=60810,
PPID=1, PGID=60810, with only that process in its group. This was **only a metadata
observation**, not a drain or install test. It must be reverified on installation.
No real service config, credentials or state were read for this observation.

Runner uses non-daemon ThreadPoolExecutor work for pipeline/coordinator/dispatcher.
`llm.default_exec` waits through subprocess.run; app-server uses Popen without
setsid/start_new_session and waits in its finally block; prod_sql's local
subprocess also waits. Runner's daemon polling threads do not detach model jobs.
These service launch paths do not intentionally detach into another session.
The installer changes no runner, model-runner, task state, database schema or
business mode. Existing database/config preservation and post-bootstrap no-kill
behavior remain covered by the frozen tests.

**F3:** retain published package bytes from `git show SHA:path` before drain;
copy and compare only against those pinned bytes thereafter. Mutable checkout
changes during drain cannot enter the installed package. Recheck every package
file against the same pinned blobs before reporting the SHA, including after
bootstrap/heartbeat. A mismatch after bootstrap raises without bootout/rollback
under newly started work. The original five nonsecret selection changes and
absolute bundled Codex path remain unchanged; no secrets are managed.

## Reproducible checks

From `tools/support_agent`:

```sh
python3 -m pytest -q -p no:cacheprovider -p tests.test_install_model_migration_races tests/test_model_migration.py tests/test_llm_router.py tests/test_pipeline_chat.py tests/test_agent_runtime.py tests/test_agent_coordinator.py tests/test_night.py tests/test_owner_and_hotfix.py tests/test_runner_and_safety.py tests/test_install_model_migration.py tests/test_install_model_migration_races.py
```

**262 PASS in 20.90s**, including 9 new and 11 frozen installer tests. The earlier
253 tests reported by the reviewer are all included. Disk errors: none. The 11
frozen tests also separately passed in 0.29s. The new test module doubles as an
explicit platform-fake adapter: the old frozen fixture supplies only PID/PPID;
the plugin supplies PGID and simulated gate acknowledgement from its existing
lifecycle flags. It does not change test expectations, model completion, timeout,
configuration, SQLite, or bootout assertions. **Use the plugin command above for
that frozen fixture.** Production has no fallback from unavailable group metadata
to unsafe PPID-only inference. Real process tests exercise the actual marker and
numeric process observations without this simulated acknowledgement.

From repository root:

```sh
python3 -m pytest -q -p no:cacheprovider scripts/ci/test_check_task_documents.py
python3 -m ruff check docs/reviews/artifacts/wms-676/install_sol61.py tools/support_agent/support_agent tools/support_agent/tests/test_install_model_migration_races.py
python3 -m mypy --cache-dir=/dev/null --follow-imports=skip docs/reviews/artifacts/wms-676/install_sol61.py
python3 scripts/ci/check_task_documents.py b18026e8f580f419a6d72a356c513f7e66336648
git diff --check
git diff e009c3fc0 -- tools/support_agent/tests/test_install_model_migration.py
git diff 449e591fb -- docs/reviews/artifacts/wms-676/astra-review-5f007b6.md
```

CI-document unit checks: **41 PASS, 2 subtests PASS in 18.13s**. Ruff, mypy,
local document check and whitespace check passed; both protected-file diffs empty.
No huge full-suite run or remote CI claim. Free space was around 488–538 MiB
in this session; no unrelated files were deleted to increase it.

## Limits requiring explicit operational separation

Group tracking covers inherited service/model subprocesses and observed
out-of-group descendants. It is not proof about an arbitrary external program
that deliberately detaches into another group and becomes unobservable before
any snapshot, or an external daemon/remote job. No new async/detached model path
was found in the inspected service launch/wait code. Internal CLI/tool behavior
under arbitrary compound crashes was not tested live and is not claimed safe
from one poll. A new detached launch path would require additional evidence
before relying on this drain boundary.

The marker is local operational installation data, not a task state. On abort its
tiny private directory is intentionally retained: a live gate could still be
opening it. Removing it then could crash a respawn. It is removed after confirmed
bootout. Automatic recovery after installer SIGKILL/power loss remains unverified;
the saved entrypoint must not be restored blindly before checking live work.
Concurrent independent installers are not supported or proven safe by this change.
The final source-file check is a point-in-time byte check, not proof against later
external edits or proof of a loaded runtime/real model call.

Root must obtain independent Astra high PASS for the published candidate and then
separately decide/run installation against the actual installed baseline. The
historical `local-install.json` was not replaced by synthetic results.
