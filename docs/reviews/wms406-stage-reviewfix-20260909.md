# WMS-406 / WMS-407 — review fixes, staging delivery and Chrome QA

On 09.09.2026 the existing staging backend was deployed from `c82783bf0d4495cc74a6210f4eb22c6edca723b0`, deployment `1b2b58f9-48e3-4d67-9d86-a5be354ad4de`. All 428 runtime Python files matched Git over SSH at 08:21:37 UTC; missing, differing and extra files: zero. Backend health and web returned 200.

The final frontend was deployed separately from `829684a0106dd8a0d6cfb050abadfebed74908dc`, deployment `abc8c3ff-4a1a-4bc7-8b71-b4d3f05d97fc`, status SUCCESS. Its backend diff against c827 is empty. Transport was limited to Git-tracked backend/frontend directories, preserving configured service-root prefixes. Temporary transport directories were removed after uploads finished and lsof showed no users. No service settings, secrets or production deployment changed.

Actual Chrome ran at 08:24:41–08:24:53 UTC using only the existing staging QA admin and seller «Эмулятор WB» `50110328-fa03-4604-b2e4-8ca27fc8bb41`. The operator selected the five FBS ledger sources, added the synthetic manual service `QA WMS407 — Нет ставки; сумма не рассчитана` for 1.00 ₽, then opened preview. The real UI showed FBS 125.00 ₽ and the manual line 1.00 ₽. This verifies that manual description text cannot hide its amount.

The operator entered a final total of 407.23 ₽. The original two lines remained and the separate adjustment was 281.23 ₽. Creation returned 201 with invoice `325b20ca-30d8-4e15-a2e1-a3d34b49d906`, number `СЧЕТ-26-09-09-2`. Reopening from history returned the same three lines. The real print popup showed the manual 1.00 ₽ and the final 407.23 ₽. UI cancellation and confirmation succeeded; final state is `cancelled`, retaining all three lines. The preview, print and cancelled screenshots were visually inspected.

Only own invoice preview/create/cancel POSTs were made. No tariff, warehouse, shipment or marketplace writes occurred. JavaScript errors: zero; blocked unexpected mutations: zero; fallback API cleanup was not needed. Chrome closed in finally.

This live fixture has five priced FBS sources. It does not prove a real unpriced shipment or the 894-order case; no synthetic warehouse/tariff changes were made to force those fixtures. Unknown snapshot preservation and manual 0/1 ₽ cases have separate targeted API regressions. PostgreSQL concurrency tests were not executed because local schema creation hit DiskFull; the isolated scratch database was subsequently deleted.

Evidence: [runtime](artifacts/wms406-stage-reviewfix-20260909/runtime.json), [delivery](artifacts/wms406-stage-reviewfix-20260909/delivery.json), [safe request/results](artifacts/wms406-stage-reviewfix-20260909/result.json), [preview](artifacts/wms406-stage-reviewfix-20260909/02-original-preview.png), [print](artifacts/wms406-stage-reviewfix-20260909/05-print.png), [cancelled](artifacts/wms406-stage-reviewfix-20260909/06-cancelled.png). Tokens and authorization headers are not present.
