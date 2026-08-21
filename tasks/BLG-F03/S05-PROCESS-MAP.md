# S05 PROCESS_MAP - BLG-F03: safe Git worktree inventory and cleanup decision

## Purpose and scope

`BLG-F03` protects unfinished work while reducing obsolete Git worktree registrations. The
only action in this stage was a read-only inventory: `git worktree list --porcelain`, followed
by branch/HEAD/status inspection for existing paths. No `git worktree remove`, `git worktree
prune`, filesystem deletion, checkout, stash, commit, push, or runtime-code change is in scope.

The inventory was observed on 2026-08-21 from the repository common directory. It contains 43
registered worktrees: 38 paths exist and require review; five paths are absent and Git marks
their registration `prunable`. `EXISTING_REVIEW_REQUIRED` deliberately is not a cleanup
decision: clean status is insufficient proof that the owner may delete a worktree.

## Read-only inventory

| Registered path | Branch | HEAD | Classification |
| --- | --- | --- | --- |
| `/Users/deniscivkunov/Projects/WMS` | `hotfix/supply-link-from-orders` | `3ce7a6f6050ae7d3c35bf6d4f84674f8db9da4b9` | EXISTING_REVIEW_REQUIRED |
| `/private/tmp/claude-501/-Users-deniscivkunov-Desktop-WMS/55b14b5a-ca4a-4583-b9a8-f3468872238a/scratchpad/hotfix-status` | `hotfix/deploy-migration-race` | `8097bc089e9a92c4053ddda619282edd57bacd78` | MISSING_PRUNABLE |
| `/private/tmp/claude-501/-Users-deniscivkunov-Desktop-WMS/55b14b5a-ca4a-4583-b9a8-f3468872238a/scratchpad/wt-e2e` | `lane/e2e-critical` | `c502ccbd52ec21fedbbc0c7df1f35cef9b0aabcf` | MISSING_PRUNABLE |
| `/private/tmp/claude-501/-Users-deniscivkunov-Desktop-WMS/55b14b5a-ca4a-4583-b9a8-f3468872238a/scratchpad/wt-flag` | `lane/chz-feature-flag` | `c155686533ef2de41414ce97cc1a1184f133c35d` | MISSING_PRUNABLE |
| `/private/tmp/claude-501/-Users-deniscivkunov-Desktop-WMS/55b14b5a-ca4a-4583-b9a8-f3468872238a/scratchpad/wt-wb` | `lane/wb-contract` | `c502ccbd52ec21fedbbc0c7df1f35cef9b0aabcf` | MISSING_PRUNABLE |
| `/private/tmp/claude-501/-Users-deniscivkunov-Desktop-WMS/b2b6485f-e0c9-4162-a5df-a138b918cf1f/scratchpad/wt-etalon-baseline` | `DETACHED` | `8c2e2c05e2bbd4aea20901b917c0860f2b50537b` | MISSING_PRUNABLE |
| `/private/tmp/wms-prodfix` | `DETACHED` | `85f632766beaea8d69dec393fb5b66f517eb3b72` | EXISTING_REVIEW_REQUIRED |
| `.worktrees/boxqr` | `hotfix/boxes-print-all-qr` | `ebd329fad1dfebeb50723908fe18ae7043257cad` | EXISTING_REVIEW_REQUIRED |
| `.worktrees/chz-bulk-required-20260813` | `hotfix/chz-bulk-required-main-20260813` | `abcd12cf18bd713ff3a0fc2c412b8bbf669745ec` | EXISTING_REVIEW_REQUIRED |
| `.worktrees/codex-mp-dashboard-e2e-20260815` | `codex/mp-dashboard-e2e-20260815` | `03bc475cb202ccda9ec0350c5a72a941b8a9839a` | EXISTING_REVIEW_REQUIRED |
| `.worktrees/fbs-followups-20260812` | `backlog/fbs-followups-20260812` | `55e234a2814df59f01477deda4cae0a3aed169d6` | EXISTING_REVIEW_REQUIRED |
| `.worktrees/fbs-visibility-warehouse-wb-retry-20260812` | `hotfix/fbs-visibility-warehouse-wb-retry-20260812` | `46b850895bbaca5d74b3a939d0da2b673a632ea9` | EXISTING_REVIEW_REQUIRED |
| `.worktrees/fbs-warehouse-filter-20260812` | `feat/fbs-warehouse-filter-20260812` | `5d514402320b028104d5ccaeae26c179b3cddaeb` | EXISTING_REVIEW_REQUIRED |
| `.worktrees/fbs-warehouse-filter-main-20260812` | `hotfix/fbs-warehouse-filter-main-20260812` | `51b88d7de72c9550edc2b83485cb5515a0008578` | EXISTING_REVIEW_REQUIRED |
| `.worktrees/fbs-wb-warehouse-filter-label-20260812` | `hotfix/fbs-wb-warehouse-filter-label-20260812` | `08abac85cf4f9d71436a9d7b16bb283bcd655270` | EXISTING_REVIEW_REQUIRED |
| `.worktrees/ff-inbound-create-20260812` | `feat/ff-inbound-create-20260812` | `f2eaa2784e37123023edcab22d0af6d3fe965fe7` | EXISTING_REVIEW_REQUIRED |
| `.worktrees/ff-inbound-create-prod-20260812` | `hotfix/fbs-openapi-contract-20260812` | `f87c9bdae70ede3a2dbe57855e19074012613979` | EXISTING_REVIEW_REQUIRED |
| `.worktrees/fix-auth-staff-e2e-20260815` | `fix/auth-staff-e2e-20260815` | `b200e730982c2104cdd4624721f2af4f3d297c27` | EXISTING_REVIEW_REQUIRED |
| `.worktrees/fix-fbs-status-sync-supply-create-hang` | `fix/fbs-status-sync-supply-create-hang-20260810` | `d872eea45e6f6e3b4dc9405db200c2906696ebd9` | EXISTING_REVIEW_REQUIRED |
| `.worktrees/fix-wave2-mp-regressions-20260815` | `fix/wave2-mp-regressions-20260815` | `9ecd31fa7967893dac56bdce4a62a1c5a32c5992` | EXISTING_REVIEW_REQUIRED |
| `.worktrees/hotfix-fbs-100-orders-20260820` | `codex/hotfix-fbs-100-orders-20260820` | `d55dd53da02d241138f51b9e09c63b9f5722996f` | EXISTING_REVIEW_REQUIRED |
| `.worktrees/inbound-sheet-20260819` | `fix/inbound-receiving-sheet-20260819` | `0ef2bdf4ba7ff2ebe8ee0df509119b7900edd83c` | EXISTING_REVIEW_REQUIRED |
| `.worktrees/integration-wave0-20260814` | `integration/wms-wave0-20260814` | `45d7fcc5b85072bc9e9d2cbe1fa240ee69c7e80f` | EXISTING_REVIEW_REQUIRED |
| `.worktrees/limit-fix` | `DETACHED` | `9a99af42205b36568154c515fd4b45975b77f048` | EXISTING_REVIEW_REQUIRED |
| `.worktrees/packing-optional` | `fix/packing-optional-20260819` | `f05207c605ddce9ae7029e8cba6ff902e2d6f1f1` | EXISTING_REVIEW_REQUIRED |
| `.worktrees/picklist-size` | `fix/picklist-size-20260819` | `8259901bdf3c7ea70f908b37635de7fc21eaf4ef` | EXISTING_REVIEW_REQUIRED |
| `.worktrees/pipeline-unified-v2` | `codex/wms-pipeline-unified-v2-20260820` | `4662c18602a001d71b8f92b16210dc6f6b59f013` | EXISTING_REVIEW_REQUIRED |
| `.worktrees/portal-logos-20260811` | `brand/portal-logos-20260811` | `a7668584593188cad10e44f068722fc2a90ed6b4` | EXISTING_REVIEW_REQUIRED |
| `.worktrees/portal-logos-live-20260811` | `brand/portal-logos-live-20260811` | `443e9445d7f41da8dbbc77c35012024b59d579cf` | EXISTING_REVIEW_REQUIRED |
| `.worktrees/portal-logos-prod-20260811` | `brand/portal-logos-prod-20260811` | `03e1f78a5bca79b21be9a011f1f381b2a9cafe16` | EXISTING_REVIEW_REQUIRED |
| `.worktrees/product-operations-ux-20260812` | `iteration/wms-product-ux-features-20260812` | `2d1a43fddcdd2366446486cd4068e31260212afa` | EXISTING_REVIEW_REQUIRED |
| `.worktrees/review-fixes-20260816` | `review/pick-and-binding-fixes-20260816` | `bce13a9dea24c3db85f615f3e789689fb1ae8622` | EXISTING_REVIEW_REQUIRED |
| `.worktrees/seller-hs-20260819` | `fix/seller-honest-sign-sync-20260819` | `1db75c4c215e66f24306e8575e01b7aafc474927` | EXISTING_REVIEW_REQUIRED |
| `.worktrees/system-review-architect-20260812` | `review/system-wide-architect-20260812` | `332deafec6c79769bfe2e547baa52ce6763b7b43` | EXISTING_REVIEW_REQUIRED |
| `.worktrees/system-review-orchestrator-20260812` | `review/system-wide-orchestrator-20260812` | `8ae4c96d283a311e8e099519a0a4abeee1c5b489` | EXISTING_REVIEW_REQUIRED |
| `.worktrees/system-review-product-20260812` | `review/system-wide-product-20260812` | `28ce2f7852c53f0abb5b181559243abf190a8a8b` | EXISTING_REVIEW_REQUIRED |
| `.worktrees/system-review-teamlead-20260812` | `review/system-wide-teamlead-20260812` | `f0588d3cc8b0988fb115a2cb46e0f419f920647e` | EXISTING_REVIEW_REQUIRED |
| `.worktrees/wave2-mpfbo-packaging-20260815` | `iteration/wms-wave2-mpfbo-packaging-20260815` | `7b955019d1ae48ed7e7e047cce9025a5a523084e` | EXISTING_REVIEW_REQUIRED |
| `.worktrees/wave2-shipment-calendar-20260815` | `iteration/wms-wave2-shipment-calendar-20260815` | `34b38cf35196446e592c7fb67c8d02454430b760` | EXISTING_REVIEW_REQUIRED |
| `.worktrees/wb-supply-mirror-20260819` | `fix/wb-supply-mirror-20260819` | `0dd20ad5850fe6b5d618416662f460a60f1196d4` | EXISTING_REVIEW_REQUIRED |
| `.worktrees/wms-fbs-strict-20260814` | `iteration/wms-fbs-strict-20260814` | `be80e908fc4ad1058052e0bcd41a052ca05c278c` | EXISTING_REVIEW_REQUIRED |
| `.worktrees/wms-product-gate-mandatory-20260814` | `process/wms-product-gate-mandatory-20260814` | `2fb61a39f4659df4bf4411924bbf3d5bc4dc38b6` | EXISTING_REVIEW_REQUIRED |
| `.worktrees/wms-system-review-protocol-20260812` | `docs/wms-system-review-protocol-20260812` | `c964e0e8a47e690d7938e486073bd40d74bf0cc7` | EXISTING_REVIEW_REQUIRED |

## Safe decision process

1. Re-run the read-only inventory immediately before any later cleanup attempt. A registration is
   classified `EXISTING`, `MISSING_PRUNABLE`, or `MISSING_UNREGISTERED`; the table records
   path, branch (or detached HEAD), and commit. Any command error, changed HEAD, or disappeared
   path restarts review for that record; it does not make the record eligible.
2. For every existing worktree, record tracked changes with `git status --porcelain=v1`,
   untracked files separately, and the exact HEAD. Dirty or untracked content is a hard no-delete
   branch. Preserve it first in an owner-approved, recoverable location and capture a manifest of
   paths, content hashes, and restore instructions. A stash alone is not sufficient evidence
   because its ownership and restore target are ambiguous.
3. For a clean worktree, compare its branch and HEAD to retained references. A detached HEAD,
   commits not reachable from a retained branch, a branch without an upstream, or a diff that is
   not provably represented by another retained commit is a `UNIQUE_HISTORY_OR_DIFF` hard
   no-delete branch. Preserve reachable proof or create an owner-approved archival reference
   before reconsidering it.
4. Only after steps 1-3 are evidenced may a record be proposed as `PRUNABLE_CANDIDATE`. The
   proposal must name the worktree, branch, HEAD, dirty/untracked result, reachability result,
   preservation location (when applicable), and a fresh inventory timestamp.
5. The owner alone authorizes any state-changing cleanup with an explicit list of candidate paths
   and exact command scope. This worker has no deletion authorization. `git worktree remove`,
   `git worktree prune`, `rm`, branch deletion, force removal, and cleanup of `/private/tmp`
   are forbidden until that approval is recorded and a later execution stage is assigned.

## No-delete conditions

Do not delete or prune when any of the following is true: the worktree exists and is dirty;
untracked files exist; HEAD or branch changed since inventory; ownership is unknown; the worktree
is detached; unique commits/diffs have not been proven recoverable; a command produced an error;
another worker may hold a lease; the candidate list is not explicitly approved; or cancellation
was requested. The five `MISSING_PRUNABLE` registrations are not automatically removable: their
branch/HEAD reachability and owner authorization are still required before pruning metadata.

## Empty, error, repeat, and cancel traces

- **Empty:** no registrations, or no candidates after safety checks, produces a dated empty
  inventory and closes this cleanup attempt without deletion.
- **Error:** a failed Git command, unreadable path, or status race records the command, target,
  and error and leaves the record `REVIEW_REQUIRED`; no fallback force command is permitted.
- **Repeat:** a repeat re-inventories all registrations and invalidates older candidate decisions
  when path, branch, HEAD, status, or reachability changes. It is read-only until a new owner
  authorization binds a fresh candidate list.
- **Cancel:** stop after the current read-only observation, preserve all evidence, issue no
  cleanup command, and leave all registrations and directories untouched.

## Handoff to S06

S06 must turn this process map into a gap analysis that names reusable Git inspection commands,
the required evidence schema, the authority boundary, and rejected alternatives (blind `prune`,
force removal, and treating clean as deletable). It must not schedule deletion.

## S05 verdict

`PROCESS_MAP_READY` is appropriate only after controller review accepts this replacement map.
The current controller state remains `WAITING` on
`BASELINE/PROCESS_MAP_GENERIC_FOR_WORKTREE_SAFETY`; this document is remediation evidence, not a
self-issued unblock, receipt, or stage transition.
