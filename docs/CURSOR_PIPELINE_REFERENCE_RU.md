# Cursor Pipeline Pointer

Pipeline v2 is `ACTIVE` and uses the same task state, stages, model policy and evidence rules in
Cursor, Claude and Codex.

- Canon: [process/PIPELINE-RU.md](process/PIPELINE-RU.md)
- Machine contract: [pipeline/pipeline.yml](../pipeline/pipeline.yml)
- Repository entrypoint: [../AGENTS.md](../AGENTS.md)
- Dispatch: `python3 scripts/pipeline/dispatch.py --task-id <TASK_ID> --executor cursor`

The former Cursor-specific role chain and hand-written handoff process are retired. Cursor must use
the controller packet for the current stage and may not reorder stages or accept its own output.
