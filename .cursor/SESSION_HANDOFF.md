# Session handoff (autopilot)

- parallel_workers: 3
- backlog: CHESTNY_ZNAK_PRODUCT_FIRST_TASKS_RU.md
- integration_branch: feat/cz-product-first
- mode: continuous + hook
- status: **BACKLOG COMPLETE** — all ids `.done` on `feat/cz-product-first` (2026-06-29)

## Closed (full backlog)

SVC-01, SVC-02, API-01, API-02, LIST-01, PROD-01, PROD-02, POOL-01, APP-01, E2E-01 — integrated

## Next step (owner)

PR `feat/cz-product-first` → `main` after full CI. Note: legacy honest-sign e2e specs still pool-row — may need follow-up.

## Runnable queue (after deps)

| Wave | ids | note |
|------|-----|------|
| 1 | SVC-01 | only runnable at start (BE service) |
| 2 | SVC-02 ∥ API-01 | after SVC-01 .done |
| 3 | API-02 | after SVC-02 + API-01 |
| 4 | LIST-01 ∥ PROD-01 ∥ POOL-01 | after API-02 — **full 3 slots** |
| 5 | APP-01 | after PROD-01 |
| 6 | PROD-02 | after PROD-01 |
| 7 | E2E-01 | after all FE |

## Invariants (ЧЗ product-first)

- Пул = один GTIN; остаток на пуле, не на товаре
- personal_available = пулы с 1 товаром; shared_baskets = пулы с ≥2
- available_count = personal_available (без задвоения общих)

## Closed

- SVC-01: integrated
- SVC-02: integrated
- API-01: integrated

- API-02: integrated

## Active builders (wave 4 — full 3 slots)

- LIST-01: in progress
- PROD-01: in progress
- POOL-01: in progress
