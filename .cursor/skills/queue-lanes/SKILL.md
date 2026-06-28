---
name: queue-lanes
description: Scheduling for .cursor/QUEUE.md autopilot — lane, files, depends_on. Load when orchestrator assigns parallel builders or authoring QUEUE backlog.
---

# Queue lanes (scheduling)

**Canonical reference (human + agent):** `docs/CURSOR_QUEUE_LANES_RU.md` in repo root.

**Attribute names (do not rename across projects):**

| Attribute | Rule |
|-----------|------|
| `lane` | Sequential within same lane |
| `files` | Lock paths; no parallel if sets intersect |
| `depends_on` | Wait until listed IDs are ` done` |

Orchestrator: read reference → parse QUEUE → pick up to `parallel_workers` runnable tasks → 1 task = 1 builder.
