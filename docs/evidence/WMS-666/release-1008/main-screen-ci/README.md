# FBS main screen export handoff evidence

These three files preserve the pre-fix `S11-export-ozon-positions-known-defect`
failure from main-screen CI run `37685685035`, candidate
`62ac8683703ebc168c1514ff799280f7925d1e64`:

- `results.json` records the failing assertion: only `OZ-MAIN-1` was exported,
  with quantity `1`, while the fixture expects both positions and quantities
  `2` and `3`.
- `ozon-positions.xls` is the downloaded file from that run.
- `S11-export-ozon-positions-known-defect.png` is the browser capture for the
  failing export scenario.

The unchanged S11 contract is in
`frontend/tests-e2e/fbs-main-screen/browser.mjs` on the release integration
branch. It expects both source positions, their seller articles, and their
quantities. These artifacts document the baseline failure; they do not claim
that the export fix has passed S11.
