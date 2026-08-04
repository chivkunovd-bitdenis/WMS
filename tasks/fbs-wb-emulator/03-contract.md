# 03 — Контракт приёмки — fbs-wb-emulator

## Цель
Тестовый HTTP-сервис `wb-emulator` зеркалит WB Marketplace API v3 так, как его читает `wildberries_client.py`. WMS переключается одной env: `WILDBERRIES_MARKETPLACE_API_BASE`.

## Критерии (наблюдаемые)
1. `POST /__admin/orders?seller=&count=` + `X-Admin-Token` создаёт заказы → они видны в `GET /api/v3/orders/new` для токена этого seller.
2. Цикл: create supply → add order → order stickers (PNG) → PUT meta sgtin (ok) → PATCH deliver = HTTP успех.
3. КИЗ со значением, содержащим `ERR` → в meta `checkStatus=error` (гейт маркировки на стороне WMS).
4. Неизвестный `Authorization` → `401` на `/api/v3/*`.
5. Разные токены → разные пулы заказов.
6. `docker-compose.prod.yml` не содержит эмулятор / `WILDBERRIES_MARKETPLACE_API_BASE` на emulator.
7. Код `backend/app/**` не изменён ради эмулятора.

## Out of scope
Реальный WB, Честный Знак, prod compose, точные тексты ошибок WB.
