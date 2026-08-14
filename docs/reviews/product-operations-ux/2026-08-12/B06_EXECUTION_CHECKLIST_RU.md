# Батч 06. Execution checklist FF-упаковки

## Статус до Browser-прогона

Чек-лист зафиксирован до первого клика в staging. Все пункты стартуют как `NOT_RUN`; после прогона каждый ID получает конечный verdict в `B06_SCREEN_ACTION_LEDGER_RU.md`. Действия с WB, реальными КМ, секретами, чужими tenants и необратимой отменой задания с прогрессом запрещены.

## A. Сессия, baseline и settled queue

| ID | Экран / действие | Проверяемый результат | До прогона |
|---|---|---|---|
| B06-C001 | Подключить именно in-app Browser к Railway staging | Existing FF session или честный auth blocker; другой browser не используется | NOT_RUN |
| B06-C002 | Зафиксировать runtime 1280×720 DPR1 | CSS viewport и screenshot dimensions измерены | NOT_RUN |
| B06-C003 | `/app/ff/products`, exact seller A/B | A3/B2 и Sorting/cells/available baseline прочитаны глазами | NOT_RUN |
| B06-C004 | Baseline packed/unpacked split | Split виден в UI либо явный gap, без вывода из total | NOT_RUN |
| B06-C005 | `/app/catalog`, exact warehouse/cell | FBS WB 1155120 и A 1.1 подтверждены; foreign state не меняется | NOT_RUN |
| B06-C006 | Nav `Упаковка` | Active nav, title/description и рабочая поверхность | NOT_RUN |
| B06-C007 | Queue immediate state | Loading не выдан за empty/populated truth | NOT_RUN |
| B06-C008 | Queue settled empty/populated | Exact visible rows/count; empty доказывает только empty | NOT_RUN |
| B06-C009 | Queue columns and task identity | Номер/status/lines/link enough to choose exact physical job | NOT_RUN |
| B06-C010 | Pending-marking badge/link baseline | Count and meaning visible; no inference from badge absence | NOT_RUN |
| B06-C011 | Queue keyboard Tab/Enter | Row and primary CTA reachable without mouse | NOT_RUN |
| B06-C012 | Queue reload | Settled state durable, no false empty or duplicate | NOT_RUN |
| B06-C013 | Browser back/forward to queue | Route/context restored | NOT_RUN |
| B06-C014 | Queue 1280 fold/scroll | Primary actions and row identity visible without hidden critical fields | NOT_RUN |
| B06-C015 | Queue wide measured runtime | Wide layout only if exact metrics; export limitation recorded | NOT_RUN |

## B. Create dialog, location and empty/populated states

| ID | Экран / действие | Проверяемый результат | До прогона |
|---|---|---|---|
| B06-C016 | Open `Создать задание` | Dialog visible, no task created yet | NOT_RUN |
| B06-C017 | Immediate dialog screenshot | Warehouse/location/product/CTA hierarchy understandable | NOT_RUN |
| B06-C018 | Warehouse default/options | Exact warehouse distinguishable; foreign warehouse not selected/mutated | NOT_RUN |
| B06-C019 | Location default/options | Sorting/system location explained; A 1.1 and barcode identity sufficient | NOT_RUN |
| B06-C020 | Select Sorting | Honest empty state because Sorting A/B=0; no hidden mutation | NOT_RUN |
| B06-C021 | Select exact A 1.1 | Populated A/B rows appear from exact place | NOT_RUN |
| B06-C022 | Product identity on 1280 | Photo/name/SKU/ШК/seller/TЗ/ЧЗ are sufficient before qty decision | NOT_RUN |
| B06-C023 | Available `Неупаковано` semantics | Difference from total/available/packed explained | NOT_RUN |
| B06-C024 | Default selected rows | Auto-selection is obvious and does not accidentally include all | NOT_RUN |
| B06-C025 | Deselect all rows | Create blocked with exact reason; no task | NOT_RUN |
| B06-C026 | Reselect one row | Correct row/qty recovered | NOT_RUN |
| B06-C027 | Toggle second row | Independent selection, no accidental quantity reset | NOT_RUN |
| B06-C028 | Change warehouse then return | Place/product context resets predictably | NOT_RUN |
| B06-C029 | Dialog close via `Отмена` | No task/reservation; queue unchanged | NOT_RUN |
| B06-C030 | Dialog close via X/Escape/backdrop if available | No task/reservation; no silent dirty loss or exact N/A reason | NOT_RUN |
| B06-C031 | Reopen after cancel | Clean defaults; no abandoned draft/task | NOT_RUN |
| B06-C032 | Browser reload while dialog open | No hidden task; recovery/context outcome visible | NOT_RUN |
| B06-C033 | Browser Back while dialog open | Dialog/route recovery and no task mutation | NOT_RUN |
| B06-C034 | Exact location empty state after stock change if reachable | Empty message is settled and specific | NOT_RUN |
| B06-C035 | Create dialog wide measured runtime | Critical row/actions visible; only exact metric claimed | NOT_RUN |

## C. Quantity, selection and input recovery

| ID | Input/action | Проверяемый результат | До прогона |
|---|---|---|---|
| B06-C036 | Qty blank | Inline error, no silent row filter/task | NOT_RUN |
| B06-C037 | Qty `0` | Rejected with clear recovery | NOT_RUN |
| B06-C038 | Qty negative | Rejected; value not silently normalized | NOT_RUN |
| B06-C039 | Qty decimal `1.9` | Rejected as non-integer, not silently floored | NOT_RUN |
| B06-C040 | Qty text/paste | Rejected or browser guard with visible state | NOT_RUN |
| B06-C041 | Qty over available | Blocked with available amount named | NOT_RUN |
| B06-C042 | Qty huge/leading zero | Predictable validation/normalization | NOT_RUN |
| B06-C043 | Valid qty `1` | Stays on exact row and CTA becomes valid | NOT_RUN |
| B06-C044 | Second product valid qty | Independent value, no cross-row overwrite | NOT_RUN |
| B06-C045 | Invalid one row + valid second | No partial hidden task; exact bad row identified | NOT_RUN |
| B06-C046 | Blank selected row + deselect | Valid rows not lost; rule understandable | NOT_RUN |
| B06-C047 | Keyboard Tab order across rows | Focus follows visual order; no mouse requirement | NOT_RUN |
| B06-C048 | Enter in qty | Does not unexpectedly submit/duplicate | NOT_RUN |
| B06-C049 | Create with missing warehouse/location | Disabled reason or inline error | NOT_RUN |
| B06-C050 | Recovery from every invalid state | Error clears only after correction and focus remains useful | NOT_RUN |

## D. Safe cancel-task creation and queue populated

| ID | Action | Проверяемый результат | До прогона |
|---|---|---|---|
| B06-C051 | Prepare one-line cancel fixture qty1 | Exact product/location/qty visible before create | NOT_RUN |
| B06-C052 | Create double-click | Exactly one task or visible busy/idempotent guard | NOT_RUN |
| B06-C053 | Created panel identity | Stable number/status, warehouse/place/product/qty visible | NOT_RUN |
| B06-C054 | Task initial status/progress | Draft0 and no stock split mutation/reservation ambiguity | NOT_RUN |
| B06-C055 | Close new task | Returns to queue; same task appears once | NOT_RUN |
| B06-C056 | Populated queue row | Human task identity, status, progress/location/seller suitability | NOT_RUN |
| B06-C057 | Queue row click | Opens exact same task | NOT_RUN |
| B06-C058 | Queue row keyboard open | Enter/Space opens exact task or explicit FAIL_UX | NOT_RUN |
| B06-C059 | Reload/reopen created task | Same ID/number/lines/progress | NOT_RUN |
| B06-C060 | Back/forward around task panel | Context preserved or exact loss visible | NOT_RUN |

## E. Task card comprehension and operator ergonomics

| ID | Screen/action | Проверяемый result | До прогона |
|---|---|---|---|
| B06-C061 | Header/status/document number | Operator can call out exact task | NOT_RUN |
| B06-C062 | Warehouse and physical place | Exact warehouse/place visible without memory from create dialog | NOT_RUN |
| B06-C063 | Seller identity | Owner visible; cross-seller mistake protected | NOT_RUN |
| B06-C064 | Product identity | Name/SKU/ШК/photo readable at 1280 | NOT_RUN |
| B06-C065 | TЗ instruction | Full current TЗ always visible at work point or explicit gap | NOT_RUN |
| B06-C066 | ЧЗ requirement | Required/not required and next marking step unambiguous | NOT_RUN |
| B06-C067 | Quantity labels | `Всего/на полке/упаковать/готово` understandable without glossary | NOT_RUN |
| B06-C068 | Main CTA hierarchy | One obvious next physical action | NOT_RUN |
| B06-C069 | Scanner input inventory | Task/location/product scan controls present and focusable or FAIL_PROCESS | NOT_RUN |
| B06-C070 | Manual `+N`/correction inventory | Partial work and mistake correction possible or explicit gap | NOT_RUN |
| B06-C071 | Page/table horizontal scroll | Identity, qty and CTA can be joined without memory | NOT_RUN |
| B06-C072 | Task 1280 full settled view | Fold/scroll and hidden controls captured | NOT_RUN |
| B06-C073 | Task wide measured view | Only exact runtime/export metrics claimed | NOT_RUN |
| B06-C074 | Attention-shift count | Create and pack flows measured | NOT_RUN |
| B06-C075 | Low-literacy read-through | No raw enum/internal code/unexplained acronym as next step | NOT_RUN |

## F. Cancel flow and stock read-back

| ID | Action | Проверяемый result | До прогона |
|---|---|---|---|
| B06-C076 | Click `Отменить задание` | Warning names exact consequence | NOT_RUN |
| B06-C077 | Cancel warning `Нет` | Task remains draft and usable | NOT_RUN |
| B06-C078 | Reload after rejected cancel | Same task/progress | NOT_RUN |
| B06-C079 | Cancel warning `Да` double-click attempt | One transition to cancelled; no repeat mutation | NOT_RUN |
| B06-C080 | Cancel outcome | Clear status/next step, not silent close only | NOT_RUN |
| B06-C081 | Queue after cancel | Cancelled task absent from open queue | NOT_RUN |
| B06-C082 | Direct/reopen cancelled task if UI permits | Terminal read-only and status durable | NOT_RUN |
| B06-C083 | Stock split after cancel | Exact A/B unchanged from pre-task | NOT_RUN |
| B06-C084 | Cancelled task delete control | Available with protection or explicit N/A; no API invention | NOT_RUN |
| B06-C085 | Cancel recovery | User can create a new correct task without stale context | NOT_RUN |

## G. Completion-task, progress, invalid/repeat actions

| ID | Action | Проверяемый result | До прогона |
|---|---|---|---|
| B06-C086 | Create one-line non-ЧЗ task qty1 | Exact safe fixture and one durable task | NOT_RUN |
| B06-C087 | Pre-pack reload/read-back | Unpacked/packed unchanged before physical action | NOT_RUN |
| B06-C088 | Empty/unknown product scan | Error and recovery, or N/A because no scanner surface | NOT_RUN |
| B06-C089 | Valid product scan/manual pack one | Exact +1 progress and same-place split outcome | NOT_RUN |
| B06-C090 | Repeat/duplicate scan/click | One unit only or explicit duplicate semantics | NOT_RUN |
| B06-C091 | Over-pack attempt | Blocked before stock change or N/A if no input surface | NOT_RUN |
| B06-C092 | Zero pack | Rejected or N/A if no input surface | NOT_RUN |
| B06-C093 | Decimal pack | Rejected, not floored, or N/A if no input surface | NOT_RUN |
| B06-C094 | Blank pack | Rejected with focus recovery or N/A | NOT_RUN |
| B06-C095 | Negative pack | Rejected or N/A | NOT_RUN |
| B06-C096 | Partial progress status | `in_progress`, done/remaining and exact next step visible | NOT_RUN |
| B06-C097 | Close after progress | Same task persists; no lost/duplicated progress | NOT_RUN |
| B06-C098 | Reload/reopen after progress | Same number/qty/status durable | NOT_RUN |
| B06-C099 | Browser back/forward after progress | Recovery without hidden new task | NOT_RUN |
| B06-C100 | Dirty-input reload | Warning/recovery or N/A because no editable draft | NOT_RUN |
| B06-C101 | Concurrent/stale repeat approximation | Second click/read-back cannot overpack; no unsafe injected concurrency | NOT_RUN |
| B06-C102 | Apply/Save controls | Meaning and consequence tested or N/A if absent | NOT_RUN |

## H. Completion and terminal read-back

| ID | Action | Проверяемый result | До прогона |
|---|---|---|---|
| B06-C103 | Complete before all packed | Blocked with exact remaining or N/A if row already full | NOT_RUN |
| B06-C104 | Complete ЧЗ-incomplete task | Blocked with exact marking requirement; no external print | NOT_RUN |
| B06-C105 | `Весь товар уже упакован` checkbox | Meaning/consequence clear; unavailable for FBS if relevant | NOT_RUN |
| B06-C106 | Complete valid non-ЧЗ task | One deliberate transition to done | NOT_RUN |
| B06-C107 | Complete double-click | One completion/inventory movement only | NOT_RUN |
| B06-C108 | Completion feedback | Status, total, place and next step visible | NOT_RUN |
| B06-C109 | Terminal controls | Pack/confirm/cancel hidden/disabled; no accidental rework | NOT_RUN |
| B06-C110 | Terminal reload | Same done task/progress durable | NOT_RUN |
| B06-C111 | Queue after done | Done absent from open queue without false empty loading | NOT_RUN |
| B06-C112 | Direct/reopen done task | Read-only history reachable or explicit process gap | NOT_RUN |
| B06-C113 | Task/document final ID | Number/ID captured for B07 and supervisor | NOT_RUN |
| B06-C114 | Stock conservation | Total/place unchanged; unpacked↓1 packed↑1 | NOT_RUN |
| B06-C115 | Final available/reserved | Available and downstream eligibility explained/read back | NOT_RUN |

## I. TЗ, print, marking and pending queue

| ID | Action | Проверяемый result | До прогона |
|---|---|---|---|
| B06-C116 | A line/TЗ visibility from packaging context | Saved B02 instruction reaches FF operator | NOT_RUN |
| B06-C117 | Product print icon safe open | Visible preview/dialog, no physical print | NOT_RUN |
| B06-C118 | Print dialog close/cancel | No printed/reserved count mutation | NOT_RUN |
| B06-C119 | Marking CTA with no available КМ | Disabled or exact error; no secret/external action | NOT_RUN |
| B06-C120 | Marking CTA repeat/reprint menu | Available only after safe evidence; otherwise BLOCKED_FIXTURE/N/A | NOT_RUN |
| B06-C121 | Defect КМ dialog | Only with synthetic already-printed code; otherwise BLOCKED_FIXTURE | NOT_RUN |
| B06-C122 | Pending-marking route settled empty/populated | Exact count/rows; empty not used for populated verdict | NOT_RUN |
| B06-C123 | Pending row selection | Checkbox/bulk hierarchy and product/task identity | NOT_RUN |
| B06-C124 | Pending print CTA safe preview | No physical print or external mutation; cancel read-back | NOT_RUN |
| B06-C125 | Pending back/reload | Context/count durable | NOT_RUN |
| B06-C126 | Marking error recovery | Operator can return to task without losing pack progress | NOT_RUN |

## J. Final integration, safety and evidence gate

| ID | Check | Проверяемый result | До прогона |
|---|---|---|---|
| B06-C127 | Linked unload field on manual task | Clearly absent; no false MP linkage | NOT_RUN |
| B06-C128 | MP linked-task entry inventory | Visible linkage only if existing safe fixture; execution deferred B07 | NOT_RUN |
| B06-C129 | Inbound link/context | Visible or N/A for manual task; no invented provenance | NOT_RUN |
| B06-C130 | Stock/task/document read-back after all actions | Exact final A/B split, open tasks and numbers | NOT_RUN |
| B06-C131 | No WB/external/shared mutation | Boundary documented in sanitized log | NOT_RUN |
| B06-C132 | No secret/credential access | Boundary documented | NOT_RUN |
| B06-C133 | Screenshot before/after/reload coverage | Every executed mutation/error has evidence | NOT_RUN |
| B06-C134 | Personal visual adjudication | Every saved PNG opened and given a visible verdict | NOT_RUN |
| B06-C135 | Input and attention counts | Actual and minimal flows compared without redesign | NOT_RUN |
| B06-C136 | Every ID final status | PASS/FRICTION/FAIL/BLOCKED/NOT_RUN/N/A, none omitted | NOT_RUN |
| B06-C137 | Handoff to B07 | Exact final stock/tasks/gaps and linked-process blockers | NOT_RUN |
| B06-C138 | Git boundary | Only B06 review docs/evidence, no app/master edits, no commit | NOT_RUN |
