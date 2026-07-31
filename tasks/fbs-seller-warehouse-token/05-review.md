# 05 — Ревью + прогон

## Adversarial
- **APPROVE WITH WARNINGS** (Composer), 30.07.2026
- Critical: нет
- Warnings (MVP): prefer-marketplace test; TC-004 only cross-tenant; private `_seller_in_tenant`; WB→502

## Verifier
- **READY** — 30.07.2026 ([Verify seller warehouse token](0647a7ca-a453-47fd-8c5b-173eaae1f480))
- `ruff check .` exit 0; `mypy app` exit 0; pytest **18 passed**
- Migration `0063` ← `0062`; router `fbs_sellers`; TC-NEW-FBS-WHTOKEN-001..004
