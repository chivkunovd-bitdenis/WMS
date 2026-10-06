# WMS-684/586 scope selector: canary evidence

This evidence accompanies test-only commit `09456c10e84a2d15d2643fe3ab13a4e8b69a25b9`.
It corrects the selector in the WMS-684/586 scope contract; it changes no
product or requirements file.

The independent canaries are recorded in
`/Users/deniscivkunov/Projects/WMS/.worktrees/wms652-process-fixes-review-20261007/docs/evidence/WMS-652/delta-review-6da0-20261007/scope-canaries.json`.
They demonstrated that a forbidden `backend/app/models/forbidden.py` was not
attributed when its commit subject was either:

1. `WMS-652 WMS-684 WMS-586: forbidden model`; or
2. `WMS-684 WMS-586 forbidden model`.

Before the selector fix, the two new isolated-repository canaries were run
against that unchanged selector with the existing backend runtime:

```text
cd backend && PYTHONDONTWRITEBYTECODE=1 /Users/deniscivkunov/Projects/WMS/backend/.venv/bin/python -m pytest -n0 -p no:cacheprovider tests/test_wms684_586_scope_contract.py -k task_id_anywhere_or_without_colon_rejects_forbidden_path -q --tb=short
```

Result: **2 failed**, both because no `AssertionError` was raised. The complete
RED output is retained in `.agent-runs/wms684586-scope-subject-canaries-red.log`.

The selector now extracts exact `WMS-<number>` tokens from the whole subject and
attributes a commit only when that set contains `684` or `586`. It therefore does
not depend on task position or a colon. It also does not treat `WMS-6840` as
WMS-684; the new isolated-repository negative case commits the same forbidden
path under `WMS-6840` and verifies that it is not attributed to this task.

Sequential verification used no installation, cache, or full suite:

```text
cd backend && PYTHONDONTWRITEBYTECODE=1 /Users/deniscivkunov/Projects/WMS/backend/.venv/bin/python -m ruff check --no-cache tests/test_wms684_586_scope_contract.py
cd backend && PYTHONDONTWRITEBYTECODE=1 /Users/deniscivkunov/Projects/WMS/backend/.venv/bin/python -m pytest -n0 -p no:cacheprovider tests/test_wms684_586_scope_contract.py -q --tb=short
```

Ruff passed. Pytest passed **7** tests, including the two repaired rejection
canaries, the `WMS-6840` non-collision case, the existing forbidden-path case,
and the existing foreign-only merged-branch case. The complete green output is
retained in `.agent-runs/wms684586-scope-subject-canaries-green.log`.
