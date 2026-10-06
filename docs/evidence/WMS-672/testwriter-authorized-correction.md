# WMS-672 — separate TESTWRITER672 handoff

Business authorizer: `6f1b196b4cb09091df341e79f6c663efb4d721d4`, requirements v2;
product pinned unchanged: `0e6a7fbc3eb11f951febf972b35c6e117c42678a`.
This is an authorized business-assertion mutation and helper scheduling correction,
not fixture-only repair, product acceptance, independent review or product fix.

Exact Git blob identities before → after:

- browser contract: `13d6d57bf1734f90d45598428997e8cf84ec3f29` → `ba1a936a2951970c71edb2bd8c1dc441038f7b72`.
- DOM C5 contract: `0fe83393d9a981f7a67c8c6df01c134703db6c7a` → `d29e1134cf728bb114c3c35a868df2fba2b7ce8e`.

Scope: bounded native PDF helper decode of every original image; C4/C6 actual
parallel held group (>1), responsive event loop and zero transfers/marks under
hold, all N before one transfer; C5 actual error150/busy clear, equivalent DOM
all-N correction. C5 additionally tests last-group error299 and complete explicit
retry. C4 checks animation-frame progress, suspended-frame fallback, and assertion
negative controls for serial overlap, premature/double transfer, missing decode,
early/incomplete/duplicate marks, plus real malformed PNG rejection in helper.
C6 waits for all original box IDs marked once in order, complete persisted attempt,
same attempt ID and HTML as transfer. Native decode failures are propagated.

N200/300, DPR4, PNG quality, original text/order, 58x40 PDF page count/size and
first/middle/last raster CODE128 checks remain unchanged. Other C3/C7/C8/C10 code
is unchanged. DOM C5 is corrected but not part of the requested browser rerun;
no local browser/build/npm ci/new database. Syntax checked with `node --check`.
Negative snapshot assertions prove the assertion functions reject those outcomes;
they are not product mutation runs and must not be described as such.

Next: publish this correction commit before remote proof, then pin exactly this
contract in the dedicated WMS-672 workflow on the immutable product. Rerun only
previously failed C1/C2 300 inbound/return and C4/C5/C6, with added subchecks inside
those cases. Existing 200 C1/C2 definitions remain but are not rerun. No C7/C8 rerun.
Their earlier PASS covers original attempt/source preservation and no second
transfer only; it does not prove all 300 technical marks completed or physical paper.
Independent product + authorized correction review must follow; tester does not
approve own changes. WMS-673 requirements/workflows/artifacts are owned elsewhere.
