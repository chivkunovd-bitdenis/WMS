# Reviewed-source activation draft

The product reference remains P `7dbce79566246f7467bf1b7c84efa8cbe8f1cd9b`.
Independent product/fixture acceptance is `982eaea9a3a05e20ee34d48350fded31a7bd19a5`.
Fixture F is `52caa65e17cf3e19a9040c7439840823b0d622f2`.
The workflow's literal product pin and the existing controlled binding fixture
move together. Historical failure and negative fixtures are preserved. This does
not select HEAD and does not change the checker or authorize deployment.

The protected registry keeps every previous file, suite, report and case ID.
It records reviewed inherited production files, precise fixture corrections and
new asset-retention protection. Nine asset tests are added to the existing exact
ci-shards receipt; no previous test is removed.

The existing production script now preserves previous assets before web build,
prepares an unstarted candidate container, adds only absent old assets, verifies
all old/new SHA-256 values, and commits that verified filesystem under the usual
compose image tag. This completes before application writers stop or new web
traffic starts. A conflicting existing path fails closed. The EXIT trap cleans
up its temporary container and directory on success or failure. The CI gate and
first Docker build ordering are unchanged; no gate exception is added.

Local checks: nine retention checks; thirty retention/existing deploy gate checks
plus 59 subtests; 31 policy tests plus 34 subtests; 67 product-reference checks
plus nine subtests. Bash syntax passes. The small real Docker probe verified 382
existing assets plus one synthetic retained file through two unstarted containers
and a separate temporary image. It did not change the live web image, start time,
or production tags. It is not a production deployment.

Activation still requires a separate trusted-main bootstrap pin PR and explicit
owner permission to merge that PR. The functional CI of F has two unresolved
frontend failures (WMS-684 PDF timeout and WMS-657 C5 geometry) at this record's
creation. Full CI and production readback remain required; this draft is not a
release PASS.
