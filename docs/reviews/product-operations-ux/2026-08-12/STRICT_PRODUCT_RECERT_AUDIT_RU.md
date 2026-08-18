# Strict Product Recert Audit — WMS iteration 2026-08-12

Дата фиксации: 2026-08-13 22:00 MSK.

Git-root:

```text
/Users/deniscivkunov/Projects/WMS/.worktrees/product-operations-ux-20260812
```

Ветка: `iteration/wms-product-ux-features-20260812`.

HEAD на момент старта проверки: `ea08284021818233516a19422aee5f905c55d295`.

Этот документ фиксирует проверку старых `BROWSER_PRODUCT_QA_PASSED` после
уточнения роли Product / UX Agent в
`HANDOFF_TO_NEW_CHAT_STRICT_WMS_GATE_RU.md`.

## Текущий статус после strict final rerun и stage verification 2026-08-14

Оперативный итог на 2026-08-14: все active release features `F01-F19`, `F22`,
`F23` имеют strict live Product evidence, повторный Final Integration Review
прошёл, финальный live Product Browser Regression rerun прошёл, stage развернут
и проверен из application deploy commit
`595bf93404794ade562b7f9fc4d6c1bdc09267c6`.

Новый финальный источник истины:
`docs/reviews/product-operations-ux/2026-08-12/evidence/final-browser-regression-rerun-live-strict/FINAL_BROWSER_REGRESSION_RERUN_LIVE_STRICT_RU.md`

Verdict: `FINAL_BROWSER_REGRESSION_PASSED`.

Хронология blockers:

- старый full regression
  `evidence/final-browser-regression-live-strict/FINAL_BROWSER_REGRESSION_LIVE_STRICT_RU.md`
  справедливо упал на seller catalog `/seller/products`;
- catalog прошёл rework, code review и live Product Browser QA;
- новый catalog group rerun прошёл live browser;
- inbound group затем упал на stale discrepancy modal после successful
  completion;
- inbound stale-modal fix прошёл code review, focused browser e2e и новый live
  Product Browser QA;
- staff/routes и packaging/delete группы прошли live browser rerun.

Stage proof:
`docs/reviews/product-operations-ux/2026-08-12/evidence/stage-deploy-verification-595bf93/STAGE_DEPLOY_VERIFICATION_595BF93_RU.md`
с verdict `STAGE_DEPLOY_VERIFIED`.

Проверено: `origin/staging` указывает на итоговый SHA, Railway deployments
`WMS`/`web` имеют status `SUCCESS`, public smoke passed, live Chromium
`headless=false` browser smoke of the staging login shell passed.

## Главный вывод

Старую матрицу нельзя принимать как release truth. По многим фичам есть
локальные headed Playwright / browser-runner evidence, screenshots и JSON, но
это не всегда доказывает новый строгий product pass: профессиональный Product /
UX Agent должен сам пройти живой процесс в браузере и зафиксировать экспертный
складской verdict по процессу и каждому визуальному элементу.

Если evidence не доказывает именно такой Product / UX pass, фича получает
`STRICT_PRODUCT_RECERT_REQUIRED` и не считается закрытой для release, даже если
в matrix стоит `BROWSER_PRODUCT_QA_PASSED`.

Абсолютное уточнение после user stop 2026-08-13: Product / UX Agent никогда не
может закрыть фичу без собственного live browser прохода. Если агент только
читает старые evidence, screenshots, JSON, Playwright reports, code review или
API/unit/build результаты, это не approval. Если live browser невозможен,
вердикт только `PRODUCT_BROWSER_BLOCKED`; если процесс/UI плохой, только
`PRODUCT_REWORK_REQUIRED`.

## Read-only evidence audit

Аудиторы читали документы и evidence без правок кода, без commit, без staging,
без production и без secret panels.

### F01-F07

Read-only auditor: `019ffc79-2990-73f1-b633-2b91a0909b1d`.

| Feature | Evidence verdict | Release decision under strict Product Agent rule | Причина |
|---|---|---|---|
| F01 | `AUTOMATED_BROWSER_ONLY` | `STRICT_PRODUCT_RECERT_REQUIRED` | Есть headed Playwright pass и UX wording, но нет независимой product/WMS expert-критики; есть необъяснённый screenshot `FAIL-F01-F04-F06-INBOUND-LIVE`. |
| F02 | `AUTOMATED_BROWSER_ONLY` | `STRICT_PRODUCT_RECERT_REQUIRED` | Есть хороший headed browser proof по габаритам, save/readback и 1280px, но это `npx playwright --headed`, не отдельный Product Agent pass. |
| F03 | `AUTOMATED_BROWSER_ONLY` | `STRICT_PRODUCT_RECERT_REQUIRED` | Автоматизированное покрытие сильное: недостача, излишек, same-seller extra item, foreign barcode error; отдельной expert product-приёмки нет. |
| F04 | `AUTOMATED_BROWSER_ONLY` | `STRICT_PRODUCT_RECERT_REQUIRED` | Evidence в основном JSON/screenshots/headed logs; нет product verdict, что emergency manual path остаётся вторичным и понятным складу. |
| F05 | `AUTOMATED_BROWSER_ONLY` | `STRICT_PRODUCT_RECERT_REQUIRED` | Был failed по geometry, потом headed after-geometry pass; нет независимого Product Agent verdict по той же карточке. |
| F06 | `AUTOMATED_BROWSER_ONLY` | `STRICT_PRODUCT_RECERT_REQUIRED` | Print fact/discrepancy проверены автоматикой; нет product/logistics critique печатного процесса, и есть общий `FAIL-F01-F04-F06` screenshot. |
| F07 | `FAILED_OR_BLOCKED` | `PRODUCT_REWORK_REQUIRED` | Dedicated F07 browser product artifact не найден; B06/handoff возвращают F07/F17/F19 в P0 packaging rework. |

### F08-F14

Read-only auditor: `019ffc79-4639-7b62-b3ba-24e23b944ab4`.

| Feature | Evidence verdict | Release decision under strict Product Agent rule | Причина |
|---|---|---|---|
| F08 | `STRICT_PRODUCT_BROWSER_PROVED` by auditor | `STRICT_PRODUCT_RECERT_RUNNING` | Evidence сильное: final F08 browser QA claims live Chromium, CRUD directions, overage, delete confirm, 1280px geometry. Для исключения спора всё равно запущена новая strict recert. |
| F09 | `STRICT_PRODUCT_BROWSER_PROVED` by auditor | `STRICT_PRODUCT_RECERT_RUNNING` | Evidence сильное: Browser tab API, MP/FBO draft, picker, error 401, planned 400, read-back, no raw codes. Для нового unified Product Agent rule запущена recert. |
| F10 | `STRICT_PRODUCT_BROWSER_PROVED` by auditor | `STRICT_PRODUCT_RECERT_RUNNING` | Evidence сильное: UI + WB emulator, positive readback 193, fail-closed multi-binding. Для нового unified Product Agent rule запущена recert. |
| F11 | `AUTOMATED_BROWSER_ONLY` | `STRICT_PRODUCT_RECERT_REQUIRED` | Только machine JSON/screenshots от headed Chromium script; нет markdown product verdict по FF catalog. |
| F12 | `MISSING_OR_CONTRADICTORY` | `PRODUCT_REWORK_REQUIRED` | Direct route/access проверены, но Final Integration Review нашёл menu discoverability conflict: route разрешён, nav item может быть скрыт. |
| F13 | `AUTOMATED_BROWSER_ONLY` | `STRICT_PRODUCT_RECERT_REQUIRED` | Первый evidence был `FAILED_PICKER_LEAK`, rerun JSON показывает pass, но нет отдельного human product/logistics browser verdict. |
| F14 | `MISSING_OR_CONTRADICTORY` | `PRODUCT_REWORK_REQUIRED` | QA report заявляет staff nav, но supporting e2e в основном ходит direct `page.goto`; handoff возвращает F12/F14 в R02. |

### F15-F19, F22, F23

Read-only auditor: `019ffc79-62ba-78c1-a4a1-e12b72472124`.

| Feature | Evidence verdict | Release decision under strict Product Agent rule | Причина |
|---|---|---|---|
| F15 | `MISSING_OR_CONTRADICTORY` | `STRICT_PRODUCT_RECERT_REQUIRED` | Есть failed/continued evidence и только частичный resumed pass; цельный product browser pass по delete-only-drafts не доказан. |
| F16 | `AUTOMATED_BROWSER_ONLY` | `STRICT_PRODUCT_RECERT_REQUIRED` | JSON/headed evidence доказывает русский заголовок `Артикул WB`, но не строгий product click-through. |
| F17 | `MISSING_OR_CONTRADICTORY` | `PRODUCT_REWORK_REQUIRED` | Print sheet evidence есть, но B06/handoff возвращают F17 в P0 packaging rework: ТЗ не доставлено, scanner/unit-flow и process не готовы. |
| F18 | `AUTOMATED_BROWSER_ONLY` | `STRICT_PRODUCT_RECERT_REQUIRED` | Есть final headed pass, но также есть failed и rerun failed из-за geometry/overflow; нужна новая product recert с явным разбором. |
| F19 | `MISSING_OR_CONTRADICTORY` | `PRODUCT_REWORK_REQUIRED` | Matrix says passed, detail card says `browser_qa_in_progress`; final QA — browser-runner, не строгий Product Agent pass; F19 также входит в P0 packaging rework. |
| F22 | `AUTOMATED_BROWSER_ONLY` | `STRICT_PRODUCT_RECERT_REQUIRED` | After-read-model proof сильный: `20 -> 20`, `WB: 7 шт`, no raw codes; но это runner/UI+emulator, нужен строгий Product Agent verdict. |
| F23 | `AUTOMATED_BROWSER_ONLY` | `STRICT_PRODUCT_RECERT_REQUIRED` | QA report пишет “прошёл руками”, но evidence runner программно кликает Chromium; нужен независимый product/WMS verdict. |

## Product recert agents started

Новые strict Product / UX passes запущены без разработки кода:

| Agent | Zone | Features | Evidence directory |
|---|---|---|---|
| `019ffc7e-5282-7e21-af0b-842b3ff34845` | inbound / reception / returns | F01-F06, F18, F19 | `evidence/strict-product-recert-inbound/` |
| `019ffc7f-005a-7e21-95b4-ba198bf00cec` | catalog / stocks / seller and FF products | F08, F09, F10, F11, F16, F22, F23 | shutdown after user stop; does not count as final recert |
| `019ffc92-9f80-7a72-a9e6-fa381ab80fec` | catalog / stocks / seller and FF products live-browser-only rerun | F08, F09, F10, F11, F16, F22, F23 | `evidence/strict-product-recert-catalog-stock-live/` |
| `019ffc7f-4173-7953-9a45-2576319fc7af` | MP/FBO packaging, staff nav/access, delete/access scope | F07, F12, F13, F14, F15, F17 | `evidence/strict-product-recert-ops-access/` |

Если любой strict Product / UX Agent вернёт `PRODUCT_REWORK_REQUIRED`, фича
возвращается на BA/UX или Atomic Dev по обычному WMS feature-gate циклу.

## Product recert results

### Inbound / reception / returns

Agent: `019ffc7e-5282-7e21-af0b-842b3ff34845`.

Evidence directory:
`docs/reviews/product-operations-ux/2026-08-12/evidence/strict-product-recert-inbound/`.

| Feature | Strict Product verdict | Причина |
|---|---|---|
| F01 | `STRICT_PRODUCT_BROWSER_APPROVED` | В FF-приёмке нет вкладки/шага `Упаковка`; процесс остаётся `скан -> факт -> расхождение -> завершить`, печать ШК товара не превращает приёмку в упаковку. |
| F02 | `STRICT_PRODUCT_BROWSER_APPROVED` | Кнопка габаритов в строке оправдана складской работой; размеры и объём сохраняются и читаются обратно. |
| F03 | `STRICT_PRODUCT_BROWSER_APPROVED` | Same-seller товар вне плана создаёт `План 0 / Факт 1` и `Добавлено ФФ`; чужой seller блокируется человеческой ошибкой. |
| F04 | `STRICT_PRODUCT_BROWSER_APPROVED` | Manual plus остаётся аварийным вторичным путём, не главным CTA; созданный товар сразу попадает в факт как расхождение. |
| F05 | `PRODUCT_REWORK_REQUIRED` | Seller fact-card перегружена: 5 summary-блоков и 9 колонок. Селлеру приходится читать таблицу как отчёт, а не быстро понять, что приехало не так. |
| F06 | `STRICT_PRODUCT_BROWSER_APPROVED` | Печать после проведения берёт факт и расхождение, без raw UUID/status/FBS-мусора. |
| F18 | `STRICT_PRODUCT_BROWSER_APPROVED` | `Возврат` выбирается до создания, остаётся в inbound route, FF видит возврат в той же очереди/карточке без отдельного return-экрана. |
| F19 | `STRICT_PRODUCT_BROWSER_APPROVED` | Switch виден только для возврата; обычная поставка его не показывает. Manual picker/create не печатают, scan WB barcode печатает, missing WB barcode fail-closed. |

Дополнительный env-риск: первый 9-сценарный прогон дал `8 passed`, затем упал
по `ENOSPC` (`no space left on device`), после удаления только созданного этим
агентом heavy `test-results-inbound` F04 был rerun отдельно и прошёл. На момент
проверки `df -h .` показывал около `232Mi` свободного места, поэтому следующие
browser runs могут падать не из-за продукта, а из-за диска.

### Catalog / stocks / seller and FF products

Agent: `019ffc92-9f80-7a72-a9e6-fa381ab80fec`.

Evidence directory:
`docs/reviews/product-operations-ux/2026-08-12/evidence/strict-product-recert-catalog-stock-live/`.

Этот проход считается валидным strict Product recert: агент поднял локальный UI
и прошёл собственный live browser pass в Chromium `headless=false`. Старые
screenshots/JSON не использовались как замена verdict.

| Feature | Strict Product verdict | Причина |
|---|---|---|
| F08 | `STRICT_PRODUCT_BROWSER_APPROVED` | Directions/FBS-pool flow прошёл live: seller catalog, directions drawer, CRUD, overage, delete, FF distribution popover; no `Лимит`, raw codes or breaking 1280px layout. |
| F09 | `STRICT_PRODUCT_BROWSER_APPROVED` | FBO/MP flow показал free FBO availability, successful planning within available amount and human overage block. |
| F10 | `STRICT_PRODUCT_BROWSER_APPROVED` | FBS sync publishes FBS pool minus active FBS reservation with read-back; ambiguous multi-binding fails closed with human UI and no raw `ambiguous_warehouse_scope` as main text. |
| F11 | `STRICT_PRODUCT_BROWSER_APPROVED` | FF catalog remains simplified and scannable without internal-stage noise, extra chips/columns/buttons or 1280px breakage. |
| F16 | `STRICT_PRODUCT_BROWSER_APPROVED` | Visible marketplace identifier is human `Артикул WB`; raw `nmID`/technical label is not used as main UI wording. |
| F22 | `STRICT_PRODUCT_BROWSER_APPROVED` | Safe sync preserves WB amount when FBS pool is missing/unknown and shows human reason; positive nonzero read-back shows compact success, no `Лимит`/raw codes/unsafe zero. |
| F23 | `STRICT_PRODUCT_BROWSER_APPROVED` | Seller catalog cleanup uses selected-row bulk only, no global all-products dangerous action, no permanent `Лимит`, compact statuses, no chip chaos/black strip/overflow; F08/F22 remain understandable. |

Machine read-back: `strict-live-recert-result.json` recorded `checks=22`,
`error=null`, all seven verdicts `STRICT_PRODUCT_BROWSER_APPROVED`.

### Seller fact-card / print / returns

Agent: `019ffc9d-b7c1-7953-990b-823c43fb53ff`.

Evidence directory:
`docs/reviews/product-operations-ux/2026-08-12/evidence/strict-product-recert-live-f05-f06-f18-f19/`.

Этот проход считается валидным strict Product recert: агент прошёл новый live
Chromium flow по локальному UI и создал screenshots/HTML/read-back без тяжёлых
traces.

| Feature | Strict Product verdict | Причина |
|---|---|---|
| F05 | `PRODUCT_REWORK_REQUIRED` | Seller fact-card всё ещё выглядит как плотный отчёт, а не быстрая fact-card: 6 summary-блоков и 9 колонок (`Фото`, `Артикул`, `ШК`, `Артикул продавца`, `Артикул WB`, `Наименование`, `Заявлено`, `Факт`, `Расхождение`). Горизонтального scroll-развала нет, но селлер перегружен чтением. |
| F06 | `STRICT_PRODUCT_BROWSER_APPROVED` | Накладная по факту печатается из live UI и показывает факт/расхождения без raw UUID/status/FBS-мусора. |
| F18 | `STRICT_PRODUCT_BROWSER_APPROVED` | Возврат работает как вариант inbound: seller выбирает `Возврат`, FF видит его в той же очереди/карточке, без отдельной лишней return-воронки. |
| F19 | `STRICT_PRODUCT_BROWSER_APPROVED` | Return autoprint ограничен возвратом; ordinary inbound не показывает switch, manual picker/create не печатают, WB barcode scan печатает, missing WB barcode fail-closed. |

Follow-up started: F05 BA/UX rework agent `019ffca7-6003-7833-892c-8e035a2a7fc7`.

### MP/FBO packaging and print

Agent: `019ffc9d-b831-76f2-bc83-d7dbd19cbc4b`.

Evidence directory:
`docs/reviews/product-operations-ux/2026-08-12/evidence/strict-product-recert-live-f07-f17/`.

Этот проход считается валидным strict Product recert: агент поднял отдельный
локальный stack API `18107`, frontend `5177`, отдельную SQLite и прошёл live
Chromium flow.

| Feature | Strict Product verdict | Причина |
|---|---|---|
| F07 | `PRODUCT_REWORK_REQUIRED` | Packaging process небезопасен: create-dialog автоселектит все товары ячейки, seller не виден по строкам, mixed-seller task создаётся, task panel без scanner/unit input, seller-ТЗ не доставлено упаковщику, completed task после reload исчезает из очереди/истории. |
| F17 | `STRICT_PRODUCT_BROWSER_APPROVED` | На финальном шаге MP/FBO-отгрузки есть печать; с кнопки получен A4 HTML-лист с seller/date/type/number/FF warehouse/MP warehouse/product/barcode/qty/instructions/`Факт`. |

Follow-up started: R01/F07 BA/UX rework agent `019ffca7-6063-71a0-96c2-b069ea1f69e9`.

### Staff access / snapshot / delete

Agent: `019ffc9d-b988-78a3-bd3d-c4a6e5797e80`.

Evidence directory:
`docs/reviews/product-operations-ux/2026-08-12/evidence/strict-product-recert-live-f12-f15/`.

Этот проход считается валидным strict Product recert: агент поднял отдельный
локальный backend `127.0.0.1:18152`, frontend `127.0.0.1:5182`, SQLite и прошёл
live Chromium flow на viewport `1280x720`.

| Feature | Strict Product verdict | Причина |
|---|---|---|
| F12 | `PRODUCT_REWORK_REQUIRED` | Snapshot у FF admin работает и read-back сохраняет `total 10 / FBS 3 / reserve 2 / free FBO 5`, но staff с `inventory` может открыть `/app/ff/inventory` напрямую, а в меню у него нет пункта `Инвентаризация`. |
| F13 | `STRICT_PRODUCT_BROWSER_APPROVED` | Vitalik видит allowed shop, не видит forbidden shop; home/allowed product views and inbound picker do not leak forbidden SKU, including direct route. |
| F14 | `PRODUCT_REWORK_REQUIRED` | Staff rights UI частично годится, но menu/direct mismatch остался: shipments staff открывает `/app/ff/fbs` без пункта FBS в меню; catalog/cells staff открывает `/app/ff/inventory`, но меню не даёт явный inventory route. |
| F15 | `PRODUCT_REWORK_REQUIRED` | Seller side passes delete-only-drafts, but FF confirmed MP unload still shows line delete for non-draft status. |

Follow-up already started: R02/F12-F14 BA/UX rework agent `019ffca7-60cd-7730-8e1c-e4cd13ab97ab`; F15 BA/UX rework agent `019ffca7-623e-7511-aa88-7c721b813062`.

## Release gate state

До завершения returned rework и финальных gates:

- release остается `NOT_READY`;
- старые `BROWSER_PRODUCT_QA_PASSED` не являются достаточным proof;
- staging запрещён;
- production запрещён;
- code/UI руками оркестратора не правятся;
- scoped commit возможен только для gate/audit документов, без `git add .`.

## Evidence consolidation after strict live recert

Дата сверки: 2026-08-13.

Правило сверки: строка из старой feature matrix с `BROWSER_PRODUCT_QA_PASSED`
не закрывает фичу сама по себе. В итог ниже попали только новые strict live
Product / UX evidence или последующие BA/UX/Product rework artifacts. Если
фича вернулась на rework, старый browser pass не считается финальным закрытием.

Итог по active release scope: 21 фича (`F01-F19`, `F22`, `F23`). Строгое live
browser Product approval сейчас есть у всех 21 active release фич: `F01`,
`F02`, `F03`, `F04`, `F05`, `F06`, `F07`, `F08`, `F09`, `F10`, `F11`, `F12`,
`F13`, `F14`, `F15`, `F16`, `F17`, `F18`, `F19`, `F22`, `F23`. Следующий gate:
общий Final Integration Review, затем полный final live Product Browser
Regression по системе. Для active release-фич нет строки без strict recert
verdict вообще.

| Feature | Consolidated strict status | Evidence / next gate |
|---|---|---|
| F01 | `STRICT_PRODUCT_BROWSER_APPROVED` | Учтён отдельный live evidence `evidence/strict-product-recert-live-f01-f04/QA_RESULT_RU.md`; это не старый matrix pass. |
| F02 | `STRICT_PRODUCT_BROWSER_APPROVED` | Учтён `evidence/strict-product-recert-live-f01-f04/QA_RESULT_RU.md`. |
| F03 | `STRICT_PRODUCT_BROWSER_APPROVED` | Учтён `evidence/strict-product-recert-live-f01-f04/QA_RESULT_RU.md`. |
| F04 | `STRICT_PRODUCT_BROWSER_APPROVED` | Учтён `evidence/strict-product-recert-live-f01-f04/QA_RESULT_RU.md`. |
| F05 | `PRODUCT_BROWSER_APPROVED`; не release-ready | Post-rework code review passed, затем strict live browser rerun approved seller fact-card and seller shell reload/nav. Учтён `evidence/f05-product-browser-qa-rerun-live-strict/F05_PRODUCT_BROWSER_QA_RERUN_LIVE_STRICT_RU.md`; это закрывает F05 per-feature browser gate, но общий release всё ещё ждёт F07/F12/F14/F15 и final integration/browser regression. |
| F06 | `STRICT_PRODUCT_BROWSER_APPROVED` | Учтён `evidence/strict-product-recert-live-f05-f06-f18-f19/STRICT_PRODUCT_LIVE_REPORT_RU.md`. |
| F07 | `PRODUCT_BROWSER_APPROVED`; не release-ready | Post-rework code review passed, затем strict live Product Browser QA rerun approved packaging flow. Учтён `evidence/r01-packaging-product-browser-qa-rerun-live-strict/R01_PACKAGING_PRODUCT_BROWSER_QA_RERUN_LIVE_STRICT_RU.md`; общий release всё ещё ждёт R02/F12/F14 final QA and integration gates. |
| F08 | `STRICT_PRODUCT_BROWSER_APPROVED` | Учтён `evidence/strict-product-recert-catalog-stock-live/STRICT_LIVE_RECERT_REPORT_RU.md`. |
| F09 | `STRICT_PRODUCT_BROWSER_APPROVED` | Учтён `evidence/strict-product-recert-catalog-stock-live/STRICT_LIVE_RECERT_REPORT_RU.md`. |
| F10 | `STRICT_PRODUCT_BROWSER_APPROVED` | Учтён `evidence/strict-product-recert-catalog-stock-live/STRICT_LIVE_RECERT_REPORT_RU.md`. |
| F11 | `STRICT_PRODUCT_BROWSER_APPROVED` | Учтён `evidence/strict-product-recert-catalog-stock-live/STRICT_LIVE_RECERT_REPORT_RU.md`. |
| F12 | `PRODUCT_BROWSER_APPROVED`; не release-ready | R02 staff navigation/direct-route final strict live browser rerun approved: FF staff/admin `/seller/products` stays in FF shell with human denied, seller portal still works, role/sidebar/direct-route matrix passed. Учтён `evidence/r02-staff-nav-product-browser-qa-final-live-strict/R02_STAFF_NAV_PRODUCT_BROWSER_QA_FINAL_LIVE_STRICT_RU.md`; общий release всё ещё ждёт integration gates. |
| F13 | `STRICT_PRODUCT_BROWSER_APPROVED` | Учтён `evidence/strict-product-recert-live-f12-f15/STRICT_PRODUCT_RECERT_LIVE_F12_F15_RU.md`. |
| F14 | `PRODUCT_BROWSER_APPROVED`; не release-ready | Same R02 final strict live browser evidence as F12: staff rights/settings/payroll visibility, menu/direct-route parity and cross-app denied surface passed. Учтён `evidence/r02-staff-nav-product-browser-qa-final-live-strict/R02_STAFF_NAV_PRODUCT_BROWSER_QA_FINAL_LIVE_STRICT_RU.md`; общий release всё ещё ждёт integration gates. |
| F15 | `PRODUCT_BROWSER_APPROVED`; не release-ready | Post-rework code review passed, then strict live Product Browser QA rerun approved delete-only-draft and box-line remove/read-back. Учтён `evidence/f15-product-browser-qa-rerun-live-strict/F15_PRODUCT_BROWSER_QA_RERUN_LIVE_STRICT_RU.md`; общий release всё ещё ждёт R02/F12/F14 final QA and integration gates. |
| F16 | `STRICT_PRODUCT_BROWSER_APPROVED` | Учтён `evidence/strict-product-recert-catalog-stock-live/STRICT_LIVE_RECERT_REPORT_RU.md`. |
| F17 | `STRICT_PRODUCT_BROWSER_APPROVED` | Latest live F07/F17 evidence approved print sheet slice; release всё равно ждёт R01/F07 packaging rework. |
| F18 | `STRICT_PRODUCT_BROWSER_APPROVED` | Учтён `evidence/strict-product-recert-live-f05-f06-f18-f19/STRICT_PRODUCT_LIVE_REPORT_RU.md`. |
| F19 | `STRICT_PRODUCT_BROWSER_APPROVED` | Учтён `evidence/strict-product-recert-live-f05-f06-f18-f19/STRICT_PRODUCT_LIVE_REPORT_RU.md`; старый card/matrix mismatch не используется как proof. |
| F20 | `out_of_scope_by_user` | Не active release feature; strict recert не требуется в этом scope. |
| F21 | `blocked_missing_repo_target` | Не active WMS release feature; в checkout нет repo/target `sellerfocus.pro`. |
| F22 | `STRICT_PRODUCT_BROWSER_APPROVED` | Учтён `evidence/strict-product-recert-catalog-stock-live/STRICT_LIVE_RECERT_REPORT_RU.md`. |
| F23 | `STRICT_PRODUCT_BROWSER_APPROVED` | Учтён `evidence/strict-product-recert-catalog-stock-live/STRICT_LIVE_RECERT_REPORT_RU.md`. |
