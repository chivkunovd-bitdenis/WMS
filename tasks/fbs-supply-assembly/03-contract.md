# 03 — Контракт

**Scope:** create supply, add orders, picking-list, pull+cache stickers.
**Out:** packaging_task, deliver, trbx, UI.

## DoD
- [ ] POST create → DB draft + wb_supply_id
- [ ] Add order → WB PATCH + order.in_supply + supply_id set; reject if already in another supply
- [ ] GET picking-list grouped counts
- [ ] POST stickers → WB batch, cache on orders, return metadata
- [ ] pytest test_fbs_supply_assembly.py green + intake/warehouse regression smoke optional
