# 04 — Тест-кейсы

| TC-ID | Notes |
|-------|-------|
| TC-NEW-FBS-WHTOKEN-001 | Given marketplace_token / When GET warehouses / Then list; negative: no token → 403 |
| TC-NEW-FBS-WHTOKEN-002 | Given token / When GET offices / Then list; negative: WB upstream error → 502/mapped error |
| TC-NEW-FBS-WHTOKEN-003 | Given only supplies_token (no marketplace) / When GET warehouses / Then 403 |
| TC-NEW-FBS-WHTOKEN-004 | Given 2 sellers / When A requests B's seller_id / Then 403/404 |

Тесты: `backend/tests/test_fbs_seller_warehouse.py`
