# WMS-607: frozen ArtMaks test contract before correction

Test-only source branch starts at refreshed `origin/etalon`
`4b298efc95be7b4b6b7fe5665be9f3671f1fe747`. No product source, printer settings,
packages, CI, release, operator data or Telegram messages were changed.
The independently recorded findings are `dfc4c54178063e4ffb3bb24ab3e4d31e1cff51a3`
`docs/evidence/WMS-607/artmaks-installer-findings-20261007/technical-review.md`.

## Exact sources run

| Source | Commit | Swift SHA256 |
|---|---|---|
| defective | `ed05387190c0b50829ec1e0f3698c9bd8dabe273` | `462e5a33020226b31c88098d527d04ebfe70af238d873f51889936b53bec09c3` |
| stable | `9a33b651c309796707053e1056c7f80dff7194d5` | `d47614beef415b86c49cdad0d531e642028c0cadf86652701736ada6385210ad` |
| journal | `3348db9c61d62dfb8038be3b432a293f27ce9a1e` | `83acdbc6fdf2f4128b83096f18e1d14a367b6eb7b0e4dba4c98e2673c6e46b32` |

The test compiles real Swift before HTTPRequest: Process timeout, resolver, size,
digest, journal and Printer are unchanged. Only `/usr/bin/lpstat` and `/usr/bin/lp`
are redirected to controlled executable fixtures; no host queue is accessed.
The candidate can use legacy or journal Printer signatures; the adapter only
drives their real enqueue/process/retry methods. The unused journal CUPS observer
symbol is bound to a fixture, but no observation runs. No timeouts are stubbed.

For installed-version compatibility, the actual pinned stable .4 source runs in
a separate process and writes its real direct-jobs.json through real Printer.
The candidate then reads that same file in two subsequent processes. Tests require
the saved receipt and zero resolver/lp calls. This checks actual persisted bytes
and hash semantics, not a copied digest expression. The dimension check captures
the actual lp process arguments, not `printArguments` source text.

## Results

* `defective-red.log`: six tests, five expected FAIL and one PASS, 18.999 s.
  Queue validation times out then yields defaultmissing despite successful general
  `-p`; list timeout yields generic unavailable; media absent; .4 receipt rejected
  as changed content; changing dimensions incorrectly replays the original receipt.
  Existing default timeout/retry/restart behavior passes.
* `stable-preservation-green.log`: real public stable .4 passes all three
  preservation tests: actual 58×40 media, restart receipt and dimension conflict.
* `journal-preservation-green.log`: current investigated journal source3348 also
  passes the same three preservation tests; this does not select it for release.

The preservation failure is proven by the real defective older source, which
reintroduces exactly the absent media/bare-PNG identity. No product file was
mutated in the checkout. Existing five resolver tests in ed053 are preserved at
`tools/print-agent/test_macos_default_printer.py`; their prior RED→GREEN evidence
is referenced by findings dfc4c541. They have not been rerun or rewritten here.
Existing journal3348 `test_macos_native.py::NativeRuntimeTest.test_compiled_store_crash_faults_and_retry_self_test`
and native self-test already cover journal recovery/legacy decoding; this new
contract specifically adds the real installed-source producer and process receipt.

## Reproduction and handoff

On macOS with existing Swift compiler, no dependency installs:

```sh
git show ed05387190c0b50829ec1e0f3698c9bd8dabe273:tools/print-agent/wms_print_direct_macos.swift > /tmp/wms607-defective.swift
WMS607_SWIFT_SOURCE=/tmp/wms607-defective.swift python3 -m unittest discover -s tools/print-agent -p test_macos_artmaks_contract.py -v
python3 -m unittest discover -s tools/print-agent -p test_macos_artmaks_contract.py -v
```

The first run is expected RED; the second targets the checked-out product source.
`WMS607_SWIFT_SOURCE` accepts a selected exact candidate extracted with git show.
For the preservation baseline, run `-k label_passes`, then `-k size`, against stable
9a33 and journal3348. Temporary copies of product sources were removed before commit;
the immutable Git commits above are their recovery source. Test temp binaries and
fixtures are removed by TemporaryDirectory; they are not distributed packages.

Developer must choose/justify a current independently reviewed Direct base,
transfer resolver-only changes preserving dimensions, receipt identity, journal
and unknown-outcome protections, and make this unchanged contract GREEN. The
five existing parser regressions remain required. Test-author reporting does not
replace review/analyst acceptance, package CI, exact artifact checks or physical
printer confirmation. No update command or package has been produced here.
