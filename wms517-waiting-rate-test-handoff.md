# WMS-517 R19: waiting caller regression

Independent test-writer handoff. Only the new test and this handoff are owned here.

`backend/tests/test_wms517_sales_waiting_rate.py` drives two concurrent public
`read_sales_report` calls for the same seller through fake Redis and HTTP boundaries.
A is already in HTTP; B reserves its 61-second slot and sleeps. A then receives
429 with `Retry-After: 120`. Advancing the fake clock to 61 must leave B asleep
without issuing HTTP; advancing subsequent scheduled wakeups must eventually
complete B's empty report with its HTTP timestamp at least 120 seconds.

RED confirmed against the existing implementation: B actually issued HTTP at 61,
failing the explicit request-timestamp assertion. No DB fixture, external HTTP,
real-time waiting, production operation, or implementation change is involved.

Run from `backend`:
`/Users/deniscivkunov/Projects/WMS/backend/.venv/bin/python -m pytest tests/test_wms517_sales_waiting_rate.py -q --tb=short`

The fake implements the existing reservation/defer Lua semantics. If the fix
introduces another Redis operation/script, its fake needs the corresponding
server semantics; preserve all behavioral assertions. Existing tests and product
files belong to the concurrent developer and were not changed here.
