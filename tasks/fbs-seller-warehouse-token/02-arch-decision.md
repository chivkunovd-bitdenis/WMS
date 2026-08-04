# 02 — Арх-решение

Наследует эпик Gate 1 ✅. Уточнения модератора 30.07.2026 — см. `01-analysis.md`.

- Поле: `marketplace_token_encrypted`
- Сервис: `fbs_seller_warehouse_service.py`
- API: `fbs_sellers.py` → `/operations/fbs-sellers/{seller_id}/warehouses`, `.../offices`
- Клиент: extend `wildberries_client.py`
- Миграция: `20260730_0063_fbs_marketplace_token.py` (после 0062)

**Ок на код** (владелец: «делай дальше в том же режиме»).
