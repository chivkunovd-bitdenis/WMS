# 06 — Док

## Бизнес
У селлера в WMS появляется отдельный токен категории «Маркетплейс»; по нему можно увидеть склады продавца и офисы/зоны WB — это нужно для следующих шагов FBS (поставки, officeId).

## Технически
Поле `marketplace_token_encrypted`; API PATCH/GET tokens + `GET /operations/fbs-sellers/{id}/warehouses|offices` через Marketplace API v3. Intake предпочитает этот токен, иначе supplies.

## Follow-up
Тест prefer-path; same-tenant isolation; UI поля токена; публичный seller-in-tenant helper.
