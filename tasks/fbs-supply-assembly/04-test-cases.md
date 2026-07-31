# 04 — Тест-кейсы

| TC-ID | Notes |
|-------|-------|
| TC-NEW-FBS-SUPPLY-001 | POST create supply draft + wb_supply_id; WB error → no orphan row |
| TC-NEW-FBS-SUPPLY-002 | Add order → in_supply; already in other supply → error |
| TC-NEW-FBS-SUPPLY-003 | Picking list grouping + empty |
| TC-NEW-FBS-SUPPLY-004 | Stickers cached; WB error surfaced |

`pytest tests/test_fbs_supply_assembly.py`
