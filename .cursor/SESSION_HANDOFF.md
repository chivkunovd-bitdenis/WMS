# Session handoff — fbs-wb-emulator

- parallel_workers: 3
- subagent_model: composer-2.5
- backlog: docs/PARALLEL_AGENT_TASKS_FBS_EMU.md
- integration_branch: feat/fbs-wb-emulator
- phase: queue complete (EMU-000…080)

## Closed
- EMU-000 … EMU-080 (all)

## EMU-050 note
- Create must be POST `/__admin/orders` (not GET).
- Single orders store: `wb_emulator/services/orders_store.py` (no seed duplicate).

## Follow-up (optional, not in queue)
- Smoke: полный цикл через UI WMS на compose+emulator overlay.
- Seed templates с реальными баркодами каталога стенда → mapping=mapped.
