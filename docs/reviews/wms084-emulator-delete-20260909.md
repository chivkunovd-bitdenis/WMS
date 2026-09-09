# WMS-084: WB emulator metadata removal

Static validation: mypy with `--follow-imports=silent --cache-dir=/dev/null` passed on both changed implementation files. Own temporary SQLite test directory was removed after validation.

The WMS client already sends DELETE /api/v3/orders/{order_id}/meta?key=sgtin and accepts an empty successful response. The emulator implemented only GET and PUT, so a real operator cancellation against the emulator stopped at HTTP 405.

Added the missing DELETE handler returning HTTP 204. It uses the existing authorization middleware and seller-scoped order lookup; an unknown token gets 401 and an absent or another seller's order gets 404. Unsupported metadata kinds return 400. A small helper removes only the requested kind from the existing seller/order metadata dictionary. Other kinds remain intact and repeating the deletion is harmless. No WMS client, warehouse state, billing, credentials, or real WB data changed.

Validation: the two new tests first failed with HTTP 405. After implementation, these two tests and the two existing PUT/GET metadata tests passed (4 passed, 0.63 seconds). They cover full GS-containing synthetic KIZ, deletion followed by GET, repeat deletion, preservation of GTIN, missing/unknown authorization, another seller, an unknown order, and invalid key without metadata changes. Ruff passed on the three changed Python files.

This is emulator support for later browser acceptance. It does not establish real WB acceptance or WMS-084 deployment. Existing emulator metadata remains process-local memory and therefore retains its existing restart/multiple-process limitation; this change does not introduce new storage.
