# Батч 05. Screen/action ledger

Каждая строка — отдельная проверенная цепочка в настоящем in-app Browser. Все 54 PNG имеют отдельный verdict в `B05_VISUAL_ADJUDICATION_RU.md`; все 148 checklist ID — в `B05_EXECUTION_CHECKLIST_RU.md`.

| Action | Что сделано и что прочитано обратно | Evidence | Verdict |
|---|---|---|---|
| B05-C001 | После user-closed tabs открыта новая in-app tab; session сохранилась, catalog и stock A/B восстановлены. | `b05-001` | `PASS` recovery; environment event. |
| B05-C002 | Exact SKU A найден; справа прочитано 3/0/3/3. | `b05-002`, `b05-003` | `PASS` state; `FAIL_UX` horizontal split. |
| B05-C003 | Exact SKU B найден; справа прочитано 2/0/2/2. | `b05-004`, `b05-005` | `PASS` state; `FAIL_UX` horizontal split. |
| B05-C004 | Barcode A + Enter нашёл exact A. | `b05-006` | `PASS_WITH_FRICTION`: generic search, scanner feedback нет. |
| B05-C005 | Name search с case/spaces дал A/B; unknown query дал понятный empty message. | `b05-007`, `b05-008` | `PASS`. |
| B05-C006 | Exact warehouse, A 1.1/barcode и system Sorting прочитаны. | `b05-009` | `PASS` directory; `FAIL_PROCESS` contents отсутствует. |
| B05-C007 | Foreign `Тестовый` открыт read-only и exact warehouse восстановлен. | `b05-010`, `b05-011` | `PASS` safety. |
| B05-C008 | Print dialog A 1.1 открыт и закрыт, physical print не запускалась. | `b05-012` | `PASS`. |
| B05-C009 | Reload cells сбросил selection на first exact warehouse; wide layout проверен. | `b05-013`, `b05-014` | `FRICTION`; `BLOCKED_ENV` exact-wide export. |
| B05-C010 | Seller menu/options проверены; exact seller оставил A/B. | `b05-015`–`b05-017` | `PASS_WITH_FRICTION` focus. |
| B05-C011 | Seller + exact A search compose до одной строки, clear возвращает A/B. | `b05-018`, `b05-022` | `PASS`. |
| B05-C012 | Single-row sort frames отклонены как proof порядка. | `b05-019`–`b05-021` | `N/A` order proof; retained and labeled limited. |
| B05-C013 | Name asc/desc и quantity asc/desc проверены на двух строках. | `b05-023`–`b05-026` | `PASS`. |
| B05-C014 | 1280 right offset показал stock A/B, но скрыл identity. | `b05-027` | `FAIL_UX` one-glance. |
| B05-C015 | Wide runtime 1920×1080 измерен в left/right offsets; DOM scrollWidth 2015. | `b05-028`, `b05-029` | `FRICTION`; exported files 1873×1080. |
| B05-C016 | Catalog reload сбросил filters/query к полному списку. | `b05-030` | `FRICTION`; stock durable. |
| B05-C017 | Exact catalog row click и keyboard inspection не дали detail: role/tabindex/onclick отсутствуют. | `b05-002`; runtime | `FAIL_UX`. |
| B05-C018 | Inventory открыт из nav, controls отсутствуют. | `b05-031` | `FAIL_PROCESS`. |
| B05-C019 | Inventory reload, Back и Forward проверены. | `b05-032`–`b05-034` | `PASS` navigation; process остаётся absent. |
| B05-C020 | Inventory wide state проверен. | `b05-035` | `FAIL_PROCESS`; `BLOCKED_ENV` exact-wide export. |
| B05-C021 | Hidden Movements direct route открыл false-empty до refresh. | `b05-036` | `FAIL_PROCESS / FAIL_UX` discoverability. |
| B05-C022 | Manual refresh загрузил 80 rows; exact A/B movement rows найдены. | `b05-037`, `b05-038` | `PASS` presence; `FAIL_PROCESS` semantics. |
| B05-C023 | Safe read-only movement digest запущен один раз и завершился 132. | `b05-039` | `PASS`. |
| B05-C024 | Movements reload снова дал empty и сбросил job status. | `b05-040` | `FAIL_PROCESS`; functional false-empty. |
| B05-C025 | Wide movements до/после manual refresh проверены. | `b05-041`, `b05-042` | `FAIL_UX` contrast/columns; `BLOCKED_ENV` exact-wide export. |
| B05-C026 | Movement rows runtime проверены на click/keyboard; search/filter/sort/pagination отсутствуют, limit 80. | `b05-037`; runtime | `FAIL_UX / FAIL_PROCESS`. |
| B05-C027 | Hidden Transfers direct route открыт; purpose copy прочитан. | `b05-043` | `FAIL_UX` discoverability/contrast. |
| B05-C028 | Safe draft A1.1→Sorting, A, qty1 создан, не submitted. | `b05-044` | `BLOCKED_FIXTURE` mutation; `FAIL_UX` raw Sorting. |
| B05-C029 | Same source/destination визуально допустимы при active CTA, не submitted. | `b05-045` | `FAIL_UX`; server result не заявлен. |
| B05-C030 | Decimal, negative, zero и clear→zero проверены без submit. | `b05-046`–`b05-049` | `FAIL_UX` pre-submit validation. |
| B05-C031 | Reload очистил unsubmitted transfer draft. | `b05-050` | `FRICTION`; stock mutation 0. |
| B05-C032 | Wide transfer form проверена. | `b05-051` | `FAIL_UX` contrast; `BLOCKED_ENV` exact-wide export. |
| B05-C033 | Final A read-back доказал 3/0/3/3. | `b05-052` | `PASS`. |
| B05-C034 | Final B read-back и reload доказали 2/0/2/2. | `b05-053`, `b05-054` | `PASS` durable. |
| B05-C035 | Shared/foreign/WB state, physical print, stock mutation и application code не затрагивались; B06 не начат. | State log; Git status | `PASS` boundary. |

## Exact counts

- Evidence checkpoints: **35/35 adjudicated**.
- Checklist: **148/148 adjudicated**, **133/148 полностью исполнены**.
- PNG: **54 saved / 54 personally viewed / 54 visual verdicts**.
- Blocked/not run: 4 `BLOCKED_FIXTURE`, 3 `BLOCKED_ENV`, 7 `NOT_RUN`, 1 `N/A`.
- Evidence gate: **`ACCEPTED`**.
- Product gate: **`STOP`**.
