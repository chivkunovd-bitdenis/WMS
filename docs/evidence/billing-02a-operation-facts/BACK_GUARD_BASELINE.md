# 2А correction round 1 — back_guard baseline

`python3 scripts/ci/back_guard.py --update` не запускался. Correction round 1
изменил ровно одну разрешённую baseline-запись отдельным commit
`a07b0c5c06ca4e9170971f7eb95c7e4f9d6072a0`:

| Source service | Было → стало | Причина |
|---|---|---|
| `backend/app/services/marketplace_unload_service.py` | `1226 → 1230` | Terminal shipment/cancel сохраняет durable `shipped_at`/`cancelled_at` рядом с canonical writer; вынесение потеряло бы атомарную связь действия и recovery source. |

Другие baseline entries не менялись. После отдельного baseline commit
`python3 scripts/ci/back_guard.py` завершился с exit 0 и сообщил `новых отступлений нет`.
