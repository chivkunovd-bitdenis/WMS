# WMS-607 actual Mac package receipts37579919987

**Run FAIL; ARM package proven, Intel package absent. No public promotion performed.**
Single actual workflow_dispatch37579919987/attempt1 started06:08:38UTC. Harness
HEADd0a0be566e2fd6ea10c64c650875d72319f9a103/ref
codex/wms607-direct-updater-mac-package-20261007; pinned checkout SOURCE
 a04a7b35f1e866c1283bdc46fff2d41eaf68b4d6. API identity and both source.txt/harness.txt
match these exact values. Both document checks passed. API/job/full logs preserved.

| Actual job | Artifact ID | Executed cases | Result | Native payload |
| --- | --- | --- | --- | --- |
|112656988359, macos-14 arm64|11464690557|10 updater +4 rollback +19 existing|33PASS;0 failure/error/skip/duplicate|WMS-Print-Console-Mac-arm64.zip|
|112656988553, macos-15-intel x86_64|11463988544|10 updater|9PASS/1ERROR;0 failure/skip/duplicate|NOT BUILT|

Original artifact-wrapper checksums (distinct from the native payload):
- arm64, artifact 11464690557: 225269 bytes,
  SHA256 6bc10c9873346465fa8fc4ce1573eb2974e72303060e82b8cfe8226930b3d630.
- x86_64, artifact 11463988544: 33143 bytes,
  SHA256 b9e0f7a2b76fde631cddafba6e02fa1d30dd4e7c56e266533b1acd44f09e1be5.

All actual executed testcase IDs equal the corresponding accepted baseline sets
from SOURCE docs/evidence/WMS-607/updater-stop-fix-20261007/updater.xml,green.xml,
existing.xml. ARM executes all33 unique IDs. Intel executes the exact10 updater IDs,
then job stops; the4 rollback/19 existing cases are NOT_RUN, not passing or waived.
Their CI steps and builder/provenance checks are skipped.

Intel error: test_macos_direct_updater_contract.UpdaterContract::
test_uc4_foreign_port_owner_and_health200_wrong_process. run_update subprocess
raises subprocess.TimeoutExpired with timeout15s at contract line255, called from
UC4 line361. Full traceback/update log/native fixture evidence retained. This is
an actual ERROR, not a presumed infrastructure issue. No handling/timeout/test
change, retry or waiver performed. Packaging run remains failed.

ARM actual Darwin23.6.0/arm64, Python3.13.15, Swift5.10; Intel actual Darwin24.6.0/
x86_64, Python3.13.15, Swift6.1.2. Full environment receipts are original artifacts.
Original ARM builder/unpacked archive self-test and provenance step PASS. Pinned
source builder performs codesign strict verification, ditto unpack and self-test;
build.log contains the successful native package self-test. CI also performs
package self-test, lipo exact arch and codesign --verify --strict; all succeed.
No native program was executed locally by this collector.

ARM immutable payload receipts:
- ZIP181772 bytes; SHA256
  85326f28ff7702042c56cee7bb23c7b81fd0f09b00f921ede23bd184b86f85ab.
- Native executable SHA256
  e7f974c13e9751116fb57e9e060d4bf17455aa016c8e7bf98c8413fe60db99c5.
- Embedded build.json SHA256
  ea622dbc5dd8424665620331c2663b03eda2cecb57af840b9be081e981f7e57c.
- Updater SHA256
  89b3f02b4ef80a3ad1703aff4a1c4f3e89b76c4040b41c2b5595e7fc745e31ed;
  archived bytes exactly equal Git SOURCE tools/print-agent/update_macos_direct.sh.

Archive.json hash/size and embedded build.json equality verified. Metadata is exact
SOURCE, darwin/arm64/direct/console=true/physical_print_verified=false. Native Mach-O
64-bit executable CPU0x0100000c/filetype2, executable mode and code-signature load
command structurally checked without execution; executable size/header details in
ledger.json. Original payload ZIP preserved byte-for-byte under raw/arm64; no
repacking, substitution or fake Intel receipt. manifest-candidate-data.json records
only immutable actual ARM fields, missing x86_64 and public_release_ready=false.
No public URL fabricated; no release/client installation/physical print claimed.

All29 ARM and16 Intel artifact members saved. Both original artifact wrapper
checksums and every member's original size/SHA256/recovery proof are in
raw-manifest.json. JSON compressed losslessly; payload ZIP kept unchanged. Full
job logs/run/job/artifact APIs, JUnit IDs/results/native evidence/source identities
are permanent Git evidence. provenance-manifest.json hashes the top-level receipts.
Only derived download wrappers removed after Git+remote+ALL manifests verify;
original payload/evidence preserved. No other checkout/cache/Git objects cleaned.

Collector owns only this docs directory on codex/wms607-mac-package-receipts-20261007.
No source/harness/product/test/handling/main/common/607developer change, no local
build/runtime/test, dispatch/rerun/public promotion/deploy/Telegram/provider action.
Integrator-owned primary production run37579921135 is separate and not evaluated
here. Next boundary is the concrete Intel UC4 ERROR; this evidence authorizes no
waiver or rerun and supplies no complete dual-architecture release proof.
