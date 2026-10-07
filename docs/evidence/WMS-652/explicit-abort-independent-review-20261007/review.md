# WMS-652: independently measured explicit-abort boundary

**PASS for the measured finite transport boundary; original CI cause UNKNOWN.** The evidence establishes a real cancellation followed by native refusal of the same observed interception ID. It supports freezing a narrowly scoped handling contract, not approval of implementation, original failure causality or software effectiveness. Independent Sol6.1/high reviewer session `01a11389-3a47-7ec0-b74c-b8d920bfcca8`; immutable input `b8bd39d95142875f6db232c3ce4b89192a779210`. Ownership is only this new report. Existing cumulative3850 PASS and diagnosis743 remain intact. Previously read AGENTS, WMS-652/672 requirements and both complete case libraries are byte-unchanged from3850 and remain the context: preserve business assertions, uncertain-outcome identity and independent test-before-code boundaries.

All **17 unique manifest members** were independently read as immutable Git blobs and matched both declared byte lengths and SHA256. Manifest SHA256 is `4f60d066b5264ba48e858cc65fe570b09b1a276ebd9818cd0d99e033c741e3f9`. Raw lifecycle is15,084 bytes, SHA256 `659a38a5aa8b30c784de1a352881eaa7367933985534ba44c583f066bfcd9d8e`; raw probe is1,383 bytes, SHA256 `610a4dd5c5016e172c03d677a78a3d2388a0d156842dc85ab82a1af6c6730de3`. These checks validate the preserved members; artifact ZIP identity/digest is saved provider provenance, not a fresh ZIP download.

Saved run37552021494 attempt1 and its sole diagnostic job112569499871 completed successfully on exact head `e54a8d17fee84b4fab7f07dcb8f4d10ad61b8e9e`. Artifact11453330140 has the corresponding run/head/name. Actual environment is Ubuntu24.04.5/Linux x64, Node24.21.0, Chrome141.0.7390.37, protocol1.3. Browser.getVersion's native result agrees with the probe/environment receipt. Uploaded observer/probe bytes equal their exact e54 Git sources; before/after hash files are identical. The observer is also byte-identical to the prior navigation observer. Its WebSocket dispatch preserves native command rejection; the diagnostic catches expected negative outcomes for recording, without a handling exemption. The runner executes only the synthetic transport probe, not the application, product browser case, build or C5.

All **44 raw events, zero dropped**, were examined. The14-event prepared boundary ledger is an exact ordered subset at raw indexes26,30,31,32,35–44 (one-based). All records share one Node time origin and monotonically ordered timestamps. The observed Fetch ID `interception-job-3.0` maps to Network ID `3156.3`, frame `1DD331B6465D837EFCBD082834C9E57E`, GET `/__wms652_paused_abort__`. Network.requestWillBeSent corroborates the URL/frame and loader `8BCEEDF14ABB71343B046BE67AAF7646`. These IDs are observed opaque identities, not parsed private counters or constants for future handling.

| Recorded event | Node monotonic ms | Raw index |
| --- | ---: | ---: |
| Exact Fetch.requestPaused mapping | 492.745126 | 30 |
| Command11 sends live-page AbortController.abort | 492.907127 | 32 |
| Matching Network.loadingFailed: canceled=true, net::ERR_ABORTED | 494.366975 | 37 |
| Command14 sends first fulfillment of that observed Fetch ID | 500.221151 | 41 |
| Command14 receives exact native -32602 / Invalid InterceptionId. | 501.308822 | 42 |
| Unknown-ID command15 sends / receives the same native error | 501.458124 / 501.773241 | 43 / 44 |

Source binds command11 to `window.__controller.abort()`; command12 returns the same fetch promise's actual `AbortError`, `signalAborted:true`, and command13 confirms the original document remains live. No Page navigation is recorded after the paused request. Command14 is the only terminal operation for that Fetch ID in the complete bounded capture: no earlier successful response or competing/duplicate terminal command, and no matching Network.loadingFinished. Cancellation precedes fulfillment send by5.854176ms in the single Node clock; no comparison of unrelated browser/Node clock origins is needed. Send/result metadata for commands14 and15 retain the exact respective IDs and native error objects. The unknown ID was never observed by Fetch.requestPaused and remains a protocol rejection, despite the diagnostic process successfully recording its expected refusal.

The negative navigation control from37550768806 retains44 events with zero dropped. After actual navigation to about:blank, the observed old Fetch ID's command12 fulfillment **succeeded**; no matching Network.loadingFailed was recorded in that bounded observation. Its unknown-ID command13 still failed with the same native signature. Raw prior lifecycle SHA256 is `077ab05cfe2608540892c4153ad7c6549f319878ce0bd0a18c1c40f00d584af0`. This control gives no cancellation explanation and does not establish a universal rule about navigation. In particular, identical textual `interception-job-3.0` values occur in different browser sessions: their distinct network/frame identities must never be combined.

The finite inference is sound **only for the exact observed request lifecycle**: retain the Fetch-to-Network/frame mapping in the same browser session and case/generation; independently record cancellation of that Network ID with `canceled === true` and exact `net::ERR_ABORTED`; identify the first owned fulfillment command for that Fetch ID, with no earlier successful/completed terminal operation or concurrent competing terminal attempt; correlate its native refusal with exact code-32602 and message`Invalid InterceptionId.`. Preserve the classified cancellation and original native payload as diagnostic evidence. A retired fixture request must not become an accepted HTTP/native-printer response or business success, and must not trigger a retry. Classification must consume that request lifecycle once: later attempts against an already completed **or already retired** ID remain failures. Merely checking “no successful response” would be insufficient for duplicate retirement attempts.

Unknown IDs, missing/wrong/ambiguous mappings, cross-session/case reuse, missing or noncanceled failure, other errorText/native signatures, duplicate terminal operations and application exceptions stay fatal. Neither the native text alone nor navigation alone justifies handling. The measured command is Fetch.fulfillRequest and cancellation was observed before its send; this experiment does not validate other terminal methods or an in-flight cancellation ordering. Keep the existing43 business assertions/timeouts and error collection strict for unexplained failures; do not replace `errors.length === 0` with a broad protocol-error allowance. These are technical boundaries on a potential fixture correction, not new product requirements or owner permission gates. No concrete defect was found in the measured chain; the single-use/duplicate condition is required to keep the proposed boundary finite.

Original common37548248403 did not log its failing command/request/lifecycle. Neither this affirmative abort control nor the navigation control can retrospectively recover them. **Original cause remains UNKNOWN**, including whether any client timeout, remount, asset request or other lifecycle triggered that old refusal. No claim is made that a30-second product timeout caused the earlier short case. No fixture fix, implementation effectiveness, analyst acceptance, SOURCE/main activation, fullCI/release/deployment or physical-paper approval is issued. Separate testwriter must freeze actual-class positive/negative boundaries before developer implementation and subsequent source review. This reviewer ran no tests, browser, build or dispatch and changed no product/test/CI/policy file.

The principal verification is reproducible offline from this permanent repository; the snippet reads immutable bytes and native event metadata only:

```python
import hashlib, json, subprocess
S = 'b8bd39d95142875f6db232c3ce4b89192a779210'
D = 'docs/evidence/WMS-652/explicit-abort-linux-20261007/'
def raw(p): return subprocess.check_output(['git', 'show', S + ':' + D + p])
m = json.loads(raw('manifest.json'))
assert len(m['members']) == len({x['path'] for x in m['members']}) == 17
for x in m['members']:
    b = raw(x['path'])
    assert len(b) == x['bytes'] and hashlib.sha256(b).hexdigest() == x['sha256']
j = json.loads(raw('raw/explicit-abort-lifecycle.json')); e = j['lifecycle']
assert len(e) == 44 and j['lifecycleDropped'] == 0
assert len({x['nodeTimeOriginMs'] for x in e}) == 1
assert all(a['nodeMonoMs'] <= b['nodeMonoMs'] for a, b in zip(e, e[1:]))
assert e[29]['requestId'] == e[40]['requestId'] == e[41]['requestId']
assert e[29]['networkId'] == e[36]['requestId']
assert e[36]['canceled'] is True and e[36]['errorText'] == 'net::ERR_ABORTED'
assert e[41]['error'] == e[43]['error'] == {'code': -32602, 'message': 'Invalid InterceptionId.'}
assert e[43]['requestId'] != e[29]['requestId']
assert [x for x in e if x.get('requestId') == e[29]['requestId']
        and x['kind'] == 'command-send'] == [e[40]]
assert json.loads(raw('raw/exit-results.json')) == {'probe_exit': 0}
```
