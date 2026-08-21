# S15 CASE_FACTORY - BLG-J01

`S15-CASES.json` is the machine-readable case matrix for the approved UI-only
card. It contains seven GOLD cases: accepted exact SGTIN tail, non-KIZ kinds,
invalid tail variants, failed entry, rapid reloads, narrow/long layout, and
close/order-change cleanup.

Every case uses a fresh local Playwright route-mock fixture and names its
planned S19 binding in `frontend/tests-e2e/ff-fbs-supply.spec.ts`. It has no
live marketplace, database, worker, print, authorization, or new API assertion
because the approved contract expressly preserves those layers.

The product oracle is the approved S09 UX contract and S11 Product contract.
There are no uncovered applicable acceptance rows. An independent
`case-auditor` must audit this matrix before Product decides S16; this BA stage
does not claim that independent verdict.

Verdict: `CASES_READY`
