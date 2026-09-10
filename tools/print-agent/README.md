# WMS-402 — transport adapter, not an integrated printer service

This executable adapter accepts one **already claimed** BackgroundJob of type
`fbs_network_print` on stdin. It checks the configured queue, copies, asset identity,
SHA256, PDF/PNG format and submits the temporary file to CUPS using `lp` without a
shell. The returned result is an OS queue receipt (`spooled`), not physical paper.
Timeout or ambiguous receipt is terminal for automatic execution; never replay
that job without checking the OS queue. No local journal, new table or key exists.

The warehouse PC operating system and printer model are still unknown. This
adapter supports CUPS (Linux/macOS). Windows spooler/driver installation and
physical 58×40 output are **not implemented or verified**.

Integration is deliberately blocked: the approved server has no agent/warehouse/
printer binding, restricted agent authorization, atomic claim or acknowledgement
routes. The proposed `/operations/fbs-print-jobs/{job_id}/content` route is NOT
implemented; it must serve the existing FbsPrintAsset with
`record_print_opened=False` after checking the claimed job's binding and checksum.
The adapter does not call the existing operator content endpoint because that
would record opening a label as a side effect of an agent fetch.

The owner decision requested in `docs/reviews/wms402-minimal-contract-20260909.md`
(warehouse → named printer → authorized agent identity) remains necessary before
implementing storage/authorization for this binding. A completed BackgroundJob
must not be repurposed as a printer registry. A general staff token is not a final
agent authorization solution. No real credentials were read or issued for this
adapter, and no production settings were changed.

Required future environment: WMS_PRINT_QUEUE, WMS_PRINT_API_URL (HTTPS), and an
existing appropriately restricted WMS_PRINT_TOKEN. No network or printer call
was made in the current verification. Tests use a fake subprocess and check
single execution, receipt semantics, validation and temporary file cleanup:

```
python3 -m unittest discover -s tools/print-agent -v
```
