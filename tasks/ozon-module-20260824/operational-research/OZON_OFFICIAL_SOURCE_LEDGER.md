# Ozon official source ledger: live correction

**Call:** `35-ozon-operational-research-live-evidence-correction-path-authorized`  
**Evidence window:** 2026-08-24T21:08:14Z–2026-08-24T21:12:37Z UTC  
**Authority rule:** Ozon-owned pages are primary. Lead run JSON is a local evidence capture of those live pages. Saved third-party OpenAPI is transport only.

## Live evidence totals

| Evidence artifact | Live source | Exact observed result | SHA-256 | Limits |
|---|---|---|---|---|
| [`33-lead-live-official-validation.json`](../../../docs/runs/ozon-module-20260824/33-lead-live-official-validation.json) | [Ozon Seller API 2.1](https://docs.ozon.ru/api/seller/?__rr=1&abt_att=1) | 90/90 operations found; 90/90 methods matched; 90/90 paths matched; 1 551/1 634 field names visible; 75/90 operations have no invisible field name. | `e160988db5dd65cc190d1eca88584d8039ecc87f2113141956f201edfdd008fa` | Field-name visibility is not proof of type, requiredness or nested semantics. |
| [`33-lead-live-core-sections.json`](../../../docs/runs/ozon-module-20260824/33-lead-live-core-sections.json) | [Ozon Seller API 2.1](https://docs.ozon.ru/api/seller/?__rr=1&abt_att=1) | 41/41 requested official sections found and nonempty. 39 method/path pairs map to contract rows; 2 are additional live sections. | `8f527f954583bce9a07a6b76d0ae15c31a0f9baafc130adb643c4b37a1d2d97e` | Text stops before example payloads; it does not expand every nested schema claim. |
| [`33-lead-live-process-pages.json`](../../../docs/runs/ozon-module-20260824/33-lead-live-process-pages.json) | Three Ozon-owned process pages below | 3/3 pages nonempty. | `4518afb268fab6f59e33ce47776c600f7cc522d426dfe0a410ac9fab06364167` | Captured body retains navigation/footer text; facts are scoped to exact passages. |

## Official source records

| ID | Direct URL | Title / version / date | Live result and accepted claim scope |
|---|---|---|---|
| LIVE-API-001 | https://docs.ozon.ru/api/seller/?__rr=1&abt_att=1 | `Документация Ozon Seller API`, Seller API 2.1; captured 2026-08-24T21:08:14Z | All 90 expected operation ids were found; every expected method and path matched. This confirms operation identity only. |
| LIVE-API-002 | https://docs.ozon.ru/api/seller/?__rr=1&abt_att=1 | Same source; field reconciliation | 1 551 of 1 634 expected field names are visible. The 83 names not visible are preserved per operation. No blanket nested-schema confirmation is inferred. |
| LIVE-API-003 | https://docs.ozon.ru/api/seller/?__rr=1&abt_att=1 | Same source; captured 2026-08-24T21:12:09Z | 41/41 requested core sections found. Their exact headings, top-level fields, descriptions and response codes are accepted where present. |
| LIVE-API-004 | https://docs.ozon.ru/api/seller/?__rr=1&abt_att=1 | Additional core section | `POST /v1/cluster/list` is live. It is recorded as an additional section and does not silently replace contract row `/v2/cluster/list`. |
| LIVE-API-005 | https://docs.ozon.ru/api/seller/?__rr=1&abt_att=1 | Additional core section | `POST /v1/returns/company/fbs/info` is live. Its existence does not reverse the unified `/v1/returns/list` migration claim. |
| LIVE-PROC-001 | https://seller-edu.ozon.ru/libra/fbs/ozon-logistika/sborka-otpravlenii-na-fbs | `Сборка отправлений на FBS`, 13 July 2026; captured 2026-08-24T21:12:37Z | Shipment formation is required only for piecewise courier and entrusted acceptance; all other cases proceed to label printing. Each split posting needs a separate package and shipping label. |
| LIVE-PROC-002 | https://seller-edu.ozon.ru/libra/fbs/ozon-logistika/otgruzka-otpravlenii-na-fbs | `Отгрузка отправлений на FBS`; captured 2026-08-24T21:12:37Z | Point handover uses warehouse barcode or posting label and later status verification. Courier requires barcode scan and transport waybills. Entrusted acceptance depends on method/point capability. |
| LIVE-PROC-003 | https://dev.ozon.ru/start/525-Rabota-s-transportnymi-gruzomestami-TGM-v-postavkakh-FBO/ | `Работа с транспортными грузоместами (ТГМ) в поставках FBO`, 4 June 2026; captured 2026-08-24T21:12:37Z | TGM is activated and used to bind GM boxes to pallets for large-volume supply flows; it is not evidence of universal applicability. |
| OFF-REL-001 | https://t.me/s/ozonsellerapi?before=648 | Ozon Seller API official channel, March 2026 | Package-label change, ship v4 error, and FBS stock/warehouse/delivery-method migration. |
| OFF-REL-002 | https://t.me/s/OzonSellerAPI?before=684 | Ozon Seller API official channel, July–August 2026 | FBS list v4, FBO list v3 and four beta FBO act paths. |
| OFF-REL-003 | https://t.me/s/OzonSellerAPI?before=428 | Ozon Seller API official channel, October 2024 | Unified `/v1/returns/list` and retirement of old split returns lists. |
| OFF-PROC-004 | https://t.me/s/ozonmarketplace?before=2781 | Ozon Marketplace official channel | Posting-by-posting handover without general shipment formation is available; old shipment process remains for needs such as transport documents. Scope is reconciled with LIVE-PROC-001/002 as capability-conditional. |

## 90/90 operation reconciliation policy

Each of the 90 `operation_rows` in [`OZON_EXACT_OPERATIONAL_CONTRACT.json`](./OZON_EXACT_OPERATIONAL_CONTRACT.json) contains a `live_official_reconciliation` object copied from the lead evidence:

- `operation_found`, observed method/path/operation id/summary;
- `method_path_confidence = CONFIRMED_OFFICIAL`;
- exact totals for visible and non-visible field names;
- `field_name_presence_confidence = CONFIRMED_OFFICIAL` only for names actually visible;
- `nested_exactness_confidence = CONFLICT` for types, requiredness, enum and nested semantics not proven by the live capture;
- whether a matching core section is present.

Thus the earlier false claim “live official docs unavailable, therefore all evidence is conflict” is removed. The transport-derived nested details are not mass-promoted.

## 41/41 core live sections

All 41 requested sections are present. The local evidence contains exact live text before examples. Thirty-nine correspond to a method/path pair in the 90-row contract. The two extra live sections are preserved separately because silently mapping v1 to v2 or a count endpoint to unified returns would be false reconciliation.

## Three live process pages

1. FBS assembly: shipment formation is conditional; posting label is mandatory per posting/package.
2. FBS handover: point, courier and entrusted-acceptance flows differ; next provider status remains the acceptance readback.
3. FBO TGM: activated pallet/large-volume flow with transport cargo ids, bindings and pallet labels.

## Saved schema transport, still non-authoritative for unsupported nested facts

- URL: https://github.com/MissiaL/ozon-api/blob/main/references/ozon-seller-openapi.json
- Blob SHA: `e59f426db90c7d58a434c0c69843e57f51667a92`
- Declared source: `https://docs.ozon.ru/api/seller/swagger.json`
- Metadata: OpenAPI 3.0.0, title `Документация Ozon Seller API`, version 2.1, 463 paths, 2 136 schemas.

The live DOM validates all 90 operation identities and most field names, but no byte hash of a live Swagger payload was captured. Unsupported nested types/requiredness remain explicit `CONFLICT`; this limitation is no longer misreported as absence of live official documentation.

## Credential/source boundary

The shared Git marker contains only a nonempty `OZON_TEST_API_KEY` variable name. `Client-Id` is absent. Secret values were not printed or stored, and provider calls equal zero. Public documentation capture is independent from authenticated account capability.
