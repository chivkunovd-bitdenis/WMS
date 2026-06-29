# Session handoff (autopilot)

- parallel_workers: 3
- backlog: CHESTNY_ZNAK_PRODUCT_FIRST_TASKS_RU.md
- integration_branch: feat/cz-product-first
- mode: continuous + hook
- status: **ACTIVE** — wave 1 started 2026-06-29

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

## Active builders (wave 3)

- API-02: pending start (depends SVC-02 + API-01 — now runnable)
