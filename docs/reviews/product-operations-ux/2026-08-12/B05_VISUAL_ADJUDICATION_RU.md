# Батч 05. Visual adjudication каждого PNG

Все 54 файла ниже лично открыты через `view_image` после сохранения. Verdict относится к тому, что действительно видно в кадре; он не расширяется до незафиксированного server behavior.

## Catalog, cells и filters

| PNG | Что видно | Visual verdict |
|---|---|---|
| `b05-001` | Восстановленный catalog, 212-row длинная таблица, identity слева. | `PASS` recovery; `FAIL_UX` ширина/масштаб списка. |
| `b05-002` | Exact SKU A оставляет одну строку. | `PASS`. |
| `b05-003` | A справа: total3, Sorting0, cells3, available3; identity скрыт. | `PASS` state; `FAIL_UX` memory join. |
| `b05-004` | B справа: total2, Sorting0, cells2, available2. | `PASS` state; `FAIL_UX` memory join. |
| `b05-005` | Exact SKU B и name видны слева. | `PASS`. |
| `b05-006` | Barcode A + Enter дал exact A. | `PASS_WITH_FRICTION`: scanner feedback/mode отсутствует. |
| `b05-007` | Name query с case/spaces показывает A/B. | `PASS`. |
| `b05-008` | Понятный no-result с исходным query. | `PASS`. |
| `b05-009` | Exact FBS warehouse, Sorting и A 1.1/barcode. | `PASS` address; `FAIL_PROCESS` contents отсутствует. |
| `b05-010` | Foreign `Тестовый` открыт read-only, его cells не мутированы. | `PASS` safety. |
| `b05-011` | Exact warehouse восстановлен. | `PASS`. |
| `b05-012` | Print dialog A 1.1 с barcode и Close/Print. | `PASS`; physical print не запускалась. |
| `b05-013` | Reload выбрал первый exact warehouse. | `FRICTION`: selection не encoded/preserved. |
| `b05-014` | Wide cells view, большие пустые зоны, contents всё равно нет. | `FAIL_UX`; `BLOCKED_ENV` file 1873×1080 при runtime 1920×1080. |
| `b05-015` | Seller control открыт/сфокусирован. | `PASS_WITH_FRICTION` keyboard discovery. |
| `b05-016` | Options `Все`, exact seller, Denmarcs. | `PASS`. |
| `b05-017` | Exact seller оставляет A/B. | `PASS`. |
| `b05-018` | Seller + exact A search compose до одной строки. | `PASS`. |
| `b05-019` | Name desc при одной строке. | `N/A` для доказательства порядка; файл честно помечен limited. |
| `b05-020` | Quantity asc при одной строке. | `N/A` для порядка; limited. |
| `b05-021` | Quantity desc при одной строке. | `N/A` для порядка; limited. |
| `b05-022` | Search cleared, seller A/B остаются. | `PASS`. |
| `b05-023` | Name asc: A перед B. | `PASS`. |
| `b05-024` | Name desc: B перед A. | `PASS`. |
| `b05-025` | Quantity asc: B2 перед A3. | `PASS`. |
| `b05-026` | Quantity desc: A3 перед B2. | `PASS`. |
| `b05-027` | A/B stock columns вместе на 1280 right offset, identity обрезан. | `PASS` quantities; `FAIL_UX` one-glance. |
| `b05-028` | Wide right: stock почти целиком, page left/identity частично обрезаны. | `FRICTION`; file 1873×1080. |
| `b05-029` | Wide left: identity виден, крайняя `Доступно` не полностью. | `FRICTION`; horizontal recovery остаётся. |
| `b05-030` | Reload сбросил filters, снова full catalog. | `FRICTION`; durable stock не stale. |

## Inventory

| PNG | Что видно | Visual verdict |
|---|---|---|
| `b05-031` | `Инвентаризация` и `Раздел в разработке`, controls 0. | `FAIL_PROCESS`. |
| `b05-032` | Reload сохраняет тот же placeholder. | `PASS` route recovery; `FAIL_PROCESS` capability. |
| `b05-033` | Browser Back возвращает catalog. | `PASS`. |
| `b05-034` | Browser Forward возвращает placeholder. | `PASS` navigation; `FAIL_PROCESS`. |
| `b05-035` | Wide placeholder с ещё большей пустой областью. | `FAIL_PROCESS`; `BLOCKED_ENV` exact-wide PNG. |

## Movements

| PNG | Что видно | Visual verdict |
|---|---|---|
| `b05-036` | Direct route сообщает `Пока пусто.` до refresh. | `FAIL_PROCESS` false-empty. |
| `b05-037` | После refresh exact A/B rows видны, только SKU/Δ/type. | `FAIL_PROCESS` traceability; `FAIL_UX` contrast/raw enum. |
| `b05-038` | Populated list и `Обновить`, отдельного success feedback нет. | `FRICTION`; stock не менялся. |
| `b05-039` | Digest status `done`, result `Всего движений: 132`. | `PASS` safe read-only job. |
| `b05-040` | Reload снова empty, digest status `—`. | `FAIL_PROCESS` recovery/state reset. |
| `b05-041` | Wide initial state также empty; тёмная card плохо читается. | `FAIL_PROCESS / FAIL_UX`; `BLOCKED_ENV` exact-wide file. |
| `b05-042` | Wide после manual refresh populated, контраст и семантика не улучшились. | `FAIL_UX`; refresh recovery only. |

## Transfers и final read-back

| PNG | Что видно | Visual verdict |
|---|---|---|
| `b05-043` | Blank transfer form, CTA visually available, dark labels. | `FAIL_UX` guidance/contrast. |
| `b05-044` | A 1.1 → `__SORTING__`, A, qty1; submit не нажат. | `FAIL_UX` raw system option; `BLOCKED_FIXTURE` mutation. |
| `b05-045` | A 1.1 → A 1.1 с active CTA. | `FAIL_UX` pre-submit guard; server behavior не заявлен. |
| `b05-046` | Decimal `1,9` видим, CTA active. | `FAIL_UX` integer guard; submit не нажат. |
| `b05-047` | Negative `-1` видим, CTA active. | `FAIL_UX` positive guard; submit не нажат. |
| `b05-048` | Zero `0` видим, CTA active. | `FAIL_UX` positive guard; submit не нажат. |
| `b05-049` | Clear number control визуально возвращает `0`, CTA active. | `FAIL_UX`; это не доказательство server acceptance. |
| `b05-050` | Reload очистил unsubmitted draft, blank form. | `FRICTION` recovery; mutation 0. |
| `b05-051` | Wide form растянута, контраст остаётся плохим. | `FAIL_UX`; `BLOCKED_ENV` exact-wide file. |
| `b05-052` | Final A right read-back: 3/0/3/3. | `PASS` unchanged. |
| `b05-053` | Final B right read-back: 2/0/2/2. | `PASS` unchanged. |
| `b05-054` | B после reload остаётся 2/0/2/2. | `PASS` durable final state. |

## Visual gate

- Saved PNG: **54**.
- Personally viewed: **54/54**.
- Individual verdict rows: **54/54**.
- Standard files: exact **1280×720**.
- Wide runtime: exact CSS **1920×1080 DPR1**; wide files: **1873×1080**, therefore exact-wide export is `BLOCKED_ENV`, not misreported as PASS.
