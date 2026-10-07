# WMS-672: independent bounded active-peer drain source review

**PASS for the source delta only** at
`47817f76589701ea36ba1f8b30fca84b6a136208`. No concrete technical defect was
found in the added cohort-drain mechanism against frozen contract
`a0e4409300d4897234c501474de2bfe45478e488`. This does not approve effectiveness,
acceptance, a product reference upgrade or any final SOURCE pin. The coordinator
reports that actual Linux capture 37539919041 still fails corrected-retry C5;
its new raw checkpoint is pending this reviewer's separate causal assessment.

This separate Sol6.1 session owns evidence only. Applicable AGENTS and complete
owner/failure libraries were already read; current rules were refreshed in the
immediately preceding review. Previously reviewed 9e message/window behavior is
not re-audited here. No product, test, workflow, policy, main or external setting
was edited. No tests, browser or CI dispatch were rerun.

## Mechanism and frozen contract

The implementation commit changes one utility with 10 insertions and one
deletion. Each decode in the current 16-image group is wrapped in an async
function, so a synchronous decode throw becomes a rejected cohort promise
rather than interrupting construction of the peer list. Promise.all still
determines the failure returned by that group. Its catch waits for all already
started group promises to settle and then throws that exact original error.
Later peer rejections cannot replace it, and are observed by the drain.

The outer failure handler therefore removes the iframe only after that active
group settles; the existing screen then releases its busy/attempt state. No
later group is started after a failure. There is no retry, error suppression,
new transfer or mark, timer/window change, or altered source generation. The
successful path still awaits readiness for every group before the existing
transfer; the non-handoff single-scan path is byte-unchanged.

The two frozen tests drive the actual utility and extracted real screen
operation with a controlled decode boundary. The async case rejects first,
holds peers, then rejects an earlier-index peer later with a different error.
The synchronous case throws directly while peers are held. Both assert the
iframe remains connected, operation unfinished and busy/attempt active until
release; then require zero pending peers at cleanup, identical original error,
no subsequent cohort, zero source saves/transfers/marks and normal state release.
These checks cover source teardown, not Chromium's internal resource admission.
Their pre-code RED and later GREEN do not prove why a real native retry fails.

## Evidence and scope checks

Independently recomputed all nine declared frozen-file hashes from source478.
Every file is unchanged from the implementation parent, including old C5,
native-seven suite and the new peer-two suite. The peer contract is also
byte-identical to the separate pre-code a0e commit. The screen is byte-identical
to the implementation parent. Machine-readable checks are in source-checks.json.

Read developer receipt commit `69065b3db93b1036c6c399c1bebe8fe71527e68b`:
peer-two TAP records 2 PASS/0 FAIL/0 SKIP, native-seven TAP records
7 PASS/0 FAIL/0 SKIP, and local receipt records typecheck/build exit0. Peer
diagnostics show 16 started decodes, source connected and busy/active while held,
then cleanup at pending0; 14/15 successful peers reflect the intentional later
async rejection/single synchronous rejection. These are saved developer runs,
not a second execution by this reviewer.

The source mechanism is consistent with its controlled regression contract.
It has not yet demonstrated corrected C5 reliability in the actual Linux
browser. Existing evidence boundaries and the 150-retry counterexample remain;
no native causality conclusion follows solely from held-peer tests.
