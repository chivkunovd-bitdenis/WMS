# WMS-652: first-proven-wait writer PID contract before the fixture fix

Basea64e45b9a90aa6ab12f4cd942d4a023af72be0d1. Actual common CI37561608930
tested merge4a118aea00ec3995d98f70d337245260b291ca7f fails HARNESS line346:
wait_seen=true, final mutable pids=batch219/ordinary219. Its preserved first
wait rows show ordinary209 blocked by batch219 during reversal-ledger INSERT;
business results[None,None]/issues[]/money/stock are correct. This identifies
fixture evidence lifetime, not a product failure or a fresh PostgreSQL proof.

The new two-case test extracts original AST nodes for actual BatchSchedule and
its native resource/sqlstate helpers; before/observe logic is never replaced.
Real asyncio events/ContextVar and native SQLAlchemy DML/FOR UPDATE clauses run.
Only driver PID values and asynchronous observer replies are controlled; replies
are filtered to the actual queried PIDs. Event.set instrumentation records pids
at the real release call and then invokes the original native Event.set.

The first case starts101/202 with an actual no-wait reply, changes live writers
to219/209 before the matching blocking reply, then checks first-wait evidence
at release. Later actual before() DML with reused219 must preserve that exposed
snapshot. The second case requires later observer queries/current-cycle detection
for301/302, preserving first wait_queries. No new internal variable name/export
or class helper is prescribed; existing pids is the evidence used by unchanged346.

Final before.xml/log contain2 cases:1 meaningful targetFAIL,1 PASS,0 skip/error.
RED is at post-release snapshot overwrite (219/209 ->219/219), after all first
wait prerequisites pass. The green live-tracking case is made meaningfully RED
by setdefault corruption of before() only in a temporary actual fixture copy:
it queries stale219/209, misses the301/302 cycle and fails the exact live-query
assertion. preservation-control.py/log/xml retain this proof; copy removed.

The cheap local command and actual XML identities are in contract.json. Local
--noconftest prevents loading the PG-heavy original fixture; CI can execute the
new extraction test normally as2 additive backend-fbs cases in backend-all.xml,
junit/exact:false. Existing conftest/pyproject/uv.lock are unchanged and included
in the source closure. Targeted new test Ruff passes. Original whole fixture,
business body/assertions, line346, timeouts and observer delay are byte-identical.

No product/old fixture/CI/policy/requirements changes, external request, native PG
or fullCI rerun, install, reviewer verdict or analyst acceptance is claimed.
Integrator owns registry/CI/docs; a separate developer changes the original fixture
only after this published contract, followed by independent review/acceptance.
