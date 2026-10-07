# WMS-666 — independent bounded contract checkpoint, 2026-10-08

**Verdict: NO-GO for release acceptance.** This checkpoint settles the GS1 normalization contract and identifies an Ozon timestamp-tie regression. It is not the accepting review R, does not designate a trusted product P, and does not authorize activation/deployment. The earlier 24-runtime-path review remains in `checkpoint-findings.md`; unchanged paths were not re-audited.

The review read the release checkout at HEAD `907510ceaa9b77337e526c3b1553582b1b2b8ef0` with the uncommitted GS1 candidate source blob `5e73abaca93b6e5cd14e4fdec215a79a919ffe6c`. The deployed comparison base is `212f19d548496fef7baf75c83204b771e304281b`. No product code or test expectation was changed by this reviewer. The independent frozen preservation guards are the API contract from `ceef76ad` and the unchanged former strict-xfail unit assertions promoted by `ae918010` on the testwriter branch.

## GS1: preserve supplied field boundaries; raw input cannot identify lost intent

An AI (application identifier) labels a field. GS is the transmitted group-separator character, byte `0x1D`. The [official GS1 syntax dictionary](https://raw.githubusercontent.com/gs1/gs1-syntax-dictionary/main/gs1-syntax-dictionary.txt), inspected 2026-10-08, defines AI 21 as `X..20` and internal AIs 91–99 as `X..90`. These fields do not have the predefined-length flag. The [GS1 2D retail guideline, element string syntax](https://ref.gs1.org/guidelines/2d-in-retail/) explains separation of variable-length fields and placing the final variable field at the end. A substring resembling another AI inside the value does not establish a boundary.

The local archived WB primary document, `tasks/fbs-marketplace-orders/wb-docs/04-labeling/verify-product-identifiers.md`, describes the familiar GTIN/serial/4-character verification-key/crypto-tail profile, and recommends scanning DataMatrix so the complete code and GS separators reach verification. It does not authorize guessing a missing boundary when the received input already has another structurally complete interpretation. This is the archived WB article (downloaded 2026-07-30; stated update 2026-05-18), not a claim that the current web article was fully reread.

`normalize_scanned_cis(raw)` receives no trusted product-category profile. It first removes scanner suffix/AIM and restores visible separator substitutes or keyboard-layout damage. The old last step strips all GS from the tail and reconstructs the known 91/key/92/signature profile from the end, even when the original surviving GS already delimit complete fields. Its claim of a unique reconstruction is only uniqueness inside that assumed profile, not uniqueness among the possible GS1 interpretations of the received bytes.

The exact frozen victim is `01{GTIN14}21AB91ZZQQ<GS>92{signature44}`. Its serial is `AB91ZZQQ`; the old deployed baseline inserts a GS before `91`, reducing that serial to `AB` and reclassifying `ZZQQ`. The new guard preserves the exact supplied value. This is a pre-existing baseline defect, not a newly introduced form-unification regression.

Both legacy half-separator test inputs have the same ambiguity. The input bytes must remain unchanged when correcting their expectations:

| Existing test parameter | Received field interpretation without inventing a separator | Consequence |
| --- | --- | --- |
| Missing before 91 | AI21 `aXq7Tz9Km91K7pQ` (15 characters), GS, AI92 signature44 | Entire 15-character serial must remain opaque. |
| Missing before 92 | AI21 `aXq7Tz9Km` (9 characters), GS, AI91 `K7pQ92` + signature44 (50 characters), end | The final AI91 field can contain the substring `92`; raw input cannot prove it was a separate field. |

Neither interpretation certifies the product's authenticity, checksum, crypto signature or WB acceptance. This review establishes the field-boundary ambiguity only. A genuinely damaged input may still be rejected by normal marketplace verification. Silently replacing it with another identity is not a valid guarantee of repair.

**Frozen contract recommendation:** after the existing transport repairs, preserve a completely parsed input's bytes and return no invented `gs_structure_restored` hint. Do not use the letters, guessed category, assumed AI91 length or signature length to distinguish the ambiguous vectors. Do not add an operator gate or a new product profile. The independent testwriter may correct exactly the two parameterized half-separator expectations to `value == half`, one GS and `hints == []`, retaining their original inputs. Rename/comment that test to describe ambiguity. Keep the exact victim unit/API assertions and all existing no-GS repair assertions.

The updated helper's removal of KIZ-specific AI91=4 and AI92=44/88 checks is appropriate for this narrowly defined boundary-preservation decision. It is not an assertion that the helper implements every GS1 semantic validation rule. Existing no-GS reconstruction remains a bounded recovery rule for the supported known shapes; this checkpoint does not generalize it to arbitrary damaged codes.

## Mechanical evidence and limits

`gs1-ambiguity-mechanical.json` records actual pure normalization functions extracted by Python AST from the deployed baseline and the candidate source, including source identity. `gs1-{baseline,candidate}-pure-source.txt` preserve those executable extracts. `reproduce-boundaries.py` replays them without application imports, database, credentials or provider calls.

The replay confirms baseline corruption and candidate preservation of the exact victim, preservation of both unchanged ambiguous vectors, and unchanged results for complete input, fully lost separators with 44-character signature, duplicate GS, and terminal GS. A further 88-character signature case preserves the established no-GS repair. This is code-level evidence, not a replacement for the frozen operator-commit API/DB test or final CI. The developer and independent testwriter received the exact contract before expectation correction.

## Ozon: quantity cap arbitrarily rejects a reader-current code at timestamp ties

**Confirmed defect requiring an independent RED regression before a fix.** Existing `ozon_fbs_marking_gate_service.current_markings` sorts by `created_at`, calculates the quantity cutoff, and includes every row tied at that cutoff. The new print-binding validator (`fbs_print_binding_service.py`, observed source blob `82c3b78c6cfd729d101de82f36a4c6a29fdb864f`) sorts by `created_at DESC, id DESC` and takes `current_rows[:quantity]`. UUID order is not evidence that a physical exemplar's code was retired.

The concrete fixture has position quantity 3; initial accepted codes for exemplars 1, 2 and 3 share a creation timestamp. A later accepted row is added for exemplar 1. Give exemplar 3 the lowest original UUID ordering. The existing reader returns all four boundary rows. The new validator selects new exemplar1 + old exemplar1 + exemplar2, rejecting exemplar3 even though no later row replaced exemplar3. Thus a legitimate code returned by the existing reader can fail print validation solely because of timestamp ties and arbitrary UUID ordering.

`ozon-tie-mechanical.json` records execution of the unchanged actual reader and a direct model of the validator's SQL ordering and slice; `ozon-current-reader-pure-source.txt` preserves the executed reader functions. This is a reproduced selection mismatch, not an endpoint/DB test. The testwriter was asked for an independent actual validator/endpoint RED with tied timestamps and deterministic UUIDs before product changes. Making every fixture timestamp unique eliminates this case and cannot establish compatibility.

The fix must agree with existing current-code selection for this legitimate exemplar without disabling tenant/order/current-binding checks or rejection of explicitly retired/replaced/rejected codes. A provider-accepted status must not become a new prerequisite for local print. This review does not authorize rewriting Ozon delivery readiness or resolving all historical ambiguous rows: `current_markings` and delivery readiness have different responsibilities, and delivery's count gate must not be imported as a new local-print gate.

## Remaining handoff

The developer and testwriter received both findings directly. Required next evidence is the independent two-expectation GS1 contract commit, frozen preservation/no-GS/API tests on the final product source, the Ozon tie RED followed by its targeted fix and GREEN, and the already planned whole finite operator/native-emulator proof on a stable final P. Final acceptance still requires the real browser paths, all decoded native outputs, DB/stock snapshots, recovery scenarios and normal synthetic provider acknowledgement semantics; physical paper and live WB acceptance must remain explicitly unclaimed. Only then can a separate published accepting R designate P as trusted for the supported data-only activation metadata update. Full CI and deployed-version verification are later distinct checks.
