# WMS-661: read-only runtime installation preflight

Snapshot: 2026-10-06 09:45–09:48 UTC. No installation, service signal, Store
initialization, model call, review/test rerun, external message, configuration
change, pause, or outbox cancellation was performed. Only this document is owned.
Fresh origin/etalon AGENTS read at `4b298efc95be7b4b6b7fe5665be9f3671f1fe747`;
owner instructions for this preflight take precedence. Historical memory was
used only to identify drain/PID hazards; all runtime conclusions below are live.

## Verified baseline and candidate

The 30 tracked installed package files in
`/Users/deniscivkunov/.wms-support-agent/app/support_agent` exactly match published
`8cd8db61598e6c80c91d7eff13301230a4ca6102` (zero mismatches). launchd label
`pro.sellerfocus.wms-support-agent` is running PID **40887**, PPID 1, PGID 40887;
heartbeat age was 0.95 seconds. This confirms package bytes and process metadata,
not introspection of every already loaded Python object.

PR [385](https://github.com/chivkunovd-bitdenis/WMS/pull/385) and its remote branch
`codex/wms661-reviewed-ordered-integration` both point to exact candidate
`9ce156c5e9eb52b38704d7cb2d6c7cb3e6273c36`. Existing checkout is
`/Users/deniscivkunov/Projects/WMS/.worktrees/support-task-14`; its package files
and installer match the pinned Git blobs. Other agents' untracked result files
were left untouched. Read published implementation and recorded acceptance,
including the synthetic-model boundary; no fresh review or 142-test rerun.

Relative to the actual installed baseline, the only package changes are:

- `support_agent/agent_instructions.md`
- `support_agent/agent_tools.py`
- `support_agent/readonly_mcp.py`

No schema or model-router change, new AI call, client silence mechanism, or
session migration is included. Configuration output was restricted to nonsecret
routing fields: CLI order `codex`; filter/routine/analyst/frontend/mockup and owner
model `gpt-6.1-sol`; review `gpt-6-astra`; configured effort `high`. Installed
router explicitly chooses `high` for review. Configured Codex executable matches
the installer. Secret fields and credentials were not displayed or managed.

## Idle boundary and preservation

At the snapshot, PID 40887 had no children/descendants and its dedicated process
group contained only itself. Read-only SQLite (`mode=ro`, `query_only=ON`) found
no jobs with running/recovering/queued/scheduled status or running/queued preflight.
Existing job statuses: 18 done, 7 needs_review. WMS-677 is ticket 22 and WMS-678
is ticket 24, both `agent_discussion`; ticket 23 is a done night record referring
to WMS-677. Discussion stages alone do not trigger the installer's busy-job guard.
These results are a snapshot, not permission to kill a later subprocess.

There are 28 tickets, 195 stored agent-session keys, 403 messages and 485 outbox
records (484 sent, one historical cancelled record id 268/ticket 17). No pause,
quiet, or client-reply control keys were found. Normal client replies remain
permitted. Do not use quiet6f31, pause-client-replies, or cancel any outbox record.
No live session IDs, message bodies, or secret configuration values are recorded.

Existing `docs/reviews/artifacts/wms-676/install_sol61.py` is byte-identical to
both published baseline and candidate; no new installer is needed. It first
verifies publication, full package baseline and checkout, no service child, and
idle saved jobs. It backs up config/replaced files, gates respawn, naturally drains
the original worker and executor threads, verifies identity/group, then bootouts.
The authoritative full DB backup is taken after natural completion. All tables,
sessions and offsets are included; the stopped DB digest must remain equal during
replacement. Only the three changed package files are installed. Its five model
selection assignments already equal current values; the preservation assertion
requires every other parsed config field, including secret fields, to remain
identical. It rewrites config formatting but does not rotate credentials or alter
model routing. No optional silence wrapper belongs in this command.

Do not bypass `AssertionError: A service subprocess is active`, the saved-job
assertion, group/identity guard or drain timeout. Let existing work finish and
recheck. After bootstrap attempt, an uncertain failure must not trigger another
stop/rollback under potentially active model work; follow the existing installer
failure boundary and inspect first.

Disk available: 268 MiB. DB was 13,856,768 bytes, WAL 4,433,152 bytes; full package
plus DB/config source size was approximately 14.5 MB (the installer backs up only
replaced files plus entrypoint and full DB). Recheck space against current DB/WAL
and backup needs before mutation. No archives, downloads or new worktree needed.
Do not delete other agents' work to make space.

## Exact next step for Root

**Installation is currently blocked:** run
[37444579599](https://github.com/chivkunovd-bitdenis/WMS/actions/runs/37444579599)
was `in_progress`, conclusion empty, exact candidate SHA; backend Pytest was still
running, subsequent migration checks pending. Other completed jobs succeeded.
A partial green run is insufficient. Read this again without rerunning CI:

```sh
gh run view 37444579599 --json headSha,status,conclusion
gh pr view 385 --json headRefOid,headRefName,state
git ls-remote origin refs/heads/codex/wms661-reviewed-ordered-integration
```

Only after **completed/success** for the exact candidate, unchanged publication
and checkout, freshly matching installed baseline, sufficient disk and freshly
idle jobs/children/group may Root execute the existing installer below in a later
installation turn. No installation is authorized by this read-only preflight.

```sh
cd /Users/deniscivkunov/Projects/WMS/.worktrees/support-task-14
python3 docs/reviews/artifacts/wms-676/install_sol61.py \
  9ce156c5e9eb52b38704d7cb2d6c7cb3e6273c36 \
  codex/wms661-reviewed-ordered-integration \
  8cd8db61598e6c80c91d7eff13301230a4ca6102
```

Use the current reviewed file, not an older quiet installer or ad hoc copy.
If a subprocess or WMS-677/678 job becomes active, the next step is wait and
read-only recheck, not terminate/pause it. Current preflight itself found no such
active blocker; unfinished full CI is the confirmed blocker. After a later install,
verify installed package bytes, new PID/heartbeat, unchanged routing and preserved
state from installer evidence before claiming installed. No merge into main or
etalon, WMS production deployment, or external task acceptance is implied.
