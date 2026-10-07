# WMS-666: independent review of exact CI history correction

Reviewer: separate session `/root/priority_663`, actual model `gpt-6.1-sol`, effort `high`. Verdict: **PASS**.
Reviewed test-only commit: `9e72ac09f537fc48a02e1681bcc4ace917b7759e`.
Parent common candidate: `20448622da89b3ef4de10443af0c8c75da9cbf0c`.
File: `frontend/src/screens/v2/wms666ChangeScope.test.ts`.
Reviewed final blob: `69f07c26fa4966875e8aa85a24ac16f7dc8d5ac4`.

The shared-history failure was an attribution error for the already accepted four-line checkout change. I read the actual shared-HEAD log: the existing actual-history assertion returned only `.github/workflows/ci.yml`, with four other cases passing. I independently inspected commit `720307d280439e815057ee4fdd78b72134149a39`: its workflow delta adds `with: fetch-depth: 0` to backend and frontend checkout. Before and after workflow blobs are exactly `621ee62065c67ae66d756b25057d56e780bb411d` and `bbec58a4b781913e7792a6718158a9fc4b806c90`.

The correction exempts only that exact immutable commit, exact path and both exact blobs during committed-history collection. It does not add the workflow path to the general allowlist. The raw scope validator, all five earlier test bodies and their expectations are byte-identical to the parent; this was independently compared using TypeScript source nodes. Staged, working-tree and untracked collection, merge-resolution collection and the existing backend/migration/stock/guard boundaries are unchanged. An absent immutable source raises an error instead of granting an exemption.

Independent checks on the exact correction, with compatible dependencies (both lockfiles SHA256 `4ec9fd6b9291d52f2c3534bc3fb4ebbfd24a9d029f3d3d01127e43404c01984c`) and Node `v20.20.2`:

- Three new cases: **3 PASS**, five unchanged cases skipped, 1.42 s. The actual negative fixture rejects a new primary WMS-666 workflow commit, untracked, unstaged, staged and index-only changes even when the working file is restored to HEAD. Raw workflow validation still rejects the path. Exact historical positive and missing-source negative pass; the expected `git fatal` output belongs to the missing-source control.
- Existing actual shared-history case on this candidate: **1 PASS**, seven other cases skipped, 1.51 s. Thus the concrete integration failure is removed without weakening future workflow boundaries.

Commands from `frontend`:

```sh
npm exec --yes --package=node@20 -- node node_modules/vitest/vitest.mjs run src/screens/v2/wms666ChangeScope.test.ts --no-file-parallelism -t 'rejects a new task workflow|accepts only the exact immutable|fails an accepted history lookup'
npm exec --yes --package=node@20 -- node node_modules/vitest/vitest.mjs run src/screens/v2/wms666ChangeScope.test.ts --no-file-parallelism -t 'keeps the actual task diff'
```

No product, workflow, checker or ledger code was changed by the reviewer. This verdict covers the narrow history-attribution correction only; it does not claim full CI, staging UI acceptance or production deployment. Earlier reviews and contract provenance remain in the canonical cumulative ledger; the author may now record this actual independent PASS.
