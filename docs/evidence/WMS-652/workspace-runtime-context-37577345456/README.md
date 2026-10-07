# WMS-652 actual workspace Runtime observation37577345456

Single workflow_dispatch attempt1, actual HEAD
cb695e445880542b0ba4b9926b5eabf442578b13/ref
codex/wms652-workspace-runtime-context-diagnostic. Run started05:38:50UTC,
completed success. Job112649098331, artifact11463481148; exact HEAD/run/attempt
artifact name and API identity checked. Ubuntu24.04.5/Node24.21.0/
Playwright1.56.1/Chromium141.0.7390.37.

Strict43PASS, original exit0, exact43 cases/order. Full native transport has11600
unique positive send/reply pairs with equal ID sets,0 native errors/timeouts/pending.
This includes two observation setup commands:4 Runtime.addBinding and5
Page.addScriptToEvaluateOnNewDocument. Excluding them,11598 original commands/pairs;
no query before fulfill, no GetResponseBody, no negative commands. Original error
forwarding/assertions remain strict; no failed FetchID exists in this actual run.

Narrow capture:255 JS fetch calls,254 fulfilled,0 rejected,46 document bindings,
257 target paused records,255 target Network request records;2913 records/893587
bytes. ALL255 calls bind through native Runtime.bindingCalled.executionContextId
to an observed unique/default-frame Runtime context (37 contexts emitted calls).
No event/byte/final-size/observer drops or binding rejection. No pending native or
readiness command; one retained call lacks a terminal binding.

Concrete context boundary: context21/unique ID
5997142605420614339.-7101201279389553568 belongs to document
4a2ced71-535d-45e4-83ae-5b568ad86606, created during pool/supply_ids=A.
After original Page.navigate5080 send for pool/supply_ids=A,B, binding call9 still
comes from EXACT context21 (module stack includes fbsApi/FfFbsSupplyWorkspace).
Then navigate reply/new loader, original readiness evaluate5084 send, context
clears, frame navigation/new context22, and readiness5084 returns false. The
binding call9 has no fulfilled/rejected observation after its context cleared.
This proves a JS call from the preceding document after the case transition; it
DOES NOT bind that call to a particular FetchID or prove abort/native job removal.
All exact sequence indices/identities are in ledger.json and full narrow raw.

One observed paused GET/protocolXHR with no NetworkID:
interception-job-4898.0, case qr+pool/supply_ids=A, generation90, frame
BFE3774D9D38EC998B00E9DCC2AF53F4, allowlisted workspace pathname. Its exact original
first fulfill5595 is successful. No native loader/executionContextId/JS-call serial
exists in that paused record; request-to-JS/document ownership remains UNKNOWN.
The native context24 creation and nearby navigation do not supply that binding.
One OTHER paused ID1664.0 has NetworkID3568.1787 but no exact narrow Network request
record; this gap is recorded rather than inferred. Counts alone are not request joins.

Native document metadata includes47 context-created,88 contexts-cleared,46 frame
navigation events,0 individual context-destroyed events.46 original navigate pairs
and661 readiness replies (338 true) retained with command/send/reply identities.
No loader/context ownership is assigned to a readiness boolean without a native
identity. Native binding proves call context only; concurrent/ambiguous same-URL
request mapping and historical cause stay UNKNOWN. No URL/time-only causal claim.

Source restoration verified against exact4c532:2546 original Git bindings and2546
before/after hashes unchanged; all43 cases, original native finite handling,
assertions/routes/body bytes/delays remain frozen. Reverse five insertions recovers
original browser exactly. Original600s shell changes only sibling runner path;
generated observer equals published HEAD. All19 artifact members saved losslessly
under raw/; JSON compressed with original lengths/SHA256 in raw-manifest.json.
API/job metadata, full job log, complete original transport, narrow context,
strict result, controls and generated/source copies are all recoverable from Git.
provenance-manifest.json hashes metadata/log/ledger. Download ZIP is removed only
after published Git/member-manifest recovery verification.

Result: NONREPRODUCTION, NOT a fix/release approval/old etalon cause proof.
The source-only readiness/context overlap is now observed for one exact JS call,
but no InvalidInterceptionId occurred, and no discriminator binds that call to a
native paused ID. Actual request-owner/job disappearance and historical cause remain
UNKNOWN. Exact etalon375670 remains failed; release/deploy gate is not changed.
No new code, browser/test rerun/install/dispatch/handling/migration/product/protected
fixture/policy/main/common/607 changes. Only this evidence directory committed.
