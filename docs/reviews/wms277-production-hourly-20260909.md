# WMS-277: first production hourly import, bounded observation

Read-only observation on 2026-09-09, ending at 01:22:54 UTC. This report records the evidence already collected; no further polling or SQL was performed to write it. The hourly run had not completed at the end of the observation.

The worker log records task `wms.wb_catalog_hourly_sync`, ID `d4c49270-5fd5-4c7f-a4c6-37b42ee22cdc`, received at **01:17:00.004 UTC**. The inspected service is `/opt/wms`, container `wms_prod-celery_worker-1` on sellerfocus.pro. At **01:22:40 UTC**, Celery inspection still reported this exact task active, with worker PID 8. Neither its final `all sellers done` summary nor its task `succeeded` record had been observed.

The log recorded ten successful seller imports between **01:17:04.339 and 01:17:30.448 UTC**. Two other sellers returned `wb_upstream_error_401`, at **01:17:14.920** and **01:17:15.491 UTC**. The worker continued processing after both failures. No credential values were inspected or printed, and no credential action was taken.

Limited read-only SQL confirmed persistence and continuing progress. The first sample found **5445 Product rows created after 01:17:00 UTC, across six sellers**. Its exact server sampling timestamp was not captured. The same sample found **7673 imported-card snapshots updated after 01:17:00 UTC, across eleven sellers**, with the latest snapshot timestamp **01:18:46.745048 UTC**. A second Product sample, explicitly timestamped by PostgreSQL at **01:22:54.435220 UTC**, found **7174 newly created Product rows across six sellers**, with the latest creation at **01:22:52.978338 UTC**. The increase of **1729 rows** between samples establishes that persistence was progressing during this observation. These are timestamp-filtered database counts, not a completed-task total or a claim that every row was independently attributed to this task.

The first PostgreSQL activity sample showed no blocked sessions and no long-running transaction. At **01:22:54 UTC**, the second sample explicitly returned **zero blocked sessions and zero transactions older than 30 seconds**, excluding the observer's own session. API `/health` returned HTTP **200** with `status=ok`; the production PostgreSQL container reported healthy. The neighboring FBS stock reconciliation task completed at **01:19:45.737 UTC** in **3.8057 seconds**, and the FBS order autopoll task completed at **01:19:46.655 UTC** in **4.7263 seconds**. These observations show that the catalog run had not stopped the worker or produced a database-wide blocking condition during the measured interval; they are not a new browser acceptance of every FBS operation.

Conclusion at the observation boundary: real successful catalog imports and continuing database writes are confirmed; completion of the full first hourly cycle remains unconfirmed. The large import was left running normally. No manual synchronization, process termination, service restart, application/configuration change, marketplace mutation, or credential management was performed by this inspection.

## Final observation by root at01:32UTC

The same task completed at01:25:51.477UTC in531.4716seconds:21seller imports
succeeded,7failed,0skipped. Five failures were WB HTTP401. The other two were
confirmed PostgreSQL unique-constraint failures while updating existing Product
sku_code in wildberries_product_import_service.py. They affect sellers
bf8eea6b-eaa6-47ea-8dfc-289142372dab and06b2e991-0533-4adf-83f3-d6cf21251433.
These two are application failures, not authentication failures. The task
continued to later sellers and finished; failed imports are not accepted as
working. Huygens is assigned a bounded importer correction preserving existing
product identities, stock and reservations, with a reproduced targeted test.
No direct production repair, manual repeat sync or credential change was made.
[Final log evidence](wms277-production-final-log-proof.json).
