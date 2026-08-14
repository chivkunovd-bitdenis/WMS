# Батч 06. Screen/action ledger FF-упаковки

## Как читать

Все строки относятся к роли старшего смены или упаковщика в физическом контексте warehouse `FBS WB 1155120`, cell `A 1.1`, если не указано иначе. `b06-NNN` означает PNG в `evidence/b06/`. Runtime-only факты не подменяют screenshot; native confirm, который Browser не смог надёжно снять и закрыть, помечен `BLOCKED_ENV`.

| ID | Фактическое действие и видимый результат | Evidence | Verdict |
|---|---|---|---|
| B06-C001 | Existing FF-admin session открыла Railway staging в настоящем in-app Browser. | `b06-001`, runtime | PASS |
| B06-C002 | CSS viewport 1280×720 DPR1; все standard PNG физически 1280×720. | `b06-001`…`029`, `031`, runtime metrics | PASS |
| B06-C003 | Exact A/B найдены через видимый search; A total/unpacked3, B total/unpacked2. | `b06-002` | PASS |
| B06-C004 | Baseline split прочитан прямо в каталоге: A3/0, B2/0 unpacked/packed. | `b06-002`, runtime row text | PASS |
| B06-C005 | Exact warehouse и A1.1 barcode `LOC-36F984B31C3D` прочитаны; foreign warehouse не мутирован. | `b06-001` | PASS |
| B06-C006 | Nav `Упаковка` открыла active route/title/description. | `b06-003` | PASS |
| B06-C007 | Immediate capture уже показал settled-looking 11-row queue; отдельного loader нет. | `b06-003`, settled `b06-004` | FRICTION |
| B06-C008 | Settled queue populated: 11 open tasks. Empty state не заявлен. | `b06-004` | PASS |
| B06-C009 | Queue показывает только number/status/line count/`Да`; seller, warehouse, place и progress отсутствуют. | `b06-004` | FAIL_PROCESS |
| B06-C010 | Pending badge `13` соответствует 13 settled rows на отдельном route. | `b06-004`, `b06-005` | PASS |
| B06-C011 | Queue rows имеют `tabIndex=-1`, role/aria отсутствуют; keyboard-open невозможен. | `b06-004`, runtime accessibility read | FAIL_UX |
| B06-C012 | Reload сохранил те же 11 open rows без duplicate. | `b06-028`, `b06-031`, runtime | PASS |
| B06-C013 | Browser Back ушёл в catalog, Forward вернул тот же 11-row queue. | `b06-031`, runtime URLs | PASS |
| B06-C014 | Queue полностью помещается на 1280; проблема не в overflow, а в недостающей business identity. | `b06-004` | PASS |
| B06-C015 | Runtime 1920×1080 DPR1; IAB export 1873×1080, поэтому exact-1920 PNG не заявлен. | `b06-030`, runtime/file metrics | FRICTION |
| B06-C016 | `Создать задание` открывает dialog; до выбора/submit task не появляется. | `b06-009`, queue before/after | PASS |
| B06-C017 | Empty dialog содержит один обязательный warehouse select и disabled Create; иерархия ясна. | `b06-009` | PASS |
| B06-C018 | Warehouse options визуально содержат exact FBS и foreign `Тестовый`; выбран только exact. | runtime visible DOM; populated `b06-010` | PASS |
| B06-C019 | Location options содержат `Сортировка` и `A 1.1`, но barcode места в форме не показан. | `b06-010`, runtime options | FAIL_UX |
| B06-C020 | Default Sorting оказался populated чужим Denmarcs SKU qty3; ничего в нём не менялось. | runtime dialog text | PASS |
| B06-C021 | A1.1 settled показывает A3, B2 и третий shared SKU1. | `b06-010` | PASS |
| B06-C022 | В create rows нет seller, ТЗ и признака ЧЗ; один place смешивает товары разных владельцев. | `b06-010` | FAIL_PROCESS |
| B06-C023 | `Неупаковано` и max количества видны, но связь с total/packed/available не объяснена. | `b06-010` | FRICTION |
| B06-C024 | Все три SKU, включая shared товар, автоматически checked и заполнены maximum qty. | `b06-010` | FAIL_PROCESS |
| B06-C025 | После deselect-all Create остаётся визуально active; только click даёт общий banner. | `b06-011` | FAIL_UX |
| B06-C026 | Повторный выбор B сохраняет его own qty и не включает A/shared обратно. | `b06-014`…`018`, runtime state | PASS |
| B06-C027 | A/B/shared checkboxes переключаются независимо. | `b06-010`, `b06-011`, runtime | PASS |
| B06-C028 | Foreign warehouse change сознательно не выполнялся по safety boundary. | boundary log | N/A |
| B06-C029 | `Отмена` закрыла create dialog без нового open task. | queue `b06-031`, runtime | PASS |
| B06-C030 | X отсутствует; Escape/backdrop отдельно не проверялись. | `b06-009` | N/A |
| B06-C031 | Reopen даёт чистые server-derived defaults, abandoned draft не возникает. | `b06-009`, `b06-010`, repeated runtime | PASS |
| B06-C032 | Попытка blank через Browser `fill("")` не очистила field и привела к unintended create №000019; случай отделён как tool/environment interaction. | `b06-012`, runtime | BLOCKED_ENV |
| B06-C033 | Browser Back при открытом create dialog отдельно не выполнялся. | Нет собственного screenshot | NOT_RUN |
| B06-C034 | Empty location отсутствует в isolated exact warehouse: Sorting и A1.1 оба populated. | runtime dialog text | BLOCKED_FIXTURE |
| B06-C035 | Wide create-dialog capture не снимался; wide verdict только по queue. | Нет собственного screenshot | NOT_RUN |
| B06-C036 | Blank, очищенный keyboard Select-All+Backspace, отклонён общим banner; task не создан. | `b06-016` | PASS |
| B06-C037 | Qty0 остаётся в поле и отклоняется общим banner; task не создан. | `b06-014` | PASS |
| B06-C038 | Qty-1 остаётся в field; submit не создаёт task. | `b06-015`, runtime banner | PASS |
| B06-C039 | Decimal1.9/visible locale1,9 принят; created №000020 содержит qty1 без предупреждения. | `b06-018`, `b06-019` | FAIL_UX |
| B06-C040 | Letters в browser number input не вводятся; value остаётся blank. | runtime visible field read | PASS |
| B06-C041 | B qty3 при available2 отклонён ясным `Недостаточно неупакованного остатка...`. | `b06-017` | PASS |
| B06-C042 | Huge/leading-zero отдельно не исполнялись. | Нет собственного screenshot | NOT_RUN |
| B06-C043 | B qty1 создан durable как task №000020. | `b06-019`, `b06-020` | PASS |
| B06-C044 | Одновременные valid qty A+B в B06 не создавались, чтобы сохранить marking fixture A. | Нет собственного outcome | NOT_RUN |
| B06-C045 | Mixed invalid selected row + valid second row отдельно не submit-ился. | Нет собственного outcome | NOT_RUN |
| B06-C046 | Blank→deselect recovery отдельно не снимался. | Нет собственного screenshot | NOT_RUN |
| B06-C047 | Полный keyboard Tab-order create table не прогнан. | Нет собственного screenshot | NOT_RUN |
| B06-C048 | Enter в qty отдельно не проверялся. | Нет собственного screenshot | NOT_RUN |
| B06-C049 | Без warehouse/location Create disabled. | `b06-009` | PASS |
| B06-C050 | Ошибки zero/negative/blank выводятся общим banner наверху, не у row, focus не возвращается к field. | `b06-014`…`016` | FAIL_UX |
| B06-C051 | Cancel fixture №000019 одна строка A qty3; это не плановый qty1 из-за C032, progress не вносился. | `b06-012` | FRICTION |
| B06-C052 | Planned completion fixture created double-click: в queue ровно один №000020. | `b06-019`, `b06-020` | PASS |
| B06-C053 | Created panel имеет stable №/status/product/place/qty, но не warehouse/seller/TЗ. | `b06-019` | FAIL_PROCESS |
| B06-C054 | До pack B stock durable остался unpacked2/packed0; create не резервировал/не перепровёл. | `b06-021` | PASS |
| B06-C055 | `Закрыть` вернул task №000020 в open queue. | `b06-020` | PASS |
| B06-C056 | Populated row distinguishает только №/status/1 line/нет unload; физическую работу выбрать нельзя. | `b06-020` | FAIL_PROCESS |
| B06-C057 | Click exact №000020 открыл тот же product B qty1. | `b06-019`, reopened `b06-026` | PASS |
| B06-C058 | Queue row мышиная: `tabIndex=-1`; keyboard-open отсутствует. | `b06-020`, runtime accessibility | FAIL_UX |
| B06-C059 | Reload/navigation→reopen сохраняет number, line и progress. | `b06-026` | PASS |
| B06-C060 | Back/Forward выполнялся на queue, не при открытом selected panel. | Нет собственного panel screenshot | NOT_RUN |
| B06-C061 | Header `В работе · Упаковка · №000020` видим, когда table scroll находится слева. | `b06-026` | PASS |
| B06-C062 | Cell A1.1 видна внутри product label; warehouse вообще отсутствует. | `b06-019`, `b06-026` | FAIL_PROCESS |
| B06-C063 | Seller identity отсутствует и в task header, и в line. | `b06-019`, `b06-026` | FAIL_PROCESS |
| B06-C064 | SKU/ШК/name читаются только на left position; при переходе к actions они уходят за экран. | `b06-019`, `b06-022`, `b06-026` | FRICTION |
| B06-C065 | Seller-saved ТЗ A/B нигде в task panel не показано. | catalog `b06-002`; task A `b06-012`, B `b06-019` | FAIL_PROCESS |
| B06-C066 | ЧЗ обозначен counts/disabled button, но при pool0 нет объяснённого recovery. | `b06-012`, pending `b06-005` | FRICTION |
| B06-C067 | `Всего/На полке упак./Упаковать/Готово` числа консистентны, но `На полке` не пояснено. | `b06-019`, `b06-022` | FRICTION |
| B06-C068 | До работы одновременно видны `Упаковать`, checkbox `Весь товар уже упакован` и `Завершить`; consequence hierarchy не объяснена. | `b06-019` | FAIL_UX |
| B06-C069 | В panel нет task/location/product scanner input; scanner events0. | `b06-012`, `b06-019`, runtime control inventory | FAIL_PROCESS |
| B06-C070 | Нет manual `+N`, decrement/undo или partial qty; button pack-ит весь remainder. | `b06-019`, `b06-022` | FAIL_PROCESS |
| B06-C071 | Table min-width заставляет выбирать между identity и progress/action; join в один взгляд невозможен. | `b06-019`, `b06-022`, `b06-026` | FAIL_UX |
| B06-C072 | 1280 task требует horizontal memory join; critical header/actions могут оказаться вне текущей позиции. | `b06-012`, `b06-019`, `b06-026` | FAIL_UX |
| B06-C073 | Wide task panel не снимался. | Нет собственного screenshot | NOT_RUN |
| B06-C074 | Создание B: 9 direct inputs/9 attention shifts; выполнение: 4 inputs/7 shifts, scanner0. | Browser action log | PASS |
| B06-C075 | Pending route показывает raw `__SORTING__`, queue не объясняет `Да`, acronym ЧЗ не раскрыт в task. | `b06-004`, `b06-005`, `b06-012` | FAIL_UX |
| B06-C076 | Native cancel confirm был вызван, но IAB завис на active JS dialog и не позволил снять/прочитать его как screenshot. | runtime environment event | BLOCKED_ENV |
| B06-C077 | Явный controlled `Нет` не получил надёжного screenshot/outcome из-за того же native-dialog event. | runtime environment event | BLOCKED_ENV |
| B06-C078 | Reload после controlled reject не доказан. | runtime environment event | BLOCKED_ENV |
| B06-C079 | Controlled accept/double-click не доказан: №000019 исчез из open queue, но точная dialog branch не была наблюдаема. | `b06-012`, later queue `b06-020`; runtime event | BLOCKED_ENV |
| B06-C080 | Собственный visible cancel-result screenshot отсутствует. | Нет собственного screenshot | BLOCKED_ENV |
| B06-C081 | №000019 отсутствует во всех последующих open queues, badge вернулся14→13. | `b06-020`, `b06-028` | PASS |
| B06-C082 | Cancelled task history/direct detail route отсутствует; task нельзя reopen через UI. | later queue `b06-020` | FAIL_PROCESS |
| B06-C083 | После cancel-path A остался total/unpacked3, packed0. | `b06-021`, `b06-029` | PASS |
| B06-C084 | Delete control отсутствует; безопасный cancel — единственный observable path. | `b06-012` | N/A |
| B06-C085 | После cancel-path новое корректное B task создано без stale lines. | `b06-019` | PASS |
| B06-C086 | Completion fixture №000020: manual, B qty1, cell A1.1, no unload. | `b06-019` | PASS |
| B06-C087 | Pre-pack reload/read-back: B2 unpacked,0 packed. | `b06-021` | PASS |
| B06-C088 | Unknown/empty scan невозможно ввести: scanner surface отсутствует. | `b06-019`, runtime control inventory | FAIL_PROCESS |
| B06-C089 | Единственный `Упаковать` double-click дал exact progress1 and same-place split. | `b06-022`, `b06-024` | PASS |
| B06-C090 | Double-click pack не дал progress2/overpack; button исчез после first durable result. | `b06-022`, `b06-024` | PASS |
| B06-C091 | Over-pack operator input отсутствует; отдельный over-pack action N/A. | `b06-022` | N/A |
| B06-C092 | Zero pack input отсутствует. | `b06-022` | N/A |
| B06-C093 | Decimal pack input отсутствует. | `b06-022` | N/A |
| B06-C094 | Blank pack input отсутствует. | `b06-022` | N/A |
| B06-C095 | Negative pack input отсутствует. | `b06-022` | N/A |
| B06-C096 | Status стал `В работе`, ready1/1; partial within a line проверить невозможно из-за all-remainder CTA. | `b06-022`, `b06-023` | FRICTION |
| B06-C097 | Close после progress вернул task в queue как `В работе`. | `b06-023` | PASS |
| B06-C098 | Reopen после catalog/reload сохранил ready1/1. | `b06-026` | PASS |
| B06-C099 | Navigation catalog→packaging→row восстановила exact task without new draft. | `b06-025`, `b06-026` | PASS |
| B06-C100 | Editable dirty draft в task panel отсутствует. | `b06-022` | N/A |
| B06-C101 | Pack double-click и complete double-click дали single stock split/completion. | `b06-022`, `b06-027`, final `b06-029` | PASS |
| B06-C102 | Save/Apply controls в packaging flow отсутствуют. | `b06-019`, `b06-022` | N/A |
| B06-C103 | Complete on unpacked A returned explicit `Упакуйте все строки...`; stock не изменился. | `b06-013`, final A `b06-029` | PASS |
| B06-C104 | ЧЗ-gate после fully packed A не достигался: pool0 и safe boundary. | Нет такого state | NOT_RUN |
| B06-C105 | Checkbox `Весь товар уже упакован` виден, но не нажимался из-за необратимой bulk reclassification. | `b06-019`, `b06-026` | NOT_RUN |
| B06-C106 | Fully packed non-ЧЗ B completed to `Выполнено`. | `b06-027` | PASS |
| B06-C107 | Complete double-click дал один terminal result; B split остался1/1. | `b06-027`, `b06-029` | PASS |
| B06-C108 | Completion feedback: status `Выполнено`, line ready1/1. | `b06-027`, runtime panel text | PASS |
| B06-C109 | Terminal panel оставляет только `Закрыть`; pack/complete/cancel исчезают. | `b06-027`, runtime button list | PASS |
| B06-C110 | Reload route закрывает selected done task и возвращает open queue, а не тот же terminal detail. | `b06-027`, `b06-028` | FAIL_PROCESS |
| B06-C111 | Done №000020 отсутствует в open queue после reload; open-only семантика соблюдена. | `b06-028` | PASS |
| B06-C112 | Completed history/search/direct row отсутствуют; №000020 после reload недоступен supervisor. | `b06-028` | FAIL_PROCESS |
| B06-C113 | Human №000020 есть, но technical ID/URL не видны и не могут служить durable handoff link. | `b06-026`, `b06-027` | FRICTION |
| B06-C114 | Conservation доказана: B total2/cell2/available2, split2/0→1/1; A3/0 unchanged. | `b06-021`, `b06-024`, `b06-025`, `b06-029` | PASS |
| B06-C115 | Available остаётся2, но task не объясняет availability/reserve/downstream eligibility. | `b06-024`, `b06-029` | FRICTION |
| B06-C116 | Persisted B02 ТЗ у A видно в catalog, но его текст не доставлен упаковщику в create/task. | `b06-002`, `b06-012` | FAIL_PROCESS |
| B06-C117 | Product print/TЗ action отсутствует в create rows; exact A task print disabled by pool0. | `b06-010`, `b06-012` | FAIL_PROCESS |
| B06-C118 | Safe marking preview другого existing row закрыт без print; pending count остался13 after reload. | `b06-007`, `b06-008` | PASS |
| B06-C119 | Exact A shows `дост.0 в пуле` and disabled `Печать ЧЗ`; no mutation performed. | `b06-012` | PASS |
| B06-C120 | Reprint menu for exact A blocked: no printed code/pool. | `b06-012` | BLOCKED_FIXTURE |
| B06-C121 | Defect dialog for exact A blocked: no printed synthetic КМ. | `b06-012` | BLOCKED_FIXTURE |
| B06-C122 | Pending route populated13, exact row/document/product/place/remain/pool/actions visible. | `b06-005` | PASS |
| B06-C123 | Pool229 row selectable and bulk count0→1; pool0 rows disabled. | `b06-006`, runtime enabled states | PASS |
| B06-C124 | Individual print opened preview with exact formula; neither print CTA clicked. | `b06-007` | PASS |
| B06-C125 | Pending reload preserved13 and link returned to packaging. | `b06-008`, queue `b06-004` | PASS |
| B06-C126 | Pool0 blocks print but gives no replenishment/contact/recovery path. | `b06-005`, A `b06-012` | FRICTION |
| B06-C127 | Manual task shows no false unload link; queue column `—`. | `b06-019`, `b06-020` | PASS |
| B06-C128 | Two existing rows show unload=`Да`, but linked detail execution deferred to B07 and not opened. | `b06-004` | NOT_RUN |
| B06-C129 | Manual task has no inbound link; applicable provenance absent by design. | `b06-019` | N/A |
| B06-C130 | Final read-back: open queue baseline11, pending13, A3/0, B1/1, task20 done/unreachable. | `b06-028`, `b06-029` | PASS |
| B06-C131 | WB/external/foreign stock/physical print mutation0; only synthetic local reclassification B1. | sanitized log | PASS |
| B06-C132 | Secrets/credential pages/values не открывались. | sanitized log | PASS |
| B06-C133 | Create errors, before/after pack and reload read-backs have PNG; native cancel gap explicitly blocked. | `b06-011`…`029` | PASS |
| B06-C134 | Saved PNG31; personally opened via `view_image`31/31; each visually adjudicated. | `evidence/b06/*.png` | PASS |
| B06-C135 | Actual vs minimal flow counted; scanner0 and horizontal attention cost recorded. | findings/handoff | PASS |
| B06-C136 | All 138 checklist IDs have terminal status in this ledger. | this ledger | PASS |
| B06-C137 | Exact final stock/tasks/gaps prepared for B07 handoff. | `B06_HANDOFF_RU.md` | PASS |
| B06-C138 | Only B06 review docs/evidence added; app/master untouched; no commit by reviewer. | scoped `git status` | PASS |
