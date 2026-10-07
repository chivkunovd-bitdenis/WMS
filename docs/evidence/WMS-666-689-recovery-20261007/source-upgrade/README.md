# Reviewed-source activation draft

The product reference is P2 `d420f8db1e7d69212ad2ea4529a02044689363b0`.
Independent product/fixture acceptance is `154cdb1ff3e84ed4e592d883688c7df560579015`.
Fixture F2 is `b9b1a83ee943523cec795de021862fa10ce8f04b`.
The workflow's literal product pin and the existing controlled binding fixture
move together. Historical failure and negative fixtures are preserved. This does
not select HEAD and does not change the checker or authorize deployment.

The protected registry keeps every previous file, suite, report and case ID.
It records reviewed inherited production files, precise fixture corrections and
new asset-retention protection. Fourteen asset tests are added to the existing exact
ci-shards receipt; no previous test is removed.

The existing production script now preserves previous assets before web build,
prepares an unstarted candidate container, adds only absent old assets, verifies
all old/new SHA-256 values, and commits that verified filesystem under the usual
compose image tag. This completes before application writers stop or new web
traffic starts. A conflicting existing path fails closed. The EXIT trap cleans
up its temporary container and directory on success or failure. The CI gate and
first Docker build ordering are unchanged; no gate exception is added.

Local checks: fourteen retention checks; thirty-five retention/existing deploy gate checks
plus 59 subtests; 36 policy tests plus 34 subtests; 67 product-reference checks
plus nine subtests. Bash syntax passes. The small real Docker probe verified 382
existing assets plus one synthetic retained file through two unstarted containers
and a separate temporary image. It did not change the live web image, start time,
or production tags. It is not a production deployment.

Activation still requires a separate trusted-main bootstrap pin PR and explicit
owner permission to merge that PR. The old F frontend failures are preserved. P2 fixes the actual WMS-657 overflow, passes all 1734 frontend tests (three explicit skipped cases), the separate C5a contract and frontend build in CI37680234422, and passes all 69 picking scenarios/125 database checkpoints in CI37679880338. Both backend shards remain running. Full CI and production readback remain required; this draft is not a release PASS.

The web build target is resolved from the current compose configuration, then
matched against its declared image list (which includes dependencies). The old
container's Config.Image is never used as the new build target. Explicit image
names and both compose project-name separators are covered; missing/ambiguous
targets fail closed. A read-only production probe returned `wms_prod-web`.
Compose JSON is piped directly to the parser and is neither printed nor saved.
