# Audit of prior Ozon research after live evidence correction

**Call:** `35-ozon-operational-research-live-evidence-correction-path-authorized`  
**Audited source:** [`OZON_OFFICIAL_PROCESS_DELTA_MATRIX.md`](../OZON_OFFICIAL_PROCESS_DELTA_MATRIX.md)  
**Classes:** `FACT_CONFIRMED`, `OUTDATED`, `EXTRAPOLATION`, `UNSUPPORTED`.

Provider fact, current-WMS baseline, owner constraint and implementation choice are kept separate. Live public evidence does not become account evidence, and no research statement is an ARCH/UI or implementation permission.

## Correction of Call 33 evidence claims

| Prior Call 33 claim | Corrected class | Live correction |
|---|---|---|
| Live Browser/official Seller API documentation was unavailable. | OUTDATED | Lead captured 90/90 operation matches and 41/41 core sections from live Seller API 2.1. |
| seller-edu FBS process pages were unavailable. | OUTDATED | Live FBS assembly and handover pages are both nonempty and preserved. |
| dev.ozon.ru TGM guide was unavailable. | OUTDATED | Live TGM guide from 4 June 2026 is nonempty and preserved. |
| Every exact operation row must remain blanket `CONFLICT` because live docs could not be reached. | OUTDATED | Method/path identity is `CONFIRMED_OFFICIAL` for 90/90. Unsupported nested types/requiredness remain `CONFLICT` per claim scope. |
| No authorised Ozon credential location existed. | OUTDATED | The designated shared marker exists and contains only nonempty `OZON_TEST_API_KEY`; Client-Id is missing; calls remain 0. |

## Eight prior “confirmed facts”

| ID | Class after live correction | Reason |
|---|---|---|
| CF-01 | FACT_CONFIRMED | Live FBS v4 operations and assembly page distinguish products, packages and posting labels. Exact unsupported nested fields remain conflict. |
| CF-02 | FACT_CONFIRMED | Live ship/exemplar operations and FBS instruction confirm conditional additional data/marking can block assembly. |
| CF-03 | FACT_CONFIRMED | Ozon posting/package labels are provider-owned and distinct from WB/internal WMS labels. |
| CF-04 | FACT_CONFIRMED_WITH_SCOPE | One-by-one point handover is supported without shipment/carriage formation; courier piecewise and entrusted acceptance require it. Therefore capability-conditional, not universal default. |
| CF-05 | EXTRAPOLATION | “Fits existing WMS document/no second stage” remains owner/product reasoning, not Ozon fact. |
| CF-06 | FACT_CONFIRMED_WITH_SCOPE | GM and TGM are distinct; live guide makes TGM an activated pallet/large-volume flow. Ordinary GM and TGM applicability remain supply-specific. |
| CF-07 | UNSUPPORTED | The preserved TGM guide describes API/scanning capability but does not prove the prior quote that scanner filling is merely “another way” or approve any UI conclusion. |
| CF-08 | FACT_CONFIRMED | Four beta FBO act operations are present in live docs and official release evidence; universal mandatory acceptance is not proven. |

`FACT_CONFIRMED_WITH_SCOPE` is an audit label, not a machine confidence value. Machine JSON continues to use only the four allowed confidence enums.

## FBS delta rows

| Row | Class | Corrected reason |
|---|---|---|
| FBS-01 | FACT_CONFIRMED | Current v4 list/unfulfilled method/path exists live; old v3 current-integration wording is outdated. |
| FBS-02 | EXTRAPOLATION | Multi-line/package identities are factual; rendering them in current cells is a product mapping. |
| FBS-03 | EXTRAPOLATION | Local work start versus provider ship separation is sensible but not an Ozon UI rule. |
| FBS-04 | EXTRAPOLATION | Physical picking does not become provider-approved UI from an API operation. |
| FBS-05 | EXTRAPOLATION | Conditional marking is factual; sufficiency of the current marking zone is a reuse conclusion. |
| FBS-06 | EXTRAPOLATION | Ship/package contracts are live; binding them to the current pack action is development scope. |
| FBS-07 | EXTRAPOLATION | Label ownership is factual; placement in a current print zone follows owner constraint, not provider docs. |
| FBS-08 | EXTRAPOLATION | Posting/package identities are factual; mapping behind WMS boxes is implementation work. |
| FBS-09 | FACT_CONFIRMED_WITH_SCOPE | Point handover can be one-by-one; courier piecewise and entrusted acceptance need shipment formation. |
| FBS-10 | EXTRAPOLATION | Provider statuses are live; grouping them into WMS statuses is not defined by Ozon. |
| FBS-11 | FACT_CONFIRMED_WITH_SCOPE | Available actions/endpoints exist live; concrete action remains state/account scoped. |

## FBO delta rows

| Row | Class | Corrected reason |
|---|---|---|
| FBO-01 | EXTRAPOLATION | Supply/destination entities are live; reuse of the current create block is product scope. |
| FBO-02 | EXTRAPOLATION | Composition exists; retaining columns is an owner/product decision. |
| FBO-03 | EXTRAPOLATION | Timeslot operations exist; current header placement is not an Ozon fact. |
| FBO-04 | EXTRAPOLATION | No separate panel follows owner constraint, not provider instruction. |
| FBO-05 | EXTRAPOLATION | Local box process is baseline; sufficiency requires concrete cargo rules. |
| FBO-06 | FACT_CONFIRMED_WITH_SCOPE | Cargo rules/create/read paths exist live; concrete GM requirements remain supply-specific. |
| FBO-07 | FACT_CONFIRMED_WITH_SCOPE | TGM activation/create/bind/labels exist and live guide scopes them to activated pallet/large-volume flow. |
| FBO-08 | EXTRAPOLATION | GM/TGM label ownership is factual; current print-zone placement is product scope. |
| FBO-09 | EXTRAPOLATION | Provider supply states exist; current footer mapping is implementation scope. |
| FBO-10 | FACT_CONFIRMED_WITH_SCOPE | Beta act operations exist; mandatory action for a concrete supply is unknown without account readback. |
| FBO-11 | FACT_CONFIRMED_WITH_SCOPE | Cancel/content/timeslot pairs exist; allowed action remains state/supply scoped. |

## Returns assertions

| Claim | Class | Corrected reason |
|---|---|---|
| Unified returns read and giveout methods exist. | FACT_CONFIRMED | Method/path identity is live; core sections include unified list and giveout barcode. |
| These methods require a new inspection UI. | UNSUPPORTED | They describe marketplace state/assets, not a WMS screen or inspection workflow. |
| Giveout/list automatically makes local stock sellable. | UNSUPPORTED | No read/giveout contract performs a local WMS mutation. |
| Ozon never performs any external restock automatically. | UNSUPPORTED | The inspected contracts do not prove that broader provider behavior. |
| A concrete return is eligible for giveout. | UNSUPPORTED | Requires account/return readback; no such call was possible without Client-Id. It is covered by the general account-capability unknown, not a new provider rule. |

## Contradictions resolved

1. **No live docs vs live capture:** prior statement is removed; 90/90, 41/41 and 3/3 are authoritative observed evidence.
2. **All rows conflict vs scoped confirmation:** operation identity is confirmed; unsupported nested schema claims remain conflict.
3. **Carriage mandatory vs unnecessary:** neither blanket claim survives. Exact resolution is capability-conditional by point/courier/entrusted acceptance/transport-document need.
4. **TGM universal vs irrelevant:** TGM is real, activated and pallet-oriented for large-volume flow; concrete supply applicability remains unknown.
5. **Returns status vs stock truth:** read/giveout facts stay marketplace-bounded; inspection UI and external restock claims are unsupported.

## Risks retained from prior work

- Treating endpoint existence as a mandatory operator click.
- Flattening posting/package/GM/TGM identities and losing label ownership.
- Calling local completion provider acceptance without readback.
- Turning a capability-specific FBS or FBO flow into a universal stage.
- Converting absence of evidence in returns contracts into a universal restock claim.
- Guessing Client-Id or exposing the found API key value.

## Prior architect prescriptions

Earlier H-01…H-07 prescriptions are not carried forward. They were product/architecture extrapolations, not provider facts. Call 35 creates no architect handoff, no ARCH/UI contract, no mockup and no implementation permission.

## Audit result and permitted sequence

The corrected research supports a reuse-first screen-readiness correction only after root explicitly accepts these artifacts. After that acceptance, the stated pipeline sequence is direct atomic developer slices. This is sequencing evidence, not a development authorization, and it does not permit a new screen, tab, modal, workspace or redesign.
