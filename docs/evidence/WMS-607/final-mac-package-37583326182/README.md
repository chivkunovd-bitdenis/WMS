# WMS-607 final-source Mac package receipts — run37583326182, attempt1

**Overall FAIL: Intel artifact creation timed out; both packages are not available.**
This is a read-only collector receipt by the same separate Sol6.1/high reviewer
session01a11370, not new source review, analytical acceptance or implementation.

- SOURCE: `a475a7342c0da72dd49b2990bd998c522ecc2c2b`.
- HARNESS: `1c2bddd844ff6baf331eae53b3a44304d834cc01`.
- Ref: `codex/wms607-direct-updater-mac-package-20261007`.
- Actual run: https://github.com/chivkunovd-bitdenis/WMS/actions/runs/37583326182,
  attempt1, completed **failure**.

## Actual per-architecture outcomes

ARM job112667738423 completed success. Its original artifact11465731935 is
`WMS607-Direct-arm64-a475a7342c0da72dd49b2990bd998c522ecc2c2b-37583326182-1`.
The exact downloaded wrapper is retained at `artifacts/arm64/original-wrapper.zip`,
229059bytes, SHA256
`0a4de3fbeece3506dcfdfeb8e954c8ea06d8d3452f5e61944427c40882ae4906`, equal to
GitHub API artifact digest. All34 wrapper files were saved byte-for-byte under
`artifacts/arm64/payload`, with all member sizes/hashes/CRC/attributes in
`artifacts/arm64/member-manifest.json`. It also lists every native archive member.
No original wrapper, payload member or native archive was deleted.

Actual ARM raw reports: updater10 + rollback4 + oldnative/HTTP/resolver19 +
startup3 = **36PASS,0FAIL,0ERROR,0SKIP**, exactly36 unique IDs. The three old report
sets exactly equal accepted SOURCE baseline IDs; startup3 exactly equals its
frozen contract. Source/hash fields match SOURCE/HARNESS, unchanged Swift/tests,
and exact corrected updater. There is no substitution of old375799 reports.
Original source.txt, harness.txt, environment.txt, archive.json, XML, logs and raw
provenance are retained under `payload/_temp/wms607-package`.

Publisher's **original ARM native ZIP**, byte-identical to the wrapper member:

`artifacts/arm64/payload/WMS/WMS/tools/print-agent/dist-console/WMS-Print-Console-Mac-arm64.zip`

Size181837bytes; SHA256
`ae50b3fcbb269e12f77611ff05652af2a9ce5681a3ed6477e389d53325f7467b`.
Its actual build.json is SOURCEa475, darwin/arm64/direct, console=true,
physical_print_verified=false. Mach-O64 CPU header is actual ARM64; executable
and every member have recorded hashes. Embedded updater equals the exact Git
SOURCE bytes. Actual CI builder/codesign/provenance steps succeeded, and original
build.log plus self-test.log confirm native package self-test after unpacking.
Nothing was executed locally by the collector.

Intel job112667738205 completed **failure at artifact upload**, not a failed test.
Its test steps, exact36 ID/no-failure/error/skip validation, native builder,
unpacked self-test and archive provenance steps all completed **success** in the
original job API/full log. The failed step was
`Preserve exact native archives and all actual raw checks`. Exact error:

`Failed to CreateArtifact: Failed to make request after 5 attempts: Request timeout: /twirp/github.actions.results.api.v1.ArtifactService/CreateArtifact`

These five attempts are upload-action internal requests in this single attempt1,
not collector reruns. The action found34 files and the expected Intel artifact
name, but no Intel artifact exists in the final run API. Therefore **Intel raw
XML/payload, source.txt/harness.txt/environment, native ZIP and archive SHA cannot
be independently read back or handed to the publisher**. Do not turn successful
job steps into a downloadable verified Intel package. Failed case: none; failed
operation: CreateArtifact. Both original full job logs and complete run/attempt/
jobs/artifact API responses are retained. `result.json` explicitly keeps Intel
payload verification false and archive hash null. No package run was retried.

## Verification and retention

`verify-receipts.py arm64` consumes only original bytes/API records, checks all36
actual IDs/flags, raw source identities, archive metadata/checksum/size, native
CPU/magic, embedded updater, payload byte readback and actual job outcomes. It
never runs native executables, tests, builds or dispatch. `payload-manifest.json`
hashes every saved evidence file except itself, including full job logs and
original API responses; wrapper/member identity is separately recorded.

No source/tests/requirements/workflow, main/etalon/common652/675, other worktree,
dependencies or account settings changed. Existing stashb396 is preserved. Fresh
origin/etalon AGENTS was read. Historical sourcea04 run37579919987/71640 remains
FAILED (IntelUC4 timeout); no old artifact was overwritten or waived. This new
upload transport failure does not diagnose that historical CPU/timing failure.

No public release/immutable updater manifest, client installation, permissions,
physical58×40 paper/QR or ArtMaks message is claimed. The collector has no sender
or publisher authority. Integrator receives the preserved ARM ZIP and strict
Intel missing-payload result; delivery awaits a recoverable verified Intel payload.
