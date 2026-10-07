# WMS-652 nested stock publication: frozen tests before the fix

Published analyst requirements476d206dc791799f88714012093c1ec315885fba define
R52/C66-C68 before this contract. Base31cd68fd70791a7433562dc2495a7d67e969d840
contains the unchanged observed hook. Four exact cases and their requirement
mapping are recorded in contract.json; C67 has separate ordinary/nested variants.

The tests import the actual production module, install a spy only on its existing
_dispatch, and use native SQLAlchemy AsyncSession, actual SQLite writes, SAVEPOINT
commit and outer commit/rollback. No Session or lifecycle event is mocked. The
spy records native in_nested_transaction() at invocation and original arguments;
it prevents provider/worker work. Each test owns its engine/table and synthetic
tenant/seller UUIDs. Existing conftest remains unchanged.

Local sparse execution uses run-target.py: it archives the exact HEAD app sources,
conftest and pyproject into a temporary source directory, copies this new test, and
uses the existing root backend .venv. Dependency installation/copying is absent.
Only isolated test SQLite/data paths are passed to the existing conftest. Temporary
source/DB directories are removed on exit. CI executes the test normally alongside
backend-fbs and contributes four IDs to existing backend-all.xml (junit/exact:false);
no workflow command or registry edit is made by this writer.

before.xml/log retain4 executed:3 targetFAIL,1 PASS,0 skip/error, exit1. All three
failures capture premature dispatch at nested-commit with native nested=True.
The true outer commit has lost its intent; outer rollback cannot undo the earlier
dispatch. The ordinary root commit preserves the original coalesced arguments once
at outer-commit/nested=False. These are assertion failures, not setup errors.

The ordinary green preservation case becomes RED when a temporary source COPY
adds an early return to the actual after_commit callback. ordinary-mutation.xml/log
record1 meaningful FAIL,0 PASS/skip/error (3 deselected), after native root commit
leaves calls empty. The mutation is removed with the copy; tracked product untouched.
The targeted new test also passes Ruff with app identified as the project package.

The unrelated interrupted allowlist draft is preserved, byte-verified, in named
stash b396ded869bc8932ad25dc448b5f7163aa62a2f7 and is not integrated or dropped.
Preservation proof hashes old backup23 assertions/7 variants, conftest, browser43,
CDP7, Node7+2+3 and scope51 sources without rerunning them. No new nested-rollback
behavior, retry, sleep, fixture-disable or queue framework is asserted.

The measured diagnostic37558149550 was an isolated PASS; historical SQLite lock
owner remains UNKNOWN. No fullCI, browser, build, provider, independent review,
acceptance, product-reference migration or SOURCE approval is claimed here.
Integrator owns requirement test-column links and additive suite registration;
developer/reviewer/analyst stages follow this published frozen contract.
