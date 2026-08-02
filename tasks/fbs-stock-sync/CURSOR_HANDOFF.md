# CURSOR_HANDOFF — fbs-stock-sync (draft for STOCK-110)

> **Status:** STOCK-100 complete; STOCK-110 will finalize gates + this document.
> **Branch:** `task/STOCK-100`
> **HEAD:** _(update after commit)_

## STOCK-100 commit

- `test(STOCK-100): prove WMS to emulator FBS stock cycle`
- TC-NEW-FBS-STOCK-017, TC-NEW-FBS-STOCK-018

## Files changed (STOCK-100)

| Path | Change |
|------|--------|
| `backend/tests/test_fbs_stock_emulator_integration.py` | New — full HTTP cycle WMS ↔ emulator |
| `wb_emulator/README.md` | Cycle test command + scope |
| `tasks/fbs-stock-sync/CURSOR_HANDOFF.md` | This draft |

## Exact cycle command

```bash
cd "/Users/deniscivkunov/Desktop/WMS /.cursor/wt/STOCK-100/backend"
pytest tests/test_fbs_stock_emulator_integration.py -q
```

Emulator suite (regression):

```bash
cd "/Users/deniscivkunov/Desktop/WMS /.cursor/wt/STOCK-100"
PYTHONPATH=. python3 -m pytest wb_emulator/tests/ -q
```

## Runtime proof (STOCK-100 session)

```
cd backend && pytest tests/test_fbs_stock_emulator_integration.py -q
..                                                                       [100%]
2 passed in ~1.1s

PYTHONPATH=. python3 -m pytest wb_emulator/tests/ -q
49 passed in ~2.1s
```

**Proved values:** publish 1 → emulator readback 1 → purchase (created=1, rejected_no_stock=1) →
emulator amount 0 → WMS intake (mapping=mapped, reserve=1, wb_warehouse_id=501001) → sync confirmed 0.
FBO unload reservation on separate WMS warehouse did not reduce FBS publish.

## STOCK-110 remaining (not done here)

- [ ] `cd backend && ruff check .`
- [ ] `cd backend && mypy .`
- [ ] `cd backend && pytest` (full)
- [ ] Alembic upgrade/downgrade on clean DB
- [ ] `git diff` anti-scope + prod compose guard re-check
- [ ] Commits list STOCK-010…100
- [ ] PR `### Test coverage` block

## Test coverage draft (for PR)

```markdown
### Test coverage

| TC-ID | Title (short) | Applies (Y/N) | Notes |
|-------|-----------------|---------------|-------|
| TC-NEW-FBS-STOCK-017 | WMS → emulator stock cycle | Y | Given: product wb_chrt_id + binding 501001 + physical qty 1. When: stock sync HTTP to emulator, admin purchase 2, order intake, second sync. Then: readback 1→0, one order reserved, confirmed amount 0. Negative: FBO reserve other WH unchanged. |
| TC-NEW-FBS-STOCK-018 | Prod compose isolation | Y | Given: docker-compose.prod.yml. When: grep for wb-emulator / emulator base URL. Then: no matches (test_prod_compose_has_no_wb_emulator). |
```

## Risks / notes

- Integration test patches `httpx.AsyncClient` to route WB calls through emulator ASGI; WMS `async_client` still passes explicit transport (unchanged).
- Emulator test count now **49** (was 37 at STOCK-000 baseline — lane additions STOCK-030/040).
- `tasks/fbs-stock-sync/` artifacts live on integration branch; worktree may not mirror all task docs.
