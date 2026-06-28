---
name: queue-lanes
description: Scheduling for docs/PARALLEL_AGENT_TASKS.md — lane, files, depends_on. Load when orchestrator assigns parallel builders.
---

# Queue lanes (scheduling)

**Backlog file:** `docs/PARALLEL_AGENT_TASKS.md` (table **read-only** for status)  
**Reference:** `docs/CURSOR_QUEUE_LANES_RU.md`

**Close task:** `touch .cursor/state/<id>.done` (orchestrator, after **integrate** + verifier READY)  
**Integrated:** `touch .cursor/state/<id>.integrated` (after merge to integration branch)  
**Block task:** `touch .cursor/state/<id>.blocked` (after 3 fix failures)  
**Isolation:** `git worktree .cursor/wt/<id>` per task, branch `task/<id>` from HEAD **integration branch**  
**Merge:** `scripts/queue-integrate.sh <id>` (WMS) — serial, one at a time

**Attributes:** `lane`, `files`, `depends_on` — see reference doc.
