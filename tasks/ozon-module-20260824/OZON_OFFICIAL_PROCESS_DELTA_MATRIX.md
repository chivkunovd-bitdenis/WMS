# Ozon FBS/FBO: official-process delta matrix against current WMS

**Call:** `22-ozon-official-process-delta-proof-path-resolved`  
**Research/access date:** 24 August 2026  
**Observed WMS baseline:** application SHA `af0779e1c425eede8d811da666822ff6ed178331`, observed 24 August 2026  
**Boundary:** research only. No application, contract, test or architecture edit; no credentials; no Seller API request; no product/stock publication.

## Decision rule

The owner rule is controlling: the existing FBS and marketplace-shipment screens, stages and physical flow remain unchanged. An Ozon API entity or endpoint is not evidence that an operator needs a new control. A UI exception is admissible only when a current official Ozon source proves a physical or mandatory-data action that the observed WMS action cannot perform. If the public evidence is unavailable, ambiguous or capability-dependent, the decision is `UNKNOWN -> UI unchanged / capability disabled`.

`Compatible via data adapter` below means that Ozon identifiers, lines, quantities, statuses or asynchronous operations may differ internally while the operator continues using the same WMS zone and action. It never authorises a new screen, tab, modal, workspace, document or parallel stage panel.

## Research questions

1. Does each observed FBS step have a current official Ozon equivalent, or must it remain `UNKNOWN`?
2. Can Ozon multi-line quantities, posting/package identity and status be mapped behind the current queue and four-stage FBS workspace?
3. Which per-unit data and print assets are mandatory before an FBS posting may be assembled and handed over?
4. Is an FBS carriage/act an unavoidable operator step, or can ready postings be handed over one by one?
5. Does each observed FBO shipment-document step have a current official Ozon equivalent, or must it remain `UNKNOWN`?
6. Do Ozon cargoes and transport cargoes require separate operator panels/actions, or are they route/capability-dependent external identities that can be mapped to current WMS boxes?
7. Which FBO labels or acceptance actions are proven unavoidable for a concrete supply, and which remain disabled pending supply-specific rules?
8. Which Call 20 UI elements lack hard incompatibility proof and therefore must be removed?

## Studied sources

### Current official Ozon sources

All links below are on Ozon-owned domains. They were checked on 24 August 2026. The interactive `docs.ozon.ru`, `seller-edu.ozon.ru` and `dev.ozon.ru` pages entered redirect loops in the research fetcher; that access limitation is not concealed. Method names and 2026 changes were cross-checked through the public official Seller API documentation/news links, but no Seller API endpoint was called.

- [Ozon Seller API documentation](https://docs.ozon.ru/api/seller/) — page title: “Ozon Seller API”; access date 2026-08-24; page publication date not exposed.
- [FBS Standard workflow](https://docs.ozon.ru/api/seller/#section/Upravlyajte-zakazami-FBO-FBS-i-rFBS/Shema-FBS-Standart) — page/section title: “Управляйте заказами FBO, FBS и rFBS → Схема FBS Стандарт”; access date 2026-08-24; section update date not exposed.
- [FBO workflow](https://docs.ozon.ru/api/seller/#section/Upravlyajte-zakazami-FBO-FBS-i-rFBS/Shema-FBO) — page/section title: “Управляйте заказами FBO, FBS и rFBS → Схема FBO”; updated with transport-cargo distribution on 2026-07-09; access date 2026-08-24.
- [Assemble FBS posting v4](https://docs.ozon.ru/api/seller/#operation/PostingAPI_ShipFbsPostingV4) — operation title: “Собрать заказ (версия 4)”; access date 2026-08-24.
- [Partial FBS package v4](https://docs.ozon.ru/api/seller/#operation/PostingAPI_ShipFbsPostingPackage) — operation title: “Частичная сборка отправления (версия 4)”; access date 2026-08-24.
- [Create FBS label-generation task](https://docs.ozon.ru/api/seller/#operation/PostingAPI_CreateLabelBatchV2) — operation title: “Создать задание на формирование этикеток”; current v2 announced 2024-05-23; access date 2026-08-24.
- [FBS packing requirements](https://seller-edu.ozon.ru/fbs/ozon-logistika/trebovaniya-k-upakovke) — page title: “Требования к упаковке”; access date 2026-08-24; current page update date not exposed.
- [FBS picking list / assembly](https://seller-edu.ozon.ru/fbs/ozon-logistika/sobrat-zakazy) — page title: “Собрать заказы”; access date 2026-08-24; current page update date not exposed.
- [FBS assembly and handover](https://seller-edu.ozon.ru/fbs/ozon-logistika/sobrat-zakazy-fbs) — page title: “Сборка заказов FBS”; access date 2026-08-24; current page update date not exposed.
- [FBS logistics documents](https://seller-edu.ozon.ru/fbs/ozon-logistika/logistics-docs) — page title: “Документы для отгрузки”; access date 2026-08-24; current page update date not exposed.
- [Create/fill an FBO supply request](https://seller-edu.ozon.ru/fbo/process-details/fill-in-application-form) — page title: “Создать и заполнить заявку на поставку”; access date 2026-08-24; current page update date not exposed.
- [Cancel/edit an FBO supply request](https://seller-edu.ozon.ru/fbo/process-details/otmenit-zayavku-na-postavku/) — page title: “Отменить заявку на поставку”; access date 2026-08-24; current page update date not exposed.
- [Transport cargoes in FBO supplies](https://dev.ozon.ru/start/525-Rabota-s-transportnymi-gruzomestami-TGM-v-postavkakh-FBO/) — page title: “Работа с транспортными грузоместами (ТГМ) в поставках FBO”; published June 2026; access date 2026-08-24.
- [FBO Seller API scanner integration guide](https://dev.ozon.ru/start/526-Gaid-integratsiia-metodov-Seller-API-FBO-so-skanerom/) — page title: “Гайд: интеграция методов Seller API FBO со сканером”; published June 2026; access date 2026-08-24.
- [FBO acceptance-act beta methods](https://dev.ozon.ru/news/781-Novye-beta-metody-dlia-raboty-s-aktami-FBO-v-Seller-API/) — page title: “Новые бета-методы для работы с актами FBO в Seller API”; published 2026-08-11; access date 2026-08-24.
- [Official Ozon news: fill FBO cargoes with a scanner](https://seller.ozon.ru/media/news/fbo-zapolnyajte-gruzomesta-cherez-skaner/) — page title: “FBO: заполняйте грузоместа через сканер”; published August 2026; access date 2026-08-24.

### Current WMS sources

- [Owner override](S0R_CALL20_OWNER_OVERRIDE_VERDICT.md) — controlling unchanged-by-default rule and rejected Call 20 patterns.
- [Observed baseline invariants](../../docs/evidence/ozon-module-20260824/baseline-current-product/BASELINE_INVARIANTS.md) — live routes, zones, actions and geometry at SHA `af0779e...`.
- Baseline code at that SHA: `frontend/src/screens/v2/FfFbsOrdersScreen.tsx`, `frontend/src/screens/v2/FfFbsSupplyWorkspace.tsx`, `frontend/src/screens/ff/FfSuppliesShipmentsPage.tsx`.
- [Earlier research](../../docs/runs/ozon-module-20260824/01-ozon-domain-research.md) — used only as leads; every retained claim was rechecked against the official links above.

## Confirmed facts

1. Ozon FBS works with a posting that can contain multiple product lines and quantities. The v4 ship/partial-package operations distinguish posting, products and packages. This is a data-model difference, not proof for new table columns or a second workspace.
2. Ozon requires the posting to be assembled before handover; mandatory exemplar/marking data can block assembly. The observed WMS already has a “Маркировка” column and an “Упаковка и маркировка” stage, so the physical action fits the existing stage.
3. An Ozon FBS posting has its own Ozon label. A WB sticker or an internal WMS box barcode cannot identify it in Ozon. This proves only a conditional Ozon print asset in the existing print zone, not a new panel.
4. Current Ozon FBS guidance permits handing ready postings over one by one by the posting barcode. Forming a common shipment remains an optional path for cases such as obtaining transport documents. Therefore a universal extra “form Ozon carriage” action is not proved.
5. Ozon FBO supply creation, composition and timeslot are external supply-order data. The current WMS shipment document already has a destination/date header, product plan and approval action; official evidence does not require a second document or changed stage structure.
6. Ozon FBO officially distinguishes cargoes (ГМ) and transport cargoes (ТГМ), and its API has rules, composition and label operations for them. The 2026 guide describes distribution and label printing. This proves distinct external identities, not that every supply uses TGM or that operators need a separate panel.
7. The August 2026 official news calls scanner-based cargo filling “another way” to fill cargo contents. It is not evidence that a separate Ozon scanner panel is mandatory.
8. FBO acceptance-act methods were introduced as beta on 11 August 2026. Their existence proves a reconciliation capability, but not a mandatory manual WMS action for every supply.

## Current WMS baseline

### FBS

The baseline has one `/app/ff/fbs` queue, the current filters and status tabs, one row-to-workspace opening path, and one modal workspace with four stages: `Состав → Подбор → Упаковка и маркировка → Короба`. Composition has the current product/order cells and one start-work action. Picking uses existing location/product scans or manual cell picking. Packing has the current counters, bulk print/pack controls and per-order rows. Boxes use the current WMS box path and current handover area. No Ozon-only route, table, stage or workspace exists in the observed URL state.

### FBO / marketplace shipment

The baseline has one `/app/ff/mp-shipments` list and one “Отгрузка на маркетплейс” modal document. Its existing stages are `Товары → Подбор → Упаковка`; the header already owns destination/date/status, the product stage owns plan and approval, the pick stage owns location/product handling, and the packaging stage owns PackagingTask and WMS boxes. The footer owns progression/approval/cancellation. No separate Ozon FBO document is part of the baseline.

## Delta matrix

Classification values: `compatible_as_is`, `compatible_via_data_adapter`, `hard_incompatible`, `unknown`. `hard_incompatible` is used only where an existing WB/internal asset cannot satisfy a current mandatory Ozon asset; it does not authorise a new surface.

| Stable id | Scheme / baseline zone and action | Official Ozon step | Classification | Why the current action is or is not sufficient | Hard-incompatibility proof | Smallest allowed delta / UI decision |
|---|---|---|---|---|---|---|
| `FBS-01` | Queue `/app/ff/fbs`: refresh/import, status tabs, filters, one row opening the existing workspace | Read unfulfilled/list postings and track status/substatus/actions | `compatible_via_data_adapter` | Posting identity/status can populate the current row and filters. API versions do not require new UI. | None | `provider-neutral data mapping`; `unchanged` |
| `FBS-02` | Workspace `Состав`: current product/order cells and quantities | A posting contains product lines and quantities; split/partial package preserves line/package identity | `compatible_via_data_adapter` | Current product cell and quantity cell can render multiple lines without changing columns. | None | `provider-neutral data mapping`; `unchanged` |
| `FBS-03` | `Состав`: one “Начать работу с поставкой” action | Begin local fulfilment before Ozon assembly confirmation | `compatible_as_is` | The physical start of warehouse work is provider-neutral. Ozon ship is a later external confirmation, not a second start button. | None | `no UI change`; `unchanged` |
| `FBS-04` | `Подбор`: scan location/product or pick manually from a cell | Seller physically picks the products listed in the posting; official picking-list guidance is optional assistance | `compatible_as_is` | Ozon does not prescribe a distinct warehouse-cell UI. Current WMS picking records the same physical movement. | None | `no UI change`; `unchanged` |
| `FBS-05` | Existing `Маркировка` column and `Упаковка и маркировка` row controls | Supply mandatory exemplar/marking data before ship where the posting requirements demand it | `hard_incompatible` only for a posting with an explicit unmet requirement; otherwise `compatible_as_is` | Generic/current WB marking values cannot satisfy a different Ozon-required exemplar value, but the existing marking zone can collect it. | Official FBS workflow blocks assembly when required exemplar/marking data is absent or invalid; requirement is posting/product-specific. | `conditional field in existing zone`; `conditional_existing_zone`, hidden/disabled unless the imported posting explicitly requires it |
| `FBS-06` | `Упаковка и маркировка`: pack selected units, then proceed | Confirm full or supported partial package with `/v4/posting/fbs/ship` or `/ship/package` | `compatible_via_data_adapter` | The operator's physical pack action is unchanged. Package/posting mutation and async state belong behind it. | None | `provider-neutral data mapping`; `unchanged` |
| `FBS-07` | Existing packing print zone and per-order print/apply flow | Generate and apply the current Ozon posting label | `hard_incompatible` | A WB sticker or internal WMS barcode cannot identify the posting to Ozon. A real Ozon label is mandatory for Ozon handover. | Official Ozon FBS assembly/handover guidance requires the Ozon posting label; Seller API exposes the current label-generation operation. | `conditional label/print asset in existing print zone`; `conditional_existing_zone`; no new panel/action family |
| `FBS-08` | `Короба`: current WMS box creation/content and existing handover area | Ready postings may be handed over one by one by posting barcode | `compatible_via_data_adapter` | WMS boxes remain physical grouping. Ozon posting/package identity must not be renamed “WMS box”, but can be mapped behind current box contents and handover. | None | `provider-neutral data mapping`; `unchanged` |
| `FBS-09` | Existing handover/footer action; no separate carriage stage | Optional common shipment/carriage and transport documents for applicable methods | `unknown` | Current guidance says one-by-one handover is generally available and the old common-shipment path remains optional. No proof makes it universal. | None; capability/route-specific evidence is absent | `no UI change`; `unchanged`, carriage capability disabled unless a concrete method proves necessity |
| `FBS-10` | Current status tabs (`В доставке`, `Завершённые`, etc.) and row state | Reconcile Ozon status after physical handover/scan | `compatible_via_data_adapter` | External status can map into current groups while retaining raw provider state internally. | None | `provider-neutral data mapping`; `unchanged` |
| `FBS-11` | Current cancelled group and existing safe recovery paths | Cancellation, partial cancellation, not-accepted/arbitration recovery where allowed | `unknown` | Available actions and recovery depend on the specific posting state. No universal extra operator action is proved. | None | `no UI change`; `unchanged`, mutation disabled until entity capability is known |
| `FBO-01` | `/app/ff/mp-shipments` create block: seller + one “Создать отгрузку на МП” | Create/read Ozon supply-order identity and select destination/route | `compatible_via_data_adapter` | The current document already represents a marketplace shipment. Ozon identity/destination can populate it without a second document. | None | `provider-neutral data mapping`; `unchanged` |
| `FBO-02` | Existing `Товары` stage: product picker, quantities, plan metrics | Fill/edit the supply product composition and validate it | `compatible_via_data_adapter` | Existing lines and quantities match the physical plan. Ozon SKU/operation ids are adapter data, not columns. | None | `provider-neutral data mapping`; `unchanged`; existing table columns retained |
| `FBO-03` | Current header/date/destination and one approval/progression action | Choose/update a timeslot and move the supply towards handover | `compatible_via_data_adapter` | Current header owns date/destination. Ozon allows a draft without a timeslot and selection later; this changes enabled state, not stage structure. | None | `conditional enabled state/copy in existing action`; layout/action count unchanged |
| `FBO-04` | Existing `Подбор` stage and `FfMpUnloadPickPanel` | Physically pick supply units from WMS stock | `compatible_as_is` | Official Ozon sources do not prescribe a different warehouse-cell action. Scanner support is an alternative input path, not a mandated separate panel. | None | `no UI change`; `unchanged`; separate Ozon pick panel rejected |
| `FBO-05` | Existing `Упаковка` / PackagingTask: create/scan WMS boxes and place units | Physically pack planned products into boxes/pallets before Ozon cargo declaration | `compatible_as_is` | Current WMS box handling performs the physical work. External cargo identities can be attached after/behind it. | None | `no UI change`; `unchanged`; separate Ozon packaging panel rejected |
| `FBO-06` | Existing box rows/cards and print menu | Declare Ozon cargoes and their contents according to supply-specific rules | `unknown` for operator UI; `compatible_via_data_adapter` for identity mapping | Official API proves cargo entities/rules, but not that a new click is unavoidable for every supply. WMS box closure can trigger/map declaration when allowed. | No supply-specific rules were read; generic endpoint existence is insufficient | `provider-neutral data mapping`; `unchanged`; extra “Связать с грузоместом Ozon” action removed/disabled |
| `FBO-07` | Existing box grouping; no TGM stage/action | Where the chosen FBO route supports/requires it, group cargoes into transport cargoes | `unknown` | Official 2026 sources prove TGM as a distinct external entity, but not that every route uses it or that current WMS grouping cannot map it. | No concrete supply/route rule was available | `no UI change`; `unchanged`; extra “Добавить в ТГМ” action removed/disabled |
| `FBO-08` | Existing per-box print zone/menu in `Упаковка` | Generate/apply Ozon cargo/TGM labels for the concrete configured entities | `hard_incompatible` only after concrete cargo/TGM rules exist; otherwise `unknown` | Internal `WHB` barcode is not an Ozon cargo/TGM label. The same existing print zone can carry the external asset. | Official FBO scanner/TGM guide includes label printing for configured GM/TGM; the exact asset set is supply-specific. | `conditional label/print asset in existing print zone`; `conditional_existing_zone`, disabled until rules/entity/label readiness are confirmed |
| `FBO-09` | Existing document footer/handover completion | Deliver at the selected point and timeslot; obtain provider state afterward | `compatible_via_data_adapter` | Physical handover and current footer remain one process; Ozon confirmation is reconciliation data. | None | `provider-neutral data mapping`; `unchanged` |
| `FBO-10` | Existing status/metrics and discrepancy/act area | Reconcile accepted/rejected quantities and, where available, accept an FBO act | `unknown` for manual acceptance; `compatible_via_data_adapter` for readback | Beta act methods prove data/reconciliation, not a universally mandatory operator click. | No official proof that every supply requires manual act acceptance in WMS | `provider-neutral data mapping`; `unchanged`; act mutation disabled by default |
| `FBO-11` | Existing cancel footer and status display | Cancel/edit supply when provider state/action permits; reconcile asynchronous result | `compatible_via_data_adapter` for status, `unknown` for each mutation | Current cancellation zone is sufficient; available action and async status determine enablement. | None | `conditional enabled state/copy in existing action`; no extra recovery panel |

## Individually judged Call 20 elements

| Rejected element id | Call 20 element | Verdict | Evidence-bound reason |
|---|---|---|---|
| `REJ-01` | Separate `ozon-fbo-pick-panel` | `remove` | Official sources do not prescribe a distinct warehouse-cell workflow; the 2026 scanner feature is another input method. Reuse `FfMpUnloadPickPanel`. |
| `REJ-02` | Separate Ozon packaging panel | `remove` | Ozon cargo entities do not replace physical WMS packing. Reuse PackagingTask and current WMS boxes. |
| `REJ-03` | Ozon-specific replacement table columns | `remove` | Posting/supply ids, lines and quantities fit current cells/lines via adapter. No physical action requires a replacement table. |
| `REJ-04` | Extra “Связать с грузоместом Ozon” action | `remove_or_disable` | Generic cargo API existence is not proof of a mandatory separate click. Supply-specific `cargoes/rules/get` evidence was unavailable. |
| `REJ-05` | Extra “Добавить в транспортное грузоместо” action | `remove_or_disable` | TGM is distinct but route-dependent. No concrete route rule proves an unavoidable operator action. |
| `REJ-06` | Ozon-only FBS packaging panel inside the existing stage | `remove` | Mandatory marking/package data belongs in existing rows/actions. A second panel duplicates the physical stage. |
| `REJ-07` | Ozon-only FBS boxes/stage panel | `remove` | One-by-one handover uses posting identity; WMS boxes stay in the existing boxes stage. No second boxes process is proved. |

## Contradictions

1. Earlier architecture/prototype text treated Ozon cargo, TGM and package identities as justification for explicit operator actions. Current official evidence proves the identities but not universal mandatory clicks. The owner rule therefore wins: map them behind existing boxes, or keep the capability disabled.
2. Earlier work treated an Ozon carriage as the natural parent of FBS postings. Current Ozon guidance permits one-by-one handover by posting barcode and keeps common shipment formation optional for some needs. A mandatory Ozon carriage stage contradicts this.
3. Earlier Call 20 replaced current FBO product/pick/pack presentation. Official sources describe external supply/cargo operations, but do not prescribe a separate WMS warehouse workflow. The UI replacement lacks hard incompatibility proof.
4. Ozon distinguishes GM and TGM, while the observed WMS has WMS boxes. They are not semantically identical; nevertheless, semantic distinction alone is not permission for a new UI. The safe default is separate backend identities linked to the same physical boxes.

## Unknowns

- The public interactive official pages could not be fully rendered in this environment because of redirect loops. Page update dates absent from public snippets are recorded as “not exposed”, not guessed.
- Exact `cargoes/rules/get` output, required cargo types, TGM availability, label formats and limits for the owner's real Ozon account/supply are unknown because no credentials or Seller API calls were authorised.
- Exact FBS exemplar fields for the owner's product categories are unknown until a real read-only posting exposes requirements. Therefore the conditional field remains hidden/disabled by default.
- Whether a concrete FBS delivery method needs an act, pass or carriage is unknown. One-by-one handover evidence prevents making it universal.
- Whether a concrete FBO supply requires a manually accepted act is unknown; the official methods are beta and capability-dependent.
- Cancellation/recovery actions depend on entity status/available actions. No mutation may be inferred from an endpoint name alone.

## Risks

1. Treating an API method as a UI requirement would recreate the rejected parallel process.
2. Flattening Ozon posting lines or package/cargo identities into a WB order or WMS box would corrupt quantity and label semantics even if the UI stays unchanged.
3. Printing an internal/WB barcode where Ozon requires its own posting/cargo label would cause physical acceptance failure.
4. Enabling cargo/TGM/act actions without a concrete capability can create invalid external state or duplicate an asynchronous operation.
5. Rendering imported external status as local completion can falsely tell an operator that Ozon accepted a handover.
6. Redirect-loop limitations make unsupported detail easy to overstate; every missing detail must remain `UNKNOWN`, not be reconstructed from the rejected prototype.

## Concrete handoff to the architect

1. Remove `REJ-01` through `REJ-07` from the contract/prototype. Do not replace them with differently named panels.
2. Preserve exactly the current routes, modal roots, stage counts, table structures and single progression actions documented in the baseline.
3. Model Ozon posting lines/packages and FBO supply/cargo/TGM/label/act identities behind provider-neutral projections. Do not rename a WMS box into an Ozon cargo.
4. Permit only two visible conditional exceptions from this matrix: `FBS-05` mandatory per-unit data inside the existing marking row/packing stage, and `FBS-07`/`FBO-08` provider labels inside existing print zones. All must be hidden/disabled until imported official requirements or concrete cargo entities prove applicability.
5. Keep FBS carriage, FBO cargo/TGM actions and act acceptance capability-off by default. A later implementation card may enable an existing action only with captured read-only entity evidence and no new surface.
6. Define one adapter-level invariant: API/data distinctions never change route, document, workspace, stage or table topology. They change data, print asset, copy or enabled state only in the exact existing zone named by the row.
7. Carry `UNKNOWN` rows forward as explicit blockers. Do not ask the owner or access credentials in architecture; a separately authorised read-only integration probe would be needed to resolve account/supply-specific rules.

## Acceptance self-check

- 11 FBS and 11 FBO baseline-step rows are present, with stable ids matching the JSON artifact.
- Every row has current official evidence or an explicit `UNKNOWN` decision.
- Default UI decision is unchanged; conditional exceptions are confined to current marking/print zones and include hard proof.
- Separate pick, packaging, table, cargo, TGM and FBS stage panels are individually judged.
- No application/contract file, credential, external API, product, stock or owner interaction was used.
