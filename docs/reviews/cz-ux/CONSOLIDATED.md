# CZ UX — сводный adversarial-review

**Статус:** ✅ **MERGED** → `main` PR #49 (`6d375ab`), prod deploy + CD PR #50 (`6f3c0ad`)  
**Прогресс review:** 47 / 47 ✅  
**Прогресс фиксов:** 4 / 4 BLOCK ✅ (FIX-01…05)

## Сводка вердиктов (на момент review)

| Verdict | Count |
|---------|-------|
| APPROVE | 0 |
| APPROVE WITH WARNINGS | 43 |
| BLOCK | 4 → **все закрыты** |

## BLOCK — закрыто

| ID | FIX | Итог |
|----|-----|------|
| PRINT-03 | FIX-01 | Select: один «ЧЗ» + «ШК ВБ» |
| FINAL-01 | FIX-03 | Терминология КМ + e2e «1 КМ» |
| CROSS-04 | FIX-02 | Re-preview не затирает title/productIds |
| PACK-05 | FIX-04 | E2e: 2-й КМ + причина брака |

## Warnings (не блокировали merge)

- TASKLOG / TC-ID — закрыто в PR #49
- Race без abort — частично FIX-05 (ledger/pools)
- Deprecated routes — OpenAPI mark BACKEND-01; удаление — отдельный тикет
- T-A5 per-user print template — ⬜ в MASTER_BACKLOG §4

## Артефакты

- Фиксы: `fix-FIX-0N.md`
- Очередь: `FIX_QUEUE.md` (COMPLETE)
- Deploy: `docs/DEPLOY_SERVER_RU.md` (CI + CD)
