# Батч 04. Screen/action ledger сортировки и размещения

Каждая строка ниже — отдельный проверенный state transition в настоящем in-app Browser. Полный verdict каждого из 54 PNG находится в `B04_VISUAL_ADJUDICATION_RU.md`; checklist ID и конечный статус — в `B04_EXECUTION_CHECKLIST_RU.md`.

| Action | Что сделано и что прочитано обратно | Evidence | Verdict |
|---|---|---|---|
| B04-C001 | Открыта populated Sorting queue на Railway staging, exact row найдена по seller/2 lines/remaining5/date. | `b04-001` | `PASS` exact; `FAIL_UX` identity. |
| B04-C002 | Через cell directory доказан exact warehouse `FBS WB 1155120`, A 1.1 и barcode; системная Sorting отделена. | `b04-002` | `PASS_WITH_FRICTION`. |
| B04-C003 | Доказаны чужие synthetic cells warehouse `Тестовый`; ни одна не использована. | `b04-003`, `b04-004` | `PASS` safety. |
| B04-C004 | Exact row открыта click; detail доказал №000007, A3/B2, remaining5, source Россыпь. | `b04-005` | `PASS` exact; `FAIL_UX` context/overflow. |
| B04-C005 | Full-page capture проверен и отклонён как неполный из-за внутреннего dialog scroll. | `b04-006` | `N/A`, не evidence нижнего detail. |
| B04-C006 | Destination A сфокусирован и открыт; option только A 1.1. | `b04-007`, `b04-008` | `PASS` isolation; `FAIL_UX` scanner отсутствует. |
| B04-C007 | Baseline stock A3/B2 доказан как Sorting-only, cells0, available0 на 1280. | `b04-009`, `b04-010` | `PASS` state; `FAIL_UX` horizontal split. |
| B04-C008 | Browser runtime CSS viewport 1920×1080 DPR1 проверен; IAB wide exports физически 1873×1080. | `b04-011`–`b04-014`; file metadata | `PASS` runtime metrics; `BLOCKED_ENV` exact 1920px export. |
| B04-C009 | Введено A=1 без destination: draft summary уже показал distributed1. | `b04-015` | `FAIL_PROCESS`. |
| B04-C010 | Save неполной row молча очистил ввод, remaining/stock не изменились. | `b04-016`, `b04-028` | `FAIL_UX`. |
| B04-C011 | В number field с A 1.1 введено -1; inline guard не появился, затем control оказался пуст. | `b04-017`, `b04-018` | `FAIL_PROCESS`; server-save не заявлен. |
| B04-C012 | Введён и сохранён zero; row молча очищена. | `b04-019`, `b04-020` | `FAIL_UX`. |
| B04-C013 | Введено 1.9; UI сразу посчитал1, Save durable сохранил1. | `b04-021`, `b04-022` | `FAIL_PROCESS`. |
| B04-C014 | Введён overage4 при accepted3; обе CTA disabled, stock не мутирован. | `b04-023` | `PASS_WITH_FRICTION`. |
| B04-C015 | Сформирован valid partial draft A1.1=1; double-click Save не создал duplicate row/version. | `b04-024` | `PASS_WITH_FRICTION`, feedback нет. |
| B04-C016 | Reload закрыл detail; queue сохранила remaining5. | `b04-025` | `FAIL_UX` recovery; `PASS` durable remaining. |
| B04-C017 | Reopen settled восстановил saved draft A1.1=1. | `b04-026`, `b04-027` | `PASS`; loading frame не переоценён. |
| B04-C018 | Read-back каталога после Save доказал отсутствие stock movement. | `b04-028` | `PASS`. |
| B04-C019 | Saved1 изменён dirty→2, затем Close без warning; reopen восстановил1. | `b04-029`–`b04-032` | `FAIL_UX` dirty loss; `PASS` saved read-back. |
| B04-C020 | Dirty Back/Forward оставили dialog при смене route; dirty value потеряно. | `b04-033`, `b04-034`; runtime | `FAIL_UX`. |
| B04-C021 | Dirty reload без warning закрыл detail; повторное открытие потребовало новый row search. | `b04-035`, `b04-036` | `FAIL_UX`. |
| B04-C022 | Double-click `+ ячейка` оставил ровно одну новую row; remove вернул одну saved row. | `b04-037`, `b04-038` | `PASS_WITH_FRICTION`. |
| B04-C023 | Double-click partial Apply A=1 дал один transition и total remaining4. | `b04-039`, `b04-040` | `PASS` idempotent visible result. |
| B04-C024 | Queue reload сохранил exact remaining4. | `b04-041` | `PASS`. |
| B04-C025 | Reopen final identity/remaining4 прочитан обратно; lower distribution подтверждена отдельным settled кадром. | `b04-042`, `b04-040` | `PASS` с ограничением viewport. |
| B04-C026 | Partial stock read-back: A Sorting2/cell1/available1; B Sorting2/cell0/available0. | `b04-043` | `PASS` conservation. |
| B04-C027 | Для финала создан новый draft A=2 и B=2 в той же exact A 1.1; split по второй cell заблокирован fixture. | `b04-044`, `b04-045` | `BLOCKED_FIXTURE` split; `PASS` one-cell path. |
| B04-C028 | Final Save сохранил draft, но не дал visible success; draft/posted summary остались смешаны. | `b04-046` | `FAIL_UX / FAIL_PROCESS`. |
| B04-C029 | Double-click final Apply дал один terminal state: remaining0, `Оприходовано`, повторная CTA отсутствует. | `b04-047` | `PASS`. |
| B04-C030 | Close и reload Sorting queue показали отсутствие exact seller/document. | `b04-048`, `b04-049` | `PASS` durable queue removal. |
| B04-C031 | Final stock на 1280: Sorting0, cells3/2, available3/2, total3/2. | `b04-050` | `PASS` state; `FAIL_UX` table width. |
| B04-C032 | Final stock при runtime 1920 DPR1 подтверждён в двух offsets; exported bytes 1873×1080. | `b04-051`, `b04-052` | `PASS` conservation; `BLOCKED_ENV` exact 1920px export; `FAIL_UX` one-glance. |
| B04-C033 | Dashboard reload/read-back показывает №000007, A3/B2, status `Оприходовано`. | `b04-053` | `PASS` durable done. |
| B04-C034 | Final cell directory показывает exact A 1.1/barcode, но не SKU/qty/balance. | `b04-054` | `FAIL_UX` traceability. |
| B04-C035 | Exact row `<tr>` проверена runtime: role/tabindex отсутствуют; Tab/Enter flow недоступен. | `b04-001`; runtime | `FAIL_UX`. |
| B04-C036 | Проверено отсутствие manual/scanner cell input и product scanner input во всём sorting panel. | `b04-008`, `b04-014`, `b04-044` | `FAIL_UX`, unknown/wrong scan `N/A`. |
| B04-C037 | Application code не менялся, внешние WB/секреты/shared tenants не затрагивались, B05 не запускался. | Git status; этот ledger | `PASS` boundary. |

## Counts

- Evidence checkpoints: **37/37 adjudicated**.
- Checklist: **102/102 adjudicated**, из них **91/102 полностью исполнены**; 3 `BLOCKED_FIXTURE`, 2 `BLOCKED_ENV` и 6 `N/A` не скрыты.
- PNG: **54 saved / 54 personally viewed / 54 visual verdicts**.
- Runtime viewports: **1280×720 DPR1** и **1920×1080 DPR1**; exported wide bytes: **1873×1080**.
- Evidence gate: **`ACCEPTED`**.
- Product gate: **`STOP`**.
