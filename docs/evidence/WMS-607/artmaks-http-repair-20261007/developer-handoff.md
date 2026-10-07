# WMS-607: legacy HTTP recovery correction, 07.10.2026

This is developer verification for renewed independent review and analyst acceptance.
Product source and separate raw results are saved; no distribution/build/install/Telegram
work occurred. Requirements and every frozen test remain unchanged.

## Before implementation

Read refreshed origin/etalon AGENTS, the developer skill, the WMS-607 requirements,
negative acceptance77443 and the new HTTP contract443bcb. In a clean dedicated
sparse checkout, created codex/wms607-artmaks-http-recovery from the pushed HTTP
test-before-code commit443bcbdf19ec3c81c1fc04dbc53a5a9a45ead609.
The real normal-entrypoint Swift HTTP contract repeated the two exact failures
on unchanged productde9: 2 FAIL / 3 PASS, exit1, 4.458seconds.
`developer-precode-red.log` and `before/*.json` preserve the actual observations.
The unsafe-known-key bypass negative control and its three failures were read
from the frozen test-author evidence; they were not rewritten or rerun here.

## Minimal product change

Only tools/print-agent/wms_print_direct_macos.swift changes. Legacy /print requests
explicitly allow retry of an existing validated job whose persisted status is
failed_before_submit. The operation reuses the existing retry method, including
image validation, storage checks and prohibitions for legacy/linked reprint jobs.
Lookup, content/size/parent validation and retry remain under the same recursive
Printer lock; concurrent requests cannot act on a stale failure after the worker
starts or receives a receipt. Worker scheduling and its existing retry-race
protection are unchanged. Protocol2 /print and direct Printer calls retain their
prior behavior via the default false argument.

Legacy error includes the actual stored reason only for failed_before_submit,
so the existing frontend receives the specific printer-service failure without
any frontend change. Unknown, submitting and accepted-receipt cases retain their
existing behavior; no error classification, timeout, journal migration, system
print command, media/digest or external-outcome handling is changed.
Unknown is never converted into a retryable failure by this correction.

## Candidate verification

All automated verification uses real Swift with isolated stores and controlled
external lp/lpstat boundaries; it does not access a host printer.

- HTTP frozen5: 5/5PASS in3.628seconds, `http-five-green.log` + `after/*.json`.
  The original same-key scan recovers to200/accepted after proven service recovery,
  replay returns the same receipt, and actual lp uses media58x40/copies1.
  The specific failed-before-submit reason is in error. Unknown, an actual live
  submitting lp, and accepted receipt never trigger a second external submit.
- Prior frozen6: 6/6PASS in18.465seconds, `frozen-six-green.log`.
  Three real timeouts, true installed .4 receipt process replay, actual dimensions
  and changed-size conflict remain protected.
- Prior parser5: 5/5PASS in2.249seconds, `resolver-five-green.log`.
- Existing native3: 3/3PASS in25.425seconds, `native-three-green.log`;
  optimized binary, crash/disk/unknown/recovery/legacy self-test and HTTP batch.
- Supplemental actual HTTP concurrency probe: after an observed409/
  failed_before_submit with zero lp, restore queue fixture and concurrently send
  eight identical legacy requests with ThreadPoolExecutor(max_workers=8), using
  the unchanged HTTP contract server fixture. All eight return200/accepted with
  Label_Printer-41, exactly one actual lp boundary. Complete raw responses/commands
  and source provenance are in `concurrent-http-recovery.json`.
- All five test/observer files are byte-identical to443bcb; checksums are in
  `source-provenance.json`. `git diff --check` passed.

Reproduce the required suites from checkout on macOS with the existing toolchain:

```sh
python3 tools/print-agent/test_macos_artmaks_http_contract.py -v
python3 -m unittest discover -s tools/print-agent -p test_macos_artmaks_contract.py -v
python3 -m unittest discover -s tools/print-agent -p test_macos_default_printer.py -v
python3 -m unittest discover -s tools/print-agent -p test_macos_native.py -v
```

Physical printing/client cause, updated packages/CI, updater/rollback, system
permissions and Telegram remain unverified/unperformed. Frontend, release652,
main and production are unchanged by this branch. Positive local checks are not
independent review or product acceptance; return this exact SHA to those roles.
