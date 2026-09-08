# Staging FBS «Подбор»: красная строка forbidden

08.09.2026 проверены HTTP access logs только по 403 и исходники `5c371f39` против базы `6afa60e7`. Код, права, конфигурация и данные не менялись.

Подтверждённый отказ: `2026-09-08T10:48:29.266177330Z GET /products/linked-wb-catalog → 403`, deployment `ebfa35d1-e2c4-41bb-bd57-93ac8ed37f5a`. В сохранённом `staging-pick-403-http.json` только timestamp, method, path, status, deployment ID; payload/headers/секретов нет.

Цепочка: `FfFbsSupplyWorkspace.tsx:1744` встраивает `FfUnloadPickPage source="fbs"`. После загрузки detail с seller_id последний вызывает `useMarketplaceProductCatalog` (`FfUnloadPickPage.tsx:173–176`). Hook делает `GET /products/linked-wb-catalog?seller_id=…` (`frontend/src/hooks/useWbProductCatalog.ts:18`). Backend (`backend/app/api/products.py:755–764`) требует `require_fulfillment_admin`; `backend/app/api/deps.py:158–165` возвращает 403/forbidden для любого user.role, отличного от fulfillment_admin. Root сообщил роль employee для denis.tsd.staging@example.com.

Это отдельная загрузка каталога, не основного подбора. Hook сохраняет ошибку как catalogError; `FfUnloadPickPage.tsx:535–539` показывает её в ErrorNotice и продолжает рисовать UnloadPickScreen. Поэтому видны состав/источники подбора и одновременно красная строка. Пустая devconsole не опровергает обработанную ошибку HTTP.

**Дефект уже присутствовал в базе 6afa60e7.** Полностью одинаковы Git blobs между 6afa60e7 и 5c371f39:
- useWbProductCatalog.ts: `c2bd93c469e8bafbb81e6498f8e9064556719da8`;
- backend/app/api/products.py: `777723334bab71bb9b120083b4b80755eedd8da7`;
- backend/app/api/deps.py: `a0b4acc16e8ab740d7399c23eea21c90f9c58451`.

В базовом FbsSupplyWorkspace уже есть FfUnloadPickPage source=fbs (1668–1671), а в базовом FfUnloadPickPage уже есть вызов hook и вывод catalogError (185–187,566–567). Изменения first40 в количественных источниках/подборе не создавали этот вызов и не меняли его guard.

Причина: общий операторский экран запрашивает endpoint каталога, разрешённый только администратору. Исправление не выполнялось: нельзя устранять это слепым повышением роли сотрудника или снятием tenant/seller guards. Этот read-only диагноз отделён от проверки упаковки и не отменяет её фактических результатов.
