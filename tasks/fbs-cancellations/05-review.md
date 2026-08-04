# 05 — Ревью

## Adversarial
**APPROVE WITH WARNINGS** ([Adversarial review cancellations](fbd46c3f-1664-4f0a-9e5e-81627c915d4a))
- Critical: нет
- Moderator: `sold→done` снимает резерв

## Verifier — **READY** ([Verify fbs-cancellations](1a69bcf8-f53f-4776-a0e4-40be40be99cd))
- ruff/mypy exit 0
- pytest cancellations+intake: **15 passed** (повтор после SQLite-флейка на combined run)
- PATCH cancel + POST sync-statuses; FOR UPDATE; TC-001..004
- Residual: SQLite isolation flake при параллельных прогонах; нет beat; returns deferred
