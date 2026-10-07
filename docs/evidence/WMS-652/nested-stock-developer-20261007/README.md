# WMS-652 R52: publication waits for the outer commit

Product-only source `1cf85fc500bc6ee7a5f4ef283b250c4bf59c5333` is based on exact common `fc729dd84a2c45de0b3c56381b41e475cb131673`. Separate testwriter contract `f1e355525edbf41177d379c70cc5ee721986c967` was published before code. The actual four native AsyncSession/SAVEPOINT contract cases were executed before any edit and gave3FAIL/1PASS/0skip/error. The failures showed dispatch before outer commit/rollback. The guard adds only two lines in existing `_after_commit`: return while sync_session.in_nested_transaction(), retaining its existing pending set. `_after_rollback`, dispatcher, coalescing, queues, provider behavior and all other product conditions are unchanged.

The new four cases now PASS without skips/errors. Existing `test_fbs_stock_publish_on_movement.py` contributes6PASS and one declared skip because it requires real PostgreSQL advisory locks; total10PASS/1skip/0FAIL/error in7.57s. The new contract uses a native isolated SQLite engine and spy on the actual dispatcher; no worker/provider request is sent. The PostgreSQL skip is not a new-contract skip or claim of real advisory-lock verification. Full Ruff passes; full mypy reports no issues in563source files. Local runtime is Python 3.14.3; dependencies are the existing root .venv with no installation.

Exact commands from this worktree's backend directory:

```sh
/Users/deniscivkunov/Projects/WMS/backend/.venv/bin/python -m pytest -n 0 -q tests/test_stock_publish_nested_commit_contract.py --junitxml=../docs/evidence/WMS-652/nested-stock-developer-20261007/precode-red.xml
/Users/deniscivkunov/Projects/WMS/backend/.venv/bin/python -m pytest -n auto -q tests/test_stock_publish_nested_commit_contract.py tests/test_fbs_stock_publish_on_movement.py --junitxml=../docs/evidence/WMS-652/nested-stock-developer-20261007/targeted-green.xml
/Users/deniscivkunov/Projects/WMS/backend/.venv/bin/ruff check .
/Users/deniscivkunov/Projects/WMS/backend/.venv/bin/mypy .
```

Preservation verifies the frozen native test matches its f1e blob, the existing publisher test/conftest/pyproject/uv.lock match the common base, and the full module delta is precisely the two-line guard. Product app paths versus accepted25eb contain only this stock module and the already reviewed CryptoPro test-title infrastructure change. Requirements, CI, policy, browser43,672 tests and provider intents are untouched. No fullbackend, browser/C5, selected diagnostic, CI dispatch, deployment or production operation occurred. Historical SQLite lock owner remains UNKNOWN and this native lifecycle correction does not promise to have fixed that old failure. Independent source review, distinct analyst acceptance/product-reference migration and actual full CI remain separate coordinator stages.
