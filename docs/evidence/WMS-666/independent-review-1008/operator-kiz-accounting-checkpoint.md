# WMS-666 — bounded operator KIZ accounting prerequisite review

**Confirmed P1 process defect; overall NO-GO continues.** This is a targeted follow-up to `c933b1a0dc11ebf9438732bd4a602cb2486e2942`, not accepting R and not a trusted-P designation. No product or frozen test was changed by the reviewer.

The reviewed `backend/app/services/fbs_kiz_service.py` blob is `5e73abaca93b6e5cd14e4fdec215a79a919ffe6c`, last changed by `fa75678717216e54df4e85287739364e5dab0ae7`. Its `_packaging_line_for_order` helper matches the deployed `212f19d548496fef7baf75c83204b771e304281b` helper exactly. The inherited prerequisite becomes reachable after the newly supported manual tape prepares an actual order binding while the accounting task remains absent.

The reviewer traced `/operations/fbs-orders/kiz/commit` through `commit_kiz_pairs` into the current-code branch. Neither API nor caller automatically creates a task. `_ensure_available` permits a PRINTED/RESERVED code already bound to this exact order and value. In `_commit_pair`, the same-value branch then calls `_packaging_line_for_order` before changing that real code to APPLIED and recording its event. The helper only reads an existing fulfillment/task line; absence raises `packaging_line_not_found`. Thus successful validation does not imply this commit can complete without an accounting record.

This was kept as a source hypothesis until the independent testwriter froze and executed the actual API sequence in commit `84864e0e48318019474bb4c4e76b9711a69f0243`:

`test_wms666_workspace_marking_pool.py::test_taskless_printed_current_kiz_can_be_applied_without_creating_task`

The writer reports RED on cedb: real tape endpoint HTTP200 prints one current CIS and sends the same value to accepted fake WB; same-order/same-value validate returns HTTP200 `{ok:true,hints:[]}`; commit returns HTTP200 with row error `packaging_line_not_found`. The reviewer independently read the entire frozen test diff and verified it contains the real API calls, no manufactured task, and the asserted postconditions. This checkpoint attributes execution to the independent testwriter; it does not claim a second reviewer-run API test or live WB acceptance.

The contract requires the existing code to become APPLIED with the same marking/code identity and `newly_bound=false`, exactly one APPLIED event with source `packing_fbs_print`, no fabricated task/line event references, absent task unchanged and stock unchanged. Its fixture has no document number; production must retain the real supply/document context when available. The same code must not be replaced or allocated again from the pool.

The narrow correction belongs to the existing optional accounting context, including adjacent new operator binding and restore-previous consumers of this helper. It must preserve their code occupancy, tenant/seller/product and current-generation checks, WB result/recovery behavior, APPLIED/event/document history and existing line counters when a line is present. In particular, the separate foreign-PRINTED-code validation fallback currently uses a line match: making the helper optional must not turn absence into permission to use another order's code. No new task creation, entity or operator gate is authorized by this correction.

Root and the same developer/testwriter sessions received the exact finding. The four preceding accounting/atomicity findings are being corrected separately; their source is not re-audited here. A new exact product identity, frozen regression GREEN and targeted fix review are required before final whole-process/native acceptance and exact-SHA CI. Physical paper and live marketplace acknowledgement remain unclaimed.
