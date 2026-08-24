# S0 — clickable Ozon prototype report

Дата: 24 августа 2026 года. Это fixture-only React/MUI прототип: он не вызывает backend или Ozon, не создаёт production models, routes, jobs или миграции. Действия меняют только состояние компонента в памяти; повторная загрузка страницы возвращает детерминированные fixtures.

## Browser acceptance map

Начать в уже аутентифицированном FF-портале и открыть пункт `Ozon` (`nav-ff-ozon`). Все URL ниже начинаются с `/app/ff`.

| ARCH scenario | URL | Role | Click/action | Visible result |
|---|---|---|---|---|
| 1. Account, identity, capability | `/ozon/connection` | Admin | `Проверить подключение`, заполнить второй fixture credential pair; открыть catalog | Карточки Loviana/Fashion, masked identity, capability matrix, permanent read-only stock boundary; никакого control/route for stock publication |
| 1. Product mapping and FBS binding | `/ozon/catalog` | Admin | `Связать` → `Подтвердить`; `Склады и доставка` → `Сохранить связь` | Account-scoped mapping becomes confirmed; six explicit topology fields and the resulting physical-route sentence are visible |
| 2. Multi-line FBS | `/ozon/fbs/4829-0001-1` | Operator | `Связать товар`, `Начать подбор`, scan location then product | Two positions / three units and per-line reserve/mapping state; product scan stays disabled until a location scan |
| 2. Marking correction | `/ozon/fbs/4829-0002-1` | Operator | `Исправить до фиксации` → `Сохранить и проверить` | Rejected exemplar becomes accepted; local/external status is explicit |
| 2. Partial package and label | `/ozon/fbs/4829-0003-1` | Operator | `Создать частичный package`, `Проверить readback`, `Печать`, `Проверить перед передачей` | Separate second package, pending→ready label, superseded v1 warning and one-by-one/carriage/manual preflight |
| 2. Cancel after pick recovery | `/ozon/fbs/4829-0004-1` | Operator | Scan `Ячейка возврата` → `Вернуть в ячейку` | Explicit reverse movement confirmation; reserve is released only after the scan |
| 2. Uncertain handover/arbitration | `/ozon/fbs/4829-0005-1` | Shift lead | Advance to `Подтверждение` | WMS handover remains distinct from Ozon scan; arbitration button is role-labelled |
| 3. FBO draft/timeslot | `/ozon/fbo` then `/ozon/fbo/SO-80931` | Planner | `Создать поставку FBO`, select supported direct mode, `Создать intent`, `Прочитать статус операции` | Unsupported multi-cluster mode is disabled with reason; async pending is not success until readback |
| 4. Cargo, TGM, labels, act | `/ozon/fbo/SO-80931` | Planner / operator | link WMS boxes, add cargo to TGM, apply labels, inspect act | WMS boxes and Ozon cargo are separate; 2 cargo in 1 TGM, failed label partial state, act 10/9/1 visible |
| 5. Unmatched return quarantine | `/ozon/returns/RET-7783` | Reception | scan barcode, `Создать приёмку в карантине`, `Открыть осмотр`, choose disposition | Unmatched return stays in quarantine; no default disposition and no auto-restock |
| 6. Account isolation | any `/ozon/*` | Admin | switch `ozon-account-select` Loviana ↔ Fashion | Loviana visibly has WB summary badge plus Ozon account; Fashion stays pending_credentials and does not inherit operational data |
| 7. State recovery | `/ozon/fbs`, `/ozon/fbo`, `/ozon/returns` | Relevant role | choose fixture state selector/button | Loading skeleton, empty, error, stale partial/429, unknown and uncertain states retain confirmed data and present one safe next action |

## Selector contract

Implemented stable selectors: `nav-ff-ozon`, `ozon-account-select`, `ozon-sync-health`, `ozon-module-tabs`, `ozon-fbs-queue`, `ozon-posting-next-action-{id}`, `ozon-scan-location`, `ozon-scan-product`, `ozon-unit-identifier-{id}`, `ozon-package-lines`, `ozon-label-status`, `ozon-handover-preflight`, `ozon-fbo-queue`, `ozon-cargo-zone`, `ozon-tgm-zone`, `ozon-acceptance-act`, `ozon-returns-queue`, `ozon-return-disposition`, `ozon-catalog-mappings`, `ozon-warehouse-binding`, and `ozon-account-health`.

## Scope boundary

The existing WB FBS, stock-sync and Wildberries screens were not changed. The single navigation entry and eight prototype route registrations are the only application integration. There is no Ozon stock-publication UI control, API call, route, state mutation or hidden capability in the prototype.

## Technical verification

On 24 August 2026, the installed locked frontend dependencies were used to run `npm run build` from `frontend/`. The command completed successfully: `tsc -b && vite build` exited 0 and Vite produced the production bundle. Vite reported only its existing chunk-size warning; it did not fail the build. This technical result is not evidence of a visible-browser acceptance. A separate Product Browser Review must record `PRODUCT_BROWSER_APPROVED` or rework against the map above.
