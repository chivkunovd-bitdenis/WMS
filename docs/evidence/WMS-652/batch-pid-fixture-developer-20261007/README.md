# WMS-652: stable first batch writer wait evidence

Fixture-only implementation `308dde98518a6c14de421caadef1a9528e0e0bd4`, branch codex/wms652-batch-pid-fixture-fix, starts at exact common4c6ce786e9aec3a06fe4faeb11a283c4df923460. Separate testwriter contract8d16fca4c7d16cc97ae9fe15608708563bb5d243 was published before code. Its actual BatchSchedule AST and native SQL clause helpers were exercised with controlled driver PID/observer replies: before edit1FAIL/1PASS/0skip/error, after edit2PASS/0FAIL/skip/error.

Only BatchSchedule changes. current_pids refreshes the live connections before every DML/locking SELECT and supplies the actual attempt/acquired trace. Each observer poll copies that live map after pg_stat_clear_snapshot and before its SELECT; that same copy determines both queried parameters and interpretation of returned waits. On the first actual matching blocking reply, self.pids receives that distinct writer snapshot before the existing barrier release. Later pooled PID reuse cannot overwrite the snapshot. Later polls still query current connections and detect mutual waits. There is no first-ever-connection shortcut or requirement suppression.

Removing BatchSchedule from old/new source leaves identical bytes. The public test function AST and all21assertions—including the original distinct-two-writers/observed-wait assertion formerly atline346—are identical. Business bodies, routes, stock/money/recovery checks, native PG identity guard, SQL errors, cycle checks, barrier timeouts and polling delay remain unchanged. Frozen new2test file matches8d16exactly. Product-reference1cf and stock publisher product bytes are untouched.

Commands from backend with the existing root .venv:

```sh
/Users/deniscivkunov/Projects/WMS/backend/.venv/bin/python -m pytest -n 0 -q tests/test_wms662_batch_pid_snapshot_contract.py --junitxml=../docs/evidence/WMS-652/batch-pid-fixture-developer-20261007/precode-red.xml
/Users/deniscivkunov/Projects/WMS/backend/.venv/bin/python -m pytest -n 0 -q tests/test_wms662_batch_pid_snapshot_contract.py --junitxml=../docs/evidence/WMS-652/batch-pid-fixture-developer-20261007/targeted-green.xml
/Users/deniscivkunov/Projects/WMS/backend/.venv/bin/ruff check .
/Users/deniscivkunov/Projects/WMS/backend/.venv/bin/mypy .
```

Full Ruff PASS; full mypy PASS563sourcefiles. Runtime is Python 3.14.3. These controlled contract results prove PID evidence preservation and live observation, not a fresh native PostgreSQL pass. No PG/fullCI/browser/provider/installation/dispatch occurred. Historical SQLite lock owner remains UNKNOWN. Independent fixture review, analyst acceptance and actual mandatory PG/commonCI remain coordinator stages. CI/policy/requirements/frozen expectations were not edited.
