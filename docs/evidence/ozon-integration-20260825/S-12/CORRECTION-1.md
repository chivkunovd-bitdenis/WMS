# S-12 correction 1 — provider dispatch

Дата: 2026-08-25

Проверено контрактными тестами:

- fake `OzonMarketplaceProvider` вызывает `dispatch_unload` до локального `shipped`;
- ответ `403` с `code=7` оставляет документ в `collecting`, не освобождает резерв и возвращает
  оператору `provider_dispatch_blocked`;
- обычная композиция использует ту же adapter boundary и при текущей блокировке тоже возвращает
  `provider_dispatch_blocked`, а не локальный успех;
- `wb_mp_warehouse_id` отвергается при create и PATCH документа Ozon;
- plan/confirm документа Ozon без строк возвращают `no_lines`, ship черновика — `bad_status`;
- селлер B того же tenant не видит документ селлера A.

Живой браузер по-прежнему BLOCKED: Browser plugin не содержит обязательный
`scripts/browser-client.mjs`; frontend dependencies не установлены из-за ограничения диска.
Интеграция сможет закрыть этот блокер после восстановления browser client и frontend toolchain.
