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

Actual dispatch was performed once by release_integrator on reviewed replacement
SHA b44ef10777f8d63555229d575558c6c9a5f3affd. Equivalent dispatch command:
`gh workflow run .github/workflows/ci.yml --repo chivkunovd-bitdenis/WMS --ref codex/wms672-c5-linux-diagnostic -f base_sha=4b298efc95be7b4b6b7fe5665be9f3671f1fe747`.
Run37527056184/attempt1 FAIL; setup PASS, real C5 FAIL, upload PASS.
Read [conclusion.md](conclusion.md) for proven native/catch chain and its limits.

Read-only collection commands:
```
gh run view 37527056184 --repo chivkunovd-bitdenis/WMS --json databaseId,headSha,event,status,conclusion,attempt,createdAt,updatedAt,jobs,url
gh run view 37527056184 --repo chivkunovd-bitdenis/WMS --log
gh run download 37527056184 --repo chivkunovd-bitdenis/WMS --name wms672-c5-linux-diagnostic-37527056184-1 --dir docs/evidence/WMS-672/c5-linux-diagnostic-20261007/raw
gh api repos/chivkunovd-bitdenis/WMS/actions/runs/37527056184/artifacts
```

The `raw/` files are downloaded artifact bytes, including actual TAP, native/catch
error identities, iframe sources, rejected PNG, environment and matching source
hashes. `rejected-image-offline.json` additionally decodes the rejected raster
with existing frozen-test CODE128 decoder; it resolves to actual label227.
