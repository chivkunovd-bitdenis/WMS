# WMS-084: WB emulator metadata removal

Static validation: mypy with `--follow-imports=silent --cache-dir=/dev/null` passed on both changed implementation files. Own temporary SQLite test directory was removed after validation.

The WMS client already sends DELETE /api/v3/orders/{order_id}/meta?key=sgtin and accepts an empty successful response. The emulator implemented only GET and PUT, so a real operator cancellation against the emulator stopped at HTTP 405.

Added the missing DELETE handler returning HTTP 204. It uses the existing authorization middleware and seller-scoped order lookup; an unknown token gets 401 and an absent or another seller's order gets 404. Unsupported metadata kinds return 400. A small helper removes only the requested kind from the existing seller/order metadata dictionary. Other kinds remain intact and repeating the deletion is harmless. No WMS client, warehouse state, billing, credentials, or real WB data changed.

Validation: the two new tests first failed with HTTP 405. After implementation, these two tests and the two existing PUT/GET metadata tests passed (4 passed, 0.63 seconds). They cover full GS-containing synthetic KIZ, deletion followed by GET, repeat deletion, preservation of GTIN, missing/unknown authorization, another seller, an unknown order, and invalid key without metadata changes. Ruff passed on the three changed Python files.

This is emulator support for later browser acceptance. It does not establish real WB acceptance or WMS-084 deployment. Existing emulator metadata remains process-local memory and therefore retains its existing restart/multiple-process limitation; this change does not introduce new storage.

## Emulator deployment and preservation, 2026-09-09

Deployed only the existing Railway wb-emulator service `582b4add-d338-424c-be03-9bb66af6c8f0` in project `c28e681d-4535-4c96-ac97-c7b600a7f8e4`, environment `58a08b66-1290-45a2-8737-e3d7408389e5`. Source commit: `49803fd014fc300e208260a12fff36c6a8c79b37`. Its Dockerfile was restored byte-for-byte from the previously deployed `520fac16f6fabaaa229883e03dd50c5a1a71ab87`. The emulator subtree delta consists only of the DELETE handler, helper and targeted tests.

Deployment `d66046a9-a26f-4e5d-aa3f-49574c912aa0` reached SUCCESS with exactly one RUNNING instance `4bc9f744-3af4-434d-9003-eec557699d51`; the previous instance was no longer active. The existing repository-root build context and `wb_emulator/Dockerfile.railway` settings were preserved. CLI deployment metadata does not provide a Git commitHash, so source identity was checked directly: all 44 included tracked emulator files match commit 49803fd0 byte-for-byte. The remaining tracked `.env.example` template is excluded by the existing `.gitignore` `.env.*` rule. PID 1 is the single uvicorn process; health returns ok and the running OpenAPI document includes the new DELETE route.

Before deployment, a fresh read-only SQLite backup and authenticated GET metadata export matched the earlier copies exactly. The database path is `/data/wb_emulator.sqlite`; no volume is mounted at `/data`. The copies are private ignored files under this worktree's `tmp/`, with permissions 0600; neither their contents nor credentials are in Git or build context. Original backups remain unchanged:

- `wms084-emulator-preserve-20260909.sqlite`: 126976 bytes, SHA-256 `078048a8d3872ecf7b0b7e5575b7ef7cf142b64773141f7ba845798d50dca185`.
- `wms084-emulator-metadata-20260909.json`: 1798 bytes, SHA-256 `2b718af00d2a6a8531543f6c0636bcfa195a47eb1cb91b9d072010699ff2d2d4`.

After rollout, the copies were staged as separate 0600 incoming files on the new emulator instance. The existing destination was verified empty, then restored through SQLite `source.backup(destination)` using a read-only source and destination opened with `mode=rw`. The backup used a progress callback with a 30-second busy deadline. No live database file was replaced by cp/mv, no separate-process engine reset was used, and no service restart followed the restore.

After restore, integrity_check returned ok, foreign_key_check returned zero violations, and the SHA-256 of the complete logical SQLite dump (schema and rows) matched the source: `b252050e3e6fe88a692e0790757d6358431abcbef887fdd07f0b24f2a50eb97d`. Counts matched: 42 orders, 15 supplies, 15 supply audit rows, 9 stock rows, 33 supply/order links, 3 boxes, zero box/order links, one schema-version row. The whole-file hash is not used to compare restored SQLite because backup can change the destination schema cookie.

The live uvicorn API then returned all 42 expected order IDs. Four nonempty metadata records were restored through the existing authenticated PUT endpoint, followed by GET comparison of all 42 orders against the saved export; every response matched, including empty metadata for the other 38 orders. The SQLite logical digest remained unchanged after these API calls. There was no restart after metadata restoration. Authentication used only the already configured token for synthetic seller_a, held in memory; no real WB/Content/Ozon service was called.

This verifies emulator deployment and preservation, not the WMS-084 browser cancellation/rebinding flow. That acceptance remains a separate coordinated step. WMS backend/web/production, infrastructure, volumes, credentials and integration settings were not changed by this operation. Process-local metadata still requires preservation before any future emulator restart.
