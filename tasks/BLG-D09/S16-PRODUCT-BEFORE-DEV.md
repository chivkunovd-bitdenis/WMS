# S16 CARD_PRODUCT_APPROVAL_BEFORE_DEV - BLG-D09

## Product verdict

`PRODUCT_APPROVED_FOR_DEV`

Product approves development of the single unchanged vertical card
`BLG-D09-C1`. The approved result is one fail-closed release proof in which a
full 40-character Git SHA remains bound to one immutable manifest, all promoted
artifact digests, every applicable runtime identity, and the concrete frontend
asset loaded by the browser. A successful command, health response, screenshot,
branch name, target-side checkout, or partial service update cannot substitute
for that chain.

The S11 product contract, S12 card, S13 architecture, independent S14
falsification, repaired fourteen-case S15 package, and independent
`CASE_AUDIT_PASSED` verdict are coherent and preserve the same outcome. The two
previous case gaps are closed before Dev: `BLG-D09-AC13` stops an incompatible
or unproven migration before launch, and `BLG-D09-AC14` proves that marketplace
synchronization is outside release success using an egress-denied local fake.

## Exact approved package

- Baseline SHA: `69c271678782d7dcfa39df97cd905cbee1678727`
- Branch HEAD observed at the gate: `5825ec2569aa93612cf71033746625c738113785`
- `S11-PRODUCT-CONTRACT.md`: `sha256:59ab6e6e6606f4d9f1e051175ebbefb019bb0f602ffcbdc1f4ecd04f8defe336`
- `S12-TASK-CUT.md`: `sha256:034e5db9a73f2bbdc35274fbf7d5cbd8ef5700b17b4e862c7df7784ee3300666`
- `S13-ARCHITECT-PLAN.md`: `sha256:541840a7d81c39ecdd77d064bc8fcde03e018e63ac0a176adc84326b2202db74`
- `S14-ARCHITECT-FALSIFICATION.md`: `sha256:d9b5e299c2310be6f047b4e096d3aecc824a6e6f99c4aa294388dea6e88c857d`
- `S15-CASE-FACTORY.md`: `sha256:e32fcc483b03e7d178f2c8b1775479ee315889eb5c8bf44d3f2b804339ec972c`
- `S15-CASES.json`: `sha256:26c413174c26d7638296c9bb6c700ec48bd72b3aa6fc4e70f75fbb05f2686ed7`
- `S15-CASE-AUDIT.md`: `sha256:dd5ec597e513514ccebfca81ceaf5f77581e30b260bc9acb74d660d3a25c152c`

Controller `next` reports S16 / `pipeline-product` / `RUNNING`, and controller
validation passes through S15. Any later change to these approved inputs,
their oracles, the service identity matrix, or the browser/rollback boundary
invalidates this Product verdict and must follow the controller-directed
rework route.

## Approved Dev boundary

S18 may implement only the bounded release-controller work allocated by S12
and S13:

- validate one explicit lowercase full SHA in a clean isolated builder;
- build once and produce a strict immutable manifest covering backend, web,
  migration and complete service identities plus frontend entry/asset hashes;
- promote only manifest-listed artifacts without target-side source selection
  or rebuild;
- fail closed when any archive, image, revision, service, migration, runtime,
  browser asset, or rollback identity is missing or mismatched;
- read back API, migrations, Celery worker, Celery beat and web identities;
- produce sanitized local browser-proof instrumentation that binds the final
  `index.html`, loaded hashed asset bytes and visible screen to the manifest;
- retain and rehearse rollback to one named previous immutable package;
- remove marketplace synchronization from the atomic release-success result;
- bind all fourteen GOLD cases to isolated local executable fixtures without
  changing their approved oracles.

The implementation must preserve the serialized file/resource locks from S13.
It may not widen into general CI/CD redesign, operator-flow changes, a service
worker, cache-policy implementation owned by BLG-D12, production execution,
secrets, live WB/Ozon calls, or an alternative mutable release route.

## Preserved release blocker

`BLK-RELEASE-001` remains open, unchanged, and owned by `release-owner`, with
`resume_stage: S23`. This S16 approval deliberately permits S17/S18 work but
does not close, resolve, defer past, or bypass that blocker. S23 must not pass
until the controller records and verifies its minimum closure artifact:

- exact candidate SHA and immutable manifest digest;
- manifest-linked asset URL and asset byte hash;
- effective root/index cache headers;
- hard-reload proof; and
- confirmation that the visible screen came from the candidate artifact.

Planned cases and local instrumentation are not closure evidence. S26 may only
produce `READY_FOR_RELEASE` without separate owner authorization for one exact
candidate SHA. S27 deployment, S28 production monitoring, production changes,
live systems and credentials are outside this verdict and were not performed.

Blocker preserved for S23: `BLK-RELEASE-001`.

Agent identity: `codex-pipeline-product-blg-d09-s16`
