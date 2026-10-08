# WMS-666 loopback Wildberries wire evidence

This folder preserves the local receiver, the bounded real-client runner, and its readbacks for the M25 synchronous replacement/refusal/restore path. The receiver binds only to `127.0.0.1`; it is a synthetic test endpoint, not Wildberries. The runner uses the isolated WMS-666 test fixture and a synthetic fixture token. Captures record only whether an authorization header was present; no credential value is stored here.

`m25-wire-restore-check.py` performs the test-fixture calls and writes `m25-wire-restore-delete-pass.json`. It resets only the loopback receiver and creates its own isolated fixture, so do not run it against an operator or production environment. The saved run's `product_sha` is `7f493b4fbff9c4fa85f0c7f6b88f096ae7df85bc`; it is retained at that exact historical source identity. The reviewed M25 client serialization and marking-service transport are source-equivalent for this wire boundary in the later candidate; the ffb browser M25 UI run is separately recorded at `whole-process/m25-ui-refusal-unlink-ffb524e-r3/`.

`server.mjs` records the actual HTTP method, path, order ID, JSON body where applicable, response code, and independent receiver state. The successful readback demonstrates initial binding, rejected replacement, restore of the previous CIS, and provider-side deletion. The intentionally failed-attempt snapshots are kept to make the chronology auditable; use the `*-delete-pass.json` file for the completed DELETE-inclusive result.

The executed 21/M41 browser runner is `frontend/tests-e2e/wms666-whole-process/compatibility-browser.proof.mjs`; current captured per-case outputs are under `browser-matrix/`. Product code and runner output are pinned separately in the release manifest.
