# WMS-672 bounded Linux C5 diagnosis

Diagnostic branch starts from exact failed run37523087363 tested merge
2d1707cacdb9bbd2e92eee75115c9749ac969fcc (PR387 headf6066d68bd198794602a6e8916612d0d3b32460f).
Only existing workflow path CI is replaced on this isolated branch by a manual,
one-job diagnostic. No PR/push/full-suite trigger, product/frozen contract edit,
release proof, external marketplace request, real print or deployment.

Run frozen C5 only (`--test-name-pattern='^C5 '`) with original30000ms assertions
and420s outer timeout; ubuntu24.04, Node24.21.0, Playwright1.56.1, exactChromium
141.0.7390.37 enforced. Browser muted. Frozen context intercepts print; adapter
blocks external origins and records request method/URL without credentials.

Observer wraps native decode with same-result/error forwarding, associates error
identity through promise catch and screen catch, records decode index/counters,
native image dimensions/data URL on failures and iframe source before removal.
Diagnostic Vite transform inserts observation before original catch expression,
without changing it. Protected sources byte-compare to original merge and hash
before/after. Rejected PNG is validated offline with CRC/inflation checks.

Observation adds one Promise forwarding step and event recording; it can change
microtask timing/resource pressure. C5-only cold run differs from earlier-suite
cache pressure. A non-reproduction would not disprove original CI failure or
justify timeout/message changes. This is diagnostic evidence, never fullCI PASS.

Dispatch requires coordinator's exact published SHA/workflow scope check; one
owner only. Raw artifacts, command, run/attempt/environment and conclusion will
be added after that single authorized run. No product fix in this branch.

Coordinator preparation review caught shallow checkout before dispatch. Checkout
now fetches history (`fetch-depth: 0`) so exact original merge byte checks can run.
No diagnostic was dispatched with the earlier prepared SHA.
