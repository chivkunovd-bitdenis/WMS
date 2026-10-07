# Independent remaining-delta evidence

Immutable candidate: `c4faeb3a58c42e2d2e04bff790230532e8970b90`; prior candidate `6da0eb63b143d71d789c25a20ee04e3c49cbf14b`. Overall **FAIL**: the new WMS-680 full-name geometry check combines two distinct actual PDF table rows.

Own scope execution in a sparse detached exact-SHA fixture:

```sh
python3 -m pytest -q backend/tests/test_wms684_586_scope_contract.py --junitxml=../docs/evidence/WMS-652/remaining-review-c4fa-20261007/scope.xml
```

`scope.log` and `scope.xml`: 7 PASS. Fixture restored only immutable source files; it reused existing dependencies without installation. The old four definitions were preserved; two previously failing task-title canaries now reject and 6840 remains a separate task. The fixture is removed after review.

Reproduce the new defect from the permanent checkout containing the Git objects:

```sh
node docs/evidence/WMS-652/remaining-review-c4fa-20261007/pdf_cell_probe.cjs
node docs/evidence/WMS-652/remaining-review-c4fa-20261007/real_pdf_cell_probe.cjs
node docs/evidence/WMS-652/remaining-review-c4fa-20261007/pdf_before_control.cjs
python3 docs/evidence/WMS-652/remaining-review-c4fa-20261007/audit.py
```

The first probe tests four bounded word scenarios. The second uses one actual installed Chrome process and pdftotext on `cross-row.html`, producing `cross-row.pdf`/`.xml`: one row has a name prefix, another a suffix, separated by 121.769526 points. It executes the exact immutable helper functions, with equivalent strict assertions, and confirms the full geometry checker accepts this invalid combination. The third executes the original helper on the same PDF and confirms rejection. Successful probe exit means the **FAIL is reproduced**, not that the candidate passed. Only the probe's own browser process/profile is stopped/removed.

JSON, stdout and stderr are preserved for each probe. Node 24.13.1's TypeScript-strip warning is recorded; no package installation was needed. `audit.py` reads only Git blobs and retained evidence. It verifies original policy preservation, 1644 current IDs, exact new additions, pending hash/canary registration, old scope/test titles, 24 source cases WMS-673, renderer's exact two replacements and product-equivalence of proposed P. Its bounded PASS does not approve the candidate or activation.

`published-proposal.json` is the proposal in immutable c4fa, not a completed activation. `pending-final-handoff.json` and its provenance record the authorized ROOT control-plane handoff: final SHA/P null, outstanding 684/658/template work. No dirty code was reviewed as immutable.

`coordinator-673-raw.json` is a real older five-case Linux receipt, not own execution and not proof of new 5868. Companion metadata pins diagnostic SHA 9f96c0c; its test bytes do not match this candidate. The mismatch and file hashes are explicit in `coordinator-673-provenance.json`. Published 24f0 and 17b0 execution counts remain attributed to their original authors; no replacement receipts are fabricated.

No unchanged full re-review, full suite, new dependencies, product edits, main/etalon changes, secrets or production access.
