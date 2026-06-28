# FIX-05 — builder report (ledger / pools / reprints / backend / docs)

**Ветка:** `feat/cz-ux-fixes`  
**Дата:** 2026-06-28  
**Агент:** builder FIX-05

## Сводка

| Действие | Файлы |
|----------|-------|
| AbortController в `load()` | `HonestSignLedgerPage.tsx`, `HonestSignScreen.tsx`, `HonestSignPoolPage.tsx` |
| E2e экспорт ленты | `ff-honest-sign-ledger.spec.ts` (TC-NEW-LEDGER-04) |
| Pytest OpenAPI deprecated | `test_marking_deprecated_openapi.py` |
| FINAL-03 backlog sync | `MASTER_BACKLOG_RU.md` |
| FINAL-02 doc audit | `CZ_DUPLICATE_SURFACES_AUDIT_RU.md` |

## Per-task status

| ID | Verdict | FIX-05 action | Остаток (warnings) |
|----|---------|---------------|-------------------|
| **LEDGER-01** | N/A gate ✅ | — | E2e `pool-filter`; flash `poolNameFromRows`; TASKLOG |
| **LEDGER-02** | **FIXED** race | AbortController в `load()` | Pytest cross-page mask; e2e `cis-mask`; unit normalize |
| **LEDGER-03** | N/A gate ✅ | — (e2e даты уже в spec) | TZ naive dates; inverted range pytest |
| **LEDGER-04** | **PARTIAL** | E2e export CSV | `export_too_large` RU; CSV EN `event_type`; debounce parity |
| **LEDGER-05** | **FIXED** race | AbortController в `load()` | E2e debounce маски; 400ms UX gap |
| **LEDGER-06** | N/A (FIX-03) | — | `EVENT_TYPES` subset; reprints drawer — FIX-03 |
| **POOLS-01** | N/A gate ✅ | — | E2e search 30+; `noOptionsText` |
| **POOLS-02** | N/A gate ✅ | — (KPI e2e в `ff-honest-sign-pools.spec.ts`) | Seller ledger route; `primary.50` theme |
| **POOLS-03** | N/A (FIX-03 lane) | — | Empty-state tooltip; 0 sellers copy |
| **POOLS-04** | N/A gate ✅ | Doc §4 ✅ | KPI low-stock empty table edge |
| **POOLS-05** | N/A gate ✅ | Doc §4 ✅ | E2e ForecastLabel; pool card drift |
| **POOLS-06** | N/A gate ✅ | Doc §4 ✅ | E2e `pool-link-quick` |
| **REPRINTS-01** | N/A gate ✅ | — | E2e help-block; TASKLOG |
| **REPRINTS-02** | N/A gate ✅ | — | E2e reject+reason POST |
| **REPRINTS-03** | N/A gate ✅ | — | Race `openCodeHistory`; `event_type` RU |
| **POOLCARD-02** | N/A gate ✅ | — | E2e «N из M»; large pool pagination |
| **POOLCARD-03** | **FIXED** race | AbortController в `loadLedger()` | E2e cap 5; error handling |
| **BACKEND-01** | **FIXED** pytest | `test_marking_deprecated_openapi.py` | Тикет на удаление routes; service dead code |
| **CROSS-02** | N/A gate ✅ | — | `total > 200` badge; API error UX |
| **PENDING-01** | N/A gate ✅ | — | `printQueueRef` on cancel; bulk guard |
| **FINAL-02** | **FIXED** docs | Ссылка `docs/`; §4 POOLS closed | `MarkingProductCodesDialog` orphan file |
| **FINAL-03** | **FIXED** docs | `MASTER_BACKLOG` lane ✅; T-A6 ✅ | T-A5/T0.2 pending; CI link-check |

## Runtime proof draft

```text
$ cd backend && ruff check tests/test_marking_deprecated_openapi.py
All checks passed!

$ pytest tests/test_marking_deprecated_openapi.py -q
.                                                                        [100%]
1 passed

$ pytest tests/ -k "honest or marking_ledger or marking_deprecated or marking_pools or marking_scan or marking_print_all or marking_verify" -q
....................                                                     [100%]
20 passed, 228 deselected in 13.13s

$ cd frontend && npm run build
✓ built in 1.47s
```

E2e `ff-honest-sign-ledger.spec.ts` (export) — не запускался в этой сессии (долгий webServer); добавлен TC-NEW-LEDGER-04 по контракту LEDGER-04.

## Риски

- Полный `ruff check .` в backend падает на **pre-existing** замечаниях в других тестах (не в зоне FIX-05).
- E2e export не прогнан локально — verifier должен включить в `npm run test:e2e`.
- Deprecated endpoints остаются живыми (410 не внедрялся) — только OpenAPI `deprecated=True`.
