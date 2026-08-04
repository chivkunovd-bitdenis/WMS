# 03 — Контракт

**Scope:** marketplace_token в credentials; GET warehouses/offices через WB v3; изоляция seller; intake prefer marketplace token.
**Out:** create warehouse, cache, frontend, stocks.

## DoD
- [ ] GET warehouses → список id/name/address (officeId если есть в ответе WB)
- [ ] GET offices → список officeId/name/city/etc из WB
- [ ] Нет marketplace_token → 403
- [ ] Чужой seller / другой tenant → 403/404
- [ ] Patch credentials принимает marketplace token
- [ ] Intake использует marketplace_token если есть
- [ ] pytest `tests/test_fbs_seller_warehouse.py` зелёный
