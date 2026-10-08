# WMS-635 omitted-SGTIN refusal guard

This focused evidence applies to product candidate `ffb524e2950cfb250993ad4db3b0f394ca55f735` on `codex/wms666-packing-release-1008`.

The tests-before-code contract was published as `f451f5c17fe2362c4f08eedcf69a10a60dd4cbe7` and integrated test-only as `9627f455a`. Its baseline was product SHA `7f493b4fbff9c4fa85f0c7f6b88f096ae7df85bc`. The exact frozen test first confirmed in a fresh session that the current marking was `rejected`, bound to the expected code, and had a final `meta_validation_fail` operation. A complete returned WB order row omitted `sgtin`; read-only sync made no PUT but changed the marking to `unknown`, failing the frozen expectation. The run was on isolated SQLite and is an application-path RED, not PostgreSQL concurrency evidence.

The product commit `ffb524e2950cfb250993ad4db3b0f394ca55f735` changes only `backend/app/services/fbs_marking_service.py`. The guard preserves rejection only for the current rejected SGTIN with a final failed write when the complete WB row omits the kind or returns it empty. A matching nonempty accepted value still applies; missing kind without a final refusal stays `unknown`; a different nonempty value stays `replacement_required`.

`backend-targeted.txt` records the exact post-fix command and result: 9 passed. It uses `sqlite+aiosqlite:///:memory:` because the disk-backed pytest database could not be opened under ENOSPC; this does not validate PostgreSQL concurrency. `static-checks.txt` records Ruff and targeted mypy results.

Relevant tracked blob identities at `ffb524e`:

- `backend/app/services/fbs_marking_service.py`: `0faa412f4a9ffac84e4d7e42cd8e9dc8ac059ca4`
- `backend/tests/test_wms635_kiz_no_wb_wait.py`: `de732464c52df3aed1c91bd336f3815017070d2b`
- `backend/tests/test_wms546_marking_verdicts.py`: `b83bc5a9c47cda08be2ebc2515a713742cce0f6e`
