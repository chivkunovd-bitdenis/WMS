# WMS-406 / WMS-407 — staging deploy and actual invoice QA, 09.09.2026

Candidate `d7d38935628805b90e3cc0295861bac4a7a0824f` deployed to the existing staging Railway project `c28e681d-4535-4c96-ac97-c7b600a7f8e4`, environment `58a08b66-1290-45a2-8737-e3d7408389e5`. No production deployment or service/source/secret settings changed.

The earlier flattened uploads did not preserve the configured `/backend` and `/frontend` service roots. Delivery used a temporary transport directory made by `git archive` of exactly `backend/ frontend/` from this commit: 1,155 tracked files, 26,731,896 bytes, no symlinks, private outputs, `.env`, `.secrets`, SQLite databases, runtime directories or dependencies. The directory was uploaded with `--path-as-root --no-gitignore`; it was a transport artifact, not another checkout.

Both deployments succeeded:

- WMS: `bd246887-7050-4413-910f-52715c8d7c22`, config `/backend/railway.toml`.
- web: `0666312e-a8fa-4cec-b758-8d2170d73909`, config `/frontend/railway.toml`.

At 07:33:53 UTC, SSH hashes of all 428 Python files in runtime `app/` and `alembic/` exactly matched the candidate. Missing, differing and extra files: zero. Backend `/health` and staging web `/` both returned HTTP 200. Frontend provenance is the tracked transport archive and successful build; new invoice behavior was then verified in its served Chrome interface.

Actual headless Chrome used the existing staging admin session only. Tenant `9c31f3f4-ce62-4c1f-891a-295b278f1e69`, seller «Эмулятор WB» `50110328-fa03-4604-b2e4-8ca27fc8bb41`, period 11.08–09.09.2026. This seller initially had no invoices. The operator path was:

1. Open «Расчёты», select 30 days and the QA seller, expand the seller.
2. Select the entire FBS section: five existing ledger sources.
3. Open invoice preview: original FBS amount 125.00 ₽.
4. Enter 407.23 ₽ and click «Применить итог»: original 125.00 ₽ retained; separate manual adjustment 282.23 ₽; total 407.23 ₽.
5. Click «Сохранить»: own invoice `731bbec1-3afb-4bd7-b71a-1a0090610286`, number `СЧЕТ-26-09-09-1`.
6. Reopen through invoice history; GET lines exactly match the saved lines. Open real print popup and inspect its screenshot: both rows and the final total are correct. No physical printer used.
7. Click «Отменить счёт» and its confirmation. Final GET and visible screen show `cancelled`, preserving the two lines.

No JavaScript errors, no blocked unexpected mutation requests. Only two invoice previews, own invoice creation and own invoice cancellation were sent as POST. No tariff, warehouse, shipment, external marketplace or other invoice mutations. Browser closed in `finally`; fallback API cleanup was not needed.

This browser run verifies the priced five-source path and manual adjustment. It does **not** claim live coverage of missing tariffs, missing ledger rows, or 894-order selection: the chosen existing QA fixture has prices and ledger rows. Missing-price and source-selection guards have separate targeted local API tests; their results do not replace this explicit browser boundary.

Evidence: [result JSON](artifacts/wms406-stage-invoice-20260909/result.json), [runtime hashes summary](artifacts/wms406-stage-invoice-20260909/runtime.json), [preview](artifacts/wms406-stage-invoice-20260909/03-explicit-total.png), [print](artifacts/wms406-stage-invoice-20260909/05-print.png), [cancelled invoice](artifacts/wms406-stage-invoice-20260909/06-cancelled.png). Screenshots were visually inspected. Tokens and request headers are absent from evidence.
