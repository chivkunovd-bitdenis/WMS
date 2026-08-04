# 04 — Тест-кейсы — fbs-wb-emulator

### Test coverage

| TC-ID | Title | Applies | Notes |
|-------|-------|---------|-------|
| TC-NEW-FBS-EMU-001 | Автопрос / seed → orders/new | Y | Given admin POST 3 заказа для seller A; When GET /orders/new с токеном A; Then заказы в списке new. Negative: unknown token → 401. Автотест: `test_full_cycle.py`, `test_admin.py` |
| TC-NEW-FBS-EMU-002 | Полный цикл до deliver | Y | Given заказ в new; When supply → stickers PNG → KIZ ok → deliver; Then все шаги HTTP ok. Negative: KIZ `ERR…` → checkStatus=error. Автотест: `test_full_happy_path_admin_to_deliver`, `test_kiz_err_sets_check_status_error` |
| TC-NEW-FBS-EMU-003 | Мультиселлер по токену | Y | Given токены A и B; When seed каждому; Then A не видит заказы B и наоборот. Автотест: `test_multi_seller_isolation` |

## Given / When / Then (сводка)

**001**  
- Дано: эмулятор с токеном A и admin token.  
- Когда: `POST /__admin/orders?seller=seller_a&count=3`, затем `GET /api/v3/orders/new`.  
- Тогда: в ответе ≥3 заказа с camelCase полями (`nmId`, `skus`, …).  
- Негатив: `Authorization: bad` → 401.

**002**  
- Дано: заказ seller A в new.  
- Когда: create supply → add order → stickers → meta sgtin OK → deliver.  
- Тогда: stickers содержат валидный PNG (magic bytes); deliver 204.  
- Негатив: sgtin `ERR…` → `checkStatus=error`.

**003**  
- Дано: два токена A/B.  
- Когда: seed отдельно каждому.  
- Тогда: пересечение пулов пустое.
