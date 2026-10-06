# WMS-672: additive resource lifecycle test contract before product changes

Separate technical testwriter, bounded owner-authorized fallback; base
`ea001a77653053624cc73acc00e622c155447292`, unchanged product
`47817f76589701ea36ba1f8b30fca84b6a136208`. Fresh `origin/etalon` rules, the
testwriter skill, requirements and causal checkpoint were read. No delegation.

The new Node/DOM test executes the actual TypeScript utility after transpilation.
Only browser decode, layout/raster and rendering/timer delivery are controlled.
RR1 permits one observed initial parallel cohort of retained original decodes;
consumption at a rendering boundary releases them only when the original images
are the eligible, nonoverlapping, ordinarily filtered thumbnails in a nonzero
in-viewport, aria-hidden, pointer-inert iframe. Other image cohorts must be
excluded. Starting another cohort without consumption cannot accumulate the
entire tape. This synthetic capacity is not the measured Chrome quota and the
test does not freeze group/thumbnail sizes, retention delays or helper names.

Command from repository root:

```sh
node --test --test-reporter=tap frontend/tests-e2e/wms672-raster-resource.test.mjs
```

Raw BEFORE output is `before.tap`: **3 cases, 2 PASS, 1 FAIL, 0 skipped**, exit1.
RR1 fails meaningfully with16 successful decodes versus300 required.32 calls
start, peak retained16, render releases0, transfers0. The first rendering
boundary reports a zero-size iframe, missing pointer inertness and no eligible
original cohort; the next cohort starts with the earlier resources still held
and receives an EncodingError. This is a controlled lifecycle reproduction,
not a new measurement of the fifteen real Linux native refusals.

RR2 preserves300 successful decodes, fallback completion with stalled parent
frames, exact original inline styles/frame zero geometry, PNG sources, full
HTML/CSS, labels/order,58×40 page size and pixelated print appearance before one
save callback and one transfer. The source lives until afterprint. RR3 delivers
a genuine-shaped iframe DOMException refusal with active peers held by an
explicit promise: no cleanup/completion or later cohort until those peers drain,
the identical first error survives, and there is zero save/transfer. Cleanup
sees restored original styles/source and no pending decoder peers.

Both preservation cases were proved by a purposeful leaked image-rendering style
in an automatically removed **untracked source copy**. `mutation-proof.py`
redirects only the utility read to that copy. `mutation-style-leak.tap` records
2 FAIL/0 PASS/0 skipped for RR2/RR3 on exact inline-style restoration; the tracked
utility was never edited. `mutation-result.json` records original/copy hashes
and reproduction command.

`cases.json` is the exact case-name array. `contract.json` duplicates that array,
records the four-file test closure (new test, actual utility, frontend package
and lock), hashes, requirements mapping and limits. The proposed future report
is **release-print/672-raster-resource.tap**, process-proof path
**print/672-raster-resource.tap**, format **node-tap**. Integrator owns CI/registry
wiring; none was changed here. `frozen-original-hashes.json` proves31 existing
test/helper/config/package/utility files match the base, including the unchanged
7 native-error,2 peer-drain and11 browser cases. `no-product-diff.json` records
the empty product comparison and pre-add status. Other suites were not rerun.

This test uses a deliberately limited declared-box CSS boundary, not a complete
layout engine. Its small synthetic PNG is unchanged;836×356 decode metadata is
modeled, not measured. It does not claim actual Chromium raster preparation,
native unrefs, asset/CODE128 quality, PDF output, screen marks or physical paper.
Those screen/error/mark assertions remain in the frozen existing suites. No
product, requirements, backlog, workflows, registry, package/lock, dependencies
or existing tests changed. No browser/provider/printer/production action,
installation/build, independent review or acceptance was performed.

**Old C5 remains RED and mandatory**, including its independent renderTape300
helper and actual Chrome141 full-series proof. Product implementation, independent
review, distinct-analyst acceptance and exact-SHA CI remain separate stages.
