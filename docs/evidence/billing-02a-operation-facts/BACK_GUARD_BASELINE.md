# 2А correction round 2 — back_guard baseline

`python3 scripts/ci/back_guard.py --update` не запускался. Единственное
разрешённое изменение baseline остаётся отдельным round 1 commit
`a07b0c5c06ca4e9170971f7eb95c7e4f9d6072a0`:

| Source service | Было → стало | Причина |
|---|---|---|
| `backend/app/services/marketplace_unload_service.py` | `1226 → 1230` | Terminal shipment/cancel сохраняет durable `shipped_at`/`cancelled_at` рядом с canonical writer; вынесение потеряло бы атомарную связь действия и recovery source. |

Round 2 изменил только tests и узкую normalisation сравнения durable UTC
timestamps в `operation_fact_recovery_service.py`; ни один permitted source
line-count не менялся. Поэтому baseline JSON не изменялся.

На финальном test HEAD `89fec60d9b571bb38fd4d43fadc86f247f5a4239`
`python3 scripts/ci/back_guard.py` завершился с exit `0` и сообщил
`новых отступлений нет`. Полный backend pytest на том же HEAD: exit `0`,
`1155 passed, 6 skipped, 9 warnings in 988.58s`.
